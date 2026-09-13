import React, { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Plus,
  Settings,
  FileText,
  ArrowUp,
  MessageSquare,
  NotebookPen,
  X,
  Search,
  Upload,
  Square,
  ExternalLink,
  Check,
  ChevronDown,
  PanelLeftClose,
  Pencil,
  Trash2,
  Sparkles,
  Info,
  Tags,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import PdfReader from "./PdfReader";
import { api, request, setToken } from "./client";
import type {
  Anchor,
  Paper,
  Thread,
  Message,
  Note,
  Provider,
  Status,
  Context,
  Run,
  Candidate,
  ExternalSource,
} from "./types";
import "./style.css";

export default function App() {
  const [status, setStatus] = useState<Status | null>(null),
    [error, setError] = useState(""),
    [papers, setPapers] = useState<Paper[]>([]),
    [paper, setPaper] = useState<Paper | null>(null),
    [page, setPage] = useState(1),
    [anchor, setAnchor] = useState<Anchor | null>(null),
    [threads, setThreads] = useState<Thread[]>([]),
    [thread, setThread] = useState<Thread | null>(null),
    [messages, setMessages] = useState<Message[]>([]),
    [notes, setNotes] = useState<Note[]>([]),
    [showCrossPaperNotes, setShowCrossPaperNotes] = useState(false),
    [runs, setRuns] = useState<Run[]>([]),
    [tab, setTab] = useState<"chat" | "notes">("chat"),
    [question, setQuestion] = useState(""),
    [workflow, setWorkflow] = useState("specialist"),
    [academicSearch, setAcademicSearch] = useState(false),
    [generating, setGenerating] = useState(false),
    [phase, setPhase] = useState(""),
    [context, setContext] = useState<Context | null>(null),
    [busy, setBusy] = useState(false),
    [collapsed, setCollapsed] = useState(false),
    [libraryWidth, setLibraryWidth] = useState(() =>
      Math.min(
        360,
        Math.max(
          160,
          Number(localStorage.getItem("paper-lab-library-width")) || 225,
        ),
      ),
    ),
    [discussionWidth, setDiscussionWidth] = useState(() =>
      Math.min(
        720,
        Math.max(
          300,
          Number(localStorage.getItem("paper-lab-discussion-width")) || 410,
        ),
      ),
    ),
    [composerHeight, setComposerHeight] = useState(() =>
      Math.min(
        520,
        Math.max(
          160,
          Number(localStorage.getItem("paper-lab-composer-height")) || 230,
        ),
      ),
    );
  const settings = useRef<HTMLDialogElement>(null),
    importDialog = useRef<HTMLDialogElement>(null),
    noteDialog = useRef<HTMLDialogElement>(null),
    topicDialog = useRef<HTMLDialogElement>(null),
    contextDialog = useRef<HTMLDialogElement>(null),
    workflowDialog = useRef<HTMLDialogElement>(null),
    sourceDialog = useRef<HTMLDialogElement>(null),
    paperDialog = useRef<HTMLDialogElement>(null),
    layout = useRef<HTMLDivElement>(null),
    discussion = useRef<HTMLElement>(null),
    bottom = useRef<HTMLDivElement>(null);
  const [directory, setDirectory] = useState(
      () => localStorage.getItem("paper-lab-directory") || "",
    ),
    [config, setConfig] = useState<Provider>({
      provider: "deepseek",
      base_url: "https://api.deepseek.com",
      model: "deepseek-flash",
      supports_images: true,
      effort: "none",
      max_tokens: 4096,
    }),
    [key, setKey] = useState(""),
    [searchQuery, setSearchQuery] = useState(""),
    [candidates, setCandidates] = useState<Candidate[]>([]),
    [searched, setSearched] = useState(false),
    [topicTitle, setTopicTitle] = useState(""),
    [noteText, setNoteText] = useState(""),
    [noteSource, setNoteSource] = useState<Message | Note | null>(null),
    [editingNote, setEditingNote] = useState(false);
  const [editingTopic, setEditingTopic] = useState(false),
    [externalSource, setExternalSource] = useState<ExternalSource | null>(null),
    [preparedExternal, setPreparedExternal] = useState<{
      key: string;
      sources: ExternalSource[];
    } | null>(null),
    [paperTags, setPaperTags] = useState("");
  const abort = useRef<AbortController | null>(null),
    epoch = useRef(0),
    messageEpoch = useRef(0),
    positionTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  function fail(e: unknown) {
    setError(e instanceof Error ? e.message : String(e));
  }
  async function refreshStatus() {
    const s = await api<Status>("/status");
    setToken(s.token);
    setStatus(s);
    setConfig(s.provider);
    if (s.data_dir) setDirectory(s.data_dir);
    return s;
  }
  useEffect(() => {
    void refreshStatus()
      .then((s) => {
        if (s.configured) return restoreSession();
      })
      .catch(fail);
    return () => {
      abort.current?.abort();
      if (positionTimer.current) clearTimeout(positionTimer.current);
    };
  }, []);
  useEffect(() => {
    if (messages.length && bottom.current?.parentElement) {
      const pane = bottom.current.parentElement;
      pane.scrollTop = pane.scrollHeight;
    }
  }, [messages.length, phase]);
  useEffect(() => {
    const mc = (
      document as unknown as {
        modelContext?: {
          registerTool: (tool: unknown, options: unknown) => Promise<void>;
        };
      }
    ).modelContext;
    if (!mc?.registerTool) return;
    const lifecycle = new AbortController();
    try {
      void Promise.resolve(
        mc.registerTool(
          {
            name: "read_paper_lab_state",
            description:
              "Read the visible paper, selected PDF region and topic. Does not send data to an LLM.",
            inputSchema: {
              type: "object",
              properties: {},
              additionalProperties: false,
            },
            annotations: { readOnlyHint: true, untrustedContentHint: true },
            execute: () => ({
              paper: paper ? { id: paper.id, title: paper.title } : null,
              page,
              selection: anchor,
              topic: thread,
            }),
          },
          { signal: lifecycle.signal },
        ),
      ).catch(() => {});
    } catch {}
    return () => lifecycle.abort();
  }, [paper, page, anchor, thread]);
  async function restoreSession() {
    const [ps, ns] = await Promise.all([
      api<Paper[]>("/papers"),
      api<Note[]>("/notes"),
    ]);
    setPapers(ps);
    setNotes(ns);
    const saved = await api<{ paper_id?: string; thread_id?: string }>(
      "/session",
    );
    const p = ps.find((p) => p.id === saved.paper_id);
    if (p) await openPaper(p, saved.thread_id);
  }
  async function loadThread(t: Thread) {
    const id = ++messageEpoch.current;
    setThread(t);
    setMessages([]);
    setRuns([]);
    const [m, r] = await Promise.all([
      api<Message[]>(`/threads/${t.id}/messages`),
      api<Run[]>(`/threads/${t.id}/runs`),
    ]);
    if (id === messageEpoch.current) {
      setMessages(m);
      setRuns(r);
    }
  }
  async function openPaper(p: Paper, preferredThread?: string) {
    if (generating) return;
    const id = ++epoch.current;
    ++messageEpoch.current;
    setPaper(p);
    setPage(p.current_page);
    setAnchor(null);
    setContext(null);
    setQuestion("");
    setThread(null);
    setMessages([]);
    setThreads([]);
    setRuns([]);
    const ts = await api<Thread[]>(`/papers/${p.id}/threads`);
    if (id !== epoch.current) return;
    setThreads(ts);
    if (ts.length) {
      const selected = ts.find((t) => t.id === preferredThread) || ts[0];
      await loadThread(selected);
      await api("/session", "PUT", { paper_id: p.id, thread_id: selected.id });
    } else await api("/session", "PUT", { paper_id: p.id });
  }
  function changePage(n: number, clearAnchor = true) {
    if (!paper) return;
    setPage(n);
    if (clearAnchor) setAnchor(null);
    if (positionTimer.current) clearTimeout(positionTimer.current);
    const p = paper;
    setPapers((old) =>
      old.map((v) => (v.id === p.id ? { ...v, current_page: n } : v)),
    );
    positionTimer.current = setTimeout(
      () =>
        void api(`/papers/${p.id}/position`, "PUT", { page: n }).catch(fail),
      300,
    );
  }
  function cite(n: number, a?: Anchor | null) {
    if (!paper || n < 1 || n > paper.page_count) return;
    changePage(n);
    if (a) setAnchor(a);
  }
  function currentAnchor(): Anchor | null {
    return (
      anchor ||
      (paper
        ? { sha256: paper.sha256, page, kind: "page", rects: [], quote: "" }
        : null)
    );
  }
  async function ensureThread(preferredTitle?: string) {
    if (preferredTitle) {
      const existing = threads.find((t) => t.title === preferredTitle);
      if (existing) {
        if (thread?.id !== existing.id) await loadThread(existing);
        return existing;
      }
    } else if (thread) return thread;
    if (!paper) throw new Error("请先打开论文。");
    const t = await api<Thread>(`/papers/${paper.id}/threads`, "POST", {
      title: preferredTitle || question.trim().slice(0, 35) || "阅读讨论",
    });
    setThreads((old) => [t, ...old]);
    await loadThread(t);
    await api("/session", "PUT", { paper_id: paper.id, thread_id: t.id });
    return t;
  }
  async function configureDirectory(path = directory) {
    setBusy(true);
    try {
      const s = await api<Status>("/workspace", "POST", { path });
      setStatus(s);
      setConfig(s.provider);
      localStorage.setItem("paper-lab-directory", s.data_dir!);
      await restoreSession();
      setError("");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function pickDirectory() {
    setBusy(true);
    try {
      const picked = await api<{ path: string | null }>(
        "/workspace/pick",
        "POST",
      );
      if (!picked.path) return;
      setDirectory(picked.path);
      const s = await api<Status>("/workspace", "POST", {
        path: picked.path,
      });
      setStatus(s);
      setConfig(s.provider);
      localStorage.setItem("paper-lab-directory", s.data_dir!);
      await restoreSession();
      setError("");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function saveProvider() {
    setBusy(true);
    try {
      const s = await api<Status>("/provider", "PUT", config);
      setStatus(s);
      if (key) {
        await api("/key", "PUT", { key });
        setKey("");
        await refreshStatus();
      }
      settings.current?.close();
      setError("");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function imported(p: Paper) {
    setPapers(await api("/papers"));
    await openPaper(p);
    importDialog.current?.close();
    setError("");
  }
  async function upload(file: File) {
    setBusy(true);
    try {
      const body = new FormData();
      body.set("file", file);
      await imported(
        await (
          await request("/papers/import", { method: "POST", body })
        ).json(),
      );
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function find() {
    setBusy(true);
    setSearched(false);
    try {
      setCandidates(await api(`/search?q=${encodeURIComponent(searchQuery)}`));
      setSearched(true);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function download(id: string) {
    setBusy(true);
    try {
      await imported(await api("/papers/download", "POST", { arxiv_id: id }));
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function savePaperTags() {
    if (!paper) return;
    setBusy(true);
    try {
      const updated = await api<Paper>(`/papers/${paper.id}/tags`, "PUT", {
        tags: paperTags.split(",").map((tag) => tag.trim()).filter(Boolean),
      });
      setPaper(updated);
      setPapers((old) => old.map((item) => item.id === updated.id ? updated : item));
      paperDialog.current?.close();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function importExternal(source: ExternalSource) {
    if (!source.arxiv_id) return;
    setBusy(true);
    try {
      const importedPaper = await api<Paper>("/papers/download", "POST", {
        arxiv_id: source.arxiv_id,
      });
      setPapers(await api("/papers"));
      await openPaper(importedPaper);
      const located = await api<{ anchor: Anchor | null }>(
        `/papers/${importedPaper.id}/locate`, "POST", { quote: source.quote },
      );
      if (located.anchor) {
        setPage(located.anchor.page);
        setAnchor(located.anchor);
        await api(`/papers/${importedPaper.id}/position`, "PUT", {
          page: located.anchor.page,
        });
      }
      sourceDialog.current?.close();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function newTopic() {
    if (!paper) return;
    setBusy(true);
    try {
      const t =
        editingTopic && thread
          ? await api<Thread>(`/threads/${thread.id}`, "PATCH", {
              title: topicTitle,
            })
          : await api<Thread>(`/papers/${paper.id}/threads`, "POST", {
              title: topicTitle,
            });
      setThreads((old) =>
        editingTopic
          ? old.map((item) => (item.id === t.id ? t : item))
          : [t, ...old],
      );
      await loadThread(t);
      await api("/session", "PUT", { paper_id: paper.id, thread_id: t.id });
      setQuestion("");
      topicDialog.current?.close();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function deleteTopic() {
    if (!paper || !thread || generating) return;
    if (
      !window.confirm(
        `删除主题“${thread.title}”及其中的对话？已确认保存的笔记会保留。`,
      )
    )
      return;
    setBusy(true);
    try {
      await api(`/threads/${thread.id}`, "DELETE");
      const remaining = threads.filter((t) => t.id !== thread.id);
      setThreads(remaining);
      setThread(null);
      setMessages([]);
      setRuns([]);
      if (remaining.length) {
        await loadThread(remaining[0]);
        await api("/session", "PUT", {
          paper_id: paper.id,
          thread_id: remaining[0].id,
        });
      } else await api("/session", "PUT", { paper_id: paper.id });
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function previewContext() {
    setBusy(true);
    try {
      const previewKey = `${paper?.id}:${question.trim()}:${academicSearch}`;
      const value = await api<Context>(
          thread
            ? `/threads/${thread.id}/context`
            : `/papers/${paper!.id}/context`,
          "POST",
          {
            question: question.trim() || "解释当前页面",
            anchor: currentAnchor(),
            academic_search: academicSearch,
            external_sources:
              academicSearch && preparedExternal?.key === previewKey
                ? preparedExternal.sources
                : [],
          },
        );
      setContext(value);
      if (academicSearch)
        setPreparedExternal({ key: previewKey, sources: value.external_sources || [] });
      contextDialog.current?.showModal();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function send(options?: {
    text?: string;
    purpose?: "question" | "pre-read" | "post-read";
    topicTitle?: string;
  }) {
    const text = (options?.text ?? question).trim();
    const purpose = options?.purpose || "question";
    if (!text || generating || !paper) return;
    setGenerating(true);
    setError("");
    setPhase("准备原文");
    const controller = new AbortController();
    abort.current = controller;
    let t: Thread | null = null;
    let sent = false;
    try {
      t = await ensureThread(options?.topicTitle);
      const a = purpose === "question" ? currentAnchor() : null;
      const previewKey = `${paper.id}:${text}:${academicSearch}`;
      const response = await request(`/threads/${t.id}/messages`, {
        method: "POST",
        body: JSON.stringify({
          question: text,
          anchor: a,
          workflow: purpose === "question" ? workflow : "specialist",
          purpose,
          academic_search: purpose === "question" && academicSearch,
          external_sources:
            purpose === "question" && preparedExternal?.key === previewKey
              ? preparedExternal.sources
              : [],
        }),
        signal: controller.signal,
      });
      sent = true;
      if (purpose === "question") setQuestion("");
      let answerId = "pending";
      setMessages((old) => [
        ...old,
        {
          id: "local-user",
          role: "user",
          content: text,
          status: "complete",
          model: null,
          anchor: a,
          context: null,
        },
        {
          id: answerId,
          role: "assistant",
          content: "",
          status: "streaming",
          model: config.model,
          anchor: a,
          context: null,
        },
      ]);
      const reader = response.body!.getReader(),
        decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === "start") {
            answerId = event.message_id;
            setMessages((old) =>
              old.map((m) =>
                m.id === "pending"
                  ? { ...m, id: answerId, context: event.context }
                  : m,
              ),
            );
          }
          if (event.type === "delta") {
            setMessages((old) =>
              old.map((m) =>
                m.id === answerId
                  ? { ...m, content: m.content + event.text }
                  : m,
              ),
            );
            setPhase("正在回答");
          }
          if (event.type === "phase")
            setPhase(
              event.phase === "editor"
                ? "Editor 正在核查并修订"
                : event.phase === "draft"
                  ? "Reader 正在形成 draft"
                  : "Specialist 正在阅读",
            );
          if (event.type === "thinking") setPhase("模型正在思考");
          if (event.type === "error") setError(event.message);
          if (event.type === "done" && event.error) setError(event.error);
        }
        if (done) break;
      }
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) fail(e);
    } finally {
      setPhase("");
      abort.current = null;
      if (t && sent) {
        try {
          await loadThread(t);
        } catch (e) {
          fail(e);
        }
      }
      setGenerating(false);
    }
  }
  async function stopGeneration() {
    if (thread) {
      try {
        await api(`/threads/${thread.id}/stop`, "POST");
      } catch (e) {
        fail(e);
        abort.current?.abort();
      }
    } else abort.current?.abort();
  }
  function stageNote(source: Message | Note) {
    setNoteSource(source);
    setNoteText(source.content);
    setEditingNote("message_id" in source);
    noteDialog.current?.showModal();
  }
  async function saveNote() {
    if (!noteSource) return;
    setBusy(true);
    try {
      if (editingNote)
        await api(`/notes/${noteSource.id}`, "PUT", { content: noteText });
      else if (paper)
        await api(`/papers/${paper.id}/notes`, "POST", {
          content: noteText,
          message_id: noteSource.id,
          anchor: noteSource.anchor,
        });
      setNotes(await api(`/notes`));
      noteDialog.current?.close();
      setError("");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  const visibleNotes = notes.filter(
    (n) => showCrossPaperNotes || !paper || n.paper_id === paper.id,
  );
  async function openNoteSource(n: Note, targetPage?: number) {
    const source = papers.find((p) => p.id === n.paper_id);
    if (!source) return;
    if (paper?.id !== source.id) await openPaper(source);
    if (targetPage) {
      setPage(targetPage);
      setAnchor(n.anchor?.page === targetPage ? n.anchor : null);
    }
  }
  function resizeBy(side: "library" | "discussion", delta: number) {
    const root = layout.current;
    if (!root) return;
    const available = root.clientWidth - 390 - 12;
    if (side === "library") {
      const maximum = Math.max(160, Math.min(360, available - discussionWidth));
      const next = Math.min(maximum, Math.max(160, libraryWidth + delta));
      setLibraryWidth(next);
      localStorage.setItem("paper-lab-library-width", String(next));
    } else {
      const usedLeft = collapsed ? 0 : libraryWidth;
      const maximum = Math.max(300, Math.min(720, available - usedLeft));
      const next = Math.min(maximum, Math.max(300, discussionWidth - delta));
      setDiscussionWidth(next);
      localStorage.setItem("paper-lab-discussion-width", String(next));
    }
  }
  function startResize(
    side: "library" | "discussion",
    event: React.PointerEvent<HTMLDivElement>,
  ) {
    if (window.innerWidth <= 800) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = side === "library" ? libraryWidth : discussionWidth;
    const root = layout.current!;
    const available = root.clientWidth - 390 - 12;
    const usedLeft = collapsed ? 0 : libraryWidth;
    document.body.classList.add("resizing-columns");
    const move = (e: PointerEvent) => {
      const total = e.clientX - startX;
      if (side === "library") {
        const maximum = Math.max(
          160,
          Math.min(360, available - discussionWidth),
        );
        const next = Math.min(maximum, Math.max(160, startWidth + total));
        setLibraryWidth(next);
        localStorage.setItem("paper-lab-library-width", String(next));
      } else {
        const maximum = Math.max(300, Math.min(720, available - usedLeft));
        const next = Math.min(maximum, Math.max(300, startWidth - total));
        setDiscussionWidth(next);
        localStorage.setItem("paper-lab-discussion-width", String(next));
      }
    };
    const stop = () => {
      document.body.classList.remove("resizing-columns");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
    window.addEventListener("pointercancel", stop, { once: true });
  }
  function resizeComposerBy(delta: number) {
    const maximum = Math.max(
      160,
      Math.min(
        520,
        (discussion.current?.clientHeight || window.innerHeight) - 260,
      ),
    );
    const next = Math.min(maximum, Math.max(160, composerHeight - delta));
    setComposerHeight(next);
    localStorage.setItem("paper-lab-composer-height", String(next));
  }
  function startComposerResize(event: React.PointerEvent<HTMLDivElement>) {
    if (window.innerWidth <= 800) return;
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = composerHeight;
    const maximum = Math.max(
      160,
      Math.min(
        520,
        (discussion.current?.clientHeight || window.innerHeight) - 260,
      ),
    );
    document.body.classList.add("resizing-rows");
    const move = (e: PointerEvent) => {
      const next = Math.min(
        maximum,
        Math.max(160, startHeight - (e.clientY - startY)),
      );
      setComposerHeight(next);
      localStorage.setItem("paper-lab-composer-height", String(next));
    };
    const stop = () => {
      document.body.classList.remove("resizing-rows");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
    window.addEventListener("pointercancel", stop, { once: true });
  }
  const dialogError = error && (
    <div role="alert" className="inline-error">
      {error}
    </div>
  );
  return (
    <div
      ref={layout}
      className={"app" + (collapsed ? " library-collapsed" : "")}
      style={
        {
          "--library-width": `${libraryWidth}px`,
          "--discussion-width": `${discussionWidth}px`,
        } as React.CSSProperties
      }
    >
      <aside className="library">
        <div className="brand">
          <BookOpen size={22} /> paper lab <span>本地</span>
        </div>
        <button
          className="primary"
          disabled={busy || generating}
          onClick={() =>
            status?.configured
              ? importDialog.current?.showModal()
              : settings.current?.showModal()
          }
        >
          <Plus size={16} /> 导入论文
        </button>
        <div className="section-label">
          我的论文 <span>{papers.length || ""}</span>
        </div>
        <div className="paper-list">
          {papers.length ? (
            papers.map((p) => (
              <button
                key={p.id}
                disabled={generating}
                className={paper?.id === p.id ? "selected" : ""}
                onClick={() => void openPaper(p).catch(fail)}
              >
                <FileText size={16} />
                <span>
                  {p.title}
                  <small>
                    {paperIdentity(p)} · {p.page_count} 页
                    {p.tags.length ? ` · ${p.tags.join(" · ")}` : ""}
                  </small>
                </span>
              </button>
            ))
          ) : (
            <div className="muted empty-library">
              {status?.configured
                ? "还没有论文。导入 PDF，或从 arXiv 搜索。"
                : "选择工作目录后，导入第一篇 PDF。"}
            </div>
          )}
        </div>
        <button
          className="settings"
          disabled={generating}
          onClick={() => settings.current?.showModal()}
        >
          <Settings size={16} /> 工作目录与模型
        </button>
      </aside>
      <ResizeHandle
        className="library-resizer"
        label="调整论文列表宽度"
        value={libraryWidth}
        hidden={collapsed}
        onPointerDown={(e) => startResize("library", e)}
        onKey={(delta) => resizeBy("library", delta)}
      />
      <main className="reader">
        <header>
          <button
            className="icon"
            aria-label="展开或收起论文库"
            onClick={() => setCollapsed(!collapsed)}
          >
            <PanelLeftClose size={16} />
          </button>
          <span className="paper-title">{paper?.title || "阅读工作台"}</span>
          {paper && (
            <button
              className="icon"
              aria-label="论文标签"
              title="论文标识与标签"
              onClick={() => {
                setPaperTags(paper.tags.join(", "));
                paperDialog.current?.showModal();
              }}
            >
              <Tags size={16} />
            </button>
          )}
          {!paper && <span className="muted">PDF · 原文与理解</span>}
        </header>
        {error && (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button
              className="icon"
              aria-label="关闭提示"
              onClick={() => setError("")}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {paper ? (
          <PdfReader
            paper={paper}
            page={page}
            setPage={changePage}
            supportsImages={config.supports_images}
            anchor={anchor}
            onSelect={(a) => {
              setAnchor(a);
              setTab("chat");
            }}
            onError={setError}
          />
        ) : (
          <div className="paper-empty">
            <div className="paper-icon">
              <FileText size={36} strokeWidth={1.2} />
            </div>
            <h1>从原文开始</h1>
            <p>
              {status?.configured
                ? "导入一篇论文，在原文旁边展开讨论。"
                : "选择本地工作目录，集中保存 PDF、对话和笔记。"}
            </p>
            <button
              className="primary"
              onClick={() =>
                status?.configured
                  ? importDialog.current?.showModal()
                  : settings.current?.showModal()
              }
            >
              {status?.configured ? "导入 PDF" : "选择工作目录"}
            </button>
            <small>支持本地 PDF 导入与 arXiv 搜索下载</small>
          </div>
        )}
      </main>
      <ResizeHandle
        className="discussion-resizer"
        label="调整对话栏宽度"
        value={discussionWidth}
        onPointerDown={(e) => startResize("discussion", e)}
        onKey={(delta) => resizeBy("discussion", delta)}
      />
      <aside className="discussion" ref={discussion}>
        <header>
          <button
            className={tab === "chat" ? "tab active" : "tab"}
            onClick={() => setTab("chat")}
          >
            <MessageSquare size={16} /> 对话
          </button>
          <button
            className={tab === "notes" ? "tab active" : "tab"}
            onClick={() => setTab("notes")}
          >
            <NotebookPen size={16} /> 笔记 {notes.length || ""}
          </button>
          <span className="persistence-note">
            对话自动保存 · 笔记由你确认
          </span>
        </header>
        {tab === "chat" ? (
          <>
            {paper && (
              <div className="topic-bar">
                <select
                  aria-label="讨论主题"
                  disabled={generating}
                  value={thread?.id || ""}
                  onChange={(e) => {
                    const t = threads.find((t) => t.id === e.target.value);
                    if (t) {
                      setQuestion("");
                      void loadThread(t)
                        .then(() =>
                          api("/session", "PUT", {
                            paper_id: paper.id,
                            thread_id: t.id,
                          }),
                        )
                        .catch(fail);
                    }
                  }}
                >
                  <option value="" disabled>
                    开始一个主题
                  </option>
                  {threads.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.title}
                    </option>
                  ))}
                </select>
                <button
                  disabled={generating}
                  aria-label="新建主题"
                  title="新建主题"
                  onClick={() => {
                    setEditingTopic(false);
                    setTopicTitle("");
                    topicDialog.current?.showModal();
                  }}
                >
                  <Plus size={17} />
                </button>
                <button
                  disabled={generating || !thread}
                  aria-label="重命名主题"
                  title="重命名主题"
                  onClick={() => {
                    if (!thread) return;
                    setEditingTopic(true);
                    setTopicTitle(thread.title);
                    topicDialog.current?.showModal();
                  }}
                >
                  <Pencil size={16} />
                </button>
                <button
                  disabled={generating || busy || !thread}
                  className="danger-icon"
                  aria-label="删除主题"
                  title="删除主题"
                  onClick={() => void deleteTopic()}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            )}
            {paper && (
              <div className="summary-actions">
                <span>
                  <Sparkles size={14} /> 全篇辅助
                </span>
                <button
                  disabled={generating || busy || !status?.key_configured}
                  onClick={() =>
                    void send({
                      text: "生成阅读前概览",
                      purpose: "pre-read",
                      topicTitle: "阅读前概览",
                    })
                  }
                >
                  阅读前概览
                </button>
                <button
                  disabled={generating || busy || !status?.key_configured}
                  onClick={() =>
                    void send({
                      text: "生成阅读后总结",
                      purpose: "post-read",
                      topicTitle: "阅读后总结",
                    })
                  }
                >
                  阅读后总结
                </button>
              </div>
            )}
            <div className="messages">
              {messages.length ? (
                messages.map((m) => {
                  const run = runs.find((candidate) => candidate.message_id === m.id);
                  return (
                  <article key={m.id} className={"message " + m.role}>
                    <div className="message-label">
                      {m.role === "user" ? "你" : m.model || "Specialist"}
                      {m.anchor && (
                        <button
                          className="citation"
                          onClick={() => cite(m.anchor!.page, m.anchor)}
                        >
                          p.{m.anchor.page}
                          {m.anchor.kind === "region" ? " · 截图" : ""}
                        </button>
                      )}
                    </div>
                    {m.role === "user" ? (
                      <p className="user-text">{m.content}</p>
                    ) : (
                      <Markdown
                        content={m.content}
                        sources={m.context?.sources || []}
                        onCite={cite}
                        externalSources={m.context?.external_sources || []}
                        onExternal={(source) => {
                          setExternalSource(source);
                          sourceDialog.current?.showModal();
                        }}
                      />
                    )}{" "}
                    {m.role === "assistant" &&
                      run?.workflow === "draft-editor" &&
                      run.trace && (
                        <details className="review-trace">
                          <summary>
                            审查记录 · Draft → Editor
                            <span>{run.status === "complete" ? "已完成" : run.status}</span>
                          </summary>
                          {run.trace.stages.map((stage, index) => (
                            <section key={`${stage.phase}-${index}`}>
                              <header>
                                <strong>
                                  {stage.phase === "draft" ? "Reader draft" : "Editor review"}
                                </strong>
                                <span>{stage.model} · {stage.status}</span>
                              </header>
                              {stage.content ? (
                                <Markdown
                                  content={stage.content}
                                  sources={m.context?.sources || []}
                                  onCite={cite}
                                  externalSources={m.context?.external_sources || []}
                                  onExternal={(source) => {
                                    setExternalSource(source);
                                    sourceDialog.current?.showModal();
                                  }}
                                />
                              ) : (
                                <p className="muted">这一阶段没有保存可显示的内容。</p>
                              )}
                            </section>
                          ))}
                        </details>
                      )}
                    {m.role === "assistant" && m.content && (
                      <div className="message-actions">
                        <button
                          disabled={generating}
                          onClick={() => stageNote(m)}
                        >
                          <NotebookPen size={14} /> 保存为笔记
                        </button>
                        {m.context && (
                          <button
                            onClick={() => {
                              setContext(m.context);
                              contextDialog.current?.showModal();
                            }}
                          >
                            查看原文上下文
                          </button>
                        )}
                        {!["complete", "streaming"].includes(m.status) && (
                          <span className="muted">
                            {m.status === "truncated"
                              ? "达到输出上限"
                              : "回答未完成"}
                          </span>
                        )}
                      </div>
                    )}
                  </article>
                  );
                })
              ) : (
                <div className="conversation-empty">
                  <span className="eyebrow">SPECIALIST</span>
                  <h2>带着问题阅读</h2>
                  <p>
                    选中一段文字或截图框选图表，
                    <br />
                    从这里继续理解。
                  </p>
                  <div className="hint">解释原理 · 补充前提 · 发现遗漏</div>
                </div>
              )}
              {generating && <div className="generating">{phase}…</div>}
              <div ref={bottom} />
            </div>
            {runs.length > 0 && (
              <details className="usage">
                <summary>
                  最近调用 ·{" "}
                  {runs[0].status === "complete" ? "已完成" : runs[0].status}
                </summary>
                {runs[0].usage?.map((u, i) => (
                  <div key={i}>
                    {u.phase} · {u.model}
                    <br />
                    {u.tokens
                      ? `输入 ${u.tokens.prompt_tokens ?? "—"} / 输出 ${u.tokens.completion_tokens ?? "—"} tokens`
                      : "usage 未返回，费用未知"}
                  </div>
                ))}
                {runs[0].error && <p>{runs[0].error}</p>}
              </details>
            )}
            {anchor && (
              <div className="selection-chip">
                <div className="selection-title">
                  <button
                    className="citation"
                    onClick={() => cite(anchor.page, anchor)}
                  >
                    p.{anchor.page} ·{" "}
                    {anchor.kind === "region" ? "截图选区" : "文字选区"}
                  </button>
                  <span>将作为问题的直接原文依据</span>
                </div>
                <details>
                  <summary>
                    {anchor.quote ? "查看选中的原文" : "此区域没有可提取文字"}
                  </summary>
                  <p>
                    {anchor.quote ||
                      "将发送区域截图；框内可提取文字只作辅助，补充原文仍按当前页、相邻页与问题关键词选择。"}
                  </p>
                </details>
                <button
                  className="icon"
                  aria-label="清除选区"
                  onClick={() => setAnchor(null)}
                >
                  <X size={15} />
                </button>
              </div>
            )}
            <HorizontalResizeHandle
              value={composerHeight}
              onPointerDown={startComposerResize}
              onKey={resizeComposerBy}
            />
            <div
              className="composer"
              style={
                {
                  "--composer-height": `${composerHeight}px`,
                } as React.CSSProperties
              }
            >
              <textarea
                aria-label="向论文助手提问"
                placeholder={
                  paper
                    ? anchor
                      ? "针对选中的原文提问…"
                      : "问一个问题，或先在左侧选中原文…"
                    : "打开论文后，围绕原文提问…"
                }
                disabled={!paper || generating}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (
                    e.key === "Enter" &&
                    !e.shiftKey &&
                    !e.nativeEvent.isComposing
                  ) {
                    e.preventDefault();
                    void send();
                  }
                }}
              />
              <div className="composer-controls">
                <select
                  aria-label="阅读模式"
                  disabled={generating}
                  value={workflow}
                  onChange={(e) => setWorkflow(e.target.value)}
                >
                  <option value="specialist">Specialist</option>
                  <option value="draft-editor">Draft + Editor</option>
                </select>
                <button
                  type="button"
                  className="workflow-info"
                  aria-label="了解阅读策略"
                  title="了解阅读策略"
                  onClick={() => workflowDialog.current?.showModal()}
                >
                  <Info size={16} />
                </button>
                {generating ? (
                  <button
                    onClick={() => void stopGeneration()}
                    aria-label="停止生成"
                  >
                    <Square size={16} />
                  </button>
                ) : (
                  <button
                    onClick={() => void send()}
                    disabled={
                      !paper ||
                      !question.trim() ||
                      !status?.key_configured ||
                      busy
                    }
                    aria-label="发送问题"
                  >
                    <ArrowUp size={18} /> <span>发送</span>
                  </button>
                )}
              </div>
              <div className="composer-meta">
                <button
                  disabled={!paper || busy || generating}
                  onClick={() => void previewContext()}
                >
                  查看将发送的原文
                </button>
                <span>{config.model}</span>
              </div>
              <label className="checkbox academic-search-toggle">
                <input
                  type="checkbox"
                  checked={academicSearch}
                  disabled={!paper || generating}
                  onChange={(e) => {
                    setAcademicSearch(e.target.checked);
                    setPreparedExternal(null);
                  }}
                />
                检索外部学术资料
              </label>
            </div>
            {status?.configured && !status.key_configured ? (
              <button
                className="key-reminder"
                onClick={() => settings.current?.showModal()}
              >
                配置 API key 后开始对话
              </button>
            ) : null}
          </>
        ) : (
          <div className="notes-panel">
            <div className="notes-heading">
              <span>全局笔记 · 已确认的理解</span>
              {paper && visibleNotes.length > 0 && !showCrossPaperNotes && (
                <a href={`/api/papers/${paper.id}/notes/export`} download>
                  导出 Markdown
                </a>
              )}
            </div>
            {paper && (
              <label className="notes-filter checkbox">
                <input
                  type="checkbox"
                  checked={showCrossPaperNotes}
                  onChange={(e) => setShowCrossPaperNotes(e.target.checked)}
                />
                跨论文显示
              </label>
            )}
            {visibleNotes.length ? (
              visibleNotes.map((n) => (
                <article className="note" key={n.id}>
                  <button
                    className="note-paper"
                    onClick={() => void openNoteSource(n)}
                  >
                    {n.paper_title || "来源论文"}
                  </button>
                  {n.anchor && (
                    <button
                      className="citation"
                      onClick={() => void openNoteSource(n, n.anchor!.page)}
                    >
                      返回 p.{n.anchor.page}
                    </button>
                  )}
                  <Markdown
                    content={n.content}
                    sources={[]}
                    allowedPages={
                      new Set(
                        Array.from(
                          { length: n.paper_page_count || 0 },
                          (_, i) => i + 1,
                        ),
                      )
                    }
                    onCite={(target) => void openNoteSource(n, target)}
                  />
                  <button onClick={() => stageNote(n)}>编辑笔记</button>
                </article>
              ))
            ) : (
              <div className="conversation-empty">
                <NotebookPen size={25} />
                <h2>理解，由你留下</h2>
                <p>
                  对话不会自动变成笔记。
                  <br />
                  在回答下点击“保存为笔记”。
                </p>
              </div>
            )}
          </div>
        )}
      </aside>
      <dialog ref={settings}>
        <DialogTitle
          title="工作目录与模型"
          close={() => settings.current?.close()}
        />
        {dialogError}
        <label>
          本地工作目录
          <div className="directory-field">
            <input
              value={directory}
              disabled={status?.configured || busy}
              placeholder="选择文件夹，或输入绝对路径"
              onChange={(e) => setDirectory(e.target.value)}
            />
            {!status?.configured && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void pickDirectory()}
              >
                {busy ? "正在打开…" : "选择文件夹…"}
              </button>
            )}
          </div>
        </label>
        {status?.configured ? (
          <p className="muted small">
            目录已打开。切换目录请重启服务后重新选择。
          </p>
        ) : (
          <button
            className="primary"
            disabled={!directory || busy}
            onClick={() => void configureDirectory(directory)}
          >
            {busy ? "正在打开…" : "打开工作目录"}
          </button>
        )}
        <p className="small muted">
          PDF 统一放在
          pdfs/；对话、笔记和进度保存在同一工作目录。选择空目录或已有 Paper Lab
          目录。“选择文件夹”会在选定后直接打开目录。
        </p>
        <hr />
        <label>
          Provider
          <select
            value={config.provider}
            onChange={(e) =>
              setConfig({
                ...config,
                provider: e.target.value,
                base_url:
                  e.target.value === "deepseek"
                    ? "https://api.deepseek.com"
                    : config.base_url,
              })
            }
          >
            <option value="deepseek">DeepSeek</option>
            <option value="openai-compatible">OpenAI-compatible API</option>
          </select>
        </label>
        <label>
          API 地址
          <input
            value={config.base_url}
            onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
          />
        </label>
        <label>
          模型名称
          <input
            value={config.model}
            onChange={(e) => setConfig({ ...config, model: e.target.value })}
          />
        </label>
        {config.provider === "deepseek" && (
          <p className="small muted">
            DeepSeek V4.1 Flash · 官方 API 名称 deepseek-flash
          </p>
        )}
        <div className="form-row">
          <label>
            推理模式
            <select
              value={config.effort}
              disabled={config.provider !== "deepseek"}
              onChange={(e) => setConfig({ ...config, effort: e.target.value })}
            >
              <option value="none">关闭思考 · 默认</option>
              <option value="low">Low</option>
              <option value="high">High</option>
            </select>
          </label>
          <label>
            常规问答输出上限
            <input
              type="number"
              min={256}
              max={16384}
              value={config.max_tokens}
              onChange={(e) =>
                setConfig({ ...config, max_tokens: Number(e.target.value) })
              }
            />
          </label>
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={config.supports_images}
            onChange={(e) =>
              setConfig({ ...config, supports_images: e.target.checked })
            }
          />{" "}
          此模型支持图像输入
        </label>
        <label>
          API key
          <input
            type="password"
            autoComplete="off"
            value={key}
            placeholder={
              status?.key_configured
                ? status.key_storage === "keychain"
                  ? "已保存在 macOS Keychain，留空保持"
                  : status.key_storage === "environment"
                    ? "已通过环境变量配置，留空保持"
                    : "Keychain 暂不可用，可重新保存"
                : "稍后配置也可以"
            }
            onChange={(e) => setKey(e.target.value)}
          />
        </label>
        <p className="small muted">
          在这里保存的 key 会进入 macOS
          Keychain，进程重启后仍可使用；不会写入工作目录、 Git 或浏览器存储。API
          调用会发送相关原文与所选图像。
        </p>
        {status && !status.poppler_ready && (
          <p className="inline-error">缺少 Poppler，导入 PDF 前需要安装。</p>
        )}
        <div className="dialog-actions">
          <button onClick={() => settings.current?.close()}>关闭</button>
          <button
            className="primary"
            disabled={!status?.configured || busy}
            onClick={() => void saveProvider()}
          >
            保存设置
          </button>
        </div>
      </dialog>
      <dialog ref={importDialog}>
        <DialogTitle
          title="导入论文"
          close={() => importDialog.current?.close()}
        />
        {dialogError}
        <label className="upload-box">
          <Upload size={25} />
          <strong>{busy ? "正在处理…" : "选择本地 PDF"}</strong>
          <span>复制到工作目录的 pdfs/ · 最大 50 MB</span>
          <input
            aria-label="选择 PDF 文件"
            type="file"
            accept="application/pdf,.pdf"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
              e.target.value = "";
            }}
          />
        </label>
        <div className="divider">或从 arXiv 搜索下载</div>
        <form
          className="search-form"
          onSubmit={(e) => {
            e.preventDefault();
            void find();
          }}
        >
          <input
            aria-label="搜索论文"
            placeholder="论文标题、关键词或 arXiv ID"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button disabled={busy || searchQuery.trim().length < 2}>
            <Search size={17} /> 搜索
          </button>
        </form>
        <div className="search-results">
          {candidates.map((c) => (
            <article key={c.arxiv_id}>
              <strong>{c.title}</strong>
              <p>
                {c.authors.slice(0, 4).join(", ")} · {c.year}
              </p>
              <div>
                <a href={c.url} target="_blank" rel="noreferrer">
                  arXiv {c.arxiv_id} <ExternalLink size={12} />
                </a>
                <button
                  disabled={busy}
                  onClick={() => void download(c.arxiv_id)}
                >
                  下载并导入
                </button>
              </div>
            </article>
          ))}
          {searched && !candidates.length && (
            <p className="muted">没有找到结果，可尝试标题关键词或手动导入。</p>
          )}
        </div>
      </dialog>
      <dialog ref={topicDialog}>
        <DialogTitle
          title={editingTopic ? "重命名讨论主题" : "新讨论主题"}
          close={() => topicDialog.current?.close()}
        />
        {dialogError}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void newTopic();
          }}
        >
          <label>
            主题名称
            <input
              autoFocus
              value={topicTitle}
              onChange={(e) => setTopicTitle(e.target.value)}
              placeholder="例如：理解并行计算的通信过程"
              maxLength={200}
            />
          </label>
          <div className="dialog-actions">
            <button className="primary" disabled={!topicTitle.trim() || busy}>
              {editingTopic ? "保存名称" : "开始讨论"}
            </button>
          </div>
        </form>
      </dialog>
      <dialog className="note-dialog" ref={noteDialog}>
        <DialogTitle
          title={editingNote ? "编辑笔记" : "确认并保存笔记"}
          close={() => noteDialog.current?.close()}
        />
        {dialogError}
        <p className="small muted">
          可以修改解释，再保存为你的阅读笔记。原对话会保留。
        </p>
        <textarea
          aria-label="笔记内容"
          value={noteText}
          onChange={(e) => setNoteText(e.target.value)}
        />
        <div className="dialog-actions">
          <button onClick={() => noteDialog.current?.close()}>取消</button>
          <button
            className="primary"
            disabled={!noteText.trim() || busy}
            onClick={() => void saveNote()}
          >
            <Check size={16} /> 保存笔记
          </button>
        </div>
      </dialog>
      <dialog className="context-dialog" ref={contextDialog}>
        <DialogTitle
          title="原文上下文"
          close={() => contextDialog.current?.close()}
        />
        {context && (
          <>
            <p className="context-scope">{context.scope}</p>
            {context.external_sources?.length ? (
              <section className="external-context">
                <h3>外部学术资料</h3>
                {context.external_sources.map((source) => (
                  <button
                    key={source.citation}
                    onClick={() => {
                      setExternalSource(source);
                      sourceDialog.current?.showModal();
                    }}
                  >
                    [{source.citation}] {source.title} · {source.locator}
                  </button>
                ))}
              </section>
            ) : null}
            <p className="small muted">
              普通提问先找选区句群，再按当前页、相邻页、问题关键词和首页概览排序；最多发送
              24 个原文片段、24,000
              字符。全篇概览/总结发送全部可提取文字；DeepSeek 总结使用 provider 的最大输出范围，
              最终仍受所选模型的 context window 与 maximum output 限制。
            </p>
            <p className="small">
              {context.coverage &&
                `覆盖 ${context.coverage.pages_included.length} / ${context.coverage.total_pages} 个 PDF 页面 · `}
              {context.characters.toLocaleString()} 字符 ·{" "}
              {context.history_messages} 条历史消息
              {context.image_attached ? " · 含选区图像" : ""}
            </p>
            {context.sources.map((s, index) => (
              <details key={`${s.page}-${index}`}>
                <summary>
                  <span>
                    {s.reason} ·{" "}
                    {s.citation ? `[${s.citation}]` : `PDF p.${s.page}`}
                    {s.truncated ? " · 节选" : ""}
                  </span>
                  <ChevronDown size={14} />
                </summary>
                <button
                  className="context-jump"
                  onClick={() => {
                    cite(s.page, s.anchor);
                    contextDialog.current?.close();
                  }}
                >
                  跳到 PDF {s.citation ? `[${s.citation}]` : `p.${s.page}`}
                </button>
                <pre>{s.text || "本页未提取到文字。图表请使用框选。"}</pre>
              </details>
            ))}
          </>
        )}
      </dialog>
      <dialog className="workflow-dialog" ref={workflowDialog}>
        <DialogTitle
          title="阅读策略"
          close={() => workflowDialog.current?.close()}
        />
        <article>
          <h3>Specialist</h3>
          <p>
            直接围绕选区、问题和补充原文解释机制、前提与容易遗漏的细节。适合已经被验证的论文、日常精读和连续追问，响应更快、成本更低。
          </p>
        </article>
        <article>
          <h3>Draft + Editor</h3>
          <p>
            Reader 先形成 draft，Editor 再对照同一批原文核查并修订。对话只显示修订后的最终回答；draft 和审查事项保存在默认折叠的审查记录中。适合最新结果、证据链复杂或你希望额外审查的内容。
          </p>
        </article>
        <p className="small muted">
          两种策略都只使用“查看将发送的原文”中列出的当前论文内容，以及本次显式开启并列出的外部学术资料；回答不会自动写入笔记。
        </p>
      </dialog>
      <dialog className="source-dialog" ref={sourceDialog}>
        <DialogTitle title="外部来源" close={() => sourceDialog.current?.close()} />
        {externalSource && (
          <>
            <span className="eyebrow">[{externalSource.citation}] {externalSource.provider}</span>
            <h3>{externalSource.title}</h3>
            <p className="muted small">
              {[externalSource.authors.join(", "), externalSource.year, externalSource.locator,
                externalSource.retrieved_at ? `检索于 ${new Date(externalSource.retrieved_at).toLocaleString()}` : ""]
                .filter(Boolean).join(" · ")}
            </p>
            <blockquote>{externalSource.quote}</blockquote>
            <div className="dialog-actions">
              <a href={externalSource.url} target="_blank" rel="noreferrer">
                打开原始来源 <ExternalLink size={14} />
              </a>
              {externalSource.arxiv_id && (
                <button disabled={busy} onClick={() => void importExternal(externalSource)}>
                  下载 PDF 并加入论文库
                </button>
              )}
            </div>
          </>
        )}
      </dialog>
      <dialog ref={paperDialog}>
        <DialogTitle title="论文标识与标签" close={() => paperDialog.current?.close()} />
        {paper && (
          <>
            <label>标题<input value={paper.title} disabled /></label>
            <label>Citation key<input value={paper.citation_key} disabled /></label>
            <label>
              自定义标签
              <input value={paperTags} onChange={(e) => setPaperTags(e.target.value)} placeholder="用逗号分隔，例如 systems, 必读" />
            </label>
            <button className="primary" disabled={busy} onClick={() => void savePaperTags()}>
              保存标签
            </button>
          </>
        )}
      </dialog>
    </div>
  );
}
function ResizeHandle({
  className,
  label,
  value,
  hidden = false,
  onPointerDown,
  onKey,
}: {
  className: string;
  label: string;
  value: number;
  hidden?: boolean;
  onPointerDown: (event: React.PointerEvent<HTMLDivElement>) => void;
  onKey: (delta: number) => void;
}) {
  return (
    <div
      className={`resize-handle ${className}` + (hidden ? " hidden" : "")}
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      aria-valuenow={Math.round(value)}
      tabIndex={hidden ? -1 : 0}
      onPointerDown={onPointerDown}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
          e.preventDefault();
          onKey(e.key === "ArrowRight" ? 12 : -12);
        }
      }}
    />
  );
}
function HorizontalResizeHandle({
  value,
  onPointerDown,
  onKey,
}: {
  value: number;
  onPointerDown: (event: React.PointerEvent<HTMLDivElement>) => void;
  onKey: (delta: number) => void;
}) {
  return (
    <div
      className="row-resize-handle"
      role="separator"
      aria-label="调整问题输入区高度"
      aria-orientation="horizontal"
      aria-valuenow={Math.round(value)}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={(e) => {
        if (e.key === "ArrowUp" || e.key === "ArrowDown") {
          e.preventDefault();
          onKey(e.key === "ArrowDown" ? 12 : -12);
        }
      }}
    />
  );
}
function DialogTitle({ title, close }: { title: string; close: () => void }) {
  return (
    <div className="dialog-title">
      <h2>{title}</h2>
      <button className="icon" aria-label="关闭" onClick={close}>
        <X size={19} />
      </button>
    </div>
  );
}
function paperIdentity(paper: Paper) {
  const authors = Array.isArray(paper.source.authors) ? paper.source.authors : [];
  const first = authors.length ? String(authors[0]).trim().split(/\s+/).at(-1) : "Anon";
  const year = paper.source.year ? String(paper.source.year) : "n.d.";
  return `${first} · ${year} · ${paper.citation_key}`;
}
function Markdown({
  content,
  sources,
  allowedPages,
  onCite,
  externalSources = [],
  onExternal,
}: {
  content: string;
  sources: Context["sources"];
  allowedPages?: Set<number>;
  onCite: (n: number, anchor?: Anchor | null) => void;
  externalSources?: ExternalSource[];
  onExternal?: (source: ExternalSource) => void;
}) {
  const allowed = allowedPages || new Set(sources.map((source) => source.page));
  const linked = content
    .replace(/\[p\.(\d+)\s+¶(\d+)\]/g, (match) => {
      const index = sources.findIndex(
        (source) => `[${source.citation}]` === match,
      );
      return index >= 0 ? `${match}(#pdf-source-${index})` : match;
    })
    .replace(/\[p\.(\d+)\]/g, (match, n) =>
      allowed.has(Number(n)) ? `[p.${n}](#pdf-page-${n})` : match,
    )
    .replace(/\[E(\d+)\]/g, (match, n) =>
      externalSources[Number(n) - 1] ? `${match}(#external-source-${Number(n) - 1})` : match,
    );
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          img: ({ alt }) => (
            <span className="muted">[图像：{alt || "请回看原文"}]</span>
          ),
          a: ({ href, children }) =>
            href?.startsWith("#pdf-source-") ? (
              <button
                className="citation"
                onClick={() => {
                  const source = sources[Number(href.slice(12))];
                  if (source) onCite(source.page, source.anchor);
                }}
              >
                {children}
              </button>
            ) : href?.startsWith("#external-source-") ? (
              <button
                className="citation external-citation"
                onClick={() => {
                  const source = externalSources[Number(href.slice(17))];
                  if (source && onExternal) onExternal(source);
                }}
              >
                {children}
              </button>
            ) : href?.startsWith("#pdf-page-") ? (
              <button
                className="citation"
                onClick={() => onCite(Number(href.slice(10)))}
              >
                {children}
              </button>
            ) : (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            ),
        }}
      >
        {linked}
      </ReactMarkdown>
    </div>
  );
}
