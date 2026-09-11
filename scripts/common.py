"""Shared YAML, identity and network primitives; no model calls."""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import os
from pathlib import Path
import re
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARXIV = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.I)
STATUSES = {"candidate", "queued", "reading", "studied", "paused", "reference"}
ROLES = {"mechanism", "systems", "evidence", "adversarial"}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def read_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def atomic_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".write-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_yaml(path, data):
    atomic_text(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


@contextlib.contextmanager
def repo_lock(root=ROOT):
    with open(root / ".paper-lab.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def safe_path(relative, root=ROOT):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path outside repository: {relative}")
    return path


def check_slug(slug):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("slug must be lowercase words joined by hyphens")
    return slug


def normalize_title(title):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", title).casefold()))


def make_slug(title, year):
    words = re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower())
    return "-".join(words[:9] or ["paper"]) + f"-{year}"


def parse_identifier(value):
    value = value.strip()
    value = re.sub(r"^arxiv:\s*", "", value, flags=re.I)
    parsed = urllib.parse.urlparse(value)
    if parsed.hostname in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        value = re.sub(r"^/(?:abs|pdf|html)/", "", parsed.path).removesuffix(".pdf")
    if ARXIV.fullmatch(value):
        version = re.search(r"v\d+$", value)
        return "arxiv", re.sub(r"v\d+$", "", value).lower(), version.group() if version else None
    if parsed.hostname in {"doi.org", "dx.doi.org"}:
        value = urllib.parse.unquote(parsed.path.lstrip("/"))
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    if re.fullmatch(r"10\.\d{4,9}/\S+", value, re.I):
        doi = value.lower()
        arxiv_doi = re.fullmatch(r"10\.48550/arxiv\.(.+)", doi)
        if arxiv_doi:
            return parse_identifier(arxiv_doi.group(1))
        return "doi", doi, None
    return "url" if parsed.scheme in {"http", "https"} else "title", value, None


def identity(metadata):
    aliases = set(metadata.get("aliases", []))
    if metadata.get("arxiv_id"):
        aliases.add("arxiv:" + re.sub(r"v\d+$", "", metadata["arxiv_id"]).lower())
    if metadata.get("doi"):
        aliases.add("doi:" + metadata["doi"].lower())
    canonical = sorted(a for a in aliases if a.startswith("arxiv:")) or sorted(a for a in aliases if a.startswith("doi:"))
    paper_id = canonical[0] if canonical else "fallback:" + hashlib.sha256(normalize_title(metadata["title"]).encode()).hexdigest()[:20]
    aliases.add(paper_id)
    return paper_id, sorted(aliases)


def fetch(url, limit=20_000_000, accept=None):
    if urllib.parse.urlparse(url).scheme != "https":
        raise ValueError("Only HTTPS public source URLs are supported")
    headers = {"User-Agent": "paper-lab/0.1 (personal scholarly reading; Python urllib)"}
    if accept:
        headers["Accept"] = accept
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as response:
                if urllib.parse.urlparse(response.url).scheme != "https":
                    raise ValueError("Refusing redirect to non-HTTPS source")
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise ValueError(f"Response exceeds {limit} bytes")
                return data, response.url
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
            time.sleep(min(8, 2 ** (attempt + 1)))
    raise RuntimeError("Fetch failed")
