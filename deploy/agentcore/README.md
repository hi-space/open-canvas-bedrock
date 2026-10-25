# Canvas AgentCore workspace deployment

`prepare.py` generates private CloudFormation files; it makes no AWS calls.
`probe_mount.py` runs inside a task with the API's native filesystem mount.
The deployment retains the existing `HtmlCanvasStack`, ALB/Cognito configuration,
Next.js/FastAPI containers, Fargate capacity, and legacy storage.

## Verified design

Facts were checked on **2026-10-25**; recheck after **2026-11-08**.
`verified` means a live account, registry, regional catalogue, or price-list check.
`documented` means current official documentation; it does not claim a successful
application-level mount or invocation.

| Fact | Confidence | Evidence and consequence |
| --- | --- | --- |
| S3 Files and its CloudFormation resources are available in Seoul | verified | Regional catalogue and live `s3files.list_file_systems`; use `ap-northeast-2`. |
| ECS supports native S3 Files volumes on Fargate at GA | documented | ECS developer guide [1]. No mount helper or privileged container is needed. |
| AgentCore microVMs accept a native S3 Files access point in VPC mode | documented | Runtime filesystem guide [2]; at most two S3 Files mounts and five total filesystem configurations. |
| The current Fargate task uses the two existing public subnets | verified | `apne2-az1` and `apne2-az2`; create a mount target in each. |
| AgentCore VPC connectivity supports both of those zones | documented | VPC guide [3]. This deployment uses only `apne2-az1` for its runtime and interface endpoints. |
| Global Opus 5.5 has an active Seoul inference profile | verified | `GetInferenceProfile` returned `ACTIVE` for `global.anthropic.claude-opus-5-5`. Actual inference remains a release smoke check. |
| Omitting `platformVersion` uses the default V1 platform | documented | Platform-version guide [4]. Omit this optional field; V2's current region list excludes Seoul. |
| Explicit `platformVersion` is not enabled for this account | verified | Creation with `V1` was rejected; the account's existing `READY` runtime has no `platformVersion` field. |
| The existing HTML bucket has no versioning enabled | verified | It remains untouched. S3 Files requires versioning [5], so use a separate bucket. |
| Native clients share close-to-open filesystem consistency | documented | Guide [2]. Both interactive readers use mounts; they do not wait for bucket synchronization. |
| A session reporting `Healthy` is ended by the 60-second idle timeout even mid-request | verified | 2026-10-25: invocations longer than 60 s lost their session, were retried once and failed with "Runtime initialization time exceeded". `/ping` reports `HealthyBusy` while an invocation runs. |

The separate `CanvasWorkspaceStack` owns:

- A private SSE-S3 encrypted, versioned bucket; the S3 Files filesystem; and its
  dedicated synchronization role. All three have retain policies.
- Two access points rooted at `/workspace`, both enforcing UID/GID `10001`.
  Both containers see that directory at `/mnt/workspace`.
- A writable API access point and a read-only agent access point. Read-only is
  enforced by IAM and the filesystem policy, not by an access-point boolean.
  The agent has explicit denials for filesystem writes/root access and backing
  object writes/deletes. It cannot assume the API or synchronization roles.
- Mount targets in both existing Fargate zones; port 2049 accepts only the
  application task and agent security groups.
- Four interface endpoints in one zone: ECR API, ECR Docker, CloudWatch Logs,
  and Bedrock Runtime. A free S3 gateway endpoint serves both route tables.
- An ARM64 AgentCore runtime using the account's default platform, an immutable image digest, and IAM inbound
  authentication. It mounts only the read-only access point. Its idle timeout
  is 60 seconds and maximum lifetime is 900 seconds, covering the agent's 720-second
  job limit inside AgentCore's 15-minute synchronous request limit.
- An isolated `canvas-writing-workspaces` DynamoDB table with `namespace` and
  `key` string keys, on-demand billing, encryption, point-in-time recovery,
  deletion protection, and retain policies.

The metadata table is a security boundary: the legacy `/store` API accepts
arbitrary namespaces in `WritingStore`. Workspace ownership, jobs, and proposal
state must use `WORKSPACE_TABLE_NAME`; `STORAGE_TABLE_NAME` remains the legacy
table. Only the API receives permissions on the new table.

The API's access point is mounted through the task definition's
`Volumes[].S3FilesVolumeConfiguration.{FileSystemArn,AccessPointArn}` and the
backend's `MountPoints`. AgentCore uses
`FilesystemConfigurations[].S3FilesAccessPoint.{AccessPointArn,MountPath}`.
TLS and IAM authentication are mandatory for S3 Files. `Ref` on
`AWS::S3Files::FileSystem` returns its ARN, which the dependent resources accept.
These fields were checked against the live Seoul CloudFormation schemas.
`PlatformVersion` is deliberately absent. Although the SDK accepts the optional
field and the guide describes `V1`/`V2`, this account rejects explicit selection,
including `V1`. Omitting it follows the documented default and matches the
existing working runtime; no feature enablement or region change is required.

Runtime creation also requires `s3files:ListMountTargets` on the exact filesystem
ARN. This is a control-plane lookup with no `s3files:AccessPointArn` condition;
that condition belongs on `ClientMount`/`ClientWrite` only. The runtime guide's
short IAM example omits this lookup, but the live runtime validation requires it.
The S3 Files authorization reference [10] confirms its filesystem resource scope.
`GetMountTarget` is not needed to inspect the target records returned by
`ListMountTargets`.

`logs:DescribeLogGroups` has no resource-level scope, so its allow uses `*` with
an `aws:RequestedRegion` condition for Seoul. Stream/group writes retain their
runtime-specific ARN scope. The agent receives no `logs:PutResourcePolicy`
permission [11].

The runtime and all applications sharing its access point can see the same
filesystem. Per-user isolation therefore also requires the runtime's bounded
file tools: the API supplies the verified owner/project, and model arguments
cannot change that root or read hidden metadata. No shell tool is exposed.
Agent changes reach canonical files only through the API's approval path.

## Network and cost

The runtime has private IP addresses. An internet gateway on a public subnet
does not give it internet access [3]. It uses the private Bedrock endpoint in
Seoul; the public-source/Firecrawl fetch happens in the existing API, which passes
extracted source content to the agent. No Firecrawl credential is placed in the
runtime image or environment.

Interface endpoint private DNS also affects the existing task. Their security
group allows its existing task security group, including ECR image pulls and
CloudWatch delivery. The S3 gateway endpoint keeps the default endpoint policy
so existing S3 access is preserved; IAM and bucket policies continue to enforce
authorization. Live ENI inspection before deployment found only the existing
ALB and application task in this VPC.

| Incremental item | Seoul rate checked on 2026-10-25 |
| --- | --- |
| Four interface endpoints, one zone, 730 hours | **$37.96/month** (`4 × 730 × $0.013`) |
| Interface endpoint data processing, first 1 PB | $0.01/GB |
| S3 gateway endpoint | No hourly or processing charge |
| S3 Files active storage | $0.33/GB-month |
| S3 Files reads / writes | $0.03 / $0.07 per GB |
| S3 Standard backing storage, first 50 TB | $0.025/GB-month |
| AgentCore V1 CPU / memory | $0.0895/vCPU-hour / $0.00945/GB-hour |
| Workspace DynamoDB read / write units | $0.1355 / $0.68 per million units |

The fixed endpoint amount is an estimate using 730 hours. Actual usage also
includes S3 versions/requests, filesystem background import/export, DynamoDB
storage/backups, ECR, logs, network transfers, and model inference. For example,
10 measured runtime vCPU-hours plus 50 measured GB-hours cost $1.3675 for
AgentCore compute alone. Existing Fargate and ALB capacity remains unchanged.
The one-zone runtime and endpoint design intentionally has lower availability
than deployment across two zones.

Current regional price feeds:

- [6] `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonVPC/current/ap-northeast-2/index.json` — published 2026-10-16.
- [7] `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/ap-northeast-2/index.json` — published 2026-10-15.
- [8] `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrockAgentCore/current/ap-northeast-2/index.json` — published 2026-10-19.
- [9] `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonDynamoDB/current/ap-northeast-2/index.json` — published 2026-09-11.

## Generate and validate

Keep the live baseline, release manifests, and generated templates outside the
repository with directory mode `0700` and file mode `0600`. The current release
workspace is:

```text
~/.local/state/open-canvas-deployments/agentcore-workspace-20261025/
```

Generate the foundation before the agent image exists:

```bash
python deploy/agentcore/prepare.py \
  --output-directory "$CANVAS_RELEASE"
```

This writes `workspace-foundation-template.json`. It includes mounts, roles,
the API's mount permissions, and network endpoints. It excludes the runtime and
metadata table, and exports the filesystem and API access-point ARNs.

After building and pushing the ARM64 runtime and the application images, provide
the immutable agent URI and an image manifest containing `frontendImage` and
`backendImage`:

```bash
python deploy/agentcore/prepare.py \
  --agent-image "$CANVAS_AGENT_IMAGE" \
  --baseline "$CANVAS_RELEASE/baseline-template.json" \
  --images "$CANVAS_RELEASE/images.json" \
  --output-directory "$CANVAS_RELEASE"

python -m unittest discover -s deploy/agentcore -p 'test_*.py'
cfn-lint -r ap-northeast-2 \
  -t "$CANVAS_RELEASE/workspace-foundation-template.json" \
     "$CANVAS_RELEASE/permissions-template.json" \
     "$CANVAS_RELEASE/workspace-support-template.json" \
     "$CANVAS_RELEASE/workspace-application-template.json"
```

The permissions template adds the metadata table and prepares the execution
role before AgentCore validates it. The full support template then adds the
runtime and API invocation permission. The application template changes only the existing ECS task
definition. It preserves its CPU/memory, health checks, secret references,
legacy environment, other volumes, and every other resource.

The existing baseline has three `W3005` redundant-dependency warnings concerning
the renderer, labeler, and ECS service. Do not modify unrelated resources merely
to remove those pre-existing warnings. New support templates should have no
lint findings.

## Deployment sequence

1. Capture the live `HtmlCanvasStack` template, parameters, task definition and
   service in the private release directory. Verify account `913524902871` and
   region `ap-northeast-2`.
2. Create and review a `CREATE` change set for `CanvasWorkspaceStack` using the
   foundation file, `CAPABILITY_IAM`, and
   `S3PrefixListId=pl-78a54011`. Execute the reviewed change set and wait for
   `CREATE_COMPLETE`.
3. Run the native mount probe in a temporary Fargate task with the existing task
   role, the exported filesystem/API access point, and the existing task security
   group. It must pass in both configured Fargate zones.
4. Create and review an `UPDATE` change set on the support stack using
   `permissions-template.json`. Preserve the prefix-list parameter. Execute it,
   wait for `UPDATE_COMPLETE`, and verify the execution role's effective
   `s3files:ListMountTargets` allow on the filesystem ARN. This separates IAM
   propagation from runtime creation.
5. Create and review another `UPDATE` change set on the same support stack using
   the full support file and real ARM64 runtime digest. This adds only the
   runtime, API invocation permission, and runtime outputs. Execute it and wait
   for `UPDATE_COMPLETE`.
6. Verify the real AgentCore invocation reads the retained probe fixture through
   its native mount. Check the runtime role's effective write denial, persist a
   proposal, and prove that canonical content is unchanged before approval.
7. Create and review the `HtmlCanvasStack` application change set, preserving
   existing parameters. It should modify only the ECS task definition and the
   service's resulting task revision. Execute it, then check ECS rollout,
   target health, ALB authentication, and the integrated application.
8. Complete the authenticated approval/persistence test, including stale-base
   rejection, before recording the release as verified.

Do not use the placeholder-image `validation-*.json` files as release templates.
They exist only for local schema validation while an image is being built.

## Native mount probe

Run the following **inside a Fargate task using the API access-point mount**:

```bash
python probe_mount.py --root /mnt/workspace --keep
```

The script has only standard-library dependencies. A one-shot task can execute
its exact text through `python -c` without rebuilding the production image.
Remove the normal `app` container, health check, and container dependencies from
that temporary task, then supply the probe as the backend command; preserve the
existing execution/task roles, networking, and native volume configuration.
The task is temporary and must not replace the application service.

The probe checks:

- The path is backed by NFS; a plain local directory fails before any writes.
- A second process cannot acquire an already-held exclusive `flock`, and can
  acquire it after release.
- An atomic replacement preserves an already-open original reader while a new
  reader sees the replacement.
- BOM, CRLF, combining characters, Korean text and emoji survive byte-for-byte.

It creates a random synthetic owner/project in the normal
`<ownerKey>/<workspaceId>/files` layout. Default behavior removes only that
fixture. `--keep` retains it and reports owner/project/path, exact content and
SHA-256 for the subsequent AgentCore read check. Retained probes must be cleaned
up after integration checks. They have no metadata-table entry and do not appear
as user projects.

`--allow-local` is exclusively for local probe tests; it is not acceptable
evidence of a working S3 Files deployment. A single-client probe also does not
replace the API-to-AgentCore freshness and approval checks.

## Rollback

Restore the captured main-stack template and previous image digests to revert
the application. Restore the preceding support template to revert a runtime
update. The bucket, filesystem, synchronization role, and metadata table retain
data on replacement/deletion. Deletion protection additionally guards the table.

Do not delete the support stack while the application imports its exports.
The runtime's default endpoint follows the latest runtime version, so runtime
image rollback must also be explicit.

If a failed creation leaves the metadata table retained but unmanaged, import it
before retrying the update. After rollback completes, copy the **live** stack
template and add only the retained table definition, matching its actual keys,
billing mode, encryption, tags, deletion protection, and backup state. Keep all
existing resource properties, parameters, and outputs unchanged. Use:

```json
[
  {
    "ResourceType": "AWS::DynamoDB::Table",
    "LogicalResourceId": "WorkspaceMetadataTable",
    "ResourceIdentifier": {"TableName": "canvas-writing-workspaces"}
  }
]
```

Create an `IMPORT` change set with that template and resource identifier file.
Import cannot be combined with resource creation or configuration changes [12].
If cancellation occurred before point-in-time recovery was enabled, import the
actual disabled state; the subsequent permissions update enables it. Do not
delete the retained table to make a retry succeed.

## Official documentation

- [1] `https://docs.aws.amazon.com/AmazonECS/latest/developerguide/s3files-volumes.html`
- [2] `https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-filesystem-configurations.html`
- [3] `https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html`
- [4] `https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html`
- [5] `https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-files-prereq-policies.html`
- [10] `https://docs.aws.amazon.com/service-authorization/latest/reference/list_s3files.html`
- [11] `https://docs.aws.amazon.com/service-authorization/latest/reference/list_logs.html`
- [12] `https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/import-resources-manually.html`
- Runtime IAM: `https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html`
- Files pricing behavior: `https://aws.amazon.com/s3/pricing/`
- Runtime pricing behavior: `https://aws.amazon.com/bedrock/agentcore/pricing/`
