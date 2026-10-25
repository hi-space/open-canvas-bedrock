# Backend dependencies and Bedrock models

Checked on **2026-10-25**. Recheck model availability after **2026-11-08**.

The writing workspace uses the stateless Bedrock Converse API. It does not create
or update a conversation, thread, server file, or stored artifact. The browser
owns the proposed text, review decisions, and explicit disk save.

## Current model catalog

The backend serves the catalog through `GET /api/models/list`; the existing
`models`, `defaultModelName`, and `defaultModelConfig` response fields are
preserved. The frontend loads this response rather than maintaining another
selectable model list.

| Canonical model | Catalog model ID | Lifecycle | Access from `us-east-1` | Confidence | confirmed_date | valid_until |
| --- | --- | --- | --- | --- | --- | --- |
| Claude Opus 5.5 — default | `global.anthropic.claude-opus-5-5` | Active | Global profile and real ECS task-role inference verified | verified | 2026-10-25 | 2026-11-08 |
| Claude Sonnet 5.5 | `global.anthropic.claude-sonnet-5-5` | Active | Global profile and real ECS task-role inference verified | verified | 2026-10-25 | 2026-11-08 |
| Claude Haiku 5.5 | `global.anthropic.claude-haiku-5-5` | Active | Global profile and real ECS task-role inference verified | verified | 2026-10-25 | 2026-11-08 |
| Claude Fable 5.1 | `global.anthropic.claude-fable-5-1` | Active | Global profile and real ECS task-role inference verified | verified | 2026-10-25 | 2026-11-08 |
| GPT-6.1 Sol | `global.openai.gpt-6.1-sol` | Active | Global profile and real ECS task-role inference verified | verified | 2026-10-25 | 2026-11-08 |
| GPT-6 Astra | `global.openai.gpt-6-astra` | Active | Global profile and real ECS task-role inference verified | verified | 2026-10-25 | 2026-11-08 |
| GPT-6 Luna | `global.openai.gpt-6-luna` | Active | Global profile and real ECS task-role inference verified | verified | 2026-10-25 | 2026-11-08 |
| Grok 4.7 | `global.xai.grok-4.7` | Active | Global profile and real ECS task-role inference verified | verified | 2026-10-25 | 2026-11-08 |
| Kimi K3 | `global.moonshotai.kimi-k3` | Active | Global profile and real ECS task-role inference verified | verified | 2026-10-25 | 2026-11-08 |

These are curated, current text-writing choices from Anthropic, OpenAI, xAI,
and Moonshot AI. The GPT choices follow OpenAI's current model families;
their Bedrock IDs and API compatibility are checked separately in AWS model
cards. All nine entries use the existing AWS credential chain and Bedrock
Converse path; no direct-provider API keys are needed.

Nova, DeepSeek, Llama, and older Claude entries are removed from both the
selectable catalog and the request allowlist, including their old geographic
aliases. This is a product catalog decision, not a claim that every removed
model has reached AWS end of life. A saved unsupported model selection must
be replaced with a current catalog choice. Claude Mythos 5.1 is not included:
its AWS model card identifies it as a gated preview for approved organizations.

The model cards document output ceilings of 128K for Claude, GPT-6 Astra, and
GPT-6 Luna, and 131,072 for GPT-6.1 Sol. Grok 4.7 and Kimi K3 use a conservative
application output cap of 32,768; this is not their provider context window
or a claimed provider maximum. Grok shares its 524,288-token context between
input and output. The general canvas default remains 4,096 output tokens.
A writing proposal requests at most 32,768 tokens, bounded by the catalog
limit. A response stopped by a token/context limit is rejected, including if
its partial output happens to parse as JSON.

### Configuration

Configure the server before starting it:

```dotenv
BEDROCK_MODEL_ID=global.anthropic.claude-opus-5-5
BEDROCK_REGION=us-east-1
```

Region resolution is `configurable.region` for existing graph callers, then
`BEDROCK_REGION`, `AWS_REGION`, `AWS_DEFAULT_REGION`, and finally `us-east-1`.
The writing endpoint ignores the proxy's additional graph `config` field and
uses the server's region. `model` may select an allowlisted model; an omitted
model uses `BEDROCK_MODEL_ID`.

Documented geographic profile variants are also accepted: `us`, `eu`, and `au`
for the three Claude 5.5 models; `jp` for Opus and Haiku; `us` for Fable, GPT,
and Grok; and `us` and `in` for Kimi K3. A configured geographic default is
included in the catalog.
Use a source region from the selected profile's AWS model-card table, for
example `eu.anthropic.claude-sonnet-5-5` from `eu-west-1`. Opus 5.5's bare
`anthropic.claude-opus-5-5` ID is documented for in-region access in `eu-west-2`
only. The new GPT, Grok, Fable, and Kimi entries require inference profile IDs;
their bare model IDs are not accepted by this Converse integration.
Global profiles can route processing across regions; select a documented
geographic profile when the application's data-location requirements need it.

Credentials come from boto3's server-side credential chain, including
environment credentials with `AWS_SESSION_TOKEN`, AWS profiles/SSO, and
workload roles. Credentials supplied in a browser request are not used.
Both runtime and control-plane clients receive the same resolved region and
session before the LangChain model is constructed.

Model visibility does not establish account access. Fable 5.1 requires the
account's data-retention mode to be `aws_review` or the compatible legacy
`provider_data_share` mode; this application does not change that setting
automatically. The production release explicitly enabled `aws_review` in Seoul.
GPT model cards require invocation
permission for the selected inference profile and the account's
`arn:aws:bedrock:{region}:{account-id}:project/default` resource. The AgentCore
deployment template includes that default-project resource in its model
invocation policy. Existing deployments need the updated policy and images
before these changes take effect.

### Sampling and tool compatibility

The catalog uses provider-default reasoning settings and omits sampling for
all nine models, including when an older canvas caller requests temperature
zero. Claude Fable 5.1 requires temperature 1.0 or unset, and several Claude
and GPT reasoning modes restrict sampling. Keeping provider defaults for Grok
and Kimi is an application choice, not a claim that they cannot accept
temperature. A fixed backend temperature range disables the frontend control.
The `supportsReasoning` catalog field drives thinking-model handling across
all providers and geographic aliases, replacing Claude-only name matching.

The Opus/Sonnet 5.5 cards document automatic tool choice, and the current
LangChain AWS implementation rejects forced tool choice for those models.
Legacy title and reflection generation use a named tool when supported, `auto`
when supported, and omit `tool_choice` otherwise (including Kimi). Their
existing tool-result validation remains in place. The writing endpoint does
not use tool calls or force a tool to obtain JSON.
Visible-text extraction also excludes reasoning blocks so adaptive thinking is
not serialized into legacy canvas replies or parsing prompts.

AWS documents a Kimi K3 Converse limitation: replaying reasoning content from
prior assistant turns can cause `InternalServerException`. Both the workspace
agent's native Converse loop and the LangChain request boundary remove those
blocks for Kimi before a request, retaining visible text and tool calls/results
without mutating stored messages. The LangChain handling covers Converse and
ConverseStream. Other models retain their provider-specific reasoning history.

## Proposal contract and validation

`POST /api/writing/propose` accepts:

```json
{
  "document": "The complete Markdown draft.",
  "selectedText": "Optional exact selected passage.",
  "instruction": "Make this clearer.",
  "model": "global.anthropic.claude-opus-5-5",
  "sources": [
    {
      "id": "source-1",
      "title": "Source title",
      "url": "https://example.com/source",
      "excerpt": "Optional source text supplied by the user."
    }
  ]
}
```

`selectedText` present means the response replaces only that passage; absent
means the response is a complete document proposal. Selection offsets remain
on the browser so JavaScript UTF-16 offsets are never interpreted as Python
character offsets. An empty document is allowed for drafting.

Limits are 200,000 characters for a document/selection, 4,000 for the editing
instruction, 50 sources, 2,048 per source URL, 20,000 per excerpt, and 100,000
excerpt characters in total. Blank instructions, missing selections, duplicate
source IDs, unsupported model IDs, non-HTTP(S) source URLs, embedded URL
credentials, and malformed request fields are rejected.

Success has exactly two string fields:

```json
{"replacement": "Proposed Markdown text.", "explanation": "What changed."}
```

The model receives static system instructions and a separate JSON user
message. Drafts, source titles, URLs, and excerpts are explicitly untrusted
context. A title/URL alone is not evidence. Newly cited supplied sources require
a nonblank excerpt; URLs already used in the document can be preserved/reused.
Markdown links, reference links, autolinks, visible HTTP URLs, and HTML link
attributes are checked, while fenced and inline code are not interpreted as
citations. Existing citation occurrences in the revised passage must survive.
Reference definitions elsewhere in the document are available when revising a
selection.

The browser must also validate the assembled full proposal, because a selection
can bisect a link destination and the server intentionally does not receive its
offsets. Citation checks enforce source URL integrity, not factual truth.
People still review the proposed wording and its cited evidence.

Missing/unknown completion reasons, truncation, refusals, tool output, malformed
JSON, duplicate JSON keys, invalid response schemas, invented citation URLs, and
removed citations fail with an HTTP error. They never produce an approvable
replacement. A model failure returns a readable `detail` without echoing
provider request data. The request timeout is 180 seconds.

## Reference retrieval

`POST /api/firecrawl/scrape` retains its `{"urls":["https://example.com"]}` input.
It now uses the Firecrawl v2 SDK directly and runs outside the event loop.
Its response remains:

```json
{
  "success": true,
  "documents": [
    {
      "name": "example.com/source",
      "type": "text",
      "data": "Retrieved Markdown.",
      "metadata": {
        "url": "https://example.com/source",
        "title": "Source title"
      }
    }
  ]
}
```

`metadata.title` is added when available. A missing key is an error; failed
retrievals are omitted and `success` is false when none succeed. Manual source
title/excerpt entry remains available in the writing workspace.

## Python dependency audit

Stable versions were resolved from the PyPI JSON API on 2026-10-25, excluding
prereleases, yanked files, and release files dated after that day. Every retained
direct runtime dependency is pinned to that stable release.

| Dependency | Previous | Current |
| --- | --- | --- |
| [FastAPI](https://pypi.org/project/fastapi/) | 0.121.3 | 0.162.0 |
| [Uvicorn](https://pypi.org/project/uvicorn/) | 0.38.0 | 0.54.0 |
| [LangChain Core](https://pypi.org/project/langchain-core/) | Transitive | 1.7.0 |
| [LangChain AWS](https://pypi.org/project/langchain-aws/) | 1.0.0 | 1.9.0 |
| [LangGraph](https://pypi.org/project/langgraph/) | 1.0.3 | 1.2.17 |
| [Pydantic](https://pypi.org/project/pydantic/) | 2.12.4 | 2.14.1 |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | 1.2.1 | 1.2.4 |
| [boto3](https://pypi.org/project/boto3/) | 1.41.1 | 1.43.118 |
| [pypdf](https://pypi.org/project/pypdf/) | Replaces PyPDF2 3.0.1 | 6.21.2 |
| [Tavily Python](https://pypi.org/project/tavily-python/) | 0.7.13 | 0.8.5 |
| [LangSmith](https://pypi.org/project/langsmith/) | 0.4.46 | 0.14.12 |
| [Firecrawl Python](https://pypi.org/project/firecrawl-py/) | 4.8.0 | 4.54.0 |
| [markdown-it-py](https://pypi.org/project/markdown-it-py/) | New citation parser | 4.2.0 |
| [pytest](https://pypi.org/project/pytest/) — tests | New direct dev dependency | 9.1.1 |
| [HTTPX](https://pypi.org/project/httpx/) — API tests | New direct dev dependency | 0.28.1 |

Unused `langchain` and the old `langchain-community` Firecrawl adapter were
removed. The code imports `langchain-core` directly. `typing-extensions` is no
longer an unnecessary direct dependency; its resolved 4.16.0 release remains
pinned transitively. The obsolete Node PDF-parser fallback was removed along
with PyPDF2; PDF extraction uses maintained pypdf.

`apps/backend/requirements.lock.txt` records all 76 distributions in the
validated Linux/Python 3.13.8 runtime and test environment. `requirements.txt`
uses that file as constraints, and `requirements-dev.txt` adds the test tools.
The direct manifests remain the installation entry points so development-only
constraints do not install test tools in a runtime environment.

```bash
cd apps/backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

The repo-local `.venv` is ignored by `apps/backend/.gitignore`.

## Verification and limits

- **verified:** Installed the pinned dependencies in `apps/backend/.venv` and
  checked dependency consistency with `pip check`.
- **verified:** Offline API/model tests cover request validation, selection and
  whole-document output, nonmutation, citation preservation and invented URLs,
  response/refusal/truncation handling, ignored proxy configuration, credential
  and region propagation, current SDK request construction, Firecrawl v2/PDF
  migrations, and legacy tool choice compatibility. Catalog-update checks
  additionally cover new-model request construction, geographic defaults,
  rejected retired models, Kimi reasoning history, and Kimi's implicit tool
  choice. These checks stub AWS; they do not establish live model access.
- **documented:** Model IDs, lifecycle, access modes, and model capabilities
  were checked in primary AWS documentation using the AWS documentation MCP.
- **verified:** The 2026-10-25 production deployment used the real ECS task role
  to complete an Opus 5.5 writing proposal through the deployed backend image.
  The default global profile was also confirmed `ACTIVE` through the Bedrock API.
- **verified:** The runtime-injected Firecrawl credential completed a real
  reference extraction. The credential is stored in Secrets Manager.
- **verified:** The model catalog release completed real inference for all nine
  global profiles through the application task role in `us-east-1` and the
  AgentCore execution role in Seoul. Fable passed after the Seoul retention
  setting was enabled. See the [model release record](./deployment/model-catalog-2026-10-25.md).
- **needs-check:** Other accounts and geographic profile variants were not
  invoked. These production checks establish access for this deployment only.

The legacy memory store still emits Python's pre-existing `datetime.utcnow()`
deprecation warning when its reflection path is exercised. It does not fail the
test suite.

## Primary model/API sources

- [Claude Sonnet 5.5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html)
- [Claude Opus 5.5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html)
- [Claude Haiku 5.5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html)
- [Claude Fable 5.1](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-1.html)
- [GPT-6.1 Sol on Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-1-sol.html)
- [GPT-6 Astra on Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-astra.html)
- [GPT-6 Luna on Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-luna.html)
- [Grok 4.7](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-xai-grok-4-7.html)
- [Kimi K3 and Converse limitations](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-moonshot-ai-kimi-k3.html)
- [Claude Mythos 5.1 access restrictions](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-mythos-5-1.html)
- [Current OpenAI models](https://developers.openai.com/api/docs/models)
- [OpenAI latest-model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [Claude extended-thinking restrictions](https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-extended-thinking.html)
- [Claude tool-use restrictions](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages-tool-use.html)
- [Claude response and stop-reason semantics](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages-request-response.html)
