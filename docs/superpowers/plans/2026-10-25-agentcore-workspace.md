# Integrated AgentCore Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> or scoped parallel execution. Steps use checkboxes for tracking.

**Goal:** Ship the approved integrated cloud file/editor/chat workspace at
canvas.hi-yoo.com with AgentCore, S3 Files, approval and local synchronization.

**Architecture:** Keep the existing web/API deployment and authentication.
Mount shared S3 Files in API and an IAM-protected AgentCore Runtime; only the API
can write canonical documents. Namespace metadata and ownership in DynamoDB.

**Tech Stack:** Existing Next.js/React, FastAPI/Python/boto3, Bedrock Converse,
AgentCore Runtime, S3 Files, DynamoDB, Cognito, ECS/Fargate.

**Spec:** ../specs/2026-10-25-agentcore-workspace-design.md

## Global constraints

- User already approved the architecture and deployment; proceed continuously.
- Preserve existing uncommitted authorized changes and production data.
- Default `global.anthropic.claude-opus-5-5`; never print/store user credentials.
- Honor the spec's public/runtime contracts, UTF-16 selections and byte limits.
- Native mount support, regional availability and costs need fresh AWS evidence.
- No approval bypass; no filesystem access controlled by a caller's owner ID.
- Work on `feat/agentcore-workspace`; do not reset, auto-commit or push prior work.

## Review focus

- Tests must attempt cross-owner IDs, traversal, symlinks and forged identity.
- Test a stale proposal after manual save and duplicate/reordered decisions.
- Test a Unicode selection and partial approvals that could remove citations.
- Test reloading a running job and duplicate chat request IDs.
- Test simultaneous local/remote edits without overwrite or unintended deletion.

## Task 1: Verified storage and deployment design

Owner: infrastructure worker; root reviews and executes mutations.

- [x] Read exact S3 Files/Fargate/AgentCore APIs and verify Seoul availability.
- [x] Inspect existing VPC, IAM and stack; calculate incremental costs.
- [x] Generate retained, encrypted filesystem/bucket/access points, scoped roles,
  private connectivity and immutable runtime/web/backend deployment updates.
- [x] Validate generated infrastructure and examine concrete change sets.

## Task 2: Workspace API, ownership and approval

Owner: root. Files: `apps/backend/api/workspaces/*`, backend registration,
Next.js forwarding, focused tests.

- [x] Write and run failing behavioral tests for ownership/path/version/approval.
- [x] Implement file locking, atomic writes, history and persistence backends.
- [x] Implement exact public contract from the spec; persist and poll agent jobs.
- [x] Verify signed ALB identity and use backend-derived workspace context.
- [x] Run full backend suite.

## Task 3: Runtime agent

Owner: agent worker. Files: `apps/backend/workspace_agent/*`,
`deploy/Dockerfile.agent`, agent tests. Consumes runtime contract in spec.

- [x] Write failing tool-boundary and proposal/selection tests.
- [x] Implement read-only file tools and bounded model tool loop.
- [x] Reuse source validators; expose `/ping` and `/invocations`.
- [x] Test no original writes, correct proposal bases, citations and failures.
- [x] Build ARM64 runtime artifact and run local contract smoke.

## Task 4: Unified UI and local sync

Owner: frontend worker. Files: new cloud workspace components/hook/client,
existing page/sidebar integration, scoped tests. Consumes API contract in spec.

- [x] Implement project/files/editor/chat/review/source/history in one workspace.
- [x] Keep current palette and proven Markdown selection/review components.
- [x] Save manual edits, poll jobs, persist chat, review individual changes.
- [x] Add explicit browser-draft import and local-folder sync with conflicts.
- [x] Test request races, reloading jobs, stale saves and sync policy.
- [x] Typecheck, full frontend tests/build and desktop/mobile browser smoke.

## Task 5: Integration review and deployment

Owner: root, with a fresh independent reviewer.

- [x] Review API/runtime/frontend contracts and fix discrepancies.
- [x] Adversarial review of ownership, approval and synchronization boundaries.
- [x] Run combined tests and realistic browser workflows.
- [x] Deploy storage/runtime then immutable web/API images with rollback.
- [x] Prove live file write/read across mounts, actual Opus agent execution,
  no mutation before approval, approval persistence and authenticated UI.
- [x] Document deployment identifiers, verification, costs and local sync limits.

## Decisions and progress

- Architecture approval is the user's “좋아 그렇게 해줘” following the complete
  architecture recommendation. Routine implementation choices are delegated.
- Existing checkout holds substantial authorized uncommitted work. Preserve it
  in place on a new feature branch rather than starting from stale committed code.
- Runtime receives a fresh session per job and explicit bounded chat history.
  Metadata uses a dedicated namespace/key DynamoDB table. The legacy store API
  accepts arbitrary namespaces, so sharing that table would let old endpoints
  overwrite project records (implementation review ruling).

## Execution ledger

**Completed:** both production stacks are `UPDATE_COMPLETE`, task `:12` is stable,
AgentCore version `2` is `READY`, and real authenticated browser generation and
approval passed. See `docs/deployment/canvas-hi-yoo.md` for final image digests.
Final validation is 160 backend tests (75 subtests), 91 frontend tests, and 12
complete browser workflows. All synthetic projects/files were cleaned up.

Final live-model correction: newer Bedrock responses include the optional
client-tool `type: "tool_use"` field. It is accepted, normalized for replay, and
covered by regression tests. Server tool execution remains rejected.

The entries below are intermediate checkpoints retained for the deployment audit.

- Backend API, ownership, approval, runtime and recovery implemented. Full suite:
  143 tests plus 52 subtests pass, including in the immutable API container.
- Runtime tool boundaries and HTTP contract tested in ARM64 image. Immutable
  agent digest: `sha256:29a544be547358b8f7cefaf9a9e2396d43cf0c43f65f38e77ac3c500ebdcc5e6`.
- API image digest:
  `sha256:ae5a0256145b9ed6697fd51b74b1cfbdf0566c676eb2ef62225661899fc397aa`.
- Independent backend review found concurrent source-limit publication,
  rejection-summary recovery, and returned source evidence handling defects.
  All reproduced with failing tests and fixed.
- Frontend reports 91 passing tests and complete desktop/mobile browser
  workflows. Independent review found hydration, composer, and proposal-read
  races; these were reproduced and fixed. Production image is being built.
- Live foundation stack `CanvasWorkspaceStack` created. Two Fargate probes
  verified native NFS4, cross-process locks, atomic replacement and exact UTF-8
  in both existing availability zones. Synthetic probe files remain for runtime
  read verification and must be cleaned after final validation.
- First runtime creation exposed required `s3files:ListMountTargets` permission.
  Added only on the workspace filesystem ARN. Live IAM simulation confirms
  discovery allowed and canonical writes explicitly denied.
- The table retained from rollback was imported into the stack without deletion;
  a separate permissions update enabled PITR and installed the corrected role.
- A subsequent creation found the account rejects explicit `PlatformVersion`,
  including V1. Omit the optional field and use the account's default platform.
- Main production stack `HtmlCanvasStack` has not yet switched from task `:11`.
  Runtime deployment, real invocation/approval verification, final UI image and
  authenticated production smoke remain required.
- Private operational artifacts, templates, image records and probe results:
  `~/.local/state/open-canvas-deployments/agentcore-workspace-20261025/`.
