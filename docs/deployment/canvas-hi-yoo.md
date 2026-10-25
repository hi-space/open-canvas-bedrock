# canvas.hi-yoo.com deployment

## Current release: integrated cloud workspace, 2026-10-25

The home page now combines project files, document editing, agent conversations,
review, sources, and history. Local-folder synchronization and explicit import
of old browser drafts are available in the same UI. Earlier conversation links
open an inline archive view and can import their document.

- `HtmlCanvasStack` and `CanvasWorkspaceStack`: `UPDATE_COMPLETE`.
- ECS task definition: `HtmlCanvasStackTaskDef2E995DD4:12`; one running, zero pending;
  rollout `COMPLETED`. Task revision `:11` remains available for rollback.
- AgentCore runtime: `canvas_writing_workspace-GKTOJW3k5H`, version `2`, `READY`,
  Seoul VPC mode, native read-only S3 Files mount at `/mnt/workspace`.
- S3 Files filesystem: `fs-0a2eb5d536990cc07`. API access point:
  `fsap-0dfe53ee5e69e9e74`; agent access point: `fsap-04ca875b8c0a1ddff`.
- Versioned private bucket: `canvas-writing-workspaces-913524902871-apne2`.
- Dedicated metadata table: `canvas-writing-workspaces`, encrypted, on demand,
  deletion protected, with PITR `ENABLED`.
- Frontend image:
  `sha256:b4d5980d525059c76777a84fb279e3caaee5b9f73d8074fa4078b6fefb015ce0`.
- Backend image:
  `sha256:ad8728d79ab2991b69357289151103495363bfc0210891327dcfb7a5156a78c3`.
- Agent image:
  `sha256:6e770c6dd9fd709c678edf6a607d8c24834873cae634b7f07135557a149cc105`.

Validation: 160 backend tests and 75 subtests pass in the deployed API image;
91 frontend tests, type checking, lint and production build pass. Twelve complete
production-browser workflows use the real local API/filesystem and deterministic
inference. Existing legacy lint/deprecation and redundant CloudFormation
dependency warnings remain.

Live AWS checks verify native NFS4 in both Fargate zones, cross-process advisory
locks, atomic file replacement and exact UTF-8. A disposable production-image
task verified actual Global Opus 5.5 through AgentCore, the shared file snapshot,
no writes before approval, approved persistence, duplicate approval idempotence,
stale-approval rejection, and BOM/CRLF/emoji preservation. Synthetic fixtures were
removed afterward.

An actual Cognito browser login on the deployed domain verified cloud project
creation/upload, real agent generation, approval, persisted file content after
reload, and zero page errors. Its temporary project was removed only after
checking that its files and records had not been changed beyond the test.
No password or browser cookies were saved.

Deployment compatibility findings:

- AgentCore requires `s3files:ListMountTargets` separately on the filesystem ARN.
  The agent's `ClientWrite`, `ClientRootAccess`, and direct S3 writes stay denied.
- This account rejects explicit `PlatformVersion`, even `V1`. The optional field
  is omitted to use the account's default platform.
- Current Bedrock client tool responses include `type: "tool_use"`. The parser
  accepts and removes this optional metadata from replay copies; server-side
  tool requests remain rejected. The live response regression is covered.
- Metadata from an interrupted stack update was retained and imported, then PITR
  enabled in a separate permissions update.

Four single-zone private interface endpoints add approximately $37.96/month at
730 hours, excluding filesystem/storage, data, AgentCore and model usage. See
[infrastructure details and price sources](../../deploy/agentcore/README.md).
Deployment templates, immutable image records and verification results are kept
privately under `~/.local/state/open-canvas-deployments/agentcore-workspace-20261025/`.

The sections below describe the earlier local-workspace release and login setup.

## Authorized change

Deploy the writing workspace and Global Claude Opus 5.5 default to the existing `canvas.hi-yoo.com` service. This explicitly supersedes the earlier implementation-only scope.

## Existing environment

- AWS region: `ap-northeast-2`; stack: `HtmlCanvasStack`; ECS cluster: `html-canvas`.
- One Fargate task, 512 CPU units and 1,024 MiB, behind an HTTPS ALB.
- The existing application performs Cognito authentication itself. The replacement must not remove that protection.
- The existing Cognito pool allows only administrator-created accounts.
- Existing HTML-document S3 storage, DynamoDB table, Lambda functions, Cognito pool/client, and secret are preserved for data retention and rollback.
- Before deployment, capture the live service, task definition, and CloudFormation template in a private release directory outside the repository.

## Deployment design

1. Build versioned frontend and backend images in the existing ECR asset repository. Use immutable digests for task definitions. Do not bake environment files or credentials into images.
2. Reuse the existing Cognito pool/domain with a dedicated confidential ALB app client. Require Cognito authentication on the HTTPS listener before forwarding to the new application. The old app client remains available for rollback.
3. Add four isolated, encrypted, on-demand DynamoDB tables matching the existing backend storage schemas. Preserve them on stack deletion/replacement. Grant only the required data operations on these table ARNs.
4. Keep the existing compute capacity and security groups. Only the ALB can reach frontend port 3000; backend port 9000 is internal to the task. Frontend `/api/health` checks backend `/health`.
5. Apply the support/authentication changes before switching application tasks, so there is no unauthenticated interval.
6. Register/deploy the two-container revision through CloudFormation, preserving ECS health checks and the existing automatic rollback circuit breaker.
7. Check the real task role's ability to serve the model catalog and invoke Global Opus 5.5, then verify the HTTPS endpoint, protected login redirect, target health, and service stability.

ALB session logout is an explicit same-origin POST. It clears ALB cookie shards and redirects through the same Cognito domain. Only the logout path bypasses the listener authentication step, allowing an expired session to log out without first logging in again.

Authenticated API mutations also require the configured application origin. The
Firecrawl key is injected into the backend from the application-scoped Secrets
Manager secret `canvas-writing/firecrawl-api-key`; no credential value appears
in source files, templates, or container images.

## Incremental cost

Existing Fargate capacity, ALB, networking, and Cognito pool are reused. The added tables use on-demand billing. The AWS Seoul price list checked on 2026-10-25 lists $0.1355 per million read request units and $0.68 per million write request units. A combined example of 100,000 read units plus 100,000 write units is $0.08155, excluding storage, backups, and model inference. Read/write units depend on item size and consistency; they are not simply HTTP request counts.

Price source: `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonDynamoDB/current/ap-northeast-2/index.json`, published 2026-09-11.

## Rollback

If rollout health checks fail, ECS/CloudFormation roll back the task revision. For a complete restoration, apply the captured original CloudFormation template with the previous parameter values. The previous image digest and original Cognito client remain available; existing data resources are never deleted. Newly created state tables use retention policies.

## Release checklist

- [x] Container tests and local health checks pass.
- [x] Image digests captured.
- [x] CloudFormation syntax/schema and security changes checked.
- [x] Support/authentication change set contains only intended additions/modifications.
- [x] Live task-role model check passes.
- [x] Application change set completes with healthy targets.
- [x] Domain requires Cognito login and forwards to the healthy new application.

## Completed release

- Release: `20261025T024553Z`; frontend image revision `r2`.
- Stack status: `UPDATE_COMPLETE`.
- ECS task definition: `HtmlCanvasStackTaskDef2E995DD4:11`.
- Service: one healthy running task, zero pending; rollout `COMPLETED`.
- Frontend digest: `sha256:32caa0c93b726949c1cbfe2c20fa1944e5b6d1a491de4956db73a93c5bf9f4fa`.
- Backend digest: `sha256:7ab6b674ee1537724a83c640109083d0ccb79054adf98bd31723ba30a58eb279`.
- Previous task revision `:10` remains `ACTIVE` for rollback.
- Public HTTPS requests without a session redirect to the existing Cognito domain
  with the ALB `/oauth2/idpresponse` callback.
- Frontend: 55 tests, type checking, production container build, and same-origin
  browser/API checks passed. Missing/cross-origin API mutations return 403.
- Backend: 29 tests and 41 subtests passed inside the image.
- A one-shot task using the production image, task role, table configuration, and
  runtime secret completed a DynamoDB probe, a real Global Opus 5.5 writing
  proposal, and a real Firecrawl extraction (36,559 source characters).
- The temporary verification task stopped successfully; its task definition was
  deregistered and local registry login credentials were removed.

Rollback templates and release manifests are backed up in the private encrypted
CDK asset bucket under `open-canvas-deployments/20261025T024553Z/`, with a private
local copy under `~/.local/state/open-canvas-deployments/20261025T024553Z/`.
The backup contains configuration and secret references, never secret values.

## Login branding

The Cognito domain now uses managed login version `2` on its existing Essentials
plan. The ALB passes `lang=ko`. The writing client uses the workspace cream
background, green controls, three-bar logo, and favicon; the legacy client has a
default managed-login style so its authentication flow remains available.

Only the domain branding version and listener language parameters changed in the
branding stack update. Password policies, accounts, OAuth grants, compute, and
data storage were not changed by that update.

The live login page passed desktop (1440×1000), mobile (390×844), Korean-label,
logo-loading, button-color, and horizontal-overflow checks. The password-recovery
screen uses the same theme. No credentials were submitted during visual checks.
Assets and the repeatable configuration script are in [deploy/cognito](../../deploy/cognito/README.md).
