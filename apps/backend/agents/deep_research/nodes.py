"""Nodes of the deep research writer graph.

Every node returns `researchStatus` first: the canvas shows it as the node's progress line.
"""
import logging
import json
import uuid
from datetime import datetime
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agents.deep_research import prompts
from agents.deep_research.assemble import assemble, figure_label
from agents.deep_research.diagrams import available_kinds, render_figure
from agents.deep_research.genres import GenreProfile, get_profile, style_guide
from agents.deep_research.llm import ainvoke_json, chunk_text, gather_limited, get_model
from agents.deep_research.schemas import Extraction, Outline, Review, ResearchBrief
from agents.deep_research.search import normalize_url, search_many
from agents.deep_research.state import DeepResearchState
from core.utils import format_messages, get_string_from_content

logger = logging.getLogger(__name__)

SOURCES_PER_EXTRACTION = {"paper": 8, "blog": 6, "linkedin": 5}
# The first round may fill only part of the source budget; the rest is kept for gap-filling rounds, which
# otherwise find the registry full and add nothing.
FIRST_ROUND_SOURCE_SHARE = 0.6
SOURCE_CHARS_IN_EXTRACTION = 7000
USER_CONTEXT_CHARS = 30000
# Output budgets include the model's reasoning tokens, which come before any visible text; tight budgets
# end answers mid-sentence (stopReason max_tokens). Billing is for tokens used, so budgets are generous.
BUDGET_JSON = 24000
BUDGET_LONG = 48000


def _say(state: DeepResearchState, ko: str, en: str) -> str:
    language = (state.get("brief") or {}).get("language", "ko")
    return ko if language.lower().startswith("ko") else en


def _profile(state: DeepResearchState) -> GenreProfile:
    return get_profile(state.get("genre") or "blog")


def _user_context(state: DeepResearchState) -> str:
    conversation = format_messages(state.get("messages", []), max_length=USER_CONTEXT_CHARS)
    return conversation + _project_material(state)


def _project_material(state: DeepResearchState) -> str:
    documents = state.get("projectContext") or []
    if not documents:
        return ""
    data = json.dumps(documents, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
    return f"\n\n<project-material>\n{data}\n</project-material>"


def _supplied_sources(state: DeepResearchState, questions: list) -> dict:
    sources, seen = {}, set()
    for source in state.get("suppliedSources") or []:
        content = source.get("excerpt") or ""
        url = source.get("url")
        if not content.strip() or not url or normalize_url(url) in seen:
            continue
        seen.add(normalize_url(url))
        sid = f"S{len(sources) + 1}"
        sources[sid] = {
            "id": sid, "url": url, "title": source.get("title") or url,
            "content": content, "question_ids": [question.id for question in questions],
            "origin": "supplied", "score": 1.0,
        }
    return sources


def _brief_text(brief: dict) -> str:
    return (
        f"Title: {brief['title']}\nAudience: {brief['audience']}\nThesis: {brief['thesis']}\n"
        f"Language: {brief['language']}"
    )


def _finding_line(f: dict, full: bool = False) -> str:
    line = f"{f['id']} [{f['question_id']}, {f['strength']}] {f['claim']} ({', '.join(f['source_ids'])})"
    if full:
        if f.get("detail"):
            line += f"\n    detail: {f['detail']}"
        if f.get("quote"):
            line += f"\n    quote: \"{f['quote']}\""
    return line


def _sources_for(findings: list[dict], sources: dict) -> str:
    ids = sorted({sid for f in findings for sid in f["source_ids"] if sid in sources}, key=lambda s: int(s[1:]))
    return "\n".join(
        f"{sid}: {sources[sid]['title']} ({sources[sid]['url']}"
        f"{', ' + sources[sid]['publishedDate'][:10] if sources[sid].get('publishedDate') else ''})"
        for sid in ids
    )


def _citation_rule(profile: GenreProfile) -> str:
    if profile.citation_style == "links":
        return ("do not use [S#] markers. Mention at most 3 of the most useful sources as plain URLs in the "
                "closing, taken from the source list.")
    return ("put [S#] markers right after the claim they support, e.g. \"... 40% lower latency [S3].\" or "
            "[S3, S7]. Only use source ids attached to the findings you were given; never cite finding ids (F#).")


def _heading_rule(profile: GenreProfile, section: dict) -> str:
    if profile.name == "linkedin":
        return "the post's emoji title line"
    return f"\"## {section['heading']}\""


# ---------------------------------------------------------------------------- research

async def plan_research_node(state: DeepResearchState, config: RunnableConfig) -> Dict[str, Any]:
    profile = _profile(state)
    system = prompts.PLAN_SYSTEM.format(
        genre_label=profile.label, today=datetime.now().strftime("%B %d, %Y"),
        min_q=profile.sub_questions[0], max_q=profile.sub_questions[1], queries=profile.queries_per_question,
    )
    brief = await ainvoke_json(
        get_model(config, BUDGET_JSON), system, f"<conversation>\n{_user_context(state)}\n</conversation>", ResearchBrief
    )
    brief.questions = brief.questions[: profile.sub_questions[1]]
    pending = [
        {"question_id": q.id, "query": query}
        for q in brief.questions for query in q.queries[: profile.queries_per_question]
    ]
    brief_dict = brief.model_dump()
    status_state = {"brief": brief_dict}
    return {
        "researchStatus": _say(
            status_state,
            f"리서치 계획: 하위 질문 {len(brief.questions)}개, 검색 쿼리 {len(pending)}개 — {brief.thesis}",
            f"Research plan: {len(brief.questions)} sub-questions, {len(pending)} queries — {brief.thesis}",
        ),
        "brief": brief_dict,
        "pendingQueries": pending,
        "round": 0,
        "sources": _supplied_sources(state, brief.questions),
        "findings": [],
        "extracted": [],
        "runId": uuid.uuid4().hex[:12],
    }


async def search_sources_node(state: DeepResearchState, config: RunnableConfig) -> Dict[str, Any]:
    profile = _profile(state)
    pending = state.get("pendingQueries") or []
    sources = dict(state.get("sources") or {})
    by_url = {normalize_url(s["url"]): sid for sid, s in sources.items()}
    asked_by: dict[str, list[str]] = {}  # one search per distinct query, credited to every question asking it
    for item in pending:
        asked_by.setdefault(item["query"].strip(), []).append(item["question_id"])
    results = await search_many(list(asked_by), profile.results_per_query)
    supplied_count = sum(source.get("origin") == "supplied" for source in sources.values())
    cap = supplied_count + profile.max_sources
    if state.get("round", 0) == 0 and profile.max_rounds > 1:
        cap = supplied_count + int(profile.max_sources * FIRST_ROUND_SOURCE_SHARE)
    added = 0
    for question_ids, hits in zip(asked_by.values(), results):
        for hit in hits:
            key = normalize_url(hit["url"])
            sid = by_url.get(key)
            if sid is None:
                if len(sources) >= cap:
                    continue
                sid = f"S{len(sources) + 1}"
                by_url[key] = sid
                sources[sid] = {**hit, "id": sid, "question_ids": []}
                added += 1
            for question_id in question_ids:
                if question_id not in sources[sid]["question_ids"]:
                    sources[sid]["question_ids"].append(question_id)
    return {
        "researchStatus": _say(
            state,
            f"라운드 {state.get('round', 0) + 1}: 쿼리 {len(asked_by)}개로 새 출처 {added}개 수집 (누적 {len(sources)}개)",
            f"Round {state.get('round', 0) + 1}: {len(asked_by)} queries, {added} new sources ({len(sources)} total)",
        ),
        "sources": sources,
        "pendingQueries": [],
    }


async def _extract(model, question: dict, batch: list[dict]) -> Extraction:
    docs = "\n\n".join(
        f"<source id=\"{s['id']}\" title=\"{s['title']}\" url=\"{s['url']}\" date=\"{s.get('publishedDate', '')}\">\n"
        f"{s['content'][:SOURCE_CHARS_IN_EXTRACTION]}\n</source>"
        for s in batch
    )
    user = f"<question id=\"{question['id']}\">{question['question']}</question>\n\n<sources>\n{docs}\n</sources>"
    return await ainvoke_json(model, prompts.EXTRACT_SYSTEM, user, Extraction)


async def extract_findings_node(state: DeepResearchState, config: RunnableConfig) -> Dict[str, Any]:
    profile = _profile(state)
    sources = state.get("sources") or {}
    extracted = set(state.get("extracted") or [])
    per_question = SOURCES_PER_EXTRACTION[profile.name]
    model = get_model(config, BUDGET_JSON)

    jobs = []
    for question in state["brief"]["questions"]:
        fresh = [
            s for s in sources.values()
            if question["id"] in s["question_ids"] and f"{question['id']}:{s['id']}" not in extracted
            and (len(s.get("content", "")) >= 200 or s.get("origin") == "supplied")
        ]
        fresh.sort(key=lambda s: (s.get("origin") == "supplied", s.get("score", 0)), reverse=True)
        batch = fresh[:per_question]
        if batch:
            jobs.append((question, batch))
            extracted.update(f"{question['id']}:{s['id']}" for s in batch)

    results = await gather_limited(_extract(model, q, batch) for q, batch in jobs)
    findings = list(state.get("findings") or [])
    gaps, follow_ups = [], []
    for (question, batch), result in zip(jobs, results):
        if isinstance(result, BaseException):
            logger.warning("extraction failed for %s: %s", question["id"], result)
            continue
        allowed = {s["id"] for s in batch}
        for f in result.findings:
            ids = [sid for sid in f.source_ids if sid in allowed]
            if not ids:
                continue  # a finding must point at a source the analyst actually read
            findings.append({
                "id": f"F{len(findings) + 1}", "question_id": question["id"], "claim": f.claim,
                "detail": f.detail, "quote": f.quote, "source_ids": ids, "strength": f.strength,
            })
        gaps.extend(f"{question['id']}: {g}" for g in result.gaps)
        follow_ups.extend({"question_id": question["id"], "query": q} for q in result.follow_up_queries)

    return {
        "researchStatus": _say(
            state,
            f"근거 {len(findings)}개 정리, 남은 공백 {len(gaps)}개",
            f"{len(findings)} findings, {len(gaps)} open gaps",
        ),
        "findings": findings,
        "extracted": sorted(extracted),
        "gaps": gaps,
        "pendingQueries": follow_ups,
        "round": state.get("round", 0) + 1,
    }


def should_continue_research(state: DeepResearchState) -> bool:
    """Decide whether another search round is worth its cost (≈ one minute and a dozen model calls).

    Inputs at hand: state["round"] (rounds done), _profile(state).max_rounds, state["gaps"] (open gaps,
    "Q2: no latency numbers ..."), state["pendingQueries"] (follow-up queries the analysts proposed),
    state["findings"] (each with "strength" and "question_id"), state["brief"]["questions"].

    Policy (owner): accuracy over speed. Search again while any gap is open or any sub-question still
    lacks a strong (primary, measured) finding, until the genre's round budget is spent.
    """
    profile = _profile(state)
    if state.get("round", 0) >= profile.max_rounds or not state.get("pendingQueries"):
        return False
    if state.get("gaps"):
        return True
    strong = {f["question_id"] for f in state.get("findings") or [] if f["strength"] == "strong"}
    return any(q["id"] not in strong for q in state["brief"]["questions"])


def route_after_extraction(state: DeepResearchState) -> str:
    return "prepareFollowups" if should_continue_research(state) else "buildOutline"


async def prepare_followups_node(state: DeepResearchState, config: RunnableConfig) -> Dict[str, Any]:
    """Cap and dedupe follow-up queries before the next round."""
    profile = _profile(state)
    seen, queries = set(), []
    for item in state.get("pendingQueries") or []:
        key = (item["question_id"], item["query"].strip().lower())
        if key not in seen:
            seen.add(key)
            queries.append(item)
    limit = len(state["brief"]["questions"]) * profile.queries_per_question
    return {
        "researchStatus": _say(state, f"공백을 메우는 추가 검색 {min(len(queries), limit)}건",
                               f"{min(len(queries), limit)} follow-up searches for open gaps"),
        "pendingQueries": queries[:limit],
    }


# ---------------------------------------------------------------------------- writing

async def build_outline_node(state: DeepResearchState, config: RunnableConfig) -> Dict[str, Any]:
    profile = _profile(state)
    brief = state["brief"]
    findings = state.get("findings") or []
    kinds = available_kinds()
    section_rule = (
        "exactly one section with id \"post\" (the whole post)." if not profile.sectioned
        else "the sections of the genre structure, 5-9 of them. For a paper the first section is the Abstract."
    )
    system = prompts.OUTLINE_SYSTEM.format(
        genre_label=profile.label, guide=style_guide(profile.name), section_rule=section_rule,
        min_words=profile.target_words[0], max_words=profile.target_words[1],
        max_figures=profile.max_figures if kinds else 0, figure_kinds=", ".join(kinds) or "none",
    )
    questions = "\n".join(f"{q['id']}: {q['question']}" for q in brief["questions"])
    user = (
        f"<brief>\n{_brief_text(brief)}\n</brief>\n\n<questions>\n{questions}\n</questions>\n\n"
        f"<findings>\n{chr(10).join(_finding_line(f) for f in findings)}\n</findings>\n\n"
        f"<open-gaps>\n{chr(10).join(state.get('gaps') or []) or 'none'}\n</open-gaps>\n\n"
        f"<conversation>\n{format_messages(state.get('messages', []), max_length=8000)}\n</conversation>"
        + _project_material(state)
    )
    outline = await ainvoke_json(get_model(config, BUDGET_LONG), system, user, Outline)
    if not profile.sectioned:
        outline.sections = outline.sections[:1]
        outline.sections[0].id = "post"
    known = {f["id"] for f in findings}
    figures_left = profile.max_figures if kinds else 0
    for section in outline.sections:
        section.finding_ids = [fid for fid in section.finding_ids if fid in known]
        if section.figure and (figures_left <= 0 or section.figure.kind not in kinds):
            section.figure = None
        elif section.figure:
            figures_left -= 1
    return {
        "researchStatus": _say(
            state,
            f"개요: {outline.title} (섹션 {len(outline.sections)}개, 그림 {sum(1 for s in outline.sections if s.figure)}개)",
            f"Outline: {outline.title} ({len(outline.sections)} sections, "
            f"{sum(1 for s in outline.sections if s.figure)} figures)",
        ),
        "outline": outline.model_dump(),
    }


async def create_diagrams_node(state: DeepResearchState, config: RunnableConfig) -> Dict[str, Any]:
    outline = state["outline"]
    findings = {f["id"]: f for f in state.get("findings") or []}
    language = state["brief"]["language"]
    planned = [s for s in outline["sections"] if s.get("figure")]
    if not planned:
        return {"researchStatus": _say(state, "그림 없음", "No figures planned"), "figures": []}
    if not state.get("assetOwner"):
        # Figures are readable only by their owner; without a known owner none are made.
        return {"researchStatus": _say(state, "그림 생략 (사용자 확인 불가)", "Figures skipped (no owner)"),
                "figures": []}
    model = get_model(config, BUDGET_JSON)

    async def make(index: int, section: dict):
        figure = section["figure"]
        evidence = "\n".join(_finding_line(findings[fid], full=True) for fid in section["finding_ids"] if fid in findings)
        evidence += _project_material(state)
        url = await render_figure(model, figure["kind"], figure["request"], evidence, language,
                                  state["assetOwner"], state["runId"], f"fig{index}")
        return section["id"], figure, url

    results = await gather_limited(make(i, s) for i, s in enumerate(planned, 1))
    figures = []
    for result in results:
        if isinstance(result, BaseException):
            logger.warning("figure task failed (%s)", type(result).__name__)
            continue
        if not result[2]:
            continue
        section_id, figure, url = result
        figures.append({"section_id": section_id, "number": len(figures) + 1,
                        "caption": figure["caption"], "kind": figure["kind"], "url": url})
    return {
        "researchStatus": _say(state, f"그림 {len(figures)}/{len(planned)}개 렌더링",
                               f"Rendered {len(figures)}/{len(planned)} figures"),
        "figures": figures,
    }


def _section_context(state: DeepResearchState, section: dict) -> str:
    profile = _profile(state)
    findings = {f["id"]: f for f in state.get("findings") or []}
    used = [findings[fid] for fid in section["finding_ids"] if fid in findings]
    sources = state.get("sources") or {}
    outline = "\n".join(
        f"- {s['id']}: {s['heading']} — {s['goal']}" + ("  <== YOU WRITE THIS" if s["id"] == section["id"] else "")
        for s in state["outline"]["sections"]
    )
    figure = next((f for f in state.get("figures") or [] if f["section_id"] == section["id"]), None)
    figure_note = (
        f"{figure_label(state['brief']['language'], figure['number'])} ({figure['caption']}) is placed right after "
        "this section. Refer to it by its label where it helps the reader." if figure else "No figure in this section."
    )
    return (
        f"<brief>\n{_brief_text(state['brief'])}\n</brief>\n\n"
        f"<document-outline title=\"{state['outline']['title']}\">\n{outline}\n</document-outline>\n\n"
        f"<section id=\"{section['id']}\" heading=\"{section['heading']}\" words=\"{section['words']}\">\n"
        f"Goal: {section['goal']}\nKey points:\n" + "\n".join(f"- {p}" for p in section["key_points"]) +
        f"\n</section>\n\n<findings>\n{chr(10).join(_finding_line(f, full=True) for f in used) or 'none'}\n</findings>\n\n"
        f"<sources>\n{_sources_for(used, sources) or 'none'}\n</sources>\n\n<figure>{figure_note}</figure>"
        + _project_material(state)
        + (f"\n\n<user-material>\n{format_messages(state.get('messages', []), max_length=12000)}\n</user-material>"
           if profile.name == "linkedin" else "")
    )


def _writer_system(template: str, state: DeepResearchState, section: dict) -> str:
    profile = _profile(state)
    return template.format(
        genre_label=profile.label, language=state["brief"]["language"], guide=style_guide(profile.name),
        heading_rule=_heading_rule(profile, section), citation_rule=_citation_rule(profile),
    )


def _section_tokens(section: dict) -> int:
    return BUDGET_LONG


async def draft_sections_node(state: DeepResearchState, config: RunnableConfig) -> Dict[str, Any]:
    sections = state["outline"]["sections"]

    async def draft(section: dict) -> str:
        model = get_model(config, _section_tokens(section))
        response = await model.ainvoke([
            SystemMessage(content=_writer_system(prompts.DRAFT_SYSTEM, state, section)),
            HumanMessage(content=_section_context(state, section)),
        ])
        return get_string_from_content(response.content).strip()

    results = await gather_limited(draft(s) for s in sections)
    drafts, failed = {}, []
    for section, result in zip(sections, results):
        if isinstance(result, BaseException):
            logger.warning("draft failed for %s: %s", section["id"], result)
            failed.append(section["id"])
            continue
        drafts[section["id"]] = result
    if not drafts:
        raise RuntimeError("Every section draft failed; see the backend log.")
    return {
        "researchStatus": _say(state, f"초안 {len(drafts)}개 섹션 작성", f"Drafted {len(drafts)} sections"),
        "drafts": drafts,
    }


async def review_draft_node(state: DeepResearchState, config: RunnableConfig) -> Dict[str, Any]:
    profile = _profile(state)
    drafts = state["drafts"]
    findings = state.get("findings") or []
    document = "\n\n".join(f"<section id=\"{sid}\">\n{text}\n</section>" for sid, text in drafts.items())
    system = prompts.REVIEW_SYSTEM.format(genre_label=profile.label, guide=style_guide(profile.name))
    user = (
        f"<brief>\n{_brief_text(state['brief'])}\n</brief>\n\n<draft>\n{document}\n</draft>\n\n"
        f"<evidence>\n{chr(10).join(_finding_line(f) for f in findings)}\n</evidence>"
        + _project_material(state)
    )
    try:
        review = await ainvoke_json(get_model(config, BUDGET_LONG), system, user, Review)
    except Exception as error:  # the drafts are complete; a missing review only costs polish
        logger.warning("review failed, finalizing without notes: %s", error)
        return {"researchStatus": _say(state, "검토 생략 (리뷰 응답 오류)", "Review skipped (reviewer error)"),
                "reviewNotes": {}}
    notes = {s.id: s.notes for s in review.sections if s.notes}
    notes["_global"] = review.global_notes
    scores = [s.score for s in review.sections]
    average = sum(scores) / len(scores) if scores else 0
    return {
        "researchStatus": _say(state, f"검토: 평균 {average:.1f}/5, 수정 지시 {sum(len(n) for n in notes.values())}건",
                               f"Review: average {average:.1f}/5, {sum(len(n) for n in notes.values())} edit notes"),
        "reviewNotes": notes,
    }


async def generate_artifact_node(state: DeepResearchState, config: RunnableConfig) -> Dict[str, Any]:
    """Final pass, one section at a time so each reads on from the last; tokens stream into the canvas."""
    profile = _profile(state)
    brief, outline = state["brief"], state["outline"]
    drafts, notes = state["drafts"], state.get("reviewNotes") or {}
    sections = [s for s in outline["sections"] if s["id"] in drafts]
    finals: list[tuple[str, str]] = []
    for index, section in enumerate(sections):
        previous = finals[-1][1][-1500:] if finals else "(this is the first section)"
        following = sections[index + 1]["heading"] if index + 1 < len(sections) else "(this is the last section)"
        section_notes = notes.get(section["id"], []) + notes.get("_global", [])
        user = (
            f"{_section_context(state, section)}\n\n<previous-section-ending>\n{previous}\n</previous-section-ending>\n"
            f"<next-section>{following}</next-section>\n\n<reviewer-notes>\n"
            + ("\n".join(f"- {n}" for n in section_notes) or "none") +
            f"\n</reviewer-notes>\n\n<draft>\n{drafts[section['id']]}\n</draft>"
        )
        model = get_model(config, _section_tokens(section))
        text = ""
        async for chunk in model.astream([
            SystemMessage(content=_writer_system(prompts.FINAL_SYSTEM, state, section)),
            HumanMessage(content=user),
        ]):
            text += chunk_text(chunk.content)
            if (chunk.response_metadata or {}).get("stopReason") == "max_tokens":
                logger.warning("final pass for %s hit max_tokens", section["id"])
        finals.append((section["id"], text.strip() or drafts[section["id"]]))

    markdown = assemble(outline["title"], finals, state.get("figures") or [], state.get("sources") or {},
                        profile, brief["language"], state.get("maxCitedSources"))
    artifact = {
        "type": "text",
        "contents": [{"type": "text", "index": 1, "title": outline["title"], "fullMarkdown": markdown}],
    }
    return {
        "researchStatus": _say(
            state,
            f"완성: {len(markdown.split())}단어, 출처 {len(state.get('sources') or {})}개 검토, 그림 {len(state.get('figures') or [])}개",
            f"Done: {len(markdown.split())} words, {len(state.get('sources') or {})} sources reviewed, "
            f"{len(state.get('figures') or [])} figures",
        ),
        "artifact": artifact,
        "messages": [AIMessage(content=markdown)],
    }
