"""User-triggered arXiv search/download only; no autonomous external browsing."""

import re
import xml.etree.ElementTree as ET
import httpx
from .documents import MAX_PDF

ARXIV_ID = re.compile(
    r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.I
)


async def search(query):
    value = (
        query.strip()
        .removeprefix("https://arxiv.org/abs/")
        .removeprefix("https://arxiv.org/pdf/")
        .removesuffix(".pdf")
    )
    params = (
        {"id_list": value}
        if ARXIV_ID.fullmatch(value)
        else {
            "search_query": 'all:"' + value.replace('"', "") + '"',
            "max_results": 8,
            "sortBy": "relevance",
        }
    )
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        r = await client.get("https://export.arxiv.org/api/query", params=params)
        r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    results = []
    for e in ET.fromstring(r.content).findall("a:entry", ns):
        identifier = (e.findtext("a:id", "", ns)).split("/abs/")[-1]
        if not ARXIV_ID.fullmatch(identifier):
            continue
        results.append(
            {
                "arxiv_id": identifier,
                "title": " ".join(e.findtext("a:title", "", ns).split()),
                "authors": [
                    a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)
                ],
                "year": e.findtext("a:published", "", ns)[:4],
                "url": "https://arxiv.org/abs/" + identifier,
            }
        )
    return results


async def download(identifier):
    if not ARXIV_ID.fullmatch(identifier):
        raise ValueError("无效的 arXiv ID。")
    matches = await search(identifier)
    if not matches:
        raise ValueError("没有找到对应论文。")
    meta = matches[0]
    # Search pins the actual version; only official arXiv PDF endpoints are allowed.
    url = "https://arxiv.org/pdf/" + meta["arxiv_id"]
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            data = bytearray()
            async for part in r.aiter_bytes():
                data.extend(part)
                if len(data) > MAX_PDF:
                    raise ValueError("PDF 超过 50 MB。")
    return bytes(data), {**meta, "kind": "arxiv", "pdf_url": url}
