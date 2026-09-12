"""Bounded academic evidence retrieval independent of the configured LLM provider."""

from __future__ import annotations
import re
import httpx
from datetime import datetime, timezone
from urllib.parse import urlparse

ENDPOINT = "https://api.semanticscholar.org/graph/v1/snippet/search"
ARXIV_IN_TEXT = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5}(?:v\d+)?)", re.I)


def _authors(value):
    result = []
    for author in value or []:
        if isinstance(author, list):
            result.extend(str(name) for name in author if name)
        elif isinstance(author, dict) and author.get("name"):
            result.append(str(author["name"]))
        elif author:
            result.append(str(author))
    return result[:12]


async def search_academic(query: str, limit: int = 5):
    query = " ".join(query.split())[:300]
    if len(query) < 2:
        return []
    async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
        response = await client.get(ENDPOINT, params={"query": query, "limit": limit})
        response.raise_for_status()
        items = response.json().get("data", [])[:limit]
        corpus_ids = [
            str((item.get("paper") or {}).get("corpusId"))
            for item in items
            if (item.get("paper") or {}).get("corpusId")
        ]
        details = {}
        if corpus_ids:
            try:
                detail_response = await client.post(
                    "https://api.semanticscholar.org/graph/v1/paper/batch",
                    params={"fields": "title,authors,year,url,externalIds,openAccessPdf"},
                    json={"ids": ["CorpusId:" + value for value in corpus_ids]},
                )
                detail_response.raise_for_status()
                details = {
                    corpus_id: item
                    for corpus_id, item in zip(corpus_ids, detail_response.json())
                    if item
                }
            except httpx.HTTPError:
                pass
    results = []
    for item in items:
        snippet, paper = item.get("snippet") or {}, item.get("paper") or {}
        paper = {
            **details.get(str(paper.get("corpusId")), {}),
            **{key: value for key, value in paper.items() if value is not None},
        }
        quote = " ".join(str(snippet.get("text") or "").split())[:3000]
        title = " ".join(str(paper.get("title") or "Untitled source").split())[:500]
        if not quote:
            continue
        corpus = str(paper.get("corpusId") or "")
        url = str(paper.get("url") or "")
        if not url and corpus.isdigit():
            url = "https://www.semanticscholar.org/paper/CorpusID:" + corpus
        external_ids = paper.get("externalIds") or {}
        arxiv = external_ids.get("ArXiv")
        if not arxiv:
            match = ARXIV_IN_TEXT.search(str(item) + str(paper.get("openAccessPdf") or {}))
            arxiv = match.group(1) if match else None
        results.append(
            {
                "citation": f"E{len(results) + 1}",
                "title": title,
                "authors": _authors(paper.get("authors")),
                "year": paper.get("year"),
                "url": url,
                "locator": str(snippet.get("section") or snippet.get("snippetKind") or "excerpt")[:300],
                "quote": quote,
                "offset": snippet.get("snippetOffset"),
                "source_type": "academic-snippet",
                "provider": "Semantic Scholar",
                "arxiv_id": arxiv,
                "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
    return results


def normalize_sources(values):
    """Validate client-echoed preview results before placing them in model context."""
    results = []
    for value in (values or [])[:5]:
        url = str(value.get("url") or "")[:2000]
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            continue
        quote = " ".join(str(value.get("quote") or "").split())[:3000]
        if not quote:
            continue
        results.append(
            {
                "citation": f"E{len(results) + 1}",
                "title": " ".join(str(value.get("title") or "Untitled source").split())[:500],
                "authors": _authors(value.get("authors")),
                "year": value.get("year"),
                "url": url,
                "locator": str(value.get("locator") or "excerpt")[:300],
                "quote": quote,
                "offset": value.get("offset"),
                "source_type": "academic-snippet",
                "provider": "Semantic Scholar",
                "arxiv_id": (
                    str(value["arxiv_id"])[:30]
                    if value.get("arxiv_id") and ARXIV_IN_TEXT.fullmatch(str(value["arxiv_id"]))
                    else None
                ),
                "retrieved_at": str(value.get("retrieved_at") or "")[:64],
            }
        )
    return results
