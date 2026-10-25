# Model catalog production release — 2026-10-25

Completed at **05:32 UTC** for `canvas.hi-yoo.com`.

The production catalog now contains Claude Opus/Sonnet/Haiku 5.5, Claude Fable
5.1, GPT-6.1 Sol, GPT-6 Astra, GPT-6 Luna, Grok 4.7, and Kimi K3. Nova and
DeepSeek are removed. Global Claude Opus 5.5 remains the default.

## Deployment

- Release record: `models-20261025T050805Z`.
- Application stack: `HtmlCanvasStack`, `UPDATE_COMPLETE`.
- ECS task definition: `HtmlCanvasStackTaskDef2E995DD4:13`.
- Service: one running task, zero pending, rollout `COMPLETED`.
- Both containers and the single ALB target are healthy.
- Backend image digest:
  `sha256:046cc61763f2b21795f1973f031aee254fb7f5cacafa5fef56a2099ccff29694`.
- Retained frontend digest:
  `sha256:b4d5980d525059c76777a84fb279e3caaee5b9f73d8074fa4078b6fefb015ce0`.

A concurrent workspace release completed while this change was being prepared.
The model update was rebased onto that release before deployment. The reviewed
CloudFormation change set modifies the backend image and the dependent ECS
service. Authentication, workspace mounts, storage, roles, and compute capacity
are preserved.

The existing AgentCore runtime version 2 already included the same catalog and
Kimi history compatibility handling. Its newer image was reused:
`sha256:6e770c6dd9fd709c678edf6a607d8c24834873cae634b7f07135557a149cc105`.

## Live verification

- All nine models completed synthetic Converse requests through the deployed
  application's AWS task role in `us-east-1`.
- All nine models completed requests through the real AgentCore runtime in
  `ap-northeast-2`, using its execution role and mounted filesystem.
- Agent checks used a freshly generated, empty temporary workspace. No user
  documents were read and no edits were proposed. The temporary directories
  were removed after verification.
- The final backend container passed 72 regression tests and 64 subtests.
- The existing production frontend displayed and selected all nine options
  against the new catalog during the isolated browser check.
- Public requests to `/` and `/api/models/list` still redirect unauthenticated
  visitors to the existing Cognito domain.
- CloudFormation validation passed. The three existing `W3005` dependency
  warnings remain; no unrelated resources were changed to silence them.
- Temporary verification tasks stopped successfully, their task definitions
  were deregistered, and local preview containers and registry credentials
  were removed.

These checks establish access for this deployment and the tested global
profiles. They do not establish access for other AWS accounts or every
geographic profile.

## Fable data retention

The existing `us-east-1` setting, `provider_data_share`, already satisfied
Fable's access requirement. AWS documents this as a compatible legacy setting.
It was preserved.

The Seoul setting was changed from `inherit` to `aws_review` to enable the
requested Fable model in AgentCore. Before the change, a real Fable request
failed because the effective mode was `default`; afterward, the runtime check
passed. This permits retention and human review by AWS for models requiring
it. It does not share content with model providers.

Source: [AWS data retention documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/data-retention.html).

## Rollback and audit records

The immediate application rollback target is
`HtmlCanvasStackTaskDef2E995DD4:12`, which includes the preceding workspace
release. Use `application-deployment-baseline.json` from this release's backup
to prepare a rollback change set. The older revision 11 is an initial discovery
snapshot and is not the rollback target for this model update.

Private records are stored under:

```text
~/.local/state/open-canvas-deployments/models-20261025T050805Z/
s3://cdk-hnb659fds-assets-913524902871-ap-northeast-2/open-canvas-deployments/models-20261025T050805Z/
```

Records include the deployment baseline, reviewed change set, immutable images,
live test results, data-retention change, and final service state. S3 backups
are private and encrypted. Registry credentials are excluded.
