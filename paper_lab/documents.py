"""One import path for uploads and search downloads. No LLM or automatic OCR."""

from __future__ import annotations
import hashlib
import json
import math
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from .store import stamp, uid

MAX_PDF = 50 * 1024 * 1024


def command(args, timeout=90):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout, check=True)
        return result.stdout
    except FileNotFoundError as exc:
        raise ValueError("缺少 Poppler，请安装 pdftotext 与 pdftoppm。") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("PDF 无法处理：可能已加密、损坏或处理超时。") from exc


def extract(path):
    raw = command(
        ["pdftotext", "-cropbox", "-bbox-layout", "-enc", "UTF-8", str(path), "-"]
    )
    doc = ET.fromstring(raw)
    pages = []
    for el in doc.iter():
        if el.tag.split("}")[-1] != "page":
            continue
        w, h = float(el.attrib["width"]), float(el.attrib["height"])
        if not (0 < w <= 14400 and 0 < h <= 14400):
            raise ValueError("PDF 页面尺寸不受支持。")
        words = []
        lines = []
        for line in el.iter():
            if line.tag.split("}")[-1] != "line":
                continue
            parts = []
            for word in line:
                if word.tag.split("}")[-1] != "word":
                    continue
                text = "".join(word.itertext())
                parts.append(text)
                words.append(
                    {
                        "text": text,
                        "rect": [
                            float(word.attrib["xMin"]) / w,
                            float(word.attrib["yMin"]) / h,
                            float(word.attrib["xMax"]) / w,
                            float(word.attrib["yMax"]) / h,
                        ],
                    }
                )
            lines.append(" ".join(parts))
        pages.append(
            {
                "number": len(pages) + 1,
                "width": w,
                "height": h,
                "text": "\n".join(lines),
                "words": words,
            }
        )
    if not pages or len(pages) > 1000:
        raise ValueError("PDF 必须包含 1–1000 页。")
    return pages


def import_pdf(workspace, data, filename, source):
    if len(data) > MAX_PDF or not data[:1024].lstrip().startswith(b"%PDF-"):
        raise ValueError("请提供不超过 50 MB 的有效 PDF。")
    sha = hashlib.sha256(data).hexdigest()
    db = workspace.store
    existing = db.all("SELECT * FROM papers WHERE sha256=?", (sha,))
    if existing:
        return existing[0]
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=workspace.root / "cache")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        pages = extract(tmp)
        paper_id = uid()
        title = str(source.get("title") or Path(filename).stem or "未命名论文")[:500]
        with db.lock, db.conn:
            # Recheck after extraction: two simultaneous imports may share a hash.
            existing = db.all("SELECT * FROM papers WHERE sha256=?", (sha,))
            if existing:
                return existing[0]
            os.replace(tmp, workspace.pdf(sha))
            db.conn.execute(
                "INSERT INTO papers(id,title,sha256,filename,source,page_count,created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    paper_id,
                    title,
                    sha,
                    Path(filename).name,
                    json.dumps(source, ensure_ascii=False),
                    len(pages),
                    stamp(),
                ),
            )
            db.conn.executemany(
                "INSERT INTO pages VALUES (?,?,?,?,?,?)",
                [
                    (
                        paper_id,
                        p["number"],
                        p["width"],
                        p["height"],
                        p["text"],
                        json.dumps(p["words"], ensure_ascii=False),
                    )
                    for p in pages
                ],
            )
        return db.one("SELECT * FROM papers WHERE id=?", (paper_id,))
    finally:
        Path(tmp).unlink(missing_ok=True)


def validate_anchor(anchor, paper):
    if anchor is None:
        return None
    if anchor.get("sha256") != paper["sha256"]:
        raise ValueError("选区对应的 PDF 版本不匹配，请重新选择。")
    page = anchor.get("page")
    if type(page) is not int or not 1 <= page <= paper["page_count"]:
        raise ValueError("选区页码无效。")
    if anchor.get("kind") not in ("text", "region", "page"):
        raise ValueError("选区类型无效。")
    rects = anchor.get("rects", [])
    if not isinstance(rects, list) or len(rects) > 200:
        raise ValueError("选区范围过大。")
    for r in rects:
        if (
            not isinstance(r, list)
            or len(r) != 4
            or not all(
                type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in r
            )
            or r[0] >= r[2]
            or r[1] >= r[3]
        ):
            raise ValueError("选区坐标无效。")
    if anchor["kind"] in ("text", "region") and not rects:
        raise ValueError("选区缺少坐标。")
    return {
        "sha256": paper["sha256"],
        "page": page,
        "kind": anchor["kind"],
        "rects": rects,
        "quote": str(anchor.get("quote", ""))[:8000],
    }


def crop(workspace, paper, anchor, page):
    # pdftoppm uses the same displayed (rotated) page orientation as PDF.js and bbox extraction.
    r = anchor["rects"][0] if anchor["rects"] else [0, 0, 1, 1]
    scale = min(120 / 72, 1600 / max(page["width"], page["height"]))
    x, y = int(r[0] * page["width"] * scale), int(r[1] * page["height"] * scale)
    w, h = (
        max(1, math.ceil((r[2] - r[0]) * page["width"] * scale)),
        max(1, math.ceil((r[3] - r[1]) * page["height"] * scale)),
    )
    return command(
        [
            "pdftoppm",
            "-cropbox",
            "-f",
            str(anchor["page"]),
            "-l",
            str(anchor["page"]),
            "-singlefile",
            "-r",
            str(scale * 72),
            "-x",
            str(x),
            "-y",
            str(y),
            "-W",
            str(w),
            "-H",
            str(h),
            "-png",
            str(workspace.verified_pdf(paper["sha256"])),
        ],
        45,
    )
