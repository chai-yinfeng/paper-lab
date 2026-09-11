"""Resolve identifiers, or emit ranked candidates without auto-selecting titles."""
from __future__ import annotations

import argparse
import difflib
from html.parser import HTMLParser
import json
import sys
import urllib.parse
import xml.etree.ElementTree as ET

from common import fetch, identity, make_slug, normalize_title, now, parse_identifier, write_yaml


class CitationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = attrs.get("name", attrs.get("property", "")).lower()
            if key.startswith("citation_"):
                self.meta.setdefault(key, []).append(attrs.get("content", ""))


def finalize(m):
    if not m.get("title") or not m.get("authors") or not m.get("year"):
        raise ValueError("Incomplete metadata: title, authors, and year are required")
    m["schema_version"] = 1
    m["paper_id"], m["aliases"] = identity(m)
    m["slug"] = make_slug(m["title"], m["year"])
    m["retrieved_at"] = now()
    return m


def from_page(url, arxiv_id=None, requested_version=None):
    raw, final_url = fetch(url)
    parser = CitationParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    meta = parser.meta
    first = lambda key: meta.get("citation_" + key, [None])[0]
    title, date = first("title"), first("date") or first("publication_date") or first("online_date")
    pdf_url = first("pdf_url")
    version = requested_version
    if arxiv_id and requested_version and pdf_url:
        kind, found_id, found_version = parse_identifier(pdf_url)
        if kind == "arxiv" and (found_id != arxiv_id or (found_version and found_version != requested_version)):
            raise ValueError("Official page points to a different arXiv document/version")
    if arxiv_id and not version:
        import re
        # arXiv embeds the selected version in its citation PDF URL or page text.
        match = re.search(re.escape(arxiv_id) + r"(v\d+)\b", pdf_url or "")
        if not match:
            match = re.search(r"arXiv:" + re.escape(arxiv_id) + r"(v\d+)\b", raw.decode("utf-8", errors="replace"))
        if not match:
            raise ValueError("Cannot pin arXiv version; resolve an explicit version (e.g. v4)")
        version = match.group(1)
    if arxiv_id:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}{version}"
        final_url = f"https://arxiv.org/abs/{arxiv_id}{version}"
    return finalize({"title": title, "authors": meta.get("citation_author", []),
                     "year": int(date[:4]) if date else None,
                     "doi": first("doi") or (f"10.48550/arXiv.{arxiv_id}" if arxiv_id else None),
                     "arxiv_id": arxiv_id, "version": version,
                     "canonical_url": final_url, "pdf_url": urllib.parse.urljoin(final_url, pdf_url) if pdf_url else None,
                     "venue": first("journal_title") or ("arXiv" if arxiv_id else None),
                     "metadata_source": url})


def from_crossref(item):
    date = item.get("published", item.get("issued", {})).get("date-parts", [[None]])[0]
    return finalize({"title": item.get("title", [None])[0],
                     "authors": [" ".join(filter(None, [a.get("given"), a.get("family")])) or a.get("name", "") for a in item.get("author", [])],
                     "year": date[0], "doi": item.get("DOI"), "arxiv_id": None, "version": None,
                     "canonical_url": item.get("URL"), "pdf_url": None,
                     "venue": next(iter(item.get("container-title", [])), None),
                     "metadata_source": "https://api.crossref.org/works/" + urllib.parse.quote(item["DOI"], safe=""),
                     "access_note": "PDF not verified as open access; locate an author, proceedings, or publisher OA version."})


def title_candidates(title):
    candidates, errors = [], []
    query = urllib.parse.urlencode({"search_query": 'ti:"' + title.replace('"', '') + '"', "max_results": 5})
    try:
        raw, _ = fetch("https://export.arxiv.org/api/query?" + query)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in ET.fromstring(raw).findall("a:entry", ns):
            get = lambda name: entry.findtext("a:" + name, namespaces=ns)
            _, aid, version = parse_identifier(get("id").replace("http://", "https://"))
            candidates.append(finalize({"title": " ".join(get("title").split()),
                "authors": [a.findtext("a:name", namespaces=ns) for a in entry.findall("a:author", ns)],
                "year": int(get("published")[:4]), "arxiv_id": aid, "version": version,
                "doi": f"10.48550/arXiv.{aid}", "canonical_url": f"https://arxiv.org/abs/{aid}{version or ''}",
                "pdf_url": f"https://arxiv.org/pdf/{aid}{version or ''}", "venue": "arXiv",
                "metadata_source": "https://export.arxiv.org/api/query?" + query}))
    except Exception as exc:
        errors.append({"provider": "arxiv", "error": str(exc)})
    try:
        raw, _ = fetch("https://api.crossref.org/works?" + urllib.parse.urlencode({"query.title": title, "rows": 5}))
        for item in json.loads(raw)["message"]["items"]:
            try:
                candidates.append(from_crossref(item))
            except ValueError:
                continue
    except Exception as exc:
        errors.append({"provider": "crossref", "error": str(exc)})
    unique = {}
    for c in candidates:
        c["title_similarity"] = round(difflib.SequenceMatcher(None, normalize_title(title), normalize_title(c["title"])).ratio(), 3)
        unique[c["paper_id"]] = c
    return {"query": title, "selection_required": True,
            "score_note": "String similarity only; not calibrated matching confidence. Verify authors, year and venue.",
            "candidates": sorted(unique.values(), key=lambda c: c["title_similarity"], reverse=True), "provider_errors": errors}


def resolve(value):
    kind, identifier, version = parse_identifier(value)
    if kind == "arxiv":
        return from_page(f"https://arxiv.org/abs/{identifier}{version or ''}", identifier, version)
    if kind == "doi":
        raw, _ = fetch("https://api.crossref.org/works/" + urllib.parse.quote(identifier, safe=""))
        return from_crossref(json.loads(raw)["message"])
    if kind == "url":
        return from_page(identifier)
    return title_candidates(identifier)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("query")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    try:
        result = resolve(args.query)
        write_yaml(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get("selection_required") and not result["candidates"] else 0
    except Exception as exc:
        print(f"Resolution failed: {exc}. Use verified official metadata; do not invent a match.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
