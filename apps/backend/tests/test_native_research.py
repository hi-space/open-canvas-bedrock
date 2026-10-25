"""HTML research chooses native technical diagrams and embeds trusted figures."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agents.deep_research import nodes
from agents.deep_research.assemble import assemble
from agents.deep_research.genres import get_profile
from agents.deep_research.schemas import Outline
from api.workspaces.html_documents import validate_html
from api.workspaces.research_html import render_research_html

MARKUP = (
    '<div><svg viewBox="0 0 400 100" role="img" aria-label="API 호출">'
    '<rect x="10" y="10" width="120" height="60"/><path d="M 130 40 L 260 40"/>'
    '<text x="20" y="45">API</text></svg><p>JSON 요청을 처리합니다.</p></div>'
)
OUTLINE = {
    "title": "처리 구조", "sections": [
        {"id": "s1", "heading": "API 처리", "goal": "구조", "key_points": ["요청"], "finding_ids": ["F1"],
         "words": 300, "figure": {"kind": "concept", "request": "API -> worker", "caption": "요청 경로"}},
    ],
}
STATE = {
    "genre": "blog", "outputFormat": "html", "messages": [],
    "brief": {"title": "구조", "audience": "개발자", "thesis": "호출 구조", "language": "ko",
              "questions": [{"id": "Q1", "question": "처리 순서", "queries": ["API flow"]}]},
    "outline": OUTLINE,
    "findings": [{"id": "F1", "question_id": "Q1", "claim": "API passes JSON", "strength": "strong",
                  "source_ids": ["S1"]}],
    "sources": {"S1": {"id": "S1", "url": "https://example.org/api", "title": "API", "content": "JSON calls"}},
    "runId": "run123",
}


def test_html_planning_keeps_technical_figures_when_no_skills_are_installed():
    with patch.object(nodes, "available_kinds", return_value=[]), \
            patch.object(nodes, "get_model", return_value=object()), \
            patch.object(nodes, "ainvoke_json", new=AsyncMock(return_value=Outline.model_validate(OUTLINE))):
        result = asyncio.run(nodes.build_outline_node(STATE, {}))
    assert result["outline"]["sections"][0]["figure"] is not None


def test_html_uses_native_without_skills_or_asset_owner():
    with patch.object(nodes, "available_kinds", return_value=[]), \
            patch.object(nodes, "get_model", return_value=object()), \
            patch.object(nodes, "create_native", create=True,
                         new=AsyncMock(return_value={"markup": MARKUP, "summary": "JSON 요청", "layout": "flow"})), \
            patch.object(nodes, "render_figure", new=AsyncMock()) as skill:
        result = asyncio.run(nodes.create_diagrams_node(STATE, {}))
    assert len(result["figures"]) == 1
    assert result["figures"][0]["renderer"] == "native"
    assert result["figures"][0]["markup"] == MARKUP
    assert result["figures"][0]["source_ids"] == ["S1"]
    skill.assert_not_called()


def test_an_explicit_available_skill_is_used_and_native_recovers_a_failed_skill():
    outline = {**OUTLINE, "sections": [{**OUTLINE["sections"][0], "figure": {
        **OUTLINE["sections"][0]["figure"], "renderer": "skill", "reason": "공식 서비스 아이콘",
    }}]}
    state = {**STATE, "assetOwner": "a" * 64, "outline": outline}
    for url in ("/api/research/assets/run123/fig1.png", None):
        with patch.object(nodes, "available_kinds", return_value=["concept"]), \
                patch.object(nodes, "get_model", return_value=object()), \
                patch.object(nodes, "create_native", create=True,
                             new=AsyncMock(return_value={"markup": MARKUP, "summary": "JSON 요청", "layout": "flow"})), \
                patch.object(nodes, "render_figure", new=AsyncMock(return_value=url)) as skill:
            result = asyncio.run(nodes.create_diagrams_node(state, {}))
        skill.assert_awaited_once()
        assert result["figures"][0]["renderer"] == ("skill" if url else "native")


def test_native_figures_are_placed_with_captions_and_citations_without_image_urls():
    figure = {"section_id": "s1", "number": 1, "kind": "concept", "renderer": "native",
              "caption": "요청 경로", "markup": MARKUP, "summary": "JSON 요청", "source_ids": ["S1"],
              "source_urls": ["https://example.org/api"]}
    markdown = assemble(
        "처리 구조", [("s1", "## API 처리\n\n요청을 전달합니다 [S1]."), ("s2", "## 다음 단계\n\n완료.")],
        [figure], STATE["sources"], get_profile("blog"), "ko",
    )
    result = render_research_html(markdown, "처리 구조", sources=[
        {"id": "reference", "url": "https://example.org/api", "excerpt": "JSON calls"},
    ], genre="blog", figures=[figure])
    validate_html(result, {"reference"})
    assert "<svg" in result and "<img" not in result
    assert "oc-diagram:" not in result
    assert result.index("<svg") < result.index(">다음 단계</h2>")
    assert "그림 1. 요청 경로" in result
    assert result.count('href="https://example.org/api"') >= 2
    assert 'data-source-ids="[&quot;reference&quot;]"' in result


def test_unknown_native_placeholders_cannot_become_broken_or_untrusted_images():
    with pytest.raises(ValueError):
        render_research_html("![unknown](oc-diagram:figure-999)", "Unknown", sources=[], genre="blog")
