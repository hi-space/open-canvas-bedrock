"""Static SVG diagrams keep one exact source region and no active/resource content."""
import pytest

from api.workspaces.html_documents import (
    html_selection, prepare_html, replace_html_selection, validate_html,
)

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 160" role="img" '
    'aria-label="API에서 저장소로" data-oc-id="diagram">'
    '<title>요청 흐름</title><desc>API가 문서를 저장합니다.</desc>'
    '<g fill="none" stroke="#246a56"><rect x="10" y="30" width="140" height="80" rx="8"/>'
    '<path d="M 150 70 L 300 70"/><polygon points="300,70 290,64 290,76"/></g>'
    '<text x="30" y="76" font-size="18">API<tspan dx="5">요청</tspan></text></svg>'
)


def test_static_svg_is_one_editable_region_and_retains_source_spelling():
    content = '<p data-oc-id="before">앞 😀</p>' + SVG + '<p data-oc-id="after">뒤</p>'
    prepared = prepare_html(content)
    assert prepared == content
    assert 'viewBox="0 0 480 160"' in prepared
    elements = validate_html(prepared)
    assert [element.tag for element in elements if element.editable] == ["p", "svg", "p"]
    selection = html_selection(prepared, "diagram")
    assert selection["text"] == SVG
    assert prepared[selection["start"]:selection["end"]] == SVG
    replacement = SVG.replace("API가 문서를 저장합니다.", "API가 JSON 문서를 저장합니다.").replace("API<tspan", "Gateway<tspan")
    result = replace_html_selection(prepared, selection, replacement)
    assert result == content.replace(SVG, replacement)


def test_generated_svg_root_gets_an_id_but_shapes_do_not():
    prepared = prepare_html('<div>' + SVG.replace(' data-oc-id="diagram"', "") + "</div>")
    elements = validate_html(prepared)
    svg = next(element for element in elements if element.tag == "svg")
    assert svg.attrs.get("data-oc-id")
    assert all("data-oc-id" not in element.attrs for element in elements if element.tag in {"g", "path", "text", "tspan"})


def test_self_closing_svg_can_be_selected_without_changing_surroundings():
    content = '<p>before</p><svg viewBox="0 0 100 100" data-oc-id="empty"/><p>after</p>'
    assert html_selection(prepare_html(content), "empty")["text"] == '<svg viewBox="0 0 100 100" data-oc-id="empty"/>'


@pytest.mark.parametrize("fragment", [
    '<svg><script>alert(1)</script></svg>',
    '<svg onload="alert(1)"><rect width="10" height="10"/></svg>',
    '<svg><foreignObject><div>HTML</div></foreignObject></svg>',
    '<svg><desc><p>HTML integration</p></desc></svg>',
    '<svg><title><img src="https://example.org/image"></title></svg>',
    '<svg><use href="#other"/></svg>',
    '<svg><image href="https://example.org/image.png"/></svg>',
    '<svg><animate attributeName="x"/></svg>',
    '<svg><a href="https://example.org"><text>link</text></a></svg>',
    '<svg><rect fill="url(https://example.org/paint)"/></svg>',
    r'<svg><rect fill="u\72l(https://example.org/paint)"/></svg>',
    '<svg><rect style="filter:url(#filter)"/></svg>',
    '<svg xmlns="http://example.org/not-svg"><text>wrong</text></svg>',
    '<svg xmlns:xlink="http://www.w3.org/1999/xlink"><path xlink:href="#x"/></svg>',
    '<path d="M 0 0 L 1 1"/>',
    '<svg><svg><text>nested viewport</text></svg></svg>',
])
def test_active_or_ambiguous_svg_is_rejected(fragment):
    with pytest.raises(ValueError):
        prepare_html(fragment)
