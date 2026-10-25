"""The HTML adapter preserves research content without another model call."""
from html.parser import HTMLParser

from api.workspaces.html_documents import validate_html


class Elements(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.tags = []
        self.text = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def render(markdown, title="연구 결과"):
    from api.workspaces.research_html import render_research_html
    return render_research_html(
        markdown, title, genre="blog", sources=[{
            "id": "s1", "url": "https://example.org/report?a=1&b=2",
            "title": "근거", "excerpt": "수치를 측정했습니다.",
        }],
    )


def test_html_keeps_tables_code_figures_and_repeated_citations():
    content = render(
        "# 연구 결과\n\n## 비교\n\n"
        "| 방식 | 정확도 |\n| --- | ---: |\n| A | 91% |\n| B | 87% |\n\n"
        "근거 [[1]](https://example.org/report?a=1&b=2).\n\n"
        "![그림 1. 흐름](/api/research/assets/run123/fig1.png)\n\n"
        "```python\nprint('<script>')\n```\n\n"
        "다시 [1](https://example.org/report?a=1&b=2).\n"
    )
    validate_html(content, {"s1"})
    parsed = Elements(content)
    assert any(tag == "table" for tag, _ in parsed.tags)
    assert any(tag == "pre" for tag, _ in parsed.tags)
    assert "91%" in parsed.text and "87%" in parsed.text
    citations = [attrs for tag, attrs in parsed.tags if tag == "a" and attrs.get("href", "").startswith("https:")]
    assert [item["href"] for item in citations] == ["https://example.org/report?a=1&b=2"] * 2
    assert all(item.get("data-source-ids") == '["s1"]' for item in citations)
    assert [attrs["src"] for tag, attrs in parsed.tags if tag == "img"] == [
        "/api/research/assets/run123/fig1.png"
    ]
    assert "<script>" not in content
    assert any(tag == "meta" and attrs.get("charset") == "utf-8" for tag, attrs in parsed.tags)
    ids = [attrs["data-oc-id"] for _, attrs in parsed.tags if "data-oc-id" in attrs]
    assert ids and len(ids) == len(set(ids))


def test_raw_markup_and_title_are_text_not_executable_html():
    content = render(
        "<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n",
        title='자료 <script>alert("title")</script>',
    )
    validate_html(content)
    parsed = Elements(content)
    assert not any(tag in {"script", "iframe", "form"} for tag, _ in parsed.tags)
    assert not any(name.startswith("on") for _, attrs in parsed.tags for name in attrs)
    assert "<script>alert(1)</script>" in "".join(parsed.text)


def test_table_of_contents_uses_unique_targets_without_changing_citations():
    content = render("# 연구 결과\n\n## 같은 제목\n\n본문.\n\n## 같은 제목\n\n다음.\n\n## 결론\n\n마지막.")
    parsed = Elements(content)
    targets = {attrs["id"] for _, attrs in parsed.tags if "id" in attrs}
    navigation = [attrs["href"][1:] for tag, attrs in parsed.tags if tag == "a" and attrs.get("href", "").startswith("#")]
    assert len(navigation) == 3
    assert len(set(navigation)) == 3
    assert set(navigation) <= targets


def test_linkedin_plain_source_urls_become_clickable_without_touching_code_or_link_labels():
    url = "https://example.org/report?a=1&b=2"
    content = render(
        f"원문 {url}.\n\n[{url}]({url})\n\n`{url}`\n\n```text\n{url}\n```\n"
    )
    validate_html(content, {"s1"})
    parsed = Elements(content)
    anchors = [attrs for tag, attrs in parsed.tags if tag == "a"]
    assert len(anchors) == 2
    assert all(anchor["href"] == url for anchor in anchors)
    assert all(anchor.get("data-source-ids") == '["s1"]' for anchor in anchors)
    assert "&amp;b=2" in content


def test_duplicate_source_urls_retain_every_contributing_excerpt_identity():
    from api.workspaces.research_html import render_research_html
    sources = [
        {"id": "latency", "url": "https://example.org/report", "excerpt": "Latency is 12 ms."},
        {"id": "accuracy", "url": "https://example.org/report", "excerpt": "Accuracy is 91%."},
    ]
    content = render_research_html(
        "Latency is 12 ms [1](https://example.org/report).\n\nhttps://example.org/report",
        "Measurements", sources=sources, genre="blog",
    )
    parsed = Elements(content)
    citations = [attrs for tag, attrs in parsed.tags if tag == "a"]
    assert len(citations) == 2
    assert all(item.get("data-source-ids") == '["latency", "accuracy"]' for item in citations)
