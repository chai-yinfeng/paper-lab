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
    [runs, setRuns] = useState<Run[]>([]),
    [tab, setTab] = useState<"chat" | "notes">("chat"),
    [question, setQuestion] = useState(""),
    [workflow, setWorkflow] = useState("specialist"),
    [generating, setGenerating] = useState(false),
    [phase, setPhase] = useState(""),
    [context, setContext] = useState<Context | null>(null),
    [busy, setBusy] = useState(false),
    [collapsed, setCollapsed] = useState(false);
  const settings = useRef<HTMLDialogElement>(null),
    importDialog = useRef<HTMLDialogElement>(null),
    noteDialog = useRef<HTMLDialogElement>(null),
    topicDialog = useRef<HTMLDialogElement>(null),
    contextDialog = useRef<HTMLDialogElement>(null),
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
    const ps = await api<Paper[]>("/papers");
    setPapers(ps);
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
    setNotes([]);
    setRuns([]);
    const [ts, ns] = await Promise.all([
      api<Thread[]>(`/papers/${p.id}/threads`),
      api<Note[]>(`/papers/${p.id}/notes`),
    ]);
    if (id !== epoch.current) return;
    setNotes(ns);
    setThreads(ts);
    if (ts.length) {
      const selected = ts.find((t) => t.id === preferredThread) || ts[0];
      await loadThread(selected);
      await api("/session", "PUT", { paper_id: p.id, thread_id: selected.id });
    } else await api("/session", "PUT", { paper_id: p.id });
  }
  function changePage(n: number) {
    if (!paper) return;
    setPage(n);
    setAnchor(null);
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
  async function ensureThread() {
    if (thread) return thread;
    if (!paper) throw new Error("请先打开论文。");
    const t = await api<Thread>(`/papers/${paper.id}/threads`, "POST", {
      title: question.trim().slice(0, 35) || "阅读讨论",
    });
    setThreads((old) => [t, ...old]);
    setThread(t);
    await api("/session", "PUT", { paper_id: paper.id, thread_id: t.id });
    return t;
  }
  async function configureDirectory() {
    setBusy(true);
    try {
      const s = await api<Status>("/workspace", "POST", { path: directory });
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
  async function newTopic() {
    if (!paper) return;
    setBusy(true);
    try {
      const t = await api<Thread>(`/papers/${paper.id}/threads`, "POST", {
        title: topicTitle,
      });
      setThreads((old) => [t, ...old]);
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
  async function previewContext() {
    setBusy(true);
    try {
      const t = await ensureThread();
      setContext(
        await api(`/threads/${t.id}/context`, "POST", {
          question: question.trim() || "解释当前页面",
          anchor: currentAnchor(),
        }),
      );
      contextDialog.current?.showModal();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function send() {
    if (!question.trim() || generating || !paper) return;
    setGenerating(true);
    setError("");
    setPhase("准备原文");
    const controller = new AbortController();
    abort.current = controller;
    let t: Thread | null = null;
    let sent = false;
    try {
      t = await ensureThread();
      const text = question.trim(),
        a = currentAnchor();
      const response = await request(`/threads/${t.id}/messages`, {
        method: "POST",
        body: JSON.stringify({ question: text, anchor: a, workflow }),
        signal: controller.signal,
      });
      sent = true;
      setQuestion("");
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
              event.phase === "checker"
                ? "Checker 正在核查"
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
    if (!paper || !noteSource) return;
    setBusy(true);
    try {
      if (editingNote)
        await api(`/notes/${noteSource.id}`, "PUT", { content: noteText });
      else
        await api(`/papers/${paper.id}/notes`, "POST", {
          content: noteText,
          message_id: noteSource.id,
          anchor: noteSource.anchor,
        });
      setNotes(await api(`/papers/${paper.id}/notes`));
      noteDialog.current?.close();
      setError("");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  const allowedPages = (m: Message) =>
    new Set(m.context?.sources.map((s) => s.page) || []);
  const dialogError = error && (
    <div role="alert" className="inline-error">
      {error}
    </div>
  );
  return (
    <div className={"app" + (collapsed ? " library-collapsed" : "")}>
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
                  <small>{p.page_count} 页 · 本地 PDF</small>
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
      <aside className="discussion">
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
                    setTopicTitle("");
                    topicDialog.current?.showModal();
                  }}
                >
                  <Plus size={17} />
                </button>
              </div>
            )}
            <div className="messages">
              {messages.length ? (
                messages.map((m) => (
                  <article key={m.id} className={"message " + m.role}>
                    <div className="message-label">
                      {m.role === "user" ? "你" : m.model || "Specialist"}
                      {m.anchor && (
                        <button
                          className="citation"
                          onClick={() => cite(m.anchor!.page, m.anchor)}
                        >
                          p.{m.anchor.page}
                          {m.anchor.kind === "region" ? " · 图表" : ""}
                        </button>
                      )}
                    </div>
                    {m.role === "user" ? (
                      <p className="user-text">{m.content}</p>
                    ) : (
                      <Markdown
                        content={m.content}
                        allowed={allowedPages(m)}
                        onCite={cite}
                      />
                    )}{" "}
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
                ))
              ) : (
                <div className="conversation-empty">
                  <span className="eyebrow">SPECIALIST</span>
                  <h2>带着问题阅读</h2>
                  <p>
                    选中一段文字或框选图表，
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
                <button
                  className="citation"
                  onClick={() => cite(anchor.page, anchor)}
                >
                  p.{anchor.page} ·{" "}
                  {anchor.kind === "region" ? "图表选区" : "文字选区"}
                </button>
                <p>{anchor.quote || "将发送此区域图像及同篇相关文字"}</p>
                <button
                  className="icon"
                  aria-label="清除选区"
                  onClick={() => setAnchor(null)}
                >
                  <X size={15} />
                </button>
              </div>
            )}
            <div className="composer">
              <textarea
                aria-label="向论文助手提问"
                placeholder={
                  paper
                    ? "问一个问题，或解释选中的内容…"
                    : "打开论文后，围绕原文提问…"
                }
                disabled={!paper || generating}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
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
                  <option value="specialist">Specialist · 1 次调用</option>
                  <option value="reader-checker">
                    Reader + Checker · 最多 2 次
                  </option>
                </select>
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
                    <ArrowUp size={18} />
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
            </div>
            {status?.configured && !status.key_configured ? (
              <button
                className="key-reminder"
                onClick={() => settings.current?.showModal()}
              >
                配置 API key 后开始对话
              </button>
            ) : (
              <p className="footnote">对话自动保存 · 笔记由你确认</p>
            )}
          </>
        ) : (
          <div className="notes-panel">
            <div className="notes-heading">
              <span>已确认的理解</span>
              {paper && notes.length > 0 && (
                <a href={`/api/papers/${paper.id}/notes/export`} download>
                  导出 Markdown
                </a>
              )}
            </div>
            {notes.length ? (
              notes.map((n) => (
                <article className="note" key={n.id}>
                  {n.anchor && (
                    <button
                      className="citation"
                      onClick={() => cite(n.anchor!.page, n.anchor)}
                    >
                      返回 p.{n.anchor.page}
                    </button>
                  )}
                  <Markdown
                    content={n.content}
                    allowed={
                      new Set(
                        Array.from(
                          { length: paper?.page_count || 0 },
                          (_, i) => i + 1,
                        ),
                      )
                    }
                    onCite={cite}
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
          <input
            value={directory}
            disabled={status?.configured || busy}
            placeholder="/absolute/path/my-paper-library"
            onChange={(e) => setDirectory(e.target.value)}
          />
        </label>
        {status?.configured ? (
          <p className="muted small">
            目录已打开。切换目录请重启服务后重新选择。
          </p>
        ) : (
          <button
            className="primary"
            disabled={!directory || busy}
            onClick={() => void configureDirectory()}
          >
            {busy ? "正在打开…" : "打开工作目录"}
          </button>
        )}
        <p className="small muted">
          PDF 统一放在
          pdfs/；对话、笔记和进度保存在同一工作目录。选择空目录或已有 Paper Lab
          目录。
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
            每次输出上限
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
              status?.key_configured ? "已配置，留空保持" : "稍后配置也可以"
            }
            onChange={(e) => setKey(e.target.value)}
          />
        </label>
        <p className="small muted">
          key 仅保留在当前服务进程中，不写入工作目录或浏览器存储。API
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
          title="新讨论主题"
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
              开始讨论
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
            <p className="small muted">
              {context.scope} · {context.characters.toLocaleString()} 字符 ·
              最近 {context.history_messages} 条历史消息
              {context.image_attached ? " · 含选区图像" : ""}
            </p>
            {context.sources.map((s) => (
              <details key={s.page}>
                <summary>
                  {s.reason} · p.{s.page}
                  {s.truncated ? " · 节选" : ""}
                  <ChevronDown size={14} />
                </summary>
                <pre>{s.text || "本页未提取到文字。图表请使用框选。"}</pre>
              </details>
            ))}
          </>
        )}
      </dialog>
    </div>
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
function Markdown({
  content,
  allowed,
  onCite,
}: {
  content: string;
  allowed: Set<number>;
  onCite: (n: number) => void;
}) {
  const linked = content.replace(/\[p\.(\d+)\]/g, (match, n) =>
    allowed.has(Number(n)) ? `[p.${n}](#pdf-page-${n})` : match,
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
            href?.startsWith("#pdf-page-") ? (
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
