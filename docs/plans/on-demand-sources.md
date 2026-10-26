# On-demand source implementation plan

**Goal:** Keep project evidence independently of the context consumed by one job.

**Architecture:** Store immutable source bodies on the existing project mount,
pass a snapshot handle to the runtime, and expose bounded search/read operations.
The research graph retrieves evidence per question. Only consumed evidence enters
proposal validation and review records.

**Stack:** Existing Python/FastAPI, Bedrock Converse, LangGraph, shared filesystem,
DynamoDB metadata, React/TypeScript. No new external service.

**Spec:** [On-demand sources](../design/on-demand-sources.md).

**Execution:** Implement inline on `codex/on-demand-sources` in the project
checkout. The user approved the described architecture and requested the fix.
Keep the execution record here instead of a private skill scratch directory.

## Constraints

- Existing source IDs, URLs, documents and proposal history survive the change.
- No cumulative project source-count or excerpt-context gate.
- Independent live-library storage limit: 2,000 records / 32 MiB. Reaching it
  never blocks a job; new evidence remains in its proposal if not added to the library.
- Individual source input remains limited to 20,000 characters.
- Active evidence remains bounded to 50 IDs and 100,000 excerpt characters.
- A model source read returns at most 8,000 characters; research uses at most
  12 registered sources and 32,000 registered-source characters per job.
- Owner/project checks, immutable snapshots, read-only runtime and approved writes
  remain mandatory.
- Public summaries/initial prompts contain no source body. UI fetches body on demand.

## Review focus

- Legacy inline sources and pending pre-release jobs during rollout.
- Deleted or edited sources while a model job is running.
- Duplicate URLs with distinct IDs and HTML provenance.
- Relevant sources near the end of a large library; Korean queries and excerpts
  whose relevant passage is not their beginning.
- New citations without an actual read, oversized returned evidence, and runtime
  snapshot/path tampering.

## Task 1 — Immutable library and source API

**Files:** new `core/source_catalog.py`, new `api/workspaces/sources.py`;
update `api/workspaces/persistence.py`, `routes.py`.

**Interfaces:**

- `SourceLibrary(files).put(source) -> summary`
- `SourceLibrary(files).summaries() -> list[dict]`
- `SourceLibrary(files).snapshot() -> str`
- `SourceLibrary(files).read(source_id) -> dict`
- `SourceCatalog(root, owner, workspace, snapshot, sources=())`
- `catalog.list(offset, limit)`, `catalog.search(query, offset, limit)`,
  `catalog.read(source_id, offset, limit)`

- [x] Add failing tests for >50 sources / >100,000 stored characters, summary-only
  responses, lazy body access, migration, immutable snapshots, and isolation.
- [x] Run targeted tests and confirm the old source gate/contract fails.
- [x] Implement versioned body and catalog storage with atomic writes, bounded
  descriptor-based reads and lightweight metadata.
- [x] Add authenticated source detail retrieval; remove project context quotas.
- [x] Run library/API regressions.

## Task 2 — Runtime reads and consumed-evidence contract

**Files:** `workspace_agent/models.py`, `tools.py`, `agent.py`;
`api/workspaces/service.py`, `proposals.py`; `deploy/Dockerfile.agent`.

**Interfaces:** runtime input `sourceSnapshot`; tools `list_sources`,
`search_sources`, `read_source`; runtime output `sourceReads` containing source
ID, version and consumed ranges. Existing fetched `sources` remain bounded.

- [x] Add failing runtime tests proving absence of excerpts in initial input and
  presence only after a read, with working citations after selective retrieval.
- [x] Add service tests for snapshot validation, concurrent removal/edit and
  consumed-only proposal evidence.
- [x] Implement lazy source tools and per-job budgets; existing document citations
  are available through the active-file read and named in the tool instructions.
- [x] Build source snapshots at job preparation; reconstruct consumed evidence
  before creating proposals; retain safe legacy input compatibility.
- [x] Verify agent image packaging and run runtime/service tests. The existing
  `core/` copy already packages the new reader; isolated-image import tests pass.

## Task 3 — Question-based research retrieval

**Files:** `api/workspaces/research.py`, new
`api/workspaces/research_sources.py`; `agents/deep_research/nodes.py` and graph
integration as needed.

**Interfaces:** a request-local source retriever in trusted graph config returns
only matched, bounded registered evidence; `sourceReads` shares Task 2's contract.

- [x] Add failing tests for full old libraries, irrelevant-source exclusion,
  related sources at the end, follow-up retrieval and citation ID preservation.
- [x] Retrieve registered evidence by research questions and explicit/current
  document URLs. Allocate the fixed registered-evidence budget across questions.
- [x] Replace remaining-project-capacity checks with request-only citation and
  evidence budgets; persist new research evidence independently.
- [x] Run research, Markdown, HTML/native diagram and citation regressions.

## Task 4 — Source panel and release verification

**Files:** workspace types/API/controller, `SourcesPanel`, `CloudInspector`,
`ResearchOptions`; tests and docs.

- [x] Add failing UI tests for lazy excerpt viewing, retry, stale responses,
  cloud source addition past 50, and local-editor compatibility.
- [x] Implement summaries, on-demand body viewing, source search/pagination and
  accurate research hints.
- [x] Run complete backend/web suites, typecheck, lint and production build.
- [x] Exercise a deterministic browser flow with an over-old-limit library:
  view one excerpt, revise a document, produce research and approve the result.
- [x] Obtain independent whole-change review; reproduce and fix material findings.
- [x] Update user guide and verification record; commit, push and deploy through
  the existing workflow and verify the live release.

## Execution record

- 2026-10-26: Confirmed clean baseline `ca5ffb1`; created the implementation branch
  in the actual project directory so documentation stays in its `docs/`.
- User-approved architecture is the authority. Implementation details above are
  builder choices; no new service or destructive migration is planned.
- Design review ruling: retain authoritative inline source records for this
  compatibility release, deriving immutable files/indexes at job boundaries.
  This allows old API writers and image rollback without losing evidence.
  Runtime prompts, payloads and public summaries still omit the body.
- The separate reading-controls change `d4bface` appeared during implementation
  and is retained; source work does not modify its four UI files.
- Independent review: fixed the production DynamoDB key-filter restriction,
  loss of prior web evidence during URL alias merging, matching-ID order, and
  late-passage relevance. Each reproduced as RED, then passed after its fix.
- Review ruling: treat unused remainder of the registered-evidence budget as
  a coverage issue, since the final question could receive no evidence. Reads
  now shrink to the available budget rather than skipping that question.
- Automated security review: added independent storage bounds and reference-aware
  cleanup. Current sources, active jobs and retained proposals keep their versions;
  unused blobs/catalogs are reclaimed. Proposal catalogs contain only consumed
  evidence. A full library still permits jobs and retains new evidence in proposals.
- Verification: backend 417 tests plus 101 subtests; web 225 tests; Chromium with
  67 stored sources, a 137-character initial model input and one 93-character
  source read. Details are in `../verification/on-demand-sources/README.md`.
- Released source `d3cb8d99628c883b2549a8dfa6b0c2371664cc9d` through workflow
  `40284643751`; all six jobs succeeded at `2026-10-26T07:24:23Z`. Independent
  verification confirmed ECS revision 22 and AgentCore live version 9.
