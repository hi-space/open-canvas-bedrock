"""Deep research jobs: research the request and propose the result as a new project file.

Runs the deep research graph in this process (it needs Tavily, the drawio CLI and Chrome on this server)
and returns the same shape as the workspace agent runtime, so run_job validates and stores it unchanged.
"""
import asyncio
import hashlib
import re
import unicodedata

from langchain_core.messages import AIMessage, HumanMessage

from api.writing.models import WritingSource

MAX_SOURCES = 50
MAX_EXCERPT_CHARACTERS = 100000
MAX_EXCERPT_PER_SOURCE = 4000
MIN_EXCERPT_PER_SOURCE = 300
HEARTBEAT_SECONDS = 60


class ResearchError(ValueError):
    """A problem the person can fix; its message is shown on the failed job."""
GENRE_LABELS = {"paper": "논문", "blog": "블로그", "linkedin": "LinkedIn"}


def source_id(url: str) -> str:
    return "research-" + hashlib.sha256(url.encode()).hexdigest()[:24]


def document_path(title: str, existing: set[str]) -> str:
    # Letters, digits, spaces and hyphens only: titles carry emoji (LinkedIn) and punctuation.
    cleaned = "".join(c if unicodedata.category(c)[0] in "LN" or c in " -" else "-" for c in title)
    stem = re.sub(r"-{2,}", "-", re.sub(r" *- *", "-", cleaned)).strip(" .-")[:80].strip(" .-") or "research"
    path, number = f"research/{stem}.md", 2
    while path in existing:
        path, number = f"research/{stem}-{number}.md", number + 1
    return path


def _excerpt(source: dict, findings: list[dict], limit: int) -> str:
    """The evidence a reviewer needs to check the citation: what was taken from the page, then the page."""
    taken = [
        f"- {f['claim']}" + (f" ({f['detail']})" if f.get("detail") else "") + (f"\n  \"{f['quote']}\"" if f.get("quote") else "")
        for f in findings if source["id"] in f["source_ids"]
    ]
    text = "\n".join(taken)
    if len(text) < limit:
        text = (text + "\n\n" + source.get("content", "")).strip()
    return text[:limit]


def _messages(payload: dict):
    history = [
        HumanMessage(content=item["content"]) if item["role"] == "user" else AIMessage(content=item["content"])
        for item in payload.get("history", [])[-10:]
    ]
    return [*history, HumanMessage(content=payload["message"])]


async def _run_graph(payload: dict, slots: int, progress) -> dict:
    from agents.deep_research.graph import graph

    from agents.deep_research.search import SearchUnavailable

    state: dict = {}
    last = ["리서치를 계획하고 있습니다."]

    async def heartbeat():
        # Writing a paper's final pass can outlast the job's stall timeout between node updates.
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            progress(last[0])

    config = {"configurable": {"customModelName": payload["model"]}}
    inputs = {"messages": _messages(payload), "genre": payload["researchGenre"], "maxCitedSources": slots}
    beat = asyncio.create_task(heartbeat())
    try:
        async for update in graph.astream(inputs, config=config, stream_mode="updates"):
            for node_output in update.values():
                if not isinstance(node_output, dict):
                    continue
                state.update({k: v for k, v in node_output.items() if k != "messages"})
                if node_output.get("researchStatus"):
                    last[0] = node_output["researchStatus"]
                    progress(last[0])
    except SearchUnavailable as error:
        raise ResearchError("웹 검색이 설정되지 않았습니다. 서버의 TAVILY_API_KEY를 확인해 주세요.") from error
    finally:
        beat.cancel()
    return state


def run_research(payload: dict, existing_paths: set[str], progress) -> dict:
    existing = payload.get("sources", [])
    slots = MAX_SOURCES - len(existing)
    budget = MAX_EXCERPT_CHARACTERS - sum(len(item.get("excerpt") or "") for item in existing)
    if slots <= 0 or budget < MIN_EXCERPT_PER_SOURCE:
        raise ResearchError("프로젝트 출처 한도가 가득 찼습니다. 출처를 정리한 뒤 다시 요청해 주세요.")
    state = asyncio.run(_run_graph(payload, min(slots, budget // MIN_EXCERPT_PER_SOURCE), progress))

    markdown = state["artifact"]["contents"][0]["fullMarkdown"]
    title = state["artifact"]["contents"][0].get("title") or "research"
    known_urls = {item["url"] for item in existing if (item.get("excerpt") or "").strip()}
    cited = [s for s in state.get("sources", {}).values() if s["url"] in markdown and s["url"] not in known_urls]
    per_source = min(MAX_EXCERPT_PER_SOURCE, budget // max(len(cited), 1))
    sources = [
        WritingSource(
            id=source_id(s["url"]), title=(s.get("title") or s["url"])[:500], url=s["url"],
            excerpt=_excerpt(s, state.get("findings", []), per_source),
        ).model_dump(exclude_none=True)
        for s in cited
    ]
    path = document_path(title, existing_paths)
    figures = len(state.get("figures") or [])
    explanation = (
        f"딥 리서치({GENRE_LABELS[payload['researchGenre']]}): 출처 {len(state.get('sources', {}))}개를 검토해 "
        f"근거 {len(state.get('findings', []))}개를 정리하고, 인용 출처 {len(cited)}개와 그림 {figures}개로 작성했습니다."
    )
    return {
        "message": f"{explanation}\n\n새 문서 `{path}` 수정안을 검토해 주세요.",
        "sources": sources,
        "proposals": [{
            "path": path, "baseVersion": None, "baseContent": "", "proposedContent": markdown,
            "explanation": explanation,
        }],
    }
