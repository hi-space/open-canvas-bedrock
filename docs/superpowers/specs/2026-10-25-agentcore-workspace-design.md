# Integrated agent workspace

The user approved the architecture described in the conversation: a single file,
document, and conversation workspace; an AgentCore Runtime agent with S3 Files;
explicit review before canonical file changes; and local-folder synchronization.
This is an extension of the already deployed writing workspace, not a fresh app.

## Product behavior

- The home screen contains a project/file sidebar, Markdown editor/reader and
  selected-text toolbar, and persistent conversation/review/source/history panel.
- Documents are canonical server files. A user may create a project, import files,
  edit/save manually, and ask the agent to inspect or revise several files.
- The agent can list, read and search only the authenticated project. It can read
  supplied sources and fetch references, but cannot write canonical documents.
- Its output is a persisted proposal containing exact base content and version.
  Each change can be accepted/rejected. Acceptance checks the current version,
  preserves citations, records history, and saves the approved result.
- Chat and job state persist independently of the browser. Reloading must show a
  running/completed/failed job and its eventual proposals. Duplicate submissions
  with the same request ID do not run the agent twice.
- Existing browser drafts require an explicit import action before cloud upload.
- Local folder connection is optional. Synchronization compares local, remote,
  and last-synchronized content, supports nested Markdown/TXT files, and never
  resolves simultaneous changes or deletions by silently overwriting content.
- Existing citation extraction, selected-text mapping, Markdown fidelity, model
  selection and responsive styling remain. Default is
  `global.anthropic.claude-opus-5-5`.

## Deployment

Keep Next.js, FastAPI, ALB/Cognito and existing data resources. Mount the same
S3 Files filesystem in Fargate and a VPC AgentCore microVM runtime. The API mount
is writable; the agent mount is read-only through IAM. Do not use asynchronous
S3 object reads for interactive document content. Use an encrypted, versioned
bucket and retained filesystem. Record metadata in a dedicated DynamoDB
namespace/key table. The legacy general-purpose store API must not be able to
overwrite ownership, conversation, or job records.

Canonical files live at `<root>/<ownerKey>/<workspaceId>/files/<path>`.
API-only proposals/history/locks live under the sibling `.canvas` directory.
`ownerKey` is a SHA-256 of the verified Cognito subject. Runtime sessions are
unique per job. Model-controlled tool arguments cannot select owner/project/root.
No shell/exec tools are exposed. Agent responses are validated again by the API.

ALB-signed identity is verified at the backend against the configured signer.
The Next.js proxy forwards only the ALB identity token, never a client-supplied
workspace owner. Local development uses an explicit local identity mode.

## API contract

All JSON properties below are camelCase. Times are epoch milliseconds. Versions
are SHA-256 of exact UTF-8 content including any BOM and original line endings.
File extensions: `.md`, `.markdown`, `.txt`; max 2 MiB / 200,000 characters;
200 files per project; path depth 8; no hidden components, symlinks, absolute paths
or traversal. Error bodies have a human-readable `detail` string.

`Workspace = {id, name, createdAt, updatedAt}`.
`FileSummary = {path, name, version, bytes, updatedAt}`.
`FileDocument = FileSummary & {content}`.
`Source = {id, title, url, excerpt?}` (existing writing source constraints).
`Message = {id, role: "user"|"assistant", content, createdAt, jobId?}`.
`Job = {id, status: "queued"|"running"|"completed"|"failed", createdAt,
 updatedAt, message?, error?, proposalIds: string[]}`.
`Change = {id, from, to, before, after,
 decision: "pending"|"accepted"|"rejected"}`. Change offsets are UTF-16.
`Proposal = {id, jobId, path, kind:"ai", instruction, explanation, baseContent,
 proposedContent, baseVersion: string|null, appliedVersion: string|null,
 changes: Change[], createdAt, status:"pending"|"accepted"|"rejected"|"partial"}`.

- `GET /api/workspaces` → `{workspaces: Workspace[], storage:"cloud"|"local"}`.
- `POST /api/workspaces {name}` → `Workspace`.
- `GET /api/workspaces/{id}` → `{workspace, files:FileSummary[], messages:Message[],
  proposals:ProposalSummary[], jobs:Job[], sources:Source[]}`.
  ProposalSummary has id/jobId/path/explanation/createdAt/status/pendingCount.
- `GET /api/workspaces/{id}/files?path=...` → `FileDocument`.
- `PUT /api/workspaces/{id}/files {path,content,baseVersion:string|null}`
  → `FileDocument`. Null means create-if-absent, never blind overwrite.
- `GET /api/workspaces/{id}/history?path=...`
  → `{revisions:[{id,content,label,createdAt}]}`.
- `POST /api/workspaces/{id}/sources {id,title,url,excerpt?}` → `Source`.
- `DELETE /api/workspaces/{id}/sources/{sourceId}` → `{ok:true}`.
- `POST /api/workspaces/{id}/chat {message,requestId,activePath?,
  activeVersion?,selection?:{from,to,text},model?}` → `{job:Job}` (202).
  Selection offsets use UTF-16. A selection requires activePath/activeVersion.
  The client saves manual changes before sending a file editing request.
- `GET /api/workspaces/{id}/jobs/{jobId}` → `Job`.
- `GET /api/workspaces/{id}/proposals/{proposalId}` → `Proposal`.
- `POST /api/workspaces/{id}/proposals/{proposalId}/decisions
  {decisions:{[changeId]:"accepted"|"rejected"}}`
  → `{proposal:Proposal,file:FileDocument|null}`.
  Decisions apply only to pending changes; repeat identical decisions are
  idempotent. A changed base returns 409 with no document mutation.

## Runtime contract

HTTP `/ping` and `/invocations`, port 8080, ARM64. The service is invoked with
AWS IAM from FastAPI, not directly from the browser. No additional agent
framework is necessary; use the existing Bedrock client/boto3.

Invocation input:
`{ownerKey,workspaceId,message,model,history:[{role,content}],
 sources:Source[],activePath?,selection?:{path,start,end,text}}`.
Selection start/end are Python code-point offsets, converted and validated by API.
Root is a server environment variable `WORKSPACE_ROOT=/mnt/workspace`.

Invocation result:
`{message:string,proposals:[{path,baseVersion:string|null,baseContent,
 proposedContent,explanation}],events:[{tool:string,detail:string}]}`.
Only trusted tool handlers produce proposals. For the active selected passage,
the propose tool receives a replacement for the selection and preserves all
other content. Each read records exact content/hash; proposals use that snapshot.
New-file proposals use baseVersion null and empty baseContent.

Use bounded list/read/search/fetch-reference/propose tools and at most 10 model
round trips. Preserve citations using the existing validator. Limit source
fetches and model output sizes; do not reveal hidden reasoning or log documents.
Persist runtime failure as a retryable failed job, with no canonical mutations.

## Review focus

Wrong-owner requests; path/symlink escape; repeated/stale/partial approvals;
simultaneous manual and agent edits; Unicode selections; client disconnects;
duplicate jobs; local/remote sync conflicts; citation preservation; rollback.
