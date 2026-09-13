# Local reader v0.2

## Design decisions

The primary interface is a local PDF reading UI. Codex skills are optional legacy entry points,
not the application runtime. Application code belongs in Git; actual PDFs, scheme, conversations,
notes, profiles and reading state belong in a user-selected workspace outside any Git repository.
No workspace is created implicitly on launch. The user will select a temporary directory before
file-based acceptance tests. No real-paper validation or paid API call is part of this implementation turn.

## Data model

- `papers`: an immutable document version identified by SHA256; original filename and import provenance.
  A different PDF hash is a separate record in this version. Identity-level version grouping is deferred.
- `paper_tags`: user-defined labels independent of the immutable title and derived citation key.
- `pages`: physical page number, CropBox dimensions, extracted text and normalized word boxes.
- `threads`: multiple named conversations per paper, ordered by activity.
- `messages`: user or assistant content, PDF anchor, context snapshot, model and completion status.
- `notes`: explicit user-confirmed text, optional source message and anchor. The notebook is global and can show
  one paper or every paper, while retaining paper provenance for source jumps. AI responses never insert notes.
- `runs`: workflow, provider, requested model, structured stage trace, actual returned model per step,
  usage and completion/error status. Draft + Editor keeps the Reader draft and Editor review in the trace;
  the linked assistant message contains only the edited final answer.
- `settings`: provider configuration and resume pointers, never API secrets.

Academic search is explicitly enabled per question and is independent of the LLM provider. Semantic Scholar
snippet results are normalized into bounded `[E1]` evidence records containing an exact excerpt, locator,
canonical link and provider. If its anonymous endpoint is rate-limited, OpenAlex abstracts provide the same
verifiable record shape and retain their provider/type provenance. The records are saved in the assistant message's
context snapshot. Sources without a fetched PDF never receive an invented page number. An arXiv-backed source can
be downloaded into the main SHA256-deduplicated library; Paper Lab then attempts an exact word-sequence match to
recover page boxes.

SQLite foreign keys and transactions protect relationships. `PRAGMA user_version` is the migration boundary;
unknown newer versions are rejected. Import writes a validated PDF before committing its database record;
a crash between these operations can leave an unreferenced PDF, but not a successful row for an unwritten file.
A process restart marks unfinished messages and runs interrupted. SQLite and PDFs move together as one directory;
stop the application before copying it. No automatic migration of previous council data occurs.

## PDF interaction

1. Upload or select an arXiv search result. Both paths validate and copy the PDF into `pdfs/`.
2. PDF.js renders one page and a selectable text layer. Fonts, CMaps and WASM are served locally.
3. Text selection records quote and per-line normalized rectangles. Rectangle selection records a region and
   nearby extracted text. Anchors use displayed CropBox coordinates and physical page numbers starting at one.
4. `Focused` ranks compact sentence-group excerpts by exact selection, current/neighboring pages, lexical matches and
   the first-page overview. It sends at most 24 excerpts, 24,000 source characters and 10,000 history characters.
   `Full paper` places all extractable source groups in a deterministic message before up to 80 history messages /
   120,000 history characters. The stable paper prefix is designed for provider prefix caching. The preview shows the
   exact source text before a paid call.
5. Region questions attach a bounded PNG rendered by Poppler; text questions send text. No OCR is silently
   substituted. Image-only pages require a vision-enabled provider and a region selection.
6. Answers use `[p.N ¶K]`; only supplied source groups become clickable citations. These are locators, not proof
   that a generated claim is true. Saved and generated anchors scroll to the group position within the page and
   restore its word-level highlight.
7. The user confirms/edits an answer to create a note. Reading position and selected topic can be resumed.
8. Overview, summary and other global tasks use `Full paper` with a user-written prompt. They are ordinary topic
   messages rather than fixed product actions, so the user can continue the same conversation or change its goal.
   The selected provider's context window and maximum output remain the hard limits.
9. The reader uses continuous vertical scrolling. Toolbar buttons and page-number input provide explicit page jumps;
   horizontal trackpad gestures do not turn pages.

The context builder is deterministic; it is not semantic retrieval and cannot guarantee finding every relevant
definition, especially for Chinese questions about English text. `Full paper` sends every extracted page; scanned
pages without text still require OCR or a future multimodal whole-document path.

## Model boundary and workflow

Default API ID: `deepseek-flash` (DeepSeek V4.1 Flash). Verified against DeepSeek's official release and API docs
on 2026-09-11. No deprecated aliases are stored. DeepSeek thinking is explicitly disabled by default to avoid
provider defaults expanding cost unexpectedly; users can enable low/high thinking. Answers are capped at 4096 output
tokens by default and are configurable from 256 to 16384.

- Specialist: one streaming Chat Completions call.
- Draft + Editor: at most two calls. Reader creates a private draft; Editor checks it against the same supplied
  excerpts/image and returns the complete corrected answer. The draft and review remain in a structured, collapsed
  trace. A truncated or failed Reader does not start Editor, and no paid request is retried automatically.
- Full council: retained in legacy skills, not run automatically or exposed as a nonfunctional UI option.

Provider adapters normalize stream deltas, completion reasons and usage. No billable request is automatically
retried. Missing usage is unknown, never zero. Token caps bound output but are not exact currency budgets.
Different provider tokenization, cached input and image accounting remain provider-specific. Cancellation closes
the upstream stream; already generated tokens may still be charged and the final usage chunk may not arrive.

## Local service and credentials

FastAPI binds loopback by default. The API validates Host and uses a per-process mutation token to prevent
cross-site requests. Only user-selected HTTPS provider endpoints receive credentials. DeepSeek uses its official
endpoint; changing providers/addresses clears the existing in-memory key. Keys are not returned by status,
written to SQLite, stored in browser localStorage or included in diagnostic responses. The browser remembers
only the chosen directory path. This is a single-user local service, not a multi-user hosted server.

Paper search is explicitly user-triggered and currently limited to arXiv. Download endpoints are derived from
validated arXiv identifiers; arbitrary remote PDF URL fetching is not exposed. User/model Markdown cannot
execute HTML or load remote embedded images. Paper text is untrusted source content, not agent instructions.

## Verification and pending acceptance

Completed without a workspace directory or paid API:

- TypeScript and production bundle build.
- In-memory SQLite and ASGI tests: context limits, source-bound anchors, topic isolation, manual notes,
  provider/key boundaries, source preview without inference, bounded two-step execution, partial failure,
  truncation, SSE parsing and token usage.
- Browser inspection of the unconfigured workspace and settings. The read-only WebMCP state tool is available.

Await a user-selected temporary directory before testing:

- Import/deduplicate a synthetic and a real PDF, including scanned and rotated/CropBox examples.
- Check text selection, rectangle crop alignment, zoom, citations, local assets and formula rendering in the browser.
- Download a user-selected arXiv paper, then restart/move the workspace and verify the complete reading state.
- Supply a key through the settings UI and validate actual DeepSeek text/image streaming, cancellation and usage.

The source code implements these paths; the pending items have not yet been declared end-to-end accepted.

## Sources

- https://www.deepseek.com/en/news/deepseek-v4-1-flash/
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://mozilla.github.io/pdf.js/
