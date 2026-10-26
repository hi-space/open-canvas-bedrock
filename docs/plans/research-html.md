# Research-backed HTML Implementation Plan


**Goal:** Create research-backed HTML with project context, citations, tables, diagrams, review, and standalone export.

**Architecture:** Reuse the research graph and common proposal lifecycle. Snapshot selected project inputs, seed supplied sources, render completed research through a static HTML adapter, and resolve managed diagram images only for preview/export.

**Tech Stack:** Python/FastAPI/LangGraph/markdown-it-py; Next.js/React/TypeScript/parse5/DOMPurify; pytest/Vitest/Playwright.

**Spec:** `docs/design/research-html.md`

## Global Constraints

- Maximum five project context files, 30,000 total characters, 12,000 per file.
- Preserve ordinary chat, Markdown research, HTML selection edits, source URLs, and explicit approval.
- No additional model call for Markdown-to-HTML conversion; no new dependencies.
- Canonical documents retain authenticated image paths; previews and exports embed PNG data.
- Bound image loads to 12 distinct assets, 2 MiB each, 8 MiB total, 15 seconds.
- Keep documentation under `docs/`; release through the existing main-branch workflow.

## Review Focus

- A document selected before submission changes while research is running: use its accepted snapshot and preserve the newer original.
- Registered source excerpts coexist with web hits at the same URL: retain supplied evidence and do not create duplicate source identities.
- A second HTML document replaces one whose images are still loading: do not render stale content or lose canonical selection offsets.
- Missing, oversized, redirected, or non-PNG managed images: readable preview plus notice, export failure without silent broken output.
- Markdown tables, raw HTML, repeated citations, code URLs, and private filenames: preserve meaningful content and citation validation without executing markup.

---

### Task 1: Research inputs and source reuse

**Files:**
- Create `apps/backend/api/workspaces/research_context.py`
- Modify `apps/backend/api/workspaces/{models,service,research}.py`
- Modify `apps/backend/agents/deep_research/{state,nodes,prompts}.py`
- Test `apps/backend/tests/test_workspace_research.py`, `test_deep_research.py`

**Interfaces:**
- Request: `contextPaths: list[str] | None`; research-only, no region selection.
- Produces `payload["projectContext"]`: list of `{path, version, content, truncated}`.
- Graph inputs: `projectContext: list[dict]`, `suppliedSources: list[dict]`.
- Context helpers: `context_excerpt(content: str, limit: int) -> str`,
  `snapshot_context(files, paths: list[str]) -> list[dict]`.
- Seed graph sources retain URLs, excerpts, and question associations.

- [x] Write tests proving selected files reach research, wrong project/path is rejected, supplied references can be cited, and the accepted snapshot survives later edits.
- [x] Run `.venv/bin/python -m pytest -q tests/test_workspace_research.py tests/test_deep_research.py`; verify missing context behavior fails.
- [x] Implement bounded snapshots and graph context across stages, including supplied source extraction.
- [x] Re-run those tests; expect all pass.
- [x] Record results and commit this tested input change.

### Task 2: Static HTML research proposals

**Files:**
- Create `apps/backend/api/workspaces/research_html.py`
- Modify `apps/backend/api/workspaces/{models,research}.py`
- Test `apps/backend/tests/test_research_html.py`, `test_workspace_research.py`, `test_workspace_html.py`

**Interfaces:**
- `render_research_html(markdown: str, title: str, *, sources: list[dict], genre: str, language: str = "ko") -> str`
- `document_path(title: str, existing: set[str], output_format: str | None = None) -> str`
- Reuses Task 1's `projectContext` for provenance in both output formats.
- Returns common new-file proposal with `.html` path and valid static HTML.

- [x] Write tests for combined HTML/research requests, review before writes, unique `.html` paths, tables, images, repeated citation anchors, private provenance, and escaped raw HTML.
- [x] Run `.venv/bin/python -m pytest -q tests/test_research_html.py tests/test_workspace_research.py tests/test_workspace_html.py`; verify unsupported-mode/renderer failures.
- [x] Implement deterministic rendering, document provenance, and output adaptation. Preserve selection exclusivity.
- [x] Re-run targeted tests; expect all pass.
- [x] Record results and commit the HTML proposal path.

### Task 3: Managed images in preview and export

**Files:**
- Create `apps/web/src/lib/workspace/html-assets.ts` and `.test.ts`
- Modify `apps/web/src/components/workspace/HtmlPreview.tsx` and `.test.tsx`
- Modify `apps/web/src/components/workspace/CloudWorkspace.tsx`

**Interfaces:**
- `resolveHtmlResearchImages(content: string, signal?: AbortSignal): Promise<{content: string; missing: string[]}>`
- `standaloneHtml(content: string, signal?: AbortSignal): Promise<string>`
- Injected image content is ephemeral and never sent as canonical editor content.

- [x] Write tests for same-origin managed PNGs, duplicate references, preserved links/source IDs, redirects/errors/MIME/size limits, export failure, and stale preview responses.
- [x] Run `yarn test src/lib/workspace/html-assets.test.ts src/components/workspace/HtmlPreview.test.tsx`; verify unresolved-image behavior fails.
- [x] Implement bounded authenticated image loading, preview warnings/retry and stale response cancellation, async download with errors.
- [x] Run targeted tests; expect all pass.
- [x] Record results and commit image delivery.

### Task 4: Composer controls and selected project material

**Files:**
- Modify `apps/web/src/lib/workspace/{cloud-types,cloud-state}.ts`
- Modify `apps/web/src/components/workspace/{CloudInspector,cloud.module.css}`
- Create `apps/web/src/components/workspace/ResearchOptions.tsx` and `.test.tsx`
- Test `apps/web/src/lib/workspace/cloud-state.test.ts`

**Interfaces:**
- `CloudChatRequest.contextPaths?: string[]`
- `controller.send()` passes format/genre/context paths; rejects creation with selection.
- Separate output control; research material checkboxes default to active file and cap at five.
- Quick edits never inherit creation options.

- [x] Write tests for combined payloads, empty selection, five-file limits, project changes, and ordinary edit behavior.
- [x] Run relevant Vitest tests; verify current mutually exclusive behavior fails.
- [x] Implement accessible controls using existing styles and update request state.
- [x] Run relevant tests plus `yarn typecheck` and `yarn lint`; expect pass.
- [x] Record results and commit composer changes.

### Task 5: Integration, documentation, and final review

**Files:**
- Create `apps/web/tests/research_html_backend.py`
- Create `apps/web/tests/research_html_smoke.py`
- Update `docs/cloud-workspace.md`

**Interfaces:**
- Local deterministic fixture uses real API/proposals/rendering and produces a real PNG.
- Chromium checks selected inputs, generated HTML preview, approval, offline download, and mobile layout.

- [x] Implement the fixture and browser workflow against local-only servers, with external model/search calls replaced.
- [x] Run the workflow, inspect desktop/mobile screenshots and offline image rendering; fix failures.
- [x] Run backend `pytest -q`, frontend `yarn test`, `yarn typecheck`, `yarn lint`, and production build.
- [x] Update the guide with the shipped controls and download behavior.
- [x] Dispatch one fresh reviewer for the full feature; reproduce and fix material findings with tests.
- [x] Record final verification, finish on the feature branch, and report the concrete result.

## Verification record

- Backend: `python -m pytest -q` — 350 passed, 101 subtests; two existing legacy
  `datetime.utcnow()` deprecation warnings.
- Frontend: `yarn test` — 215 passed across 25 files.
- `yarn typecheck`, `yarn lint`, and production `yarn build` passed. Lint retains
  existing warnings in legacy components; changed components have no new warnings.
- The standalone production server was exercised with the real research graph,
  workspace API/storage, PNG renderer fixture, and Chromium. External model and
  web-search boundaries used deterministic fixtures.
- Chromium verified selected material, proposal before writes, PNG preview,
  explicit approval, corrupt-PNG notice/export rejection/retry, offline HTML
  images and citations, and a 390-pixel mobile document layout.
- The mobile application composer was checked separately at 390 × 844.
- Independent review found three material issues: new citation registration slots,
  duplicate supplied-URL evidence/provenance, and incomplete PNG validation.
  Each was reproduced with failing tests and fixed in one pass; the final suites
  and browser workflow passed after the fixes. No minor findings were deferred.
- `core/research_sources.py` now shares evidence grouping between the graph and
  HTML adapter; source registration budgets and browser decoding validation
  preserve the accepted input and output contracts.
- Research-result reuse, durable checkpoints, additional diagram engines, and
  deployment remain outside this first release, as specified in the design.
