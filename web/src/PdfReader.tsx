import { useEffect, useRef, useState } from "react";
import {
  getDocument,
  GlobalWorkerOptions,
  TextLayer,
  type PDFDocumentProxy,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "pdfjs-dist/web/pdf_viewer.css";
import {
  ChevronLeft,
  ChevronRight,
  Scan,
  TextSelect,
  Minus,
  Plus,
  List,
} from "lucide-react";
import type { Anchor, Paper, Rect } from "./types";
GlobalWorkerOptions.workerSrc = workerUrl;
const clamp = (v: number) => Math.min(1, Math.max(0, v));
export default function PdfReader({
  paper,
  page,
  setPage,
  anchor,
  onSelect,
  onError,
}: {
  paper: Paper;
  page: number;
  setPage: (p: number) => void;
  anchor: Anchor | null;
  onSelect: (a: Anchor) => void;
  onError: (e: string) => void;
}) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null),
    [width, setWidth] = useState(650),
    [zoom, setZoom] = useState(1),
    [region, setRegion] = useState(false),
    [outline, setOutline] = useState<{ title: string; dest: unknown }[]>([]),
    [showOutline, setShowOutline] = useState(false);
  const scroll = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let active = true;
    const task = getDocument({
      url: `/api/papers/${paper.id}/pdf`,
      cMapUrl: "/pdf-assets/cmaps/",
      cMapPacked: true,
      standardFontDataUrl: "/pdf-assets/standard_fonts/",
      wasmUrl: "/pdf-assets/wasm/",
    });
    task.promise
      .then(async (value) => {
        if (!active) return;
        setDoc(value);
        const items = await value.getOutline();
        if (active)
          setOutline(
            (items || []).map((i) => ({ title: i.title, dest: i.dest })),
          );
      })
      .catch((e) => {
        if (active) onError("PDF 无法打开：" + e.message);
      });
    return () => {
      active = false;
      setDoc(null);
      void task.destroy();
    };
  }, [paper.id]);
  useEffect(() => {
    const element = scroll.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(240, entries[0].contentRect.width - 48)),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  async function jump(dest: unknown) {
    if (!doc) return;
    try {
      const target =
        typeof dest === "string" ? await doc.getDestination(dest) : dest;
      if (!Array.isArray(target)) return;
      const index =
        typeof target[0] === "number"
          ? target[0]
          : await doc.getPageIndex(target[0]);
      setPage(index + 1);
      setShowOutline(false);
    } catch {
      onError("这个目录条目无法定位。");
    }
  }
  return (
    <>
      <div className="pdf-toolbar">
        <button
          aria-label="论文目录"
          title="论文目录"
          onClick={() => setShowOutline(!showOutline)}
        >
          <List size={17} />
        </button>
        <button
          aria-label="上一页"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
        >
          <ChevronLeft size={17} />
        </button>
        <input
          aria-label="PDF 页码"
          type="number"
          min={1}
          max={paper.page_count}
          value={page}
          onChange={(e) => {
            const n = Number(e.target.value);
            if (n >= 1 && n <= paper.page_count) setPage(n);
          }}
        />
        <span>/ {paper.page_count}</span>
        <button
          aria-label="下一页"
          disabled={page >= paper.page_count}
          onClick={() => setPage(page + 1)}
        >
          <ChevronRight size={17} />
        </button>
        <div className="toolbar-spacer" />
        <button
          aria-label="缩小"
          disabled={zoom <= 0.6}
          onClick={() => setZoom(Math.max(0.6, zoom - 0.2))}
        >
          <Minus size={16} />
        </button>
        <span>{Math.round(zoom * 100)}%</span>
        <button
          aria-label="放大"
          disabled={zoom >= 2}
          onClick={() => setZoom(Math.min(2, zoom + 0.2))}
        >
          <Plus size={16} />
        </button>
        <button
          className={region ? "active" : ""}
          onClick={() => setRegion(!region)}
          title={region ? "切换文字选择" : "框选图表"}
        >
          {region ? <Scan size={17} /> : <TextSelect size={17} />}
          <span>{region ? "框选" : "文字"}</span>
        </button>
      </div>
      {showOutline && (
        <div className="outline">
          {outline.length ? (
            outline.map((item, i) => (
              <button key={i} onClick={() => void jump(item.dest)}>
                {item.title}
              </button>
            ))
          ) : (
            <p>此 PDF 没有内置目录，可直接输入页码。</p>
          )}
        </div>
      )}
      <div className="pdf-scroll" ref={scroll}>
        {doc ? (
          <PdfPage
            key={`${paper.id}-${page}-${width}-${zoom}`}
            doc={doc}
            paper={paper}
            page={page}
            width={width * zoom}
            region={region}
            anchor={anchor}
            onSelect={onSelect}
            onError={onError}
          />
        ) : (
          <p className="muted">正在打开 PDF…</p>
        )}
      </div>
    </>
  );
}
function PdfPage({
  doc,
  paper,
  page,
  width,
  region,
  anchor,
  onSelect,
  onError,
}: {
  doc: PDFDocumentProxy;
  paper: Paper;
  page: number;
  width: number;
  region: boolean;
  anchor: Anchor | null;
  onSelect: (a: Anchor) => void;
  onError: (s: string) => void;
}) {
  const holder = useRef<HTMLDivElement>(null),
    canvas = useRef<HTMLCanvasElement>(null),
    text = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(width * 1.4),
    [drag, setDrag] = useState<Rect | null>(null),
    [ready, setReady] = useState(false);
  const start = useRef<[number, number] | null>(null);
  useEffect(() => {
    let stopped = false;
    let render:
      | ReturnType<Awaited<ReturnType<PDFDocumentProxy["getPage"]>>["render"]>
      | undefined;
    let layer: TextLayer | undefined;
    (async () => {
      const p = await doc.getPage(page);
      if (stopped || !canvas.current || !text.current) return;
      const base = p.getViewport({ scale: 1 }),
        viewport = p.getViewport({ scale: width / base.width });
      setHeight(viewport.height);
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.current.width = Math.floor(viewport.width * ratio);
      canvas.current.height = Math.floor(viewport.height * ratio);
      canvas.current.style.width = viewport.width + "px";
      canvas.current.style.height = viewport.height + "px";
      render = p.render({
        canvas: canvas.current,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      });
      await render.promise;
      if (stopped) return;
      text.current!.style.setProperty("--scale-factor", String(viewport.scale));
      text.current!.style.setProperty(
        "--total-scale-factor",
        String(viewport.scale),
      );
      layer = new TextLayer({
        textContentSource: await p.getTextContent(),
        container: text.current!,
        viewport,
      });
      await layer.render();
      if (!stopped) setReady(true);
    })().catch((e) => {
      if (!stopped) onError("页面渲染失败：" + e.message);
    });
    return () => {
      stopped = true;
      render?.cancel();
      layer?.cancel();
    };
  }, [doc, page, width]);
  function point(e: { clientX: number; clientY: number }): [number, number] {
    const box = holder.current!.getBoundingClientRect();
    return [
      clamp((e.clientX - box.left) / box.width),
      clamp((e.clientY - box.top) / box.height),
    ];
  }
  function selected() {
    if (region || !ready) return;
    const selection = window.getSelection();
    if (
      !selection ||
      selection.isCollapsed ||
      !selection.rangeCount ||
      !text.current?.contains(selection.anchorNode) ||
      !text.current?.contains(selection.focusNode)
    )
      return;
    const quote = selection.toString().trim();
    if (!quote) return;
    const box = holder.current!.getBoundingClientRect();
    const rects = Array.from(selection.getRangeAt(0).getClientRects())
      .filter((r) => r.width > 1 && r.height > 1)
      .slice(0, 200)
      .map(
        (r) =>
          [
            clamp((r.left - box.left) / box.width),
            clamp((r.top - box.top) / box.height),
            clamp((r.right - box.left) / box.width),
            clamp((r.bottom - box.top) / box.height),
          ] as Rect,
      )
      .filter((r) => r[0] < r[2] && r[1] < r[3]);
    if (rects.length)
      onSelect({
        sha256: paper.sha256,
        page,
        kind: "text",
        rects,
        quote: quote.slice(0, 8000),
      });
  }
  function finish() {
    if (!start.current || !drag) return;
    start.current = null;
    if (drag[2] - drag[0] < 0.01 || drag[3] - drag[1] < 0.01) {
      setDrag(null);
      return;
    }
    const box = holder.current!.getBoundingClientRect();
    const quote = Array.from(text.current?.querySelectorAll("span") || [])
      .filter((el) => {
        const r = el.getBoundingClientRect();
        const x = (r.left + r.width / 2 - box.left) / box.width,
          y = (r.top + r.height / 2 - box.top) / box.height;
        return x >= drag[0] && x <= drag[2] && y >= drag[1] && y <= drag[3];
      })
      .map((el) => el.textContent)
      .join(" ");
    onSelect({
      sha256: paper.sha256,
      page,
      kind: "region",
      rects: [drag],
      quote: quote.slice(0, 8000),
    });
    setDrag(null);
  }
  const highlights = drag ? [drag] : anchor?.page === page ? anchor.rects : [];
  return (
    <div
      className="pdf-page"
      ref={holder}
      style={{ width, height }}
      onMouseUp={selected}
      onKeyUp={selected}
    >
      <canvas ref={canvas} />
      <div ref={text} className="textLayer" />
      <div className="highlights">
        {highlights.map((r, i) => (
          <div
            key={i}
            style={{
              left: r[0] * 100 + "%",
              top: r[1] * 100 + "%",
              width: (r[2] - r[0]) * 100 + "%",
              height: (r[3] - r[1]) * 100 + "%",
            }}
          />
        ))}
      </div>
      {region && (
        <div
          className="region-layer"
          onPointerDown={(e) => {
            if (!ready) return;
            start.current = point(e);
            setDrag([...start.current, ...start.current]);
            e.currentTarget.setPointerCapture(e.pointerId);
          }}
          onPointerMove={(e) => {
            if (!start.current) return;
            const p = point(e),
              s = start.current;
            setDrag([
              Math.min(s[0], p[0]),
              Math.min(s[1], p[1]),
              Math.max(s[0], p[0]),
              Math.max(s[1], p[1]),
            ]);
          }}
          onPointerUp={finish}
          onPointerCancel={() => {
            start.current = null;
            setDrag(null);
          }}
        />
      )}
    </div>
  );
}
