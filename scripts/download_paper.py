"""Cache a verified public PDF and page-indexed text, bound to its SHA-256."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from common import ROOT, atomic_text, fetch, now, read_yaml, repo_lock, safe_path, write_yaml


def cache_pdf(metadata, root=ROOT, local_pdf=None, pdf_url=None, access_basis=None):
    m = dict(metadata)
    url = pdf_url or m.get("pdf_url")
    if not local_pdf and not url:
        raise ValueError("No public PDF URL: locate an accessible copy or provide --local-pdf")
    if pdf_url and not access_basis:
        raise ValueError("An alternate --pdf-url requires --access-basis (e.g. author manuscript)")
    existing = m.get("document", {})
    if existing and not local_pdf and not pdf_url:
        cached = safe_path(existing["pdf_path"], root)
        if cached.exists():
            data, resolved_url = cached.read_bytes(), existing.get("download_url")
        else:
            data, resolved_url = fetch(url, limit=100_000_000)
    elif local_pdf:
        data, resolved_url = Path(local_pdf).read_bytes(), None
    else:
        data, resolved_url = fetch(url, limit=100_000_000)
    if not data.startswith(b"%PDF-"):
        raise ValueError("Source returned non-PDF content (possibly an access/login page)")
    digest = hashlib.sha256(data).hexdigest()
    if existing and existing.get("sha256") != digest:
        raise ValueError("PDF changed: preserve current evidence and create an explicit version migration")
    if m.get("arxiv_id") and not re.fullmatch(r"v\d+", m.get("version") or ""):
        raise ValueError("arXiv downloads must be pinned to a version")
    key = re.sub(r"[^a-zA-Z0-9.-]", "-", m["paper_id"]) + "-" + (m.get("version") or digest[:12])
    folder = root / ".cache/papers" / key
    folder.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=".pdf", dir=folder)
    os.close(fd)
    temporary = Path(name)
    try:
        temporary.write_bytes(data)
        result = subprocess.run(["pdftotext", "-layout", str(temporary), "-"], capture_output=True, check=True)
        pages = result.stdout.decode("utf-8").split("\f")
        if pages and not pages[-1].strip():
            pages.pop()
        if not pages or sum(len(p.strip()) for p in pages) < 100:
            raise ValueError("No usable text: OCR/visual reading required; do not mark extraction complete")
        info = subprocess.run(["pdfinfo", str(temporary)], capture_output=True, check=True).stdout.decode()
        count = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))
        if len(pages) != count:
            raise ValueError("Page extraction count mismatch")
        destination = folder / "paper.pdf"
        os.replace(temporary, destination)
        for number, page in enumerate(pages, 1):
            atomic_text(folder / "pages" / f"{number:03}.txt", page)
        atomic_text(folder / "paper.txt", "\n".join(f"\n=== PDF PAGE {n} ===\n{page}" for n, page in enumerate(pages, 1)))
        m["pdf_url"] = url
        m["document"] = {"sha256": digest, "version": m.get("version"), "page_count": count,
            "pdf_path": str(destination.relative_to(root)), "text_path": str((folder / "paper.txt").relative_to(root)),
            "pages_path": str((folder / "pages").relative_to(root)), "download_url": resolved_url,
            "retrieved_at": existing.get("retrieved_at", now()),
            "access_basis": access_basis or existing.get("access_basis") or ("user-supplied copy" if local_pdf else "public source link"),
            "extraction": "pdftotext -layout; PDF page numbers are 1-based; equations/figures require visual verification"}
        return m
    finally:
        temporary.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("metadata")
    p.add_argument("--local-pdf")
    p.add_argument("--pdf-url")
    p.add_argument("--access-basis")
    args = p.parse_args()
    try:
        with repo_lock():
            m = cache_pdf(read_yaml(args.metadata), local_pdf=args.local_pdf, pdf_url=args.pdf_url, access_basis=args.access_basis)
            write_yaml(args.metadata, m)
        print(m["document"]["pdf_path"])
        return 0
    except Exception as exc:
        print(f"PDF acquisition failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
