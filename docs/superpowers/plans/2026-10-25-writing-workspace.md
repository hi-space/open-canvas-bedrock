# Writing Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver a file-based writing workspace with approval-based AI revisions and linked references, on current stable dependencies and Bedrock models.

**Architecture:** A browser-owned Markdown workspace persists files, drafts, history, and proposals in IndexedDB. A stateless FastAPI proposal endpoint reuses the Bedrock factory without mutating conversation history. The existing canvas remains accessible while the home page uses the new workspace.

**Tech Stack:** Next.js, React, TypeScript, CodeMirror, react-markdown, diff-match-patch, FastAPI, LangChain AWS, Amazon Bedrock.

**Spec:** `docs/superpowers/specs/2026-10-25-writing-workspace-design.md`

## Global Constraints

- Markdown is the canonical, lossless document format. Support `.md`, `.markdown`, and `.txt`.
- Approved changes update the draft; writing to disk is an explicit Save action.
- A failed/truncated request never becomes an approvable proposal.
- Use stable registry releases and officially documented model IDs, not guessed future names.
- Keep existing conversation functionality accessible at `/canvas`.
- Filesystem and AI network access remain behind explicit user actions in the product.
- Preserve all existing user work; no deployment, publication, or automatic Git commits.

## Review Focus

- Repeated identical passages and Korean/emoji selections must edit the exact selected source location.
- External file edits made after review or immediately before save must not be silently overwritten.
- Reload, failed persistence, revoked directory permission, and deleted files must not discard a draft.
- A pending request completed after switching files must stay attached to its original document.
- Citation URLs and text in code blocks must remain intact; references must not become executable links.

## Task 1: Upgrade the frontend platform

**Files:** `apps/web/package.json`, lockfile, Next.js/ESLint/TypeScript/PostCSS configuration, affected existing frontend modules.

**Interfaces:** Preserve existing `GraphContext`/model response APIs. Do not edit new workspace modules or `src/shared/models.ts` (owned by Task 2).

- [x] Resolve stable package versions from npm; record before/after versions.
- [x] Remove unused deprecated packages and update tooling to supported APIs.
- [x] Install without peer bypasses and correct affected existing React/Next.js/assistant-ui code.
- [x] Run `yarn typecheck`, `yarn lint`, and `yarn build`; report baseline issues explicitly.

## Task 2: Upgrade the backend and model catalog; implement proposals

**Files:** `apps/backend/requirements.txt`, `apps/backend/core/models.py`, `apps/backend/core/bedrock_client.py`, affected backend integrations, `apps/web/src/shared/models.ts`, new `apps/backend/api/writing/` modules and `apps/backend/tests/test_writing.py`, router registration.

**Interfaces:** `POST /api/writing/propose` consumes/produces the exact types in the spec. `/api/models/list` retains its existing JSON shape.

- [x] Check latest stable PyPI versions and primary AWS model documentation.
- [x] Write failing tests for non-mutating proposals, invalid selections, invalid URLs, invented citations, malformed responses, truncation, and model configuration.
- [x] Upgrade dependencies and factory configuration; implement validated proposal generation.
- [x] Run backend tests and `pip check` in an isolated virtual environment.
- [x] Record verified model IDs, regions, defaults, sources, and any actual invocation limitations.

## Task 3: Document, review, and file persistence logic

**Files:** new `apps/web/src/lib/workspace/{types,review,files,storage,sources}.ts`, corresponding unit tests, and `apps/web/src/hooks/useWritingWorkspace.ts`.

**Interfaces:** An immutable `ReviewProposal` with base/proposed text and change decisions; a `WorkspaceDocument` with source content, disk snapshot, reference metadata, and bounded history. File handles are kept in IndexedDB, never JSON-serialized.

- [x] Write failing tests for exact selection splicing, per-change decisions, stale-base detection, repeated passages, Unicode, and citation parsing.
- [x] Implement pure review and source utilities without modifying input snapshots.
- [x] Write failing disk-conflict tests, then implement bounded directory scanning and compare-before-write.
- [x] Implement IndexedDB persistence and a React hook with serialized saves, request cancellation, per-file state, polling, and recoverable errors.
- [x] Run the full frontend unit test command.

## Task 4: Writing UI and app integration

**Files:** new `apps/web/src/components/workspace/` components/styles, `apps/web/src/app/page.tsx`, `apps/web/src/app/canvas/page.tsx`, relevant layout metadata, and usage documentation.

**Interfaces:** Consume Task 3 state and Task 2 proposal endpoint through same-origin fetch. Use latest dependency APIs from Task 1.

- [x] Build the file rail, document toolbar, lossless editor, reading view, and responsive inspector.
- [x] Add sentence/paragraph actions, precise inline change cards, approval/rejection, source links, and history restoration.
- [x] Retain the legacy canvas route and make it discoverable.
- [x] Test browser workflows with mocked inference and real application state, including reload and mobile layout.
- [x] Run frontend tests, typecheck, lint, production build, backend tests, and inspect the complete diff.
- [x] Have a fresh reviewer inspect integration, resolve material findings, and summarize verification and remaining environment limits.

## Execution notes

Frontend dependency migration and backend migration own disjoint files and can run concurrently. Workspace implementation stays in the main agent's context. A design reviewer checks the specification before these product changes begin. Changes remain reviewable in the working tree.

## Completion record

All four tasks are complete. Final verification: 39 frontend tests, 29 backend tests plus 41 subtests, eight writing-workspace browser workflows, legacy canvas browser checks, clean dependency consistency, and a successful production build. See `docs/writing-workspace-verification.md` for review findings and their regression coverage. Live paid inference and native OS picker permissions remain environment checks, as specified.
