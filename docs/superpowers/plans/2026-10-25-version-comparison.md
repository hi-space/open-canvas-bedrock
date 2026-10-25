# Version comparison implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Let authors compare complete previous and revised documents side by side from review and saved history.

**Architecture:** A shared, explicitly opened comparison dialog renders immutable inputs. Review reuses its existing decision controls inside the dialog; history compares a selected revision with the current draft. Markdown uses source offsets for block highlights and an exact source view; HTML reuses the existing isolated preview.

**Tech Stack:** React, TypeScript, CSS modules, Radix Dialog, react-markdown, remark-gfm, diff-match-patch, Vitest, existing Playwright smoke infrastructure.

**Spec:** The approved scope below records the design accepted in this conversation on 2026-10-25.

## Approved scope

- A “나란히 비교” button opens a wide comparison surface.
- Previous version on the left, revised/current version on the right.
- Markdown retains document formatting and highlights changes.
- HTML displays both rendered versions.
- Existing approve/reject actions remain available while comparing proposals.
- Saved revisions can be compared with the current document.

## Global constraints

- Reuse installed dependencies, the current workspace typography, and existing approval safeguards.
- Opening, reading, or closing a comparison must not mutate a document or approve a change.
- Proposal comparisons retain the original base snapshot after partial approval.
- HTML uses the existing sanitized, noninteractive preview.
- File/proposal navigation must not leave a comparison from a different document open.
- No deployment or remote writes are part of this task.

## Review focus

- BOM, CRLF, emoji, repeated paragraphs: highlight the correct source without splitting surrogate pairs.
- Changes to formatting or link targets: source comparison remains available even when visible text looks identical.
- Partial acceptance and stale drafts: stable before/after snapshots and the existing disabled approval behavior.
- Empty/new/deleted documents: both sides remain understandable.
- Mobile and keyboard use: readable panes, visible close control, focus restoration, no page overflow.

## Task 1: Comparison data and display

**Files:** `apps/web/src/lib/workspace/comparison.ts`, `comparison.test.ts`; `apps/web/src/components/workspace/DocumentComparison.tsx`, `DocumentComparison.test.tsx`, `comparison.module.css`.

**Interfaces:**

- `comparisonRanges(before: string, after: string): { before: ComparisonRange[]; after: ComparisonRange[] }`, with `ComparisonRange = { from: number; to: number }`.
- `proposalComparisonContent(proposal: ReviewProposal): string` defines the right-hand snapshot.
- `DocumentComparison` takes document name/path, labeled before/after snapshots, a trigger, and optional review controls.

- [x] Write tests for exact changed ranges, Unicode boundaries, identical/empty content.
- [x] Run the tests and confirm missing implementation fails.
- [x] Implement comparison ranges and a wide, accessible dialog with rendered/source modes.
- [x] Test simultaneous Markdown/HTML rendering, source fidelity, unchanged and empty states.

## Task 2: Review and history integration

**Files:** `apps/web/src/components/workspace/ReviewPanel.tsx`, `HistoryPanel.tsx`, `ComparisonIntegration.test.tsx`.

**Consumes:** Task 1’s comparison component and proposal snapshot policy.

**Produces:** Comparison entry points in the existing review and history panels.

- [x] Write interaction tests for opening review and history comparisons without mutation.
- [x] Confirm the tests fail before adding entry points.
- [x] Share review decision controls between the existing panel and comparison dialog.
- [x] Keep stale/deciding protections, original proposal snapshots, and distinct history/current labels.
- [x] Confirm partial decisions, close/reopen behavior, and document/proposal identity changes.

## Task 3: Browser verification and documentation

**Files:** `apps/web/tests/comparison_smoke.py`, `docs/cloud-workspace.md`.

- [x] Use the existing deterministic backend for Markdown and HTML revision comparison.
- [x] Verify desktop/mobile layouts, keyboard close/focus, approvals, and saved-history comparison.
- [x] Run the full frontend suite, lint, typecheck, and production build.
- [x] Review the complete change and resolve material findings.
- [x] Document how to open comparisons and the difference between proposal and saved-history inputs.

## Execution notes

- Baseline: 20 frontend test files, 158 tests pass.
- Work proceeds in the managed worktree on `feat/version-comparison`.
- Approved design is implemented inline; there is no additional design approval gate.
- Final whole-change review found two rendering issues: structural Markdown highlights
  and the HTML frame height chain. Both were reproduced with failing checks and fixed.
- Browser checks also protect the comparison's accessible name on mobile and keyboard
  scrolling within each pane.
- Final verification: 174 frontend tests pass; all 5 browser workflows pass.
  Lint has the same 17 existing warnings as the unchanged checkout and no errors.
- Applied the verified patch to the original workspace. Typecheck, production build,
  changed-file formatting, and patch whitespace checks pass there.
- The proposal comparison retains both original snapshots; individual decisions are
  displayed separately. History compares a selected saved revision with the live draft.
