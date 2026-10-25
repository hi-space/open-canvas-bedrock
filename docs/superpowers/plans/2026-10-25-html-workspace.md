# HTML Workspace Implementation Plan

> **For agentic workers:** Use superpowers:test-driven-development and
> superpowers:dispatching-parallel-agents for the independent backend and
> preview tasks. Steps use checkboxes for tracking.

**Goal:** Complete the approved static HTML generation and region editing flow.

**Architecture:** Preserve the existing file/version/proposal system. Add a
validated HTML format and atomic element replacement on the backend, an
isolated HTML preview with source-location mapping, and workspace UI wiring.

**Tech Stack:** Existing Next.js/React/CodeMirror and FastAPI/Python stack;
parse5 for HTML source locations and DOMPurify for browser sanitization.

**Spec:** `docs/superpowers/specs/2026-10-25-html-workspace-design.md`

## Global Constraints

- Keep Markdown behavior and the existing source/version/approval guarantees.
- HTML/CSS only; generated JavaScript and external preview requests are denied.
- Preserve source formatting and stable `data-oc-id` values.
- HTML changes are atomic, including associated styles and source references.
- Use the existing Korean workspace copy and visual design.

## Review Focus

- Identical text and emoji in different regions must select the correct source.
- An edit made while saving or generating must not be silently overwritten.
- Tag changes and style changes must not be partially applied.
- Malicious HTML, CSS requests, and forged iframe messages must not escape.
- Newly generated HTML must be inspectable before approval and downloadable.

## Task 1: Backend HTML files, generation, and atomic proposals

**Files:** Create `apps/backend/api/workspaces/html_documents.py`; modify
workspace files/models/service/proposals, workspace-agent models/tools/prompts;
add `apps/backend/tests/test_workspace_html.py`. Include the helper in
`deploy/Dockerfile.agent`, verified by `test_workspace_agent_image.py`.

**Interfaces:** `is_html_path(path)`, `prepare_html(content)`,
`html_selection(content, node_id)` returning exact Python offsets/source;
optional `Selection.nodeId`; optional chat/agent `outputFormat: "html"`.
Normalize IDs at save/proposal creation, preserve selection boundaries, and
return one review change for HTML. `data-source-ids` is a JSON string array.

- [x] Write failing tests for file roundtrips, stable IDs, exact node selection,
  script/malformed input, citations, atomic decisions, and output-format routing.
- [x] Run the focused test file and inspect expected failures.
- [x] Implement the format and propagate the additive contract through API/agent.
- [x] Run focused and existing backend tests.

## Task 2: HTML preview primitives and component

**Files:** Create `apps/web/src/lib/workspace/html.ts`, `html.test.ts`,
`apps/web/src/components/workspace/HtmlPreview.tsx`, `html.module.css`;
extend `TextSelection` in workspace types.

**Interfaces:** `htmlRegions(content): HtmlRegion[]`,
`createHtmlPreview(content, token, interactive): string`,
`selectionForHtmlMessage(data, token, content): TextSelection | undefined`.
`HtmlRegion` has `nodeId`, `from`, `to`, `text`, `label`, `previewText`,
`sourceIds`, and optional parent node ID. `HtmlPreview` takes `content`,
optional `onSelection`, `selection`, `title`, and `compact`.

- [x] Write failing tests for duplicate text, UTF-16 ranges, data metadata,
  removed active content, CSP, forged messages, and preview-only instrumentation.
- [x] Run the focused tests and inspect expected failures.
- [x] Implement parser mapping, sanitization, trusted bridge, and accessible picker.
- [x] Run focused tests and type checking.

## Task 3: Connect the workspace, source editor, and rendered review

**Files:** Modify workspace cloud types/state, file helpers, CloudWorkspace,
CloudInspector, MarkdownEditor, ReviewPanel, SourcesPanel, and related tests.

**Interfaces:** Consume tasks 1/2. Preserve `nodeId` in chat payloads. Add a
generation choice that sends `outputFormat: "html"`, independent of research.

- [x] Add failing controller/file tests for HTML import/download and generation.
- [x] Implement views, correct MIME download, source editing, generation controls,
  region tools, source lookup, and before/after previews.
- [x] Verify source-normalizing saves preserve concurrent edits and refresh
  selection mappings only against the returned canonical file.
- [x] Run web tests, typecheck, lint, and production build.

## Task 4: Integration, browser verification, and documentation

- [x] Exercise the API with deterministic agent responses and the real browser:
  generate HTML, review before saving, approve, select, revise, approve, download.
- [x] Verify iframe isolation, keyboard selection, narrow layouts, and Markdown.
- [x] Update `docs/cloud-workspace.md` with supported HTML workflow and limits.
- [x] Review the complete change independently; resolve material findings.
- [x] Report checks, usage, and any remaining environmental limitations.

## Verification — 2026-10-25

- Web: `yarn test` — 158 tests passed; `yarn typecheck` and `yarn lint` passed
  (17 existing lint warnings elsewhere).
- Backend: `.venv/bin/python -m pytest -q --tb=short` — 266 tests and 75
  subtests passed (two existing datetime deprecation warnings). This run
  includes concurrent work present in the shared checkout.
- `yarn build` completed successfully.
- Agent image source imports pass from an isolated COPY staging directory,
  under both the project virtual environment and system Python with installed
  dependency paths. A container image build was not performed.
- Chromium: generation with fixed model responses, unsaved proposal preview,
  atomic approval, duplicate-text element selection, selected-only revision,
  exact HTML download, keyboard/parent selection, 375px and landscape layouts,
  and Markdown editing/selection were exercised.
- Browser probes produced zero outbound resource requests, no generated script
  execution, no nested iframe/refresh element, and a `SecurityError` when
  attempting parent DOM access. Live model calls and other browser engines
  were not exercised.
- Independent review findings were fixed: inline/linked-card citation insertion,
  source-ID retention, normalized folder-sync baselines, parser repair
  ambiguities, and runtime image packaging.
