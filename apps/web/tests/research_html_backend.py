"""Local-only browser fixture: real research graph/API, deterministic external boundaries.

Run from apps/backend with PYTHONPATH=. and a temporary WORKSPACE_ROOT:
  WORKSPACE_AUTH_MODE=local .venv/bin/python ../web/tests/research_html_backend.py
"""
import json
import os
from typing import ClassVar

import uvicorn
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from PIL import Image, ImageDraw, ImageFont

if os.environ.get("WORKSPACE_AUTH_MODE") != "local" or not os.environ.get("WORKSPACE_ROOT"):
    raise RuntimeError("Use explicit local mode and a temporary WORKSPACE_ROOT for this fixture.")
os.environ.update(STORAGE_TYPE="memory", WORKSPACE_METADATA="file", FIRECRAWL_API_KEY="",
                  LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false")

from main import app
from agents.deep_research import nodes
from agents.deep_research.diagrams.assets import asset_url, run_dir
from api.workspaces import research, service

TITLE = "프로젝트 자료로 완성한 리서치 보고서"
NATIVE_ONLY = os.environ.get("NATIVE_HTML_DIAGRAMS_ONLY") == "1"
SOURCE = "https://example.org/project-guide"
WEB = "https://example.org/evaluation"
BRIEF = {
    "title": TITLE, "language": "ko", "audience": "프로젝트 팀",
    "thesis": "프로젝트 제약과 검증한 근거를 함께 사용한다",
    "questions": [{"id": "Q1", "question": "자료를 어떻게 비교하는가?", "queries": ["document evaluation"]}],
}
OUTLINE = {
    "title": TITLE,
    "sections": [
        {"id": "s1", "heading": "프로젝트의 출발점", "goal": "제약", "key_points": ["프로젝트 자료"],
         "finding_ids": ["F1"], "words": 100},
        {"id": "s2", "heading": "근거와 처리 흐름", "goal": "비교", "key_points": ["정확한 인용"],
         "finding_ids": ["F1", "F2"], "words": 100,
         "figure": {"kind": "concept", "request": "Project files -> Research -> HTML report", "caption": "자료에서 보고서까지",
                    "renderer": "native" if NATIVE_ONLY else "skill"}},
        {"id": "s3", "heading": "팀이 확인할 다음 단계", "goal": "적용", "key_points": ["검토"],
         "finding_ids": ["F2"], "words": 100},
    ],
}
SECTIONS = {
    "s1": "## 프로젝트의 출발점\n\n프로젝트 자료 brief.md의 대상은 **세 팀**입니다. 확인한 원문을 함께 비교합니다 [S1].",
    "s2": (
        "## 근거와 처리 흐름\n\n검증용 예시 수치입니다 [S1, S2].\n\n"
        "| 방식 | 예시 정확도 |\n| --- | ---: |\n| 기존 방식 | 87% |\n| 개선 방식 | 91% |\n\n"
        "```python\nprint('Keep the evidence with the report')\n```"
    ),
    "s3": "## 팀이 확인할 다음 단계\n\n원문 링크와 다이어그램을 검토한 뒤 문서를 승인합니다 [S2].",
}
invocations = []
skill_calls = []
if NATIVE_ONLY:
    OUTLINE["sections"][0]["figure"] = {
        "kind": "concept", "request": "Explain the architecture layers and responsibilities",
        "caption": "컴포넌트의 책임과 계층", "renderer": "auto",
    }


class FixtureModel(BaseChatModel):
    inputs: ClassVar[list] = []

    @property
    def _llm_type(self):
        return "research-html-browser-fixture"

    def _reply(self, messages):
        system = messages[0].content
        self.inputs.append(messages[1].content)
        if "technical diagram designer" in system:
            return json.dumps({
                "title": "문서 리서치의 내부 구조",
                "description": "API는 작업을 접수하고, 리서치 그래프는 문서를 읽어 HTML 어댑터에 근거를 전달합니다.",
                "layout": "layers" if "architecture layers" in messages[1].content else "flow",
                "rows": [
                    {"label": "요청과 실행", "nodes": [
                        {"id": "api", "label": "Workspace API", "detail": "요청과 문서 버전 확인", "kind": "input"},
                        {"id": "research", "label": "Research graph", "detail": "검색 · 근거 추출 · 집필", "kind": "service"},
                    ]},
                    {"label": "프로젝트 자료와 출력", "nodes": [
                        {"id": "files", "label": "Project files", "detail": "선택한 문서 스냅샷", "kind": "store"},
                        {"id": "html", "label": "HTML adapter", "detail": "본문 · 인용 · 도식 조립", "kind": "service"},
                    ]},
                ],
                "edges": [
                    {"source": "api", "target": "research", "label": "POST /chat · 조사 요청"},
                    {"source": "research", "target": "files", "label": "선택한 문서 읽기"},
                    {"source": "files", "target": "research", "label": "고정된 버전과 본문"},
                    {"source": "research", "target": "html", "label": "근거 · 본문 · 도식 명세"},
                ],
            }, ensure_ascii=False)
        if "research lead" in system:
            return json.dumps(BRIEF, ensure_ascii=False)
        if "research analyst" in system:
            return json.dumps({
                "findings": [
                    {"claim": "기존 방식 예시 87%", "source_ids": ["S1"], "strength": "strong"},
                    {"claim": "개선 방식 예시 91%", "source_ids": ["S2"], "strength": "strong"},
                ],
                "gaps": [], "follow_up_queries": [],
            })
        if "editor-in-chief" in system:
            return json.dumps(OUTLINE, ensure_ascii=False)
        if "senior reviewer" in system:
            return json.dumps({"global_notes": [], "sections": [{"id": "s1", "score": 5, "notes": []}]})
        for section in OUTLINE["sections"]:
            if f'id="{section["id"]}" heading=' in messages[1].content:
                return SECTIONS[section["id"]]
        raise AssertionError("Unexpected fixture model request")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content=self._reply(messages), response_metadata={"stopReason": "end_turn"},
        ))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        text = self._reply(messages)
        yield ChatGenerationChunk(message=AIMessageChunk(
            content=text, response_metadata={"stopReason": "end_turn"},
        ))


async def search(queries, _max_results):
    return [[{"url": WEB, "title": "검증용 평가", "content": "개선 방식 예시 91%. " * 30,
              "snippet": "비교 자료", "score": 1.0}] for _ in queries]


async def figure(_model, _kind, _request, _evidence, _language, owner, run_id, slug):
    skill_calls.append(slug)
    if NATIVE_ONLY:
        raise AssertionError("Native HTML must not call a rasterizer.")
    image = Image.new("RGB", (960, 240), "#edf3eb")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("DejaVuSans.ttf", 22)
    for index, label in enumerate(("Project files", "Research", "HTML report")):
        x = 32 + index * 318
        draw.rounded_rectangle((x, 70, x + 255, 170), 12, fill="#ffffff", outline="#246a56", width=3)
        draw.text((x + 24, 105), label, font=font, fill="#19392f")
        if index < 2:
            draw.line((x + 267, 120, x + 302, 120), fill="#246a56", width=4)
            draw.polygon([(x + 302, 120), (x + 292, 114), (x + 292, 126)], fill="#246a56")
    image.save(run_dir(owner, run_id) / f"{slug}.png")
    return asset_url(run_id, f"{slug}.png")


real_run_graph = research._run_graph


async def record_graph(payload, slots, progress):
    invocations.append({"context": payload.get("projectContext", []), "format": payload.get("outputFormat")})
    return await real_run_graph(payload, slots, progress)


nodes.get_model = lambda *_args, **_kwargs: FixtureModel()
nodes.search_many = search
nodes.available_kinds = lambda: [] if NATIVE_ONLY else ["concept"]
nodes.render_figure = figure
research._run_graph = record_graph
service.invoke_agent = lambda _payload: {"message": "리서치 브라우저 검증용 실행입니다.", "proposals": []}


@app.get("/__test/research-inputs")
def inputs():
    return invocations


@app.get("/__test/diagram-calls")
def diagram_calls():
    return {"skillCalls": skill_calls, "nativeOnly": NATIVE_ONLY}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("RESEARCH_HTML_TEST_PORT", "9017")),
                log_level="warning")
