# Native HTML Diagrams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Explain technical structures in HTML using native HTML/CSS and SVG with optional specialized diagram skills.

**Architecture:** Add a semantic native renderer and select it by output format and explicit outline intent. Support a narrow static SVG subset across server validation and browser preview, treating an SVG subtree as one editing region. Resolve trusted native figures in the HTML adapter.

**Tech Stack:** Python/Pydantic/LangGraph, Next.js/React/parse5/DOMPurify, pytest/Vitest/Chromium.

**Spec:** `docs/superpowers/specs/2026-10-25-native-html-diagrams-design.md`

## Global Constraints

- HTML defaults to native rendering without installed skills, Chrome, or PNG assets.
- Keep existing Markdown research and explicitly selected skill renderers working.
- SVG is atomic for selection; preserve exact surrounding source.
- Keep sandboxing, citations, and explicit approval; no active SVG/resource references.
- Do not silently drop graph relationships; escape labels and validate endpoints.
- No new dependencies or deployment.

## Review Focus

- SVG namespace and HTML integration points must not introduce active HTML or stale source ranges.
- Self-closing SVG geometry and emoji before the SVG must retain exact selection offsets.
- Missing skills, failed specialized rendering, and no asset owner must not disable native HTML figures.
- Captions and source links must survive native insertion without leaking placeholder URIs.
- Non-adjacent/reverse edges, duplicate IDs, and long labels must remain technically interpretable.

---

### Task 1: Static SVG validation and atomic preview

**Files:** backend `api/workspaces/html_documents.py`, new `api/workspaces/svg.py`;
frontend `lib/workspace/html.ts`, new `lib/workspace/svg.ts`;
tests `test_workspace_svg.py`, `html.test.ts`; workspace agent prompt.

**Interfaces:** SVG tag/attribute constants and validation helpers; `prepare_html`,
`html_selection`, `htmlRegions`, and `createHtmlPreview` keep existing signatures.

- [x] Write tests for valid geometry/text, atomic selection/replacement, dangerous
  SVG, foreign integration points, and sanitized SVG namespace/attributes.
- [x] Run focused pytest/Vitest and observe missing SVG support fail.
- [x] Add the static subset with atomic SVG roots and update the HTML agent prompt.
- [x] Run targeted tests and typecheck; expect pass, retaining old malicious cases.

### Task 2: Semantic native diagram renderer

**Files:** new `agents/deep_research/diagrams/native.py`, `test_native_diagrams.py`.

**Interfaces:** `NativeDiagramSpec`; `render_native(spec) -> str`;
`create_native(model, request, evidence, language) -> dict` returning markup and summary.

- [x] Test HTML layers, SVG flows/sequences, label escaping, endpoint/ID validation,
  and that every relationship is represented.
- [x] Run tests to observe the missing renderer fail.
- [x] Implement bounded model output and deterministic geometry with readable labels,
  responsibilities, direction, and an accessible relationship description.
- [x] Run tests and validate generated markup with the real HTML validator.

### Task 3: Research routing and HTML figure assembly

**Files:** deep research `state.py`, `schemas.py`, `prompts.py`, `nodes.py`,
`assemble.py`; workspace `research.py`, `research_html.py`; related tests.

**Interfaces:** figure `renderer`, `reason`, native `markup`/`summary` fields;
`render_research_html(..., figures: list[dict] | None = None)`.

- [x] Test skill-free HTML planning/rendering, explicit skill selection/fallback,
  unchanged Markdown behavior, native placement, captions and source citations.
- [x] Run focused tests; verify current skill dependency/PNG-only assembly fails.
- [x] Add output-aware capabilities and native fallback. Resolve trusted native
  placeholders after Markdown parsing and preserve the common proposal contract.
- [x] Run backend suite and frontend tests.

### Task 4: Browser verification, docs and review

**Files:** browser fixture and smoke tests; cloud workspace guide.

- [x] Exercise real graph/API and HTML preview in Chromium with skills disabled,
  then approve and download a native SVG report with no image fetches.
- [x] Inspect desktop/mobile diagrams and verify atomic selection; retain the
  existing explicit-skill PNG/offline/corrupt-image regression workflow.
- [x] Run full suites, typecheck, lint, and production build.
- [ ] Dispatch one fresh code reviewer and fix material findings with regressions.
- [ ] Record results, commit the reviewed change, and preserve the worktree.
