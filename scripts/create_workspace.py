"""Idempotent workspace creation; existing source versions are never overwritten."""
import argparse
import sys

from common import ROOT, STATUSES, atomic_text, check_slug, identity, now, read_yaml, repo_lock, write_yaml

SECTIONS = ["Problem", "Core Thesis", "Mental Model", "Architecture / Algorithm", "Key Design Decisions",
            "Assumptions", "Claim → Evidence Map", "Engineering Implications", "Alternatives", "Disputed Issues",
            "Prerequisite Gaps", "Reproduction Opportunities", "What I Should Read Carefully", "What Can Be Skimmed", "Open Questions"]


def create(metadata, slug=None, status="queued", root=ROOT):
    if status not in STATUSES:
        raise ValueError("Unknown library status")
    m = dict(metadata)
    if m.get("selection_required"):
        raise ValueError("Select and verify one candidate before workspace creation")
    for key in ("title", "authors", "year", "canonical_url"):
        if not m.get(key):
            raise ValueError(f"Missing metadata: {key}")
    m["paper_id"], m["aliases"] = identity(m)
    slug = check_slug(slug or m["slug"])
    index_path = root / "library/index.yaml"
    with repo_lock(root):
        index = read_yaml(index_path)
        # Scan workspaces too: recover from interruption between directory creation and index update.
        for source in (root / "papers").glob("*/source.yaml"):
            existing = read_yaml(source)
            if set(existing["aliases"]) & set(m["aliases"]):
                if m.get("version") and m.get("version") != existing.get("version"):
                    raise ValueError("Existing paper has another version; explicit migration required")
                if m.get("document") and existing.get("document") and m["document"]["sha256"] != existing["document"]["sha256"]:
                    raise ValueError("Existing paper PDF differs; explicit migration required")
                slug, m = source.parent.name, existing
                break
        for entry in index["papers"]:
            if set(entry.get("aliases", [entry["id"]])) & set(m["aliases"]):
                if entry["slug"] != slug:
                    raise ValueError("Identity already indexed under another slug")
                # Promote acquisition into reading, but never silently demote an existing state.
                if entry["status"] in {"candidate", "queued"} and status == "reading":
                    entry["status"] = "reading"
        folder = root / "papers" / slug
        source = folder / "source.yaml"
        if source.exists() and read_yaml(source)["paper_id"] != m["paper_id"]:
            raise ValueError("Slug collision: choose a distinct slug")
        m["slug"] = slug
        if not source.exists():
            write_yaml(source, m)
        initial = {"claims.yaml": {"schema_version": 1, "claims": []},
                   "issues.yaml": {"schema_version": 1, "issues": []},
                   "prerequisites.yaml": {"schema_version": 1, "prerequisites": []},
                   "run.yaml": {"schema_version": 1, "phase": "acquired" if m.get("document") else "resolved",
                       "source_sha256": m.get("document", {}).get("sha256"), "blind_reviews": {}, "cross_reviews": {},
                       "rounds_completed": 0, "updated_at": now()}}
        for name, content in initial.items():
            if not (folder / name).exists():
                write_yaml(folder / name, content)
        markdown = {"scheme.md": f"# {m['title']}\n\n状态：尚未完成 council。\n\n" + "\n\n".join(f"## {s}\n" for s in SECTIONS),
                    "open_questions.md": "# Open Questions\n\n权威争议状态保存在 issues.yaml；此文件是阅读入口。\n",
                    "reading_log.md": "# Reading Log\n\n" + f"- {now()}：创建 workspace，尚未完成阅读。\n"}
        for name, content in markdown.items():
            if not (folder / name).exists():
                atomic_text(folder / name, content)
        (folder / "debates").mkdir(exist_ok=True)
        if not any(e["id"] == m["paper_id"] for e in index["papers"]):
            index["papers"].append({"id": m["paper_id"], "aliases": m["aliases"], "slug": slug, "title": m["title"],
                                    "status": status, "topics": [], "priority": "normal"})
        write_yaml(index_path, index)
    return folder


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("metadata")
    p.add_argument("--slug")
    p.add_argument("--status", choices=sorted(STATUSES), default="queued")
    args = p.parse_args()
    try:
        print(create(read_yaml(args.metadata), args.slug, args.status))
        return 0
    except Exception as exc:
        print(f"Workspace creation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
