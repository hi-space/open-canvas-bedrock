"""Technical native diagrams preserve semantic relationships without external renderers."""
from html.parser import HTMLParser

import pytest
from pydantic import ValidationError

from api.workspaces.html_documents import validate_html

SPEC = {
    "title": "문서 서비스 구조", "description": "API는 요청을 받고 검색기는 저장소에서 근거를 읽습니다.",
    "layout": "flow",
    "rows": [
        {"label": "요청 처리", "nodes": [
            {"id": "api", "label": "API Gateway", "detail": "HTTPS 요청 검증", "kind": "input"},
            {"id": "worker", "label": "Research worker", "detail": "검색과 근거 정리", "kind": "service"},
        ]},
        {"label": "데이터", "nodes": [
            {"id": "files", "label": "프로젝트 저장소", "detail": "버전이 고정된 문서", "kind": "store"},
        ]},
    ],
    "edges": [
        {"source": "api", "target": "worker", "label": "POST /research · JSON 요청"},
        {"source": "worker", "target": "files", "label": "문서와 버전 조회"},
        {"source": "files", "target": "api", "label": "승인된 보고서 반환"},
    ],
}


class DiagramElements(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.elements = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def render(spec):
    from agents.deep_research.diagrams.native import NativeDiagramSpec, render_native
    return render_native(NativeDiagramSpec.model_validate(spec))


def test_svg_flow_represents_every_edge_including_diagonal_and_reverse_connections():
    markup = render(SPEC)
    validate_html(markup)
    elements = DiagramElements(markup).elements
    assert any(tag == "svg" for tag, _ in elements)
    relationships = [
        (attrs["data-edge-source"], attrs["data-edge-target"])
        for tag, attrs in elements if tag == "g" and "data-edge-source" in attrs
    ]
    assert relationships == [("api", "worker"), ("worker", "files"), ("files", "api")]
    for edge in SPEC["edges"]:
        assert edge["label"] in markup
    assert "viewBox=" in markup
    assert "<img" not in markup and "url(" not in markup


def test_html_layers_show_responsibilities_and_relationships_without_svg():
    markup = render({**SPEC, "layout": "layers"})
    validate_html(markup)
    assert "<svg" not in markup and "<img" not in markup
    assert "프로젝트 저장소" in markup
    assert "버전이 고정된 문서" in markup
    assert "POST /research" in markup
    assert "flex-wrap" in markup


def test_sequence_has_ordered_messages_and_supports_self_calls():
    spec = {**SPEC, "layout": "sequence", "edges": [
        {"source": "api", "target": "worker", "label": "HTTPS 요청"},
        {"source": "worker", "target": "worker", "label": "정책 확인"},
        {"source": "worker", "target": "api", "label": "결과 반환"},
    ]}
    markup = render(spec)
    validate_html(markup)
    assert markup.index("HTTPS 요청") < markup.index("정책 확인") < markup.index("결과 반환")
    assert markup.count("data-edge-source=") == 3
    assert "stroke-dasharray" in markup  # participant lifelines


def test_reverse_connection_badges_do_not_cover_each_other():
    spec = {**SPEC, "edges": [
        {"source": "api", "target": "worker", "label": "request"},
        {"source": "worker", "target": "files", "label": "read"},
        {"source": "files", "target": "worker", "label": "return"},
    ]}
    circles = [
        attrs for tag, attrs in DiagramElements(render(spec)).elements if tag == "circle"
    ]
    for index, first in enumerate(circles):
        for second in circles[index + 1:]:
            distance = ((float(first["cx"]) - float(second["cx"])) ** 2 +
                        (float(first["cy"]) - float(second["cy"])) ** 2) ** 0.5
            assert distance >= float(first["r"]) + float(second["r"])


@pytest.mark.parametrize("edges", [
    [
        {"source": "api", "target": "worker", "label": "request"},
        {"source": "worker", "target": "api", "label": "response"},
    ],
    [
        {"source": "api", "target": "worker", "label": "request"},
        {"source": "worker", "target": "files", "label": "read"},
        {"source": "api", "target": "files", "label": "metadata"},
        {"source": "worker", "target": "api", "label": "response"},
        {"source": "files", "target": "api", "label": "result"},
        {"source": "files", "target": "worker", "label": "return"},
    ],
])
def test_adjacent_returns_and_six_edge_flows_have_distinct_number_badges(edges):
    circles = [attrs for tag, attrs in DiagramElements(render({**SPEC, "edges": edges})).elements if tag == "circle"]
    assert len(circles) == len(edges)
    for index, first in enumerate(circles):
        for second in circles[index + 1:]:
            distance = ((float(first["cx"]) - float(second["cx"])) ** 2 +
                        (float(first["cy"]) - float(second["cy"])) ** 2) ** 0.5
            assert distance >= float(first["r"]) + float(second["r"])


@pytest.mark.parametrize("update", [
    {"edges": [{"source": "missing", "target": "api", "label": "unknown"}]},
    {"rows": [{"label": "", "nodes": [
        {"id": "same", "label": "A"}, {"id": "same", "label": "B"},
    ]}]},
    {"edges": []},
])
def test_invalid_relationships_or_duplicate_ids_are_not_silently_dropped(update):
    with pytest.raises(ValidationError):
        render({**SPEC, **update})


def test_labels_are_escaped_and_long_technical_names_are_kept():
    malicious = {**SPEC, "title": "<script>bad()</script>", "rows": [{
        "label": "시스템 <script>", "nodes": [
            {"id": "api", "label": 'API <script>alert("x")</script>', "detail": "길고 구체적인 기술적 책임 설명"},
            {"id": "worker", "label": "Amazon Bedrock Knowledge Bases"},
            {"id": "files", "label": "Storage & references"},
        ],
    }]}
    markup = render(malicious)
    validate_html(markup)
    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup
    assert "Storage &amp; references" in markup
