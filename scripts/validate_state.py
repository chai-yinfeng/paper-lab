"""Validate persistent references, evidence binding, and completed council checkpoints."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys

from common import ROOT, ROLES, STATUSES, check_slug, identity, read_yaml, safe_path

CLAIM_STATUSES = {"CONFIRMED", "DISPUTED", "OPEN", "REJECTED"}
PHASES = ["resolved", "acquired", "blind_review", "cross_review", "synthesis", "complete"]


def validate(root=ROOT, require_cache=False):
    errors, warnings = [], []

    def require(condition, message):
        if not condition:
            errors.append(message)

    def load(path, key=None):
        try:
            data = read_yaml(path)
            if not isinstance(data, dict) or data.get("schema_version") != 1:
                raise ValueError("expected schema_version: 1 mapping")
            if key is not None and not isinstance(data.get(key), list):
                raise ValueError(f"expected {key} list")
            return data
        except Exception as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
            return {key: []} if key else {}

    def objects(data, prefix, label):
        result = {}
        for obj in data:
            if not isinstance(obj, dict):
                errors.append(f"{label}: expected mapping item")
                continue
            identifier = obj.get("id", "")
            require(bool(re.fullmatch(prefix + r"[1-9]\d*", str(identifier))), f"{label}: invalid ID {identifier}")
            require(identifier not in result, f"{label}: duplicate ID {identifier}")
            result[identifier] = obj
        return result

    def evidence(items, document, label):
        if not isinstance(items, list):
            errors.append(f"{label}: evidence must be list")
            return
        for item in items:
            if not isinstance(item, dict):
                errors.append(f"{label}: evidence item must be mapping")
                continue
            require(item.get("source_sha256") == document.get("sha256") and bool(document.get("sha256")), f"{label}: source hash mismatch")
            page = item.get("page")
            require(type(page) is int and 1 <= page <= document.get("page_count", 0), f"{label}: invalid PDF page {page}")
            require(any(item.get(k) for k in ("section", "equation", "figure", "table", "algorithm", "appendix", "locator")), f"{label}: missing locator")
            require(bool(item.get("note")), f"{label}: missing evidence scope note")

    def acyclic(graph, label):
        active, done = set(), set()
        def visit(node):
            if node in active:
                raise ValueError(f"{label}: dependency cycle at {node}")
            if node in done:
                return
            active.add(node)
            for dependency in graph.get(node, []):
                visit(dependency)
            active.remove(node)
            done.add(node)
        try:
            for node in graph:
                visit(node)
        except ValueError as exc:
            errors.append(str(exc))

    index = load(root / "library/index.yaml", "papers")["papers"]
    indexed, aliases, slugs = {}, {}, set()
    for item in index:
        if not isinstance(item, dict):
            errors.append("library: expected paper mapping")
            continue
        pid, slug = item.get("id"), item.get("slug", "")
        require(isinstance(pid, str) and bool(pid), "library: missing paper ID")
        require(pid not in indexed, f"library: duplicate paper ID {pid}")
        require(slug not in slugs, f"library: duplicate slug {slug}")
        try:
            check_slug(slug)
        except (ValueError, TypeError):
            errors.append(f"library: invalid slug {slug}")
        require(item.get("status") in STATUSES, f"library: invalid status for {pid}")
        for alias in item.get("aliases", [pid]):
            require(alias not in aliases or aliases[alias] == pid, f"library: duplicated identity alias {alias}")
            aliases[alias] = pid
        indexed[pid], _ = item, slugs.add(slug)
        if item.get("status") in {"reading", "studied", "paused"}:
            require((root / "papers" / slug / "source.yaml").is_file(), f"library: active paper missing workspace {slug}")

    for folder in sorted((root / "papers").glob("*")):
        if not folder.is_dir():
            continue
        label = folder.name
        source = load(folder / "source.yaml")
        require(source.get("slug") == label, f"{label}: source slug mismatch")
        require(source.get("paper_id") in indexed, f"{label}: not in library")
        for key in ("title", "authors", "year", "canonical_url", "metadata_source", "retrieved_at", "aliases"):
            require(bool(source.get(key)), f"{label}: missing source {key}")
        if source.get("title"):
            expected_id, expected_aliases = identity(source)
            require(expected_id == source.get("paper_id"), f"{label}: identity mismatch")
            require(set(expected_aliases) == set(source.get("aliases", [])), f"{label}: identity aliases incomplete")
        document = source.get("document", {})
        run = load(folder / "run.yaml")
        require(run.get("phase") in PHASES, f"{label}: invalid phase")
        if run.get("phase") != "resolved":
            require(bool(re.fullmatch(r"[0-9a-f]{64}", document.get("sha256", ""))), f"{label}: invalid document hash")
            require(type(document.get("page_count")) is int and document["page_count"] > 0, f"{label}: invalid page count")
            require(run.get("source_sha256") == document.get("sha256"), f"{label}: run/source hash mismatch")
        if document:
            require(document.get("version") == source.get("version"), f"{label}: document version mismatch")
            for key in ("pdf_path", "text_path", "pages_path"):
                try:
                    path = safe_path(document[key], root)
                    require(path.is_relative_to((root / ".cache/papers").resolve()), f"{label}: cache path outside .cache/papers")
                    if not path.exists():
                        (errors if require_cache else warnings).append(f"{label}: missing local cache {key}; restore via download_paper.py")
                    elif key == "pdf_path":
                        require(hashlib.sha256(path.read_bytes()).hexdigest() == document["sha256"], f"{label}: cached PDF hash mismatch")
                except Exception as exc:
                    errors.append(f"{label}: invalid {key}: {exc}")
        claims = objects(load(folder / "claims.yaml", "claims")["claims"], "C", label)
        issues = objects(load(folder / "issues.yaml", "issues")["issues"], "I", label)
        prereqs = objects(load(folder / "prerequisites.yaml", "prerequisites")["prerequisites"], "P", label)
        for cid, claim in claims.items():
            tag = f"{label}/{cid}"
            require(bool(claim.get("statement")), f"{tag}: missing statement")
            require(claim.get("type") in {"SOURCE", "DERIVED", "SPECULATION"}, f"{tag}: invalid claim type")
            require(claim.get("status") in CLAIM_STATUSES, f"{tag}: invalid status")
            require(claim.get("confidence") in {"high", "medium", "low"} and bool(claim.get("confidence_reason")), f"{tag}: missing confidence rationale")
            require(isinstance(claim.get("history"), list) and bool(claim.get("history")), f"{tag}: missing history")
            evidence(claim.get("evidence", []), document, tag)
            if claim.get("type") in {"SOURCE", "DERIVED"}:
                require(bool(claim.get("evidence")), f"{tag}: non-speculative claim has no evidence")
            if claim.get("type") == "DERIVED":
                require(bool(claim.get("depends_on")) and bool(claim.get("reasoning")), f"{tag}: missing derivation")
            if claim.get("type") == "SPECULATION":
                require(bool(claim.get("testable_by")) and claim.get("status") != "CONFIRMED", f"{tag}: speculation needs test and cannot be confirmed")
            for dep in claim.get("depends_on", []):
                require(dep in claims, f"{tag}: unknown dependency {dep}")
            if claim.get("superseded_by"):
                require(claim["superseded_by"] in claims, f"{tag}: unknown replacement claim")
        acyclic({k: v.get("depends_on", []) for k, v in claims.items()}, f"{label}/claims")
        for iid, issue in issues.items():
            tag = f"{label}/{iid}"
            require(issue.get("status") in CLAIM_STATUSES, f"{tag}: invalid issue status")
            require(bool(issue.get("title")) and bool(issue.get("related_claims")), f"{tag}: missing title/claims")
            for cid in issue.get("related_claims", []):
                require(cid in claims, f"{tag}: unknown related claim {cid}")
            require(bool(issue.get("positions")) and bool(issue.get("resolution")), f"{tag}: missing positions/resolution")
            for position in issue.get("positions", []):
                require(bool(position.get("role")) and bool(position.get("position")), f"{tag}: incomplete position")
                evidence(position.get("evidence", []), document, tag)
            if issue.get("status") in {"OPEN", "DISPUTED"}:
                require(bool(issue.get("remaining_uncertainty")), f"{tag}: unresolved issue needs uncertainty")
            require(bool(issue.get("history")), f"{tag}: missing history")
        for pid, prereq in prereqs.items():
            tag = f"{label}/{pid}"
            require(prereq.get("current_level") in ["unknown", 0, 1, 2, 3, 4], f"{tag}: invalid current level")
            require(type(prereq.get("required_level")) is int and 0 <= prereq["required_level"] <= 4, f"{tag}: invalid required level")
            require(prereq.get("status") in {"unassessed", "learning", "resolved"}, f"{tag}: invalid prerequisite status")
            require(all(prereq.get(k) for k in ("topic", "reason", "basis")), f"{tag}: incomplete prerequisite")
            for cid in prereq.get("related_claims", []):
                require(cid in claims, f"{tag}: unknown related claim {cid}")
        for name in ("scheme.md", "open_questions.md", "reading_log.md"):
            path = folder / name
            require(path.is_file(), f"{label}: missing {name}")
            if path.is_file():
                for ref in re.findall(r"\b[CIP][1-9]\d*\b", path.read_text()):
                    require(ref in claims or ref in issues or ref in prereqs, f"{label}/{name}: dangling reference {ref}")
        blind, cross = run.get("blind_reviews", {}), run.get("cross_reviews", {})
        for kind, reviews in (("blind", blind), ("cross", cross)):
            if not isinstance(reviews, dict):
                errors.append(f"{label}: {kind} reviews must be mapping")
                continue
            for role, review in reviews.items():
                try:
                    memo = safe_path(review["memo"], root)
                    require(memo.is_relative_to((folder / "debates").resolve()), f"{label}: memo outside paper debates")
                    require(memo.is_file() and memo.stat().st_size > 0, f"{label}: missing {kind} memo for {role}")
                    require(review.get("source_sha256") == document.get("sha256"), f"{label}: stale {kind} memo for {role}")
                    require(bool(review.get("agent_id")) and bool(review.get("completed_at")), f"{label}: missing {kind} provenance")
                except Exception as exc:
                    errors.append(f"{label}: invalid {kind} review: {exc}")
        if run.get("phase") in {"cross_review", "synthesis", "complete"}:
            require(isinstance(blind, dict) and set(blind) == ROLES, f"{label}: four blind roles required before cross-review")
        if run.get("phase") in {"synthesis", "complete"}:
            require(isinstance(cross, dict) and len(cross) >= 2, f"{label}: at least two cross reviews required before synthesis")
            require(run.get("rounds_completed", 0) >= 1, f"{label}: no completed cross-review round")
        if run.get("phase") == "complete":
            require(bool(claims), f"{label}: completed council has no claims")
            require(not run.get("blocker"), f"{label}: completed council still has blocker")
            require((folder / "debates/initial-review.md").is_file(), f"{label}: missing initial issue register")
    queue = load(root / "library/reading_queue.yaml", "queue")["queue"]
    graph = {}
    for entry in queue:
        pid = entry.get("paper_id")
        require(pid in indexed, f"queue: unknown paper {pid}")
        require(pid not in graph, f"queue: duplicate paper {pid}")
        require(bool(entry.get("reason")), f"queue: missing reason for {pid}")
        graph[pid] = entry.get("prerequisites", [])
        for dep in graph[pid]:
            require(dep in indexed, f"queue: unknown prerequisite {dep}")
    acyclic(graph, "queue")
    reader = load(root / "profile/reader.yaml")
    for topic, value in reader.get("knowledge", {}).items():
        require(value.get("level") in ["unknown", 0, 1, 2, 3, 4] and bool(value.get("basis")), f"reader: invalid assessment {topic}")
    load(root / "discovery/topics.yaml", "topics")
    return errors, warnings


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--require-cache", action="store_true")
    p.add_argument("--root", type=Path, default=ROOT)
    args = p.parse_args()
    try:
        errors, warnings = validate(args.root.resolve(), args.require_cache)
    except Exception as exc:
        print(f"ERROR: malformed state: {exc}", file=sys.stderr)
        return 1
    for w in warnings:
        print("WARNING:", w)
    for e in errors:
        print("ERROR:", e)
    print(f"Validation: {len(errors)} errors, {len(warnings)} warnings")
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
