# Proofread Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save the full correction as a separate project file and retain its original/corrected snapshots for later comparison.

**Architecture:** A proposal-copy endpoint uses the existing project lock and recovery journal. Immutable comparison records live beside existing history files and are returned by the history endpoint. The current review and comparison components expose saving and opening a copy.

**Tech Stack:** Python/FastAPI, TypeScript/React/Next.js, pytest, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-25-proofread-copy-design.md`

## Global Constraints

- Preserve source files and existing approval decisions.
- Save the full proposed content, including changes individually rejected.
- Keep both comparison snapshots independently of the rolling 30 revisions.
- Use existing authorization, project locks, path/content limits and HTML validation.
- No new dependencies or model calls; work in the isolated checkout.

## Review Focus

- A later original edit or partial decision must not change the copied snapshot (Task 1).
- Retry after metadata failure must recover one copy, including after later copy edits (Task 1).
- UTF-8 name limits, deep paths and an existing destination must not overwrite files (Task 1).
- A late response must preserve newer navigation and unsaved drafts (Task 2).
- Comparison must remain available after reload and after editing the saved copy (Task 3).

---

### Task 1: Persistent, recoverable correction copies

**Files:**
- Create `apps/backend/api/workspaces/corrections.py`.
- Modify `apps/backend/api/workspaces/{files,proposals,routes}.py`.
- Create `apps/backend/tests/test_workspace_copies.py`.

**Interfaces:**
- `save_proposal_copy(files, proposal_id)` returns `{proposal, file}`.
- `correction_for(files, path)` returns a record or `None`.
- A record contains `proposalId`, `sourcePath`, `path`, `createdAt`, `baseContent`, `proposedContent`.
- `proposal.savedCopy` contains `path` and `createdAt`, including in summaries.
- `POST /{workspace}/proposals/{proposal_id}/copy` accepts no content payload.
- `GET /{workspace}/history?path=…` adds optional `correction`.

- [x] Write API/storage tests for exact copy bytes, partial decisions, stale original, retry, ownership, collisions, long names, HTML, and recovery after metadata failure.
- [x] Run `.venv/bin/python -m pytest -q tests/test_workspace_copies.py`; new copy requests must fail before the endpoint exists.
- [x] Implement copy naming and immutable records; extend the existing journal recovery to finalize copies, preserving ordinary approvals.
- [x] Run `.venv/bin/python -m pytest -q tests/test_workspace_copies.py tests/test_workspaces.py tests/test_workspace_job_consistency.py`; expect all pass.

### Task 2: Captured client state and saved-copy controls

**Files:**
- Modify `apps/web/src/lib/workspace/{types,cloud-types,cloud-api,cloud-state}.ts`.
- Modify `apps/web/src/lib/workspace/cloud-state.test.ts`.
- Modify `apps/web/src/components/workspace/{ReviewPanel,CloudInspector,HistoryPanel}.tsx`.
- Modify `apps/web/src/components/workspace/workspace.module.css` if needed.
- Modify `apps/web/src/components/workspace/ComparisonIntegration.test.tsx`.

**Interfaces:**
- Shared `CorrectionRecord` matches Task 1; `WorkspaceDocument.correction` is optional.
- `WorkspaceService.copy(id, proposalId)` returns `{proposal: CloudProposal, file: CloudFile}`.
- History returns `{revisions: DocumentRevision[], correction?: CorrectionRecord | null}`.
- `CloudWorkspaceController.saveProposalCopy(id, proposalId)` returns a file or no-op during an in-flight operation.
- `CloudProjectState.copying` tracks proposal IDs; `corrections` tracks records by file path.
- `ReviewPanel` takes optional `onSaveCopy`, `savingCopy`, `savedCopyPath`, `onOpenCopy`.

- [x] Write state tests for full-copy results, draft preservation, captured project/navigation, duplicate clicks, failure cleanup, and history record hydration.
- [x] Write component tests for save controls in the panel/dialog, busy state, saved-copy opening, and comparison of immutable snapshots rather than the current edited copy.
- [x] Run `yarn test src/lib/workspace/cloud-state.test.ts src/components/workspace/ComparisonIntegration.test.tsx`; expect new functionality to fail.
- [x] Implement the API binding, captured state updates and optional review controls. Keep saving separate from approval and navigation.
- [x] Display **교정 전후 비교** in the copy's history, using the record's snapshots.
- [x] Run the same test command; expect all pass.

### Task 3: Browser flow and final verification

**Files:**
- Create `apps/web/tests/correction_copy_smoke.py`.
- Modify `docs/cloud-workspace.md`.

- [x] Exercise actual local API/storage and Chromium: generate a proposal, make partial decisions, save/open/reload a copy, compare, edit the copy and compare its saved snapshots again.
- [x] Cover HTML copy previews and a mobile viewport, and assert no browser page errors.
- [x] Document the new buttons, full-proposal semantics, persistent comparison records and unchanged partial-approval flow.
- [x] Run backend tests, web tests, lint and typecheck. Run the browser smoke with the deterministic agent; inspect screenshots.
- [x] Request one fresh review of the completed change, resolve material findings, and report validation with the implementation.

## Verification — 2026-10-25

- Backend: 331 tests and 91 subtests passed; two existing `utcnow` deprecation warnings.
- Web: 189 tests in 23 files passed; typecheck passed.
- Lint: exit 0, with 17 warnings in untouched legacy components.
- Chromium: all five correction-copy scenarios passed, including reload, subsequent edits,
  mobile layout and isolated HTML previews; screenshots inspected.
- Review: fixed a delayed-copy response that could replace a newer saved destination.
  Two regression cases first failed, then passed; the reviewer verified the fix.
