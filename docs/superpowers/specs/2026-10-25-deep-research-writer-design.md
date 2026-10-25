# Deep Research Writer — design

## Why

The current path for "research and write" is: one LLM-rewritten query → one Tavily `basic` search (5 snippets)
→ one message stuffed into `generateArtifact`, whose prompt has no notion of genre. The result is shallow: no
sub-questions, no full-text reading, no gap filling, no outline, no evidence tracking, one-shot writing.

Goal: a writer that researches like a careful analyst and writes like an expert in the chosen genre, with
figures when they help — the quality one gets when driving Claude Code by hand. Single user (the owner),
runs on this server, LangGraph + Bedrock only (no Agent SDK).

## Decisions (owner)

- Genres: `paper` (academic), `blog` (technical blog), `linkedin` (post). Selected in the composer.
- Diagrams via the installed skills' deterministic tooling: aws-drawio-diagram (brief → spec → .drawio → PNG)
  for AWS architectures, aws-diagram-design `awsdiag.Canvas` for concept/process figures.
- No Claude Agent SDK.

## Pipeline (`agents/deep_research`)

```
planResearch → searchSources → extractFindings ─┬─(gaps & rounds left)→ searchSources
                                                 └→ buildOutline → createDiagrams → draftSections
                                                    → reviewDraft → generateArtifact
```

| Node | Does |
|---|---|
| planResearch | Brief: title, audience, thesis, language, N sub-questions with search queries (N from genre profile) |
| searchSources | Parallel Tavily `advanced` search with raw markdown content; dedupe by URL; source registry `S1..Sn` |
| extractFindings | Per sub-question (parallel): evidence-backed findings `{claim, detail, quote, sources}` + gaps + follow-up queries |
| (loop) | `should_continue_research` — another round while gaps remain and the genre budget allows |
| buildOutline | Genre-shaped outline; each section gets its finding ids, word budget, optional figure request |
| createDiagrams | Renders requested figures to PNG under `RESEARCH_ASSETS_DIR`, served at `/api/research/assets/...` |
| draftSections | Parallel evidence-grounded drafts, citing `[S#]` only from assigned findings |
| reviewDraft | Genre rubric + citation fidelity critique → per-section revision notes |
| generateArtifact | Sequential final pass per section (streams to canvas), applies notes, keeps flow; assembles figures and references |

Named `generateArtifact` so the existing frontend streams it into the canvas. The node's final output carries
the assembled markdown (figures, numbered references), which the frontend now applies on `on_chain_end`.

## Genre profiles (`genres.py`)

Research depth, source budget, structure, length, citation style, figure budget and voice differ per genre.
LinkedIn loads the owner's `linkedin-writer` style guide when present (`LINKEDIN_STYLE_GUIDE_PATH`).

## Non-goals

- Editing an existing artifact through research (turn the genre off to edit normally).
- Multi-user cost controls.

## Failure behaviour

- No `TAVILY_API_KEY` → explicit error (no silent knowledge-only writing).
- A diagram that fails validation after retries is skipped and logged; the document still ships.
- Unknown `[S#]` citations are dropped at assembly, never turned into links.
