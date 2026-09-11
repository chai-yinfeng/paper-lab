import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import identity, parse_identifier, read_yaml, write_yaml
from create_workspace import create
from download_paper import cache_pdf
from resolve_paper import from_page, title_candidates
from resume_paper import resume
from validate_state import validate


def metadata():
    return {"schema_version": 1, "title": "Example Paper", "authors": ["A. Author"], "year": 2020,
            "arxiv_id": "2001.00001", "version": "v1", "doi": "10.48550/arXiv.2001.00001",
            "canonical_url": "https://arxiv.org/abs/2001.00001v1", "pdf_url": "https://arxiv.org/pdf/2001.00001v1",
            "metadata_source": "https://arxiv.org/abs/2001.00001v1", "retrieved_at": "2026-09-10T00:00:00Z",
            "slug": "example-2020"}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name, content in {"library/index.yaml": {"papers": []}, "library/reading_queue.yaml": {"queue": []},
                              "profile/reader.yaml": {"knowledge": {"math": {"level": "unknown", "basis": "unassessed"}}},
                              "discovery/topics.yaml": {"topics": []}}.items():
            write_yaml(self.root / name, {"schema_version": 1, **content})

    def tearDown(self):
        self.temp.cleanup()

    def acquired(self):
        m = metadata()
        data = b"%PDF-test-fixture"
        cache = self.root / ".cache/papers/example"
        (cache / "pages").mkdir(parents=True)
        (cache / "paper.pdf").write_bytes(data)
        (cache / "paper.txt").write_text("mock source")
        (cache / "pages/001.txt").write_text("mock source")
        m["document"] = {"sha256": hashlib.sha256(data).hexdigest(), "version": "v1", "page_count": 1,
                         "pdf_path": ".cache/papers/example/paper.pdf", "text_path": ".cache/papers/example/paper.txt",
                         "pages_path": ".cache/papers/example/pages"}
        return create(m, root=self.root)

    def test_identifier_variants_and_arxiv_doi_alias(self):
        for value in ["1909.08053v4", "arxiv:1909.08053v4", "arXiv:1909.08053v4", "https://arxiv.org/pdf/1909.08053v4.pdf"]:
            self.assertEqual(parse_identifier(value), ("arxiv", "1909.08053", "v4"))
        self.assertEqual(parse_identifier("https://doi.org/10.48550/arXiv.1909.08053"), ("arxiv", "1909.08053", None))
        self.assertEqual(parse_identifier("https://doi.org/10.1000/EXAMPLE"), ("doi", "10.1000/example", None))
        self.assertEqual(parse_identifier("hep-th/9901001v2"), ("arxiv", "hep-th/9901001", "v2"))

    def test_title_hash_normalization(self):
        self.assertEqual(identity({"title": "A Paper: On   Models"})[0], identity({"title": "a paper on models"})[0])

    def test_idempotent_creation_preserves_analysis_and_promotes_queue(self):
        folder = create(metadata(), root=self.root)
        (folder / "scheme.md").write_text("My reviewed analysis")
        again = create(metadata(), status="reading", root=self.root)
        self.assertEqual(folder, again)
        self.assertEqual((folder / "scheme.md").read_text(), "My reviewed analysis")
        index = read_yaml(self.root / "library/index.yaml")["papers"]
        self.assertEqual(len(index), 1)
        self.assertEqual(index[0]["status"], "reading")

    def test_version_and_slug_collisions_fail_without_overwrite(self):
        folder = create(metadata(), root=self.root)
        old = (folder / "source.yaml").read_bytes()
        changed = metadata(); changed["version"] = "v2"
        with self.assertRaisesRegex(ValueError, "version"):
            create(changed, root=self.root)
        changed = metadata(); changed.update(arxiv_id="2001.00002", doi="10.1000/different")
        with self.assertRaisesRegex(ValueError, "collision"):
            create(changed, root=self.root)
        self.assertEqual((folder / "source.yaml").read_bytes(), old)

    def test_interrupted_index_update_is_recovered(self):
        folder = create(metadata(), root=self.root)
        write_yaml(self.root / "library/index.yaml", {"schema_version": 1, "papers": []})
        self.assertEqual(create(metadata(), root=self.root), folder)
        self.assertEqual(len(read_yaml(self.root / "library/index.yaml")["papers"]), 1)

    def test_candidates_and_path_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError, "candidate"):
            create({"selection_required": True}, root=self.root)
        with self.assertRaises(ValueError):
            create(metadata(), slug="../escape", root=self.root)
        with self.assertRaises(ValueError):
            resume("../escape", root=self.root)

    def test_html_citation_metadata_pins_selected_version(self):
        raw = b'<meta name="citation_title" content="Example"><meta name="citation_author" content="Author"><meta name="citation_date" content="2020/01/01"><meta name="citation_pdf_url" content="https://arxiv.org/pdf/2001.00001v3">'
        with patch("resolve_paper.fetch", return_value=(raw, "https://arxiv.org/abs/2001.00001")):
            m = from_page("https://arxiv.org/abs/2001.00001", "2001.00001")
        self.assertEqual(m["version"], "v3")
        self.assertEqual(m["paper_id"], "arxiv:2001.00001")
        with patch("resolve_paper.fetch", return_value=(raw, "https://arxiv.org/abs/2001.00001")):
            with self.assertRaisesRegex(ValueError, "different arXiv"):
                from_page("https://arxiv.org/abs/2001.00001v2", "2001.00001", "v2")

    def test_provider_failure_is_explicit_not_fake_match(self):
        with patch("resolve_paper.fetch", side_effect=OSError("offline")):
            result = title_candidates("Example")
        self.assertTrue(result["selection_required"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(len(result["provider_errors"]), 2)

    def test_non_pdf_response_is_not_cached(self):
        m = metadata(); m["paper_id"] = identity(m)[0]
        with patch("download_paper.fetch", return_value=(b"<html>login</html>", m["pdf_url"])):
            with self.assertRaisesRegex(ValueError, "non-PDF"):
                cache_pdf(m, root=self.root)
        self.assertFalse((self.root / ".cache/papers").exists())

    def test_source_change_fails_before_mutating_cached_pdf(self):
        folder = self.acquired()
        m = read_yaml(folder / "source.yaml")
        alternate = self.root / "different.pdf"; alternate.write_bytes(b"%PDF-different")
        with self.assertRaisesRegex(ValueError, "changed"):
            cache_pdf(m, root=self.root, local_pdf=alternate)
        self.assertEqual((self.root / m["document"]["pdf_path"]).read_bytes(), b"%PDF-test-fixture")

    def test_missing_cache_is_portable_but_strict_mode_fails(self):
        folder = self.acquired()
        m = read_yaml(folder / "source.yaml")
        (self.root / m["document"]["pdf_path"]).unlink()
        errors, warnings = validate(self.root)
        self.assertEqual(errors, [])
        self.assertTrue(warnings)
        self.assertTrue(validate(self.root, require_cache=True)[0])

    def test_bad_evidence_and_dangling_references_are_detected(self):
        folder = self.acquired()
        claim = {"id": "C1", "statement": "Some result", "type": "SOURCE", "status": "CONFIRMED",
                 "confidence": "high", "confidence_reason": "Report", "history": [{"change": "created"}],
                 "evidence": [{"source_sha256": "wrong", "page": 9, "section": "3", "note": "result"}]}
        write_yaml(folder / "claims.yaml", {"schema_version": 1, "claims": [claim]})
        (folder / "scheme.md").write_text("See C99")
        errors, _ = validate(self.root)
        self.assertTrue(any("hash mismatch" in e for e in errors))
        self.assertTrue(any("invalid PDF page" in e for e in errors))
        self.assertTrue(any("dangling reference" in e for e in errors))

    def test_incomplete_council_cannot_be_marked_complete(self):
        folder = self.acquired()
        run = read_yaml(folder / "run.yaml"); run["phase"] = "complete"
        write_yaml(folder / "run.yaml", run)
        errors, _ = validate(self.root)
        self.assertTrue(any("four blind" in e for e in errors))
        self.assertTrue(any("cross reviews" in e for e in errors))

    def test_queue_cycle_detected(self):
        folder = create(metadata(), root=self.root)
        pid = read_yaml(folder / "source.yaml")["paper_id"]
        write_yaml(self.root / "library/reading_queue.yaml", {"schema_version": 1, "queue": [
            {"paper_id": pid, "priority": "high", "reason": "test", "prerequisites": [pid]}]})
        self.assertTrue(any("cycle" in e for e in validate(self.root)[0]))

    def test_resume_excludes_historical_memo(self):
        folder = create(metadata(), root=self.root)
        (folder / "debates/private.md").write_text("HISTORICAL_MEMO_SENTINEL")
        context = resume(folder.name, self.root)
        self.assertNotIn("HISTORICAL_MEMO_SENTINEL", context)
        self.assertIn("claims.yaml", context)
        self.assertIn("issues.yaml", context)


if __name__ == "__main__":
    unittest.main()
