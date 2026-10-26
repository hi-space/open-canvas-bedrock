# canvas.hi-yoo.com deployment

## Automated releases

Every merge to `main` deploys through `.github/workflows/deploy.yml`; release
from that path only, not from a local working tree. Pull requests run the tests
without AWS access.

Keep design documents, verification evidence and release records in this
project's `docs/`. A documentation-only commit recording a completed release
uses `[skip ci]` to avoid redeploying unchanged application code; the record
identifies the source SHA that actually produced the deployed images.

1. Backend, deployment-script and web tests (pytest, vitest, typecheck, lint).
2. Frontend and backend images build on x86-64 runners, the agent image on an
   ARM64 runner. The agent container must answer `/ping` before it is pushed,
   which catches modules missing from `deploy/Dockerfile.agent`.
3. `deploy/release.py` changes only the ECS task definition images and the
   AgentCore runtime image and lifecycle, through change sets that it rejects
   when any other resource would change or be replaced. It then checks the ECS
   rollout, target health, runtime `READY` and the Cognito redirects, and
   restores the previous images if a check fails.

AWS access is the OIDC role `open-canvas-github-deploy`, trusted only for the
repository's `production` environment, which accepts deployments from `main`.
CloudFormation runs as the CDK execution role. The backend's private build
context (diagram skills and the LinkedIn style guide) is a checksummed archive
under `open-canvas-build/` in the CDK assets bucket; the `production`
environment variables `AWS_DEPLOY_ROLE_ARN`, `SKILLS_BUNDLE_S3_URI` and
`SKILLS_BUNDLE_SHA256` point to it. Workflow logs are public: they show image
digests and resource status only.

## Current release: on-demand sources, 2026-10-26

Project source storage and model context are separate. Chat reads source
passages through tools; research retrieves evidence per question. Used evidence
keeps immutable versions, while unused copies are reclaimed. The storage quota
does not block document revision or research jobs.

- Source commit: `d3cb8d99628c883b2549a8dfa6b0c2371664cc9d`, branch `main`.
- GitHub Actions run: [40284643751](https://github.com/hi-space/open-canvas-bedrock/actions/runs/40284643751);
  all six jobs successful at `2026-10-26T07:24:23Z`.
- Both stacks `UPDATE_COMPLETE`; ECS revision `22`, one healthy running task,
  zero pending tasks, healthy ALB target.
- AgentCore runtime and DEFAULT endpoint `READY`, serving version `9`.
- Independent verification at `2026-10-26T07:25:28Z` checked all image digests,
  the runtime lifecycle and Cognito redirects. Previous task revision `21`
  remains `ACTIVE`.

The [release record](2026-10-26-on-demand-sources.md) contains the manifest,
workflow result, before/after snapshots and validation scope. The
[feature guide](../on-demand-sources.md) describes usage and storage compatibility.

## Previous release: research HTML and native diagrams, 2026-10-26

Deep research can produce HTML from selected project files with native HTML/CSS
and SVG diagrams. Specialized diagram skills remain optional. SVG selection
and revision are atomic, source citations survive rendering, and exported HTML
retains its diagrams. The release also includes the HTML wide preview from
remote `main`.

- Source commit: `53c3ac82965cd34dc4f7addf550dc38c859bca8a`, branch `main`.
- GitHub Actions run: [40247301060](https://github.com/hi-space/open-canvas-bedrock/actions/runs/40247301060),
  all six jobs successful; completed at `2026-10-26T00:10:41Z`.
- Both CloudFormation stacks: `UPDATE_COMPLETE`.
- ECS task definition: `HtmlCanvasStackTaskDef2E995DD4:20`; rollout `COMPLETED`,
  one running task, zero pending, both containers and the ALB target healthy.
  Previous revision `:19` remains `ACTIVE`.
- AgentCore runtime and `DEFAULT` endpoint: `READY`, serving version `7`.
- Independent verification at `2026-10-26T00:11:04Z` confirmed all three image
  digests, the runtime lifecycle and Cognito redirects for `/` and `/api/workspaces`.

The [release record](2026-10-26-research-html.md) contains the immutable image
manifest, workflow result, before/after AWS snapshots, validation scope and
rollback baseline. The [feature guide](../research-html.md) links the design
documents and reproducible browser evidence, all under this project's `docs/`.

## Previous release: HTML canvas and bounded revisions, 2026-10-25

The workspace generates static HTML/CSS from project sources, previews new
documents before approval, and supports element selection, rendered before/after
review, source editing, citations and HTML download. HTML changes are atomic.
Long-document revisions preserve Markdown links and code blocks, share one
output-token budget, and maintain a heartbeat while external work is running.

- Source commit: `9ebb72e0d075ec7fd44b73f1a11a26487101c237`, branch
  `feat/html-workspace`.
- Release: `html-workspace-20261025T082913Z`; verified at
  `2026-10-25T09:20:32Z`.
- `HtmlCanvasStack` and `CanvasWorkspaceStack`: `UPDATE_COMPLETE`.
- ECS task definition: `HtmlCanvasStackTaskDef2E995DD4:16`; rollout `COMPLETED`,
  one running task, zero pending, both containers and the ALB target healthy.
  Previous revision `:15` remains `ACTIVE` for rollback.
- AgentCore runtime: `canvas_writing_workspace-GKTOJW3k5H`, version `3`, `READY`;
  the `DEFAULT` endpoint serves version `3`. Maximum lifetime is 900 seconds;
  idle timeout remains 60 seconds.
- Frontend image:
  `sha256:4a63d8d62821ebaaad5869d02d2de57e08e3eb828a06bb6ddacdc6d1763cb9b2`.
- Backend image:
  `sha256:320ebd45e0ef8fd3853310cb04d2932e789673557633baf112f6f42da68e79e3`.
- ARM64 agent image:
  `sha256:01ef081894806383455235504ca7671fd7bab3f17ab8aab1dbccb49b2bacdca4`.

The application template changes the two container images. The support template
changes the runtime image and maximum lifetime. CloudFormation also reevaluates
`ApiWorkspacePolicy` through `Runtime.AgentRuntimeArn`; both its template and
effective policy document match the baseline. Existing capacity, networking,
authentication, roles and filesystem configuration are retained.

Validation: 158 web tests, type checking, lint and the production build pass.
The exact backend image passes 318 tests and 84 subtests as application UID
10001; the ARM64 agent image passes startup, HTML-selection and request-validation
checks. All 17 deployment tests and CloudFormation validation pass. Existing
lint, datetime and redundant-dependency warnings remain.

A real Cognito browser session verified source-file-based HTML generation through
AgentCore, preview without a canonical write, atomic approval, selected-region
revision, persistence after reload, stale-write rejection, and exact HTML export.
There were no page errors. The temporary login and project were removed; cleanup
used the application's native filesystem mount and task role, and its temporary
task definition was deregistered. Test passwords and browser cookies were not
saved. Automated authenticated write probes send a matching `Origin` header,
as required by the production proxy.

Baseline templates, immutable source/image manifests, reviewed change sets,
container checks and live verification records are stored privately under
`~/.local/state/open-canvas-deployments/html-workspace-20261025T082913Z/`.

## Previous release: revision source navigation, 2026-10-25

Revision cards now include **본문에서 보기**. The action scrolls to the affected
paragraph or Markdown range, highlights it with the same change number, and
provides a return-to-review control on mobile. Locations account for earlier
approvals; hidden Markdown definitions open in source view.

- Release: `review-focus-20261025T064600Z`; completed at `2026-10-25T06:55:31Z`.
- `HtmlCanvasStack`: `UPDATE_COMPLETE`.
- ECS task definition: `HtmlCanvasStackTaskDef2E995DD4:15`; one healthy running
  task, zero pending; rollout `COMPLETED`; one healthy ALB target.
- Previous task revision `:14` remains `ACTIVE` for rollback.
- Frontend image:
  `sha256:06dc538e29a195f2921b1fa38b62206a52f742772a4c65f89393f7be9b55ba04`.
- Backend image:
  `sha256:47e073c22af14b6ab5c169352b504d436a6cea7cd8232aa916c7205dce9e8e08`.

The template delta changes only the frontend image and the service's resulting
task revision. The live task retains its 2,048 CPU units, 4,096 MiB, roles,
networking, filesystem mount, and backend image.

Verification: 97 frontend tests, type checking, lint, production build, and 22
local browser scenarios pass. The exact release container passed all 10 source
navigation browser scenarios with the deterministic local API fixture. Live AWS
checks confirm the expected image digest, healthy frontend/backend containers
and ALB target, no startup log errors, and Cognito redirects for unauthenticated
HTTPS requests to `/` and `/api/workspaces`. Existing lint warnings remain.

The captured baseline template, rollback image, source snapshot, reviewed change
set, and verification results are stored privately under
`~/.local/state/open-canvas-deployments/review-focus-20261025T064600Z/`.

## Previous release: deep research writer, 2026-10-25

Workspace chat offers a deep research genre (paper, blog, LinkedIn). The backend
researches with Tavily, renders figures with draw.io and Chrome, and proposes the
result as a new project file for approval. Source: commit `b65918e`.

- Change set `research-writer-20261025` on `HtmlCanvasStack` changed only three
  resources: task definition (CPU 512 → 2048, memory 1024 → 4096 MiB, both image
  digests, `TAVILY_API_KEY` secret on `backend`), the service's task definition,
  and `WritingReferenceSecretPolicy` (adds the Tavily secret). Stack `UPDATE_COMPLETE`.
- ECS task definition `HtmlCanvasStackTaskDef2E995DD4:14`; one task running, both
  containers healthy, rollout `COMPLETED`. Revision `:13` remains for rollback.
- Frontend `sha256:05f85b808026327d36e4d9583d0cfc403dbb8001d68e6afa8a8fbcc7c868f590`;
  backend `sha256:47e073c22af14b6ab5c169352b504d436a6cea7cd8232aa916c7205dce9e8e08`
  (draw.io 32.6.1, checksum-verified; Chrome; Nanum fonts; diagram skills from a
  named build context). AgentCore runtime and agent image unchanged.
- New secret `canvas-writing/tavily-api-key` (tag `Application=open-canvas-writing`);
  no value in templates, images or logs.
- Figures are written per owner under `/mnt/workspace/research-assets/` on the
  existing S3 Files access point and served only to the owner's session.

Validation: 168 backend tests, 91 frontend tests and type checking pass. In the
production image locally, both figure renderers and a full research job passed.
A one-off task with the production task definition, task role, secret and S3 Files
volume completed a real LinkedIn research job in 162 s: Tavily key injected, one
figure on shared storage linked from the document, three cited sources with
excerpts; its synthetic owner's files were removed and the task definition
deregistered. Unauthenticated `/` and `/api/research/assets/...` redirect to Cognito.

Cost: Fargate Seoul on-demand $0.04656 per vCPU-hour and $0.00511 per GB-hour
(AWS Price List API, published 2026-10-19): about $20.7 → $82.9 per month at 730 hours
(+$62.2). The secret adds $0.40 per month. Tavily and model usage are billed per use.

Rollback: re-apply `template-before.json` from the private release directory
`~/.local/state/open-canvas-deployments/research-20261025/` (task definition `:13`).

Note: the AWS CLI 2.28 used here drops `s3filesVolumeConfiguration` when reading
task definitions; register verification tasks with boto3 ≥ 1.43 so they mount S3 Files.

## Earlier release: integrated cloud workspace, 2026-10-25

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
