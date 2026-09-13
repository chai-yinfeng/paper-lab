"""Offline in-memory tests. No workspace directory, PDF import or paid model call."""

import json
import asyncio
import io
import os
import tempfile
import unittest
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx

from paper_lab.api import create_app
from paper_lab.context import build_context, build_full_context, build_summary_context
from paper_lab.documents import validate_anchor, import_pdf
from paper_lab.keychain import SERVICE
from paper_lab.keychain import get_key as keychain_get
from paper_lab.keychain import set_key as keychain_set
from paper_lab.preferences import recent_workspace, remember_workspace
from paper_lab.providers import ProviderSettings, payload, stream_completion
from paper_lab.scholarly import normalize_sources, search_academic
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
        "INSERT INTO threads(id,paper_id,title,context_mode,created_at,updated_at) VALUES (?,?,?,?,?,?)",
        ("topic", "paper", "Synthetic topic", "focused", stamp(), stamp()),
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
        self.assertIn("[p.1 ¶1]", messages[-1]["content"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(packet["sources"][0]["reason"], "当前页相关段落")
        self.assertEqual(packet["coverage"]["total_pages"], 3)

    def test_context_citation_locates_extracted_words(self):
        words = [
            {"text": "matrix", "rect": [0.1, 0.2, 0.2, 0.22]},
            {"text": "definition", "rect": [0.21, 0.2, 0.34, 0.22]},
        ] * 8
        self.db.execute(
            "UPDATE pages SET words=? WHERE paper_id=? AND number=1",
            (json.dumps(words), "paper"),
        )
        packet, messages = build_context(
            self.db, self.paper, "topic", "matrix definition", None, budget=9000
        )
        source = packet["sources"][0]
        self.assertEqual(source["citation"], "p.1 ¶1")
        self.assertEqual(source["anchor"]["kind"], "text")
        self.assertEqual(source["anchor"]["rects"][0], [0.1, 0.2, 0.2, 0.22])
        self.assertIn("[p.1 ¶1]", messages[-1]["content"])

    def test_page_is_split_into_precise_sources_with_distinct_word_boxes(self):
        words = []
        for sentence in range(8):
            for word in range(35):
                token = f"s{sentence}w{word}" + ("." if word == 34 else "")
                words.append(
                    {
                        "text": token,
                        "rect": [sentence / 10, word / 100, sentence / 10 + 0.01, word / 100 + 0.01],
                    }
                )
        self.db.execute(
            "UPDATE pages SET text=?,words=? WHERE paper_id=? AND number=1",
            (" ".join(word["text"] for word in words), json.dumps(words), "paper"),
        )
        packet, _ = build_summary_context(self.db, self.paper, "topic", "post-read")
        page_sources = [source for source in packet["sources"] if source["page"] == 1]
        self.assertGreater(len(page_sources), 3)
        self.assertNotEqual(
            page_sources[0]["anchor"]["rects"][0],
            page_sources[1]["anchor"]["rects"][0],
        )
        self.assertEqual(page_sources[0]["anchor"]["quote"], page_sources[0]["text"])

    def test_layout_rewind_prevents_two_column_source_groups(self):
        words = []
        for column, x in enumerate((0.1, 0.6)):
            for index in range(30):
                y = 0.15 + index * 0.02
                words.append(
                    {
                        "text": f"c{column}w{index}",
                        "rect": [x, y, x + 0.04, y + 0.015],
                    }
                )
        self.db.execute(
            "UPDATE pages SET text=?,words=? WHERE paper_id=? AND number=1",
            (" ".join(word["text"] for word in words), json.dumps(words), "paper"),
        )
        packet, _ = build_summary_context(self.db, self.paper, "topic", "post-read")
        page_sources = [source for source in packet["sources"] if source["page"] == 1]
        self.assertEqual(len(page_sources), 2)
        for source in page_sources:
            rects = source["anchor"]["rects"]
            self.assertFalse(min(rect[0] for rect in rects) < 0.5 < max(rect[2] for rect in rects))

    def test_full_summary_sends_all_extracted_text_without_app_cap(self):
        packet, messages = build_summary_context(
            self.db, self.paper, "topic", "post-read"
        )
        self.assertEqual(packet["coverage"]["pages_included"], [1, 2, 3])
        self.assertGreater(packet["characters"], 6000)
        self.assertTrue(packet["coverage"]["complete_text"])
        self.assertIn("未做字符截断", packet["scope"])
        self.assertIn("[p.3 ¶1]", messages[-1]["content"])
        self.assertNotIn("覆盖范围：", messages[-1]["content"])
        self.assertIn("直接进入论文内容", messages[0]["content"])
        self.assertIn("外部背景（未检索）", messages[0]["content"])

    def test_full_context_keeps_paper_as_stable_prefix_before_history(self):
        first_packet, first = build_full_context(
            self.db, self.paper, "topic", "first question", None
        )
        self.db.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
            ("u", "topic", "user", "first question", None, None, "complete", None, stamp()),
        )
        self.db.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
            ("a", "topic", "assistant", "first answer", None, None, "complete", None, stamp()),
        )
        second_packet, second = build_full_context(
            self.db, self.paper, "topic", "second question", None
        )
        self.assertEqual(first[:2], second[:2])
        self.assertEqual(second[2:4], [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
        ])
        self.assertEqual(first_packet["context_mode"], "full")
        self.assertEqual(second_packet["coverage"]["pages_included"], [1, 2, 3])

    def test_confirmed_notes_are_bounded_long_term_context(self):
        self.db.execute(
            "INSERT INTO notes VALUES (?,?,?,?,?,?,?)",
            (
                "note1", "paper", None, "Confirmed tensor-parallel insight.",
                None, stamp(), stamp(),
            ),
        )
        packet, messages = build_context(
            self.db, self.paper, "topic", "continue", None
        )
        rendered = "\n".join(message["content"] for message in messages)
        self.assertEqual(packet["memory"]["confirmed_notes"], 1)
        self.assertIn("Confirmed tensor-parallel insight", rendered)
        self.assertIn("NOTE 标签不是论文证据引用", rendered)

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

    def test_v1_store_migrates_runs_to_structured_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.sqlite3"
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE runs (
                 id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, message_id TEXT NOT NULL,
                 workflow TEXT NOT NULL, status TEXT NOT NULL, provider TEXT NOT NULL,
                 model TEXT NOT NULL, usage TEXT, error TEXT, created_at TEXT NOT NULL,
                 finished_at TEXT);
                PRAGMA user_version=1;
                """
            )
            conn.close()
            migrated = Store(path)
            try:
                columns = [row[1] for row in migrated.conn.execute("PRAGMA table_info(runs)")]
                self.assertIn("trace", columns)
                self.assertEqual(
                    migrated.conn.execute("PRAGMA user_version").fetchone()[0], 5
                )
                self.assertIn(
                    "context_mode",
                    {row[1] for row in migrated.conn.execute("PRAGMA table_info(threads)")},
                )
                self.assertIn(
                    "memory_compactions",
                    {
                        row[0]
                        for row in migrated.conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    },
                )
            finally:
                migrated.close()


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

    async def test_thread_context_mode_is_persistent(self):
        response = await self.client.patch(
            "/api/threads/topic", json={"context_mode": "full"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["context_mode"], "full")
        threads = (await self.client.get("/api/papers/paper/threads")).json()
        self.assertEqual(threads[0]["context_mode"], "full")

    async def test_reviewed_memory_compaction_replaces_only_working_history(self):
        for identifier, role, content in (
            ("u1", "user", "Explain the interrupt path."),
            ("a1", "assistant", "The interrupt path uses the VGIC [p.1 ¶1]."),
        ):
            self.db.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
                (identifier, "topic", role, content, None, None, "complete", None, stamp()),
            )
        calls = []

        async def fake(settings, key, messages):
            calls.append(messages)
            yield {"type": "delta", "text": "## 已建立的理解\nVGIC path [p.1 ¶1]."}
            yield {"type": "usage", "usage": {"prompt_tokens": 120}}
            yield {"type": "finish", "reason": "stop"}

        initial = (await self.client.get("/api/threads/topic/memory")).json()
        self.assertEqual(initial["eligible_messages"], 2)
        self.assertIsNone(initial["active"])
        with patch("paper_lab.api.stream_completion", fake):
            response = await self.client.post("/api/threads/topic/memory/draft")
        self.assertEqual(response.status_code, 200, response.text)
        state = response.json()
        self.assertIsNone(state["active"])
        self.assertEqual(state["draft"]["source_message_count"], 2)
        self.assertIn("[M:u1]", calls[0][-1]["content"])
        draft_id = state["draft"]["id"]
        edited = await self.client.put(
            f"/api/threads/topic/memory/{draft_id}",
            json={"summary": "用户确认的 VGIC 记忆 [p.1 ¶1]."},
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        activated = await self.client.post(
            f"/api/threads/topic/memory/{draft_id}/activate"
        )
        self.assertEqual(activated.status_code, 200, activated.text)
        packet, prompt = build_context(
            self.db, self.db.one("SELECT * FROM papers"), "topic", "continue", None
        )
        rendered = "\n".join(item["content"] for item in prompt)
        self.assertTrue(packet["memory"]["active"])
        self.assertIn("用户确认的 VGIC 记忆", rendered)
        self.assertNotIn("Explain the interrupt path", rendered)
        self.assertEqual(
            len((await self.client.get("/api/threads/topic/messages")).json()), 2
        )
        disabled = await self.client.delete(
            f"/api/threads/topic/memory/{draft_id}"
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertIsNone(disabled.json()["active"])

    async def test_paper_identity_and_user_tags_are_separate_from_pdf_storage(self):
        paper = (await self.client.get("/api/papers")).json()[0]
        self.assertEqual(paper["citation_key"], "AnonNDSynthetic")
        self.assertEqual(paper["tags"], [])
        response = await self.client.put(
            "/api/papers/paper/tags", json={"tags": ["systems", " 必读 ", "systems"]}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["tags"], ["systems", "必读"])
        self.assertEqual(response.json()["sha256"], SHA)

    async def test_academic_evidence_is_saved_and_sent_with_stable_ids(self):
        captured = []

        async def fake(settings, key, messages):
            captured.append(messages)
            yield {"type": "delta", "text": "External claim [E1]."}
            yield {"type": "finish", "reason": "stop"}

        source = {
            "citation": "anything",
            "title": "External Paper",
            "authors": ["A. Author"],
            "year": 2024,
            "url": "https://www.semanticscholar.org/paper/example",
            "locator": "Methods",
            "quote": "This is an exact external evidence passage long enough to validate.",
            "arxiv_id": None,
        }
        with patch("paper_lab.api.stream_completion", fake):
            response = await self.client.post(
                "/api/threads/topic/messages",
                json={
                    "question": "Explain",
                    "academic_search": True,
                    "external_sources": [source],
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("[E1] External Paper", captured[0][-1]["content"])
        message = (await self.client.get("/api/threads/topic/messages")).json()[-1]
        self.assertEqual(message["context"]["external_sources"][0]["citation"], "E1")
        self.assertEqual(message["context"]["external_sources"][0]["quote"], source["quote"])
    async def test_delete_topic_preserves_confirmed_note(self):
        self.db.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?)",
            ("msg", "topic", "assistant", "saved", None, None, "complete", None, stamp()),
        )
        note = await self.client.post(
            "/api/papers/paper/notes", json={"message_id": "msg", "content": "keep me"}
        )
        response = await self.client.delete("/api/threads/topic")
        self.assertEqual(response.status_code, 200, response.text)
        saved = (await self.client.get("/api/notes")).json()
        self.assertEqual(saved[0]["id"], note.json()["id"])
        self.assertIsNone(saved[0]["message_id"])
        self.assertEqual(saved[0]["paper_title"], "Synthetic source")

    async def test_summary_is_always_one_call(self):
        calls = []

        async def fake(settings, key, messages):
            calls.append((settings.max_tokens, messages))
            yield {"type": "delta", "text": "Summary [p.1]."}
            yield {"type": "finish", "reason": "stop"}

        with patch("paper_lab.api.stream_completion", fake):
            response = await self.client.post(
                "/api/threads/topic/messages",
                json={"question": "总结", "purpose": "pre-read", "workflow": "draft-editor"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 384000)
        self.assertEqual(self.db.one("SELECT * FROM runs")["workflow"], "specialist")

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
        for workflow, count in [("specialist", 1), ("draft-editor", 2)]:
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

    async def test_draft_editor_saves_trace_and_only_publishes_final(self):
        calls = []

        async def fake(settings, key, messages):
            calls.append(messages)
            text = (
                "Reader draft [p.1 ¶1]."
                if len(calls) == 1
                else "<review>修正了一个前提。</review><final>Edited final [p.1 ¶1].</final>"
            )
            yield {"type": "delta", "text": text}
            yield {"type": "model", "model": "deepseek-flash"}
            yield {"type": "finish", "reason": "stop"}

        with patch("paper_lab.api.stream_completion", fake):
            response = await self.client.post(
                "/api/threads/topic/messages",
                json={"question": "Explain", "workflow": "draft-editor"},
            )
        events = [json.loads(line) for line in response.text.splitlines()]
        deltas = [event["text"] for event in events if event["type"] == "delta"]
        self.assertEqual(deltas, ["Edited final [p.1 ¶1]."])
        message = self.db.one("SELECT * FROM messages WHERE role='assistant'")
        self.assertEqual(message["content"], "Edited final [p.1 ¶1].")
        run = (await self.client.get("/api/threads/topic/runs")).json()[0]
        self.assertEqual(run["workflow"], "draft-editor")
        self.assertEqual(run["trace"]["stages"][0]["content"], "Reader draft [p.1 ¶1].")
        self.assertEqual(run["trace"]["stages"][1]["content"], "修正了一个前提。")

    async def test_truncation_prevents_editor_and_preserves_partial(self):
        async def fake(*args):
            yield {"type": "delta", "text": "partial"}
            yield {"type": "finish", "reason": "length"}

        with patch("paper_lab.api.stream_completion", fake):
            r = await self.client.post(
                "/api/threads/topic/messages",
                json={"question": "Explain", "workflow": "draft-editor"},
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


class ScholarlyTests(unittest.IsolatedAsyncioTestCase):
    async def test_openalex_fallback_preserves_verifiable_source_type(self):
        async def limited(*args):
            request = httpx.Request("GET", "https://api.semanticscholar.org")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("limited", request=request, response=response)

        source = {
            "citation": "E1",
            "title": "Fallback paper",
            "authors": ["A. Author"],
            "year": 2025,
            "url": "https://openalex.org/W1",
            "locator": "abstract",
            "quote": "An exact abstract excerpt.",
            "offset": None,
            "source_type": "academic-abstract",
            "provider": "OpenAlex",
            "arxiv_id": None,
            "retrieved_at": "2026-09-12T00:00:00+00:00",
            "content_hash": "ignored",
        }

        async def fallback(*args):
            return [source]

        with (
            patch("paper_lab.scholarly._search_semantic_scholar", limited),
            patch("paper_lab.scholarly._search_openalex", fallback),
        ):
            results = await search_academic("attention")
        self.assertEqual(results[0]["provider"], "OpenAlex")
        normalized = normalize_sources(results)
        self.assertEqual(normalized[0]["provider"], "OpenAlex")
        self.assertEqual(normalized[0]["source_type"], "academic-abstract")


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


class PreferencesTests(unittest.TestCase):
    def test_only_a_marked_recent_workspace_is_restored(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "config"
            workspace = Path(root) / "papers"
            workspace.mkdir()
            (workspace / "workspace.json").write_text(
                json.dumps({"schema_version": 1, "application": "paper-lab"})
            )
            with patch.dict(os.environ, {"PAPER_LAB_CONFIG_DIR": str(config)}):
                remember_workspace(str(workspace))
                self.assertEqual(recent_workspace(), str(workspace.resolve()))
                (workspace / "workspace.json").write_text("{}")
                self.assertIsNone(recent_workspace())


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
