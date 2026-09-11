"""Print the canonical reading context without historical review memos."""
import argparse
import sys

from common import ROOT, check_slug, read_yaml


def resume(slug, root=ROOT):
    folder = root / "papers" / check_slug(slug)
    if not (folder / "source.yaml").is_file():
        raise ValueError("Paper workspace not found; inspect library/index.yaml")
    run = read_yaml(folder / "run.yaml")
    chunks = [f"Paper: {slug}\nCouncil phase: {run['phase']}\nHistorical debates omitted.\n"]
    for path in [root / "profile/reader.yaml"] + [folder / name for name in
            ("source.yaml", "run.yaml", "scheme.md", "claims.yaml", "issues.yaml", "open_questions.md", "prerequisites.yaml")]:
        chunks.append(f"\n--- {path.relative_to(root)} ---\n{path.read_text(encoding='utf-8')}")
    return "\n".join(chunks)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("slug")
    args = p.parse_args()
    try:
        print(resume(args.slug))
        return 0
    except Exception as exc:
        print(f"Resume failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
