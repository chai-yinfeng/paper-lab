"""Offline in-memory tests. No workspace directory, PDF import or paid model call."""

import json
import asyncio
import io
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx

from paper_lab.api import create_app
from paper_lab.context import build_context
from paper_lab.documents import validate_anchor, import_pdf
from paper_lab.keychain import SERVICE
from paper_lab.keychain import get_key as keychain_get
from paper_lab.keychain import set_key as keychain_set
from paper_lab.providers import ProviderSettings, payload, stream_completion
from paper_lab.store import Store, stamp
from paper_lab.workspace import Workspace, REPO

SHA = "a" * 64


# papers has eight columns; explicit column lists prevent fixtures drifting with migrations.
def seed(db):
    db.execute(
        "INSERT INTO papers(id,title,sha256,filename,source,page_count,current_page,created_at) VALUES (?,?,?,?,?,?,?,?)",
        ("paper", "Synthetic source", SHA, "synthetic.pdf", "{}", 3, 1, stamp()),
    )
    for n in range(1, 4):
        db.execute(
            "INSERT INTO pages VALUES (?,?,?,?,?,?)",
            (
                "paper",
                n,
                600,
                800,
                ("matrix definition " if n == 1 else "source passage ") * 1000,
                "[]",
            ),
        )
    db.execute(
        "INSERT INTO threads VALUES (?,?,?,?,?)",
        ("topic", "paper", "Synthetic topic", stamp(), stamp()),
    )


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.db = Store(":memory:")
        seed(self.db)
        self.paper = self.db.one("SELECT * FROM papers")

    def tearDown(self):
        self.db.close()

    def test_context_bounded_and_page_grounded(self):
        packet, messages = build_context(
            self.db, self.paper, "topic", "matrix definition", None, budget=9000
        )
        self.assertLessEqual(packet["characters"], 9000)
        self.assertEqual(packet["sources"][0]["page"], 1)
        self.assertIn("[p.1]", messages[-1]["content"])
        self.assertEqual(len(messages), 2)

    def test_anchor_rejects_wrong_source_and_nonfinite_coordinates(self):
        a = {
            "sha256": SHA,
            "page": 1,
            "kind": "region",
            "rects": [[0.1, 0.1, 0.5, 0.5]],
        }
        self.assertEqual(validate_anchor(a, self.paper)["page"], 1)
        for bad in [
            {**a, "sha256": "b" * 64},
            {**a, "page": 9},
            {**a, "rects": [[0, 0, float("nan"), 1]]},
            {**a, "rects": []},
            {**a, "rects": [[0, 0, 1.1, 1]]},
        ]:
            with self.assertRaises(ValueError):
                validate_anchor(bad, self.paper)

    def test_repository_data_path_rejected_before_any_write(self):
        with self.assertRaisesRegex(ValueError, "Git"):
            Workspace(str(REPO / "do-not-create"))
        self.assertFalse((REPO / "do-not-create").exists())

    def test_provider_default_and_no_secret_in_payload(self):
        p = ProviderSettings()
        self.assertEqual(p.model, "deepseek-flash")
        self.assertEqual(payload(p, [])["thinking"], {"type": "disabled"})
        self.assertEqual(payload(p, [])["max_tokens"], 4096)
        with self.assertRaises(ValueError):
            ProviderSettings(base_url="https://example.com")
        with self.assertRaises(ValueError):
            ProviderSettings(base_url="http://api.deepseek.com")


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.keychain_get = patch("paper_lab.api.keychain_get", return_value=None)
        self.keychain_set = patch("paper_lab.api.keychain_set")
        self.keychain_get.start()
        self.keychain_set.start()
        self.app = create_app()
        self.db = Store(":memory:")
        seed(self.db)
        self.app.state.workspace = SimpleNamespace(
            store=self.db, root=Path("/not-created")
        )
        self.app.state.key_cache[("deepseek", "https://api.deepseek.com")] = (
            "test-placeholder-not-a-real-key",
            "keychain",
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
            headers={"X-Paper-Lab-Token": self.app.state.token},
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.db.close()
        self.keychain_set.stop()
        self.keychain_get.stop()

    async def test_notes_require_explicit_save_and_remain_editable(self):
        self.db.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "msg",
                "topic",
                "assistant",
                "draft",
                None,
                None,
                "complete",
                "deepseek-flash",
                stamp(),
            ),
        )
        self.assertEqual((await self.client.get("/api/papers/paper/notes")).json(), [])
        r = await self.client.post(
            "/api/papers/paper/notes",
            json={"message_id": "msg", "content": "My confirmed note"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        nid = r.json()["id"]
        r = await self.client.put("/api/notes/" + nid, json={"content": "Revised"})
        self.assertEqual(r.json()["content"], "Revised")
        self.assertEqual(self.db.one("SELECT * FROM messages")["content"], "draft")

    async def test_cross_paper_note_rejected(self):
        self.db.execute(
            "INSERT INTO papers(id,title,sha256,filename,source,page_count,created_at) VALUES (?,?,?,?,?,?,?)",
            ("other", "Other", "b" * 64, "other.pdf", "{}", 1, stamp()),
        )
        self.db.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "msg",
                "topic",
                "assistant",
                "draft",
                None,
                None,
                "complete",
                None,
                stamp(),
            ),
        )
        r = await self.client.post(
            "/api/papers/other/notes", json={"message_id": "msg", "content": "bad"}
        )
        self.assertEqual(r.status_code, 400)

    async def test_topics_and_messages_are_isolated(self):
        r = await self.client.post(
            "/api/papers/paper/threads", json={"title": "Second"}
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(
            (
                await self.client.get("/api/threads/" + r.json()["id"] + "/messages")
            ).json(),
            [],
        )
        self.assertEqual(
            len((await self.client.get("/api/papers/paper/threads")).json()), 2
        )

    async def test_missing_key_does_not_create_message_or_run(self):
        self.app.state.key_cache[("deepseek", "https://api.deepseek.com")] = (
            None,
            "none",
        )
        r = await self.client.post(
            "/api/threads/topic/messages", json={"question": "Explain"}
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.all("SELECT * FROM messages"), [])
        self.assertEqual(self.db.all("SELECT * FROM runs"), [])

    async def test_csrf_and_dns_rebinding_rejected(self):
        r = await self.client.post(
            "/api/key", headers={"X-Paper-Lab-Token": ""}, json={"key": "x"}
        )
        self.assertEqual(r.status_code, 403)
        r = await self.client.get("/api/status", headers={"Host": "evil.example"})
        self.assertEqual(r.status_code, 400)

    async def test_provider_switch_clears_key_without_persisting_secret(self):
        r = await self.client.put(
            "/api/provider",
            json={
                "provider": "openai-compatible",
                "base_url": "https://api.example.com/v1",
                "model": "example-model",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["key_configured"])
        self.assertNotIn(
            "test-placeholder", json.dumps(self.db.all("SELECT * FROM settings"))
        )

    async def test_api_key_is_saved_to_keychain_not_sqlite(self):
        key = "test-key-that-is-never-sent"
        response = await self.client.put("/api/key", json={"key": key})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["key_storage"], "keychain")
        self.assertNotIn(key, json.dumps(self.db.all("SELECT * FROM settings")))
        self.assertEqual(
            self.app.state.key_cache[("deepseek", "https://api.deepseek.com")],
            (key, "keychain"),
        )

    async def test_native_directory_picker_returns_path_or_cancel(self):
        workspace = self.app.state.workspace
        self.app.state.workspace = None
        try:
            with patch(
                "paper_lab.api.pick_directory", return_value="/tmp/paper-lab-choice"
            ):
                response = await self.client.post("/api/workspace/pick")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {"path": "/tmp/paper-lab-choice"})

            with patch("paper_lab.api.pick_directory", return_value=None):
                response = await self.client.post("/api/workspace/pick")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {"path": None})
        finally:
            self.app.state.workspace = workspace

    async def test_single_and_pair_have_bounded_calls_and_saved_usage(self):
        for workflow, count in [("specialist", 1), ("reader-checker", 2)]:
            calls = []

            async def fake(settings, key, messages):
                calls.append(messages)
                yield {"type": "delta", "text": "Grounded explanation [p.1]."}
                yield {"type": "model", "model": "deepseek-flash"}
                yield {
                    "type": "usage",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
                yield {"type": "finish", "reason": "stop"}

            with patch("paper_lab.api.stream_completion", fake):
                r = await self.client.post(
                    "/api/threads/topic/messages",
                    json={"question": "Explain", "workflow": workflow},
                )
            self.assertEqual(r.status_code, 200, r.text)
            events = [json.loads(x) for x in r.text.splitlines()]
            self.assertEqual(events[-1]["status"], "complete", events)
            self.assertEqual(len(calls), count)
            self.assertEqual(len(events[-1]["usage"]), count)
            self.assertEqual(self.db.all("SELECT * FROM notes"), [])
            self.assertFalse(self.app.state.active)

    async def test_truncation_prevents_checker_and_preserves_partial(self):
        async def fake(*args):
            yield {"type": "delta", "text": "partial"}
            yield {"type": "finish", "reason": "length"}

        with patch("paper_lab.api.stream_completion", fake):
            r = await self.client.post(
                "/api/threads/topic/messages",
                json={"question": "Explain", "workflow": "reader-checker"},
            )
        final = json.loads(r.text.splitlines()[-1])
        self.assertEqual(final["status"], "truncated")
        self.assertEqual(len(final["usage"]), 1)
        self.assertEqual(
            self.db.one("SELECT * FROM messages WHERE role='assistant'")["content"],
            "partial",
        )

    async def test_upstream_failure_preserves_partial_and_releases_topic(self):
        async def fake(*args):
            yield {"type": "delta", "text": "partial"}
            raise ValueError("connection failed")

        with patch("paper_lab.api.stream_completion", fake):
            r = await self.client.post(
                "/api/threads/topic/messages", json={"question": "Explain"}
            )
        self.assertEqual(json.loads(r.text.splitlines()[-1])["status"], "error")
        self.assertEqual(self.db.one("SELECT * FROM runs")["status"], "error")
        self.assertFalse(self.app.state.active)

    async def test_context_preview_never_calls_model(self):
        with patch(
            "paper_lab.api.stream_completion",
            side_effect=AssertionError("must not call model"),
        ):
            r = await self.client.post(
                "/api/threads/topic/context", json={"question": "Explain matrix"}
            )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.db.all("SELECT * FROM messages"), [])

    async def test_image_rejected_before_billing_for_text_only_provider(self):
        self.db.set_setting(
            "provider", ProviderSettings(supports_images=False).model_dump()
        )
        a = {
            "sha256": SHA,
            "page": 1,
            "kind": "region",
            "rects": [[0.1, 0.1, 0.3, 0.3]],
        }
        r = await self.client.post(
            "/api/threads/topic/messages", json={"question": "Explain", "anchor": a}
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.all("SELECT * FROM runs"), [])

    async def test_stop_preserves_partial_and_releases_running_request(self):
        started = asyncio.Event()

        async def fake(*args):
            yield {"type": "delta", "text": "partial"}
            started.set()
            await asyncio.Event().wait()

        with patch("paper_lab.api.stream_completion", fake):
            running = asyncio.create_task(
                self.client.post(
                    "/api/threads/topic/messages", json={"question": "Explain"}
                )
            )
            await asyncio.wait_for(started.wait(), 2)
            response = await self.client.post("/api/threads/topic/stop")
            self.assertTrue(response.json()["requested"])
            await asyncio.wait_for(running, 2)
        self.assertEqual(self.db.one("SELECT * FROM runs")["status"], "interrupted")
        self.assertEqual(
            self.db.one("SELECT * FROM messages WHERE role='assistant'")["content"],
            "partial",
        )
        self.assertFalse(self.app.state.active)

    async def test_resume_pointer_survives_between_api_reads(self):
        r = await self.client.put(
            "/api/session", json={"paper_id": "paper", "thread_id": "topic"}
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(
            (await self.client.get("/api/session")).json()["thread_id"], "topic"
        )

    async def test_import_uses_one_record_for_duplicate_bytes_without_disk(self):
        workspace = SimpleNamespace(
            store=self.db,
            root=Path("/not-created"),
            pdf=lambda sha: Path("/not-created") / (sha + ".pdf"),
        )
        pages = [
            {"number": 1, "width": 600, "height": 800, "text": "Synthetic", "words": []}
        ]
        with (
            patch(
                "paper_lab.documents.tempfile.mkstemp",
                return_value=(999, "/not-created/input.pdf"),
            ),
            patch("paper_lab.documents.os.fdopen", return_value=io.BytesIO()),
            patch("paper_lab.documents.extract", return_value=pages),
            patch("paper_lab.documents.os.replace") as move,
            patch("paper_lab.documents.Path.unlink"),
        ):
            first = import_pdf(
                workspace, b"%PDF-synthetic", "example.pdf", {"kind": "upload"}
            )
            second = import_pdf(
                workspace, b"%PDF-synthetic", "different-name.pdf", {"kind": "upload"}
            )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(move.call_count, 1)
        self.assertEqual(
            len(self.db.all("SELECT * FROM pages WHERE paper_id=?", (first["id"],))), 1
        )


class KeychainTests(unittest.TestCase):
    @patch("paper_lab.keychain.platform.system", return_value="Darwin")
    @patch("paper_lab.keychain.subprocess.run")
    def test_secret_is_sent_over_stdin_not_process_arguments(self, run, _system):
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        keychain_set("deepseek", "https://api.deepseek.com", "secret-value")
        args = run.call_args.args[0]
        self.assertNotIn("secret-value", args)
        self.assertEqual(
            run.call_args.kwargs["input"], "secret-value\nsecret-value\n"
        )
        self.assertEqual(args[-1], "-w")
        self.assertEqual(args[args.index("-s") + 1], SERVICE)
        self.assertEqual(SERVICE, "com.chai-yinfeng.paper-lab.api-key")
        self.assertTrue(args[args.index("-a") + 1].startswith("deepseek:api.deepseek.com:"))

    @patch("paper_lab.keychain.platform.system", return_value="Darwin")
    @patch("paper_lab.keychain.subprocess.run")
    def test_saved_key_can_be_loaded_after_restart(self, run, _system):
        run.return_value = SimpleNamespace(
            returncode=0, stdout="persisted-secret\n", stderr=""
        )
        self.assertEqual(
            keychain_get("deepseek", "https://api.deepseek.com"),
            "persisted-secret",
        )


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_sse_usage_on_finish_chunk_and_exact_model_id(self):
        captured = []

        def handler(request):
            captured.append(json.loads(request.content))
            chunks = [
                {
                    "model": "deepseek-flash",
                    "choices": [{"delta": {"content": "Hello"}, "finish_reason": None}],
                },
                {
                    "choices": [{"delta": {}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                },
            ]
            return httpx.Response(
                200,
                text="\n\n".join("data: " + json.dumps(c) for c in chunks)
                + "\n\ndata: [DONE]\n\n",
            )

        original = httpx.AsyncClient

        def client(**kwargs):
            return original(**kwargs, transport=httpx.MockTransport(handler))

        with patch("paper_lab.providers.httpx.AsyncClient", client):
            events = [
                e async for e in stream_completion(ProviderSettings(), "fake", [])
            ]
        self.assertEqual(captured[0]["model"], "deepseek-flash")
        self.assertTrue(any(e["type"] == "usage" for e in events))
        self.assertTrue(any(e.get("reason") == "stop" for e in events))

    async def test_stream_eof_without_finish_is_failure(self):
        original = httpx.AsyncClient

        def client(**kwargs):
            return original(
                **kwargs,
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(
                        200,
                        text='data: {"choices": [{"delta": {"content": "partial"}}]}\n\n',
                    )
                ),
            )

        with patch("paper_lab.providers.httpx.AsyncClient", client):
            with self.assertRaises(ValueError):
                async for _ in stream_completion(ProviderSettings(), "fake", []):
                    pass


if __name__ == "__main__":
    unittest.main()
