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
- `pages`: physical page number, CropBox dimensions, extracted text and normalized word boxes.
- `threads`: multiple named conversations per paper, ordered by activity.
- `messages`: user or assistant content, PDF anchor, context snapshot, model and completion status.
- `notes`: explicit user-confirmed text, optional source message and anchor. The notebook is global and can show
  one paper or every paper, while retaining paper provenance for source jumps. AI responses never insert notes.
- `runs`: workflow, provider, requested model, actual returned model per step, usage and completion/error status.
- `settings`: provider configuration and resume pointers, never API secrets.

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
4. A question ranks paragraph-sized excerpts by exact selection, current/neighboring pages, lexical matches and
   the first-page overview. It sends at most 10 excerpts, 24,000 source characters and 10,000 history characters.
   The preview states why every excerpt was selected and shows the exact text before a paid call.
5. Region questions attach a bounded PNG rendered by Poppler; text questions send text. No OCR is silently
   substituted. Image-only pages require a vision-enabled provider and a region selection.
6. Answers use `[p.N]`; only supplied source pages become clickable citations. These are locators, not proof
   that a generated claim is true. Saved user anchors restore highlights; generated page citations return to a page.
7. The user confirms/edits an answer to create a note. Reading position and selected topic can be resumed.
8. Reading-before and reading-after summaries each use one Specialist call. Up to 80,000 extracted characters
   are distributed across every physical page; long pages retain their beginning and end and disclose sampling.
   Paper claims require page citations. Unsearched model knowledge is explicitly labeled external background.
9. The reader supports normal scrolling within a page, wheel/trackpad page turns at vertical edges, horizontal
   swipes, touch swipes and PageUp/PageDown or left/right keys.

The context builder is deterministic; it is not semantic retrieval and cannot guarantee finding every relevant
definition, especially for Chinese questions about English text. Full-paper summaries are complete only when all
extracted text fits the stated budget; otherwise they are page-balanced summaries with disclosed sampling.

## Model boundary and workflow

Default API ID: `deepseek-flash` (DeepSeek V4.1 Flash). Verified against DeepSeek's official release and API docs
on 2026-09-11. No deprecated aliases are stored. DeepSeek thinking is explicitly disabled by default to avoid
provider defaults expanding cost unexpectedly; users can enable low/high thinking. Output is capped at 4096
per call by default and is configurable from 256 to 16384.

- Specialist: one streaming Chat Completions call.
- Reader + Checker: at most two calls. The second checks a bounded draft against the same supplied original
  excerpts/image, without a moderator or automatic revision loop. A truncated/failed reader does not start a checker.
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
