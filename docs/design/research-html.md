# Research-backed HTML documents

## Accepted scope

The user approved the first release proposed in the conversation: selected project
material plus deep research produces a new HTML document with citations, tables,
and diagrams, with preview, explicit approval, and a standalone HTML download.
Reuse of a completed investigation, independent figure regeneration, additional
chart engines, and durable graph execution remain later releases.

## Behavior

- Keep normal chat, ordinary HTML generation, and Markdown research working.
- Let people choose a research genre and HTML output together. Selecting a text
  region still means editing that region, and cannot be combined with creating a
  research document or HTML page.
- In the composer, keep the existing genre choices and add a separate output
  format choice. For research, show the project files used and let people choose
  up to five. Initially include the open file. Registered source excerpts are
  included automatically.
- The server reads selected files within the authorized project and snapshots
  their current contents when accepting the job. Reuse the current save/version
  checks for the active file.
- Supply bounded project context to planning, outlining, writing, reviewing, and
  diagram generation. Treat it as untrusted material, not instructions. Preserve
  project filenames as provenance; never invent public URLs for private files.
- Supply existing reference excerpts to evidence extraction as real sources, so
  they can receive ordinary citations alongside newly searched sources.
- Research produces a new `research/<title>.md` or `.html` proposal. Existing
  files are not overwritten. Approval remains the only canonical write path.
- Convert the completed, citation-assembled Markdown into static HTML with the
  existing markdown-it dependency: no additional model call to rewrite facts.
  Support tables, lists, code, citations, figures, and a responsive reading layout.
  Render authored raw HTML as text. Include source provenance and stable editor IDs.
- Reuse the existing concept/AWS diagram renderers. A run can have zero figures
  when none are relevant or a renderer is unavailable; never invent a missing
  image. Surface actual rendered counts in the existing job reply.
- Preserve source URLs in generated HTML. Render figures as existing authenticated
  `/api/research/assets/<run>/<name>.png` references in canonical documents.
- Resolve only those exact managed image paths outside the sandbox, using the
  current user's same-origin session. Validate PNG content and bound downloads.
  Inject data images into the ephemeral preview; do not mutate the source or
  change its selection offsets.
- Download HTML with managed images embedded and ordinary citations preserved.
  If a required image cannot be loaded, explain the problem instead of silently
  downloading a broken report. Markdown download is unchanged.
- Missing preview images must not hide readable text; show a retryable notice.
  Stale asynchronous image work cannot replace a newer document or selection.

## Implementation choices

These are builder choices, not additional user requirements.

- Extend `ChatRequest` with optional `contextPaths`; omit to default to the active
  file, provide `[]` for a web-only request. Maximum five project files.
- Keep the `researchGenre` and `outputFormat` fields for compatibility; relax
  only their mutual exclusion. Do not send research-only fields to AgentCore.
- A context document carries `path`, `version`, bounded `content`, and `truncated`.
  Allow up to 30,000 total context characters and 12,000 per document. Show when
  material is shortened. File content never becomes a trusted user message.
- Seed usable registered sources into the graph source registry with stable
  graph-local S IDs. Deduplicate by normalized URL and retain supplied excerpts
  rather than replacing them with a search snippet.
- Private project material is separately labeled context, with an appended
  provenance list (filename and snapshot version). Web reference IDs and links
  keep their existing validation contract.
- HTML rendering is an adapter at the workspace boundary; the legacy canvas
  graph continues returning Markdown artifacts.
- Follow the application's restrained editorial style. Use a static inline
  stylesheet, local font fallbacks, scrollable wide tables/code, and print rules.
- PNG downloads: at most 12 distinct assets, at most 2 MiB per image, 8 MiB total,
  15-second timeout including native browser decoding. Check dimensions before
  decoding (at most 64 × 1024 × 1024 pixels). Do not cache private asset contents
  globally. Shared resolution within one document prevents duplicate downloads.
- Supplied source aliases share combined evidence and all contributing source IDs.
  Newly registered citations have a separate budget from existing supplied sources.
- Keep project documentation and verification artifacts under `docs/`. Releases
  follow the existing GitHub Actions workflow on `main`.

## Verification

Offline tests replace only Bedrock, web search, and image retrieval boundaries.
Cover combined-mode routing, project isolation, content snapshots, source reuse,
HTML tables/citations/provenance, review before writes, image validation, stale
previews, standalone downloads, and selection identity. Run the full existing
backend/frontend suites plus typecheck/lint. A real Chromium workflow against a
local deterministic backend must generate, preview, approve, and download a
report; open the downloaded HTML without the application and verify its figure.
