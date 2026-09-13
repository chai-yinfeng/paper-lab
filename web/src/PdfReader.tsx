import {
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
  type RefObject,
} from "react";
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
  supportsImages,
  anchor,
  onSelect,
  onError,
}: {
  paper: Paper;
  page: number;
  setPage: (p: number, clearAnchor?: boolean) => void;
  supportsImages: boolean;
  anchor: Anchor | null;
  onSelect: (a: Anchor) => void;
  onError: (e: string) => void;
}) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null),
    [width, setWidth] = useState(650),
    [zoom, setZoom] = useState(1),
    [region, setRegion] = useState(false),
    [ratios, setRatios] = useState<number[]>([]),
    [outline, setOutline] = useState<{ title: string; dest: unknown }[]>([]),
    [showOutline, setShowOutline] = useState(false);
  const scroll = useRef<HTMLDivElement>(null);
  const pageElements = useRef(new Map<number, HTMLDivElement>());
  const internalPage = useRef<number | null>(null);
  const scrollFrame = useRef<number | null>(null);
  useEffect(() => {
    if (!supportsImages) setRegion(false);
  }, [supportsImages]);
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
        const [items, pageRatios] = await Promise.all([
          value.getOutline(),
          Promise.all(
            Array.from({ length: value.numPages }, async (_, index) => {
              const pdfPage = await value.getPage(index + 1);
              const viewport = pdfPage.getViewport({ scale: 1 });
              return viewport.height / viewport.width;
            }),
          ),
        ]);
        if (active) {
          setOutline(
            (items || []).map((i) => ({ title: i.title, dest: i.dest })),
          );
          setRatios(pageRatios);
        }
      })
      .catch((e) => {
        if (active) onError("PDF 无法打开：" + e.message);
      });
    return () => {
      active = false;
      setDoc(null);
      setRatios([]);
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
  useEffect(() => {
    if (!ratios.length) return;
    if (internalPage.current === page) {
      internalPage.current = null;
      return;
    }
    requestAnimationFrame(() => {
      const root = scroll.current;
      const target = pageElements.current.get(page);
      if (!root || !target) return;
      const rootBox = root.getBoundingClientRect();
      const targetBox = target.getBoundingClientRect();
      const anchorY =
        anchor?.page === page && anchor.rects.length ? anchor.rects[0][1] : 0;
      const top =
        root.scrollTop +
        targetBox.top -
        rootBox.top +
        anchorY * targetBox.height -
        (anchorY ? Math.min(rootBox.height * 0.22, 180) : 0);
      root.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
    });
  }, [page, anchor, ratios.length, width, zoom]);
  function goTo(target: number, behavior: ScrollBehavior = "smooth") {
    if (target < 1 || target > paper.page_count) return;
    setPage(target);
    pageElements.current
      .get(target)
      ?.scrollIntoView({ block: "start", behavior });
  }
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
      goTo(index + 1);
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
          onClick={() => goTo(page - 1)}
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
            if (n >= 1 && n <= paper.page_count) goTo(n);
          }}
        />
        <span>/ {paper.page_count}</span>
        <button
          aria-label="下一页"
          disabled={page >= paper.page_count}
          onClick={() => goTo(page + 1)}
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
          disabled={!supportsImages}
          onClick={() => {
            window.getSelection()?.removeAllRanges();
            setRegion(!region);
          }}
          title={
            !supportsImages
              ? "当前模型未启用图像输入"
              : region
                ? "当前为截图框选；在页面上拖动，或点击这里切回文字选择"
                : "切换到截图框选"
          }
        >
          {region ? <Scan size={17} /> : <TextSelect size={17} />}
          <span>{region ? "截图框选" : "文字"}</span>
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
      <div
        className="pdf-scroll"
        ref={scroll}
        tabIndex={0}
        aria-label="连续 PDF 页面。上下滚动阅读，使用工具栏按钮翻页"
        onPointerDown={(e) => {
          if (
            !region &&
            e.target instanceof Element &&
            !e.target.closest(".textLayer span")
          )
            window.getSelection()?.removeAllRanges();
        }}
        onScroll={() => {
          if (scrollFrame.current !== null) return;
          scrollFrame.current = requestAnimationFrame(() => {
            scrollFrame.current = null;
            const root = scroll.current;
            if (!root) return;
            const rootBox = root.getBoundingClientRect();
            const targetY = rootBox.top + Math.min(rootBox.height * 0.35, 260);
            let visiblePage = page;
            let distance = Infinity;
            for (const [number, element] of pageElements.current) {
              const box = element.getBoundingClientRect();
              const d =
                targetY < box.top
                  ? box.top - targetY
                  : targetY > box.bottom
                    ? targetY - box.bottom
                    : 0;
              if (d < distance) {
                distance = d;
                visiblePage = number;
              }
            }
            if (visiblePage !== page) {
              internalPage.current = visiblePage;
              setPage(visiblePage, false);
            }
          });
        }}
      >
        {region && (
          <div className="region-mode-hint">
            在页面上拖动框选图表；发送时会附带该区域截图，框内文字仅作辅助。
          </div>
        )}
        {doc && ratios.length ? (
          <div className="pdf-pages">
            {ratios.map((ratio, index) => {
              const number = index + 1;
              return (
                <LazyPdfPage
                  key={`${paper.id}-${number}`}
                  root={scroll}
                  registry={pageElements}
                  doc={doc}
                  paper={paper}
                  page={number}
                  width={width * zoom}
                  ratio={ratio}
                  region={region}
                  anchor={anchor}
                  onSelect={onSelect}
                  onError={onError}
                />
              );
            })}
          </div>
        ) : (
          <p className="muted">正在打开 PDF…</p>
        )}
      </div>
    </>
  );
}

function LazyPdfPage({
  root,
  registry,
  ratio,
  ...props
}: Parameters<typeof PdfPage>[0] & {
  root: RefObject<HTMLDivElement | null>;
  registry: MutableRefObject<Map<number, HTMLDivElement>>;
  ratio: number;
}) {
  const holder = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (holder.current) registry.current.set(props.page, holder.current);
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { root: root.current, rootMargin: "1000px 0px" },
    );
    if (holder.current) observer.observe(holder.current);
    return () => {
      observer.disconnect();
      registry.current.delete(props.page);
    };
  }, [props.page, registry, root]);
  return (
    <div
      ref={holder}
      className="pdf-page-shell"
      style={{ height: props.width * ratio }}
    >
      {visible && <PdfPage {...props} />}
    </div>
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
      const canvasElement = canvas.current;
      const textElement = text.current;
      if (stopped || !canvasElement || !textElement) return;
      setReady(false);
      textElement.replaceChildren();
      const base = p.getViewport({ scale: 1 }),
        viewport = p.getViewport({ scale: width / base.width });
      setHeight(viewport.height);
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvasElement.width = Math.floor(viewport.width * ratio);
      canvasElement.height = Math.floor(viewport.height * ratio);
      canvasElement.style.width = viewport.width + "px";
      canvasElement.style.height = viewport.height + "px";
      render = p.render({
        canvas: canvasElement,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      });
      await render.promise;
      if (stopped || !textElement.isConnected) return;
      textElement.style.setProperty("--scale-factor", String(viewport.scale));
      textElement.style.setProperty(
        "--total-scale-factor",
        String(viewport.scale),
      );
      const textContent = await p.getTextContent();
      if (stopped || !textElement.isConnected) return;
      layer = new TextLayer({
        textContentSource: textContent,
        container: textElement,
        viewport,
      });
      await layer.render();
      if (!stopped && textElement.isConnected) setReady(true);
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
      .filter(
        (r) =>
          r.width > 1 &&
          r.height > 1 &&
          r.right > box.left &&
          r.left < box.right &&
          r.bottom > box.top &&
          r.top < box.bottom,
      )
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
    if (rects.length) {
      onSelect({
        sha256: paper.sha256,
        page,
        kind: "text",
        rects,
        quote: quote.slice(0, 8000),
      });
      selection.removeAllRanges();
    }
  }
  function finish() {
    if (!start.current || !drag) return;
    start.current = null;
    if (drag[2] - drag[0] < 0.01 || drag[3] - drag[1] < 0.01) {
      setDrag(null);
      return;
    }
    const box = holder.current!.getBoundingClientRect();
    const quote = Array.from(
      text.current?.querySelectorAll(":scope > span") || [],
    )
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
