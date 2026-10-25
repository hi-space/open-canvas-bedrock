"""Validate static HTML and insert editor IDs without serializing its source.

The parser deliberately accepts a bounded static subset with explicit end tags.
It rejects constructs that make browsers move or implicitly close source nodes;
the preview's parser can therefore map each editable element to these same bytes.
This is validation, not a replacement for the preview's sanitizer and sandbox.
"""
from dataclasses import dataclass
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit


NODE_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}"
_NODE_ID = re.compile(NODE_ID_PATTERN)
_VOID = frozenset({"br", "col", "hr", "img", "meta", "wbr"})
_NON_EDITABLE = frozenset({"html", "head", "body", "title", "meta", "style"})
_ALLOWED = _NON_EDITABLE | _VOID | frozenset({
    "a", "abbr", "address", "article", "aside", "b", "bdi", "bdo", "blockquote",
    "caption", "cite", "code", "colgroup", "dd", "del", "details", "dfn", "div",
    "dl", "dt", "em", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4",
    "h5", "h6", "header", "hgroup", "i", "ins", "kbd", "li", "main", "mark",
    "nav", "ol", "p", "pre", "q", "rp", "rt", "ruby", "s", "samp", "section",
    "small", "span", "strong", "sub", "summary", "sup", "table", "tbody", "td",
    "tfoot", "th", "thead", "time", "tr", "u", "ul", "var",
})
_BLOCK = frozenset({
    "address", "article", "aside", "blockquote", "details", "div", "dl", "fieldset",
    "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hgroup", "hr", "main", "nav", "ol", "p", "pre", "section", "summary", "table", "ul",
})
_TABLE_CHILDREN = {
    "table": {"caption", "colgroup", "thead", "tbody", "tfoot", "tr"},
    "thead": {"tr"}, "tbody": {"tr"}, "tfoot": {"tr"}, "tr": {"td", "th"},
    "colgroup": {"col"},
}
_REQUIRED_PARENT = {
    "caption": {"table"}, "colgroup": {"table"}, "col": {"colgroup"},
    "thead": {"table"}, "tbody": {"table"}, "tfoot": {"table"},
    "tr": {"table", "thead", "tbody", "tfoot"}, "td": {"tr"}, "th": {"tr"},
    "li": {"ul", "ol"}, "dt": {"dl"}, "dd": {"dl"},
    "rt": {"ruby"}, "rp": {"ruby"},
    "summary": {"details"},
}
_GLOBAL_ATTRIBUTES = frozenset({"id", "class", "style", "title", "lang", "dir", "role", "hidden", "tabindex"})
_TAG_ATTRIBUTES = {
    "a": {"href", "target", "rel", "hreflang", "type"},
    "blockquote": {"cite"}, "q": {"cite"},
    "del": {"cite", "datetime"}, "ins": {"cite", "datetime"},
    "img": {"src", "alt", "width", "height", "loading", "decoding"},
    "meta": {"charset", "name", "content", "property"},
    "style": {"media", "type"},
    "ol": {"start", "reversed", "type"}, "li": {"value"},
    "td": {"colspan", "rowspan", "headers"}, "th": {"colspan", "rowspan", "headers", "scope", "abbr"},
    "col": {"span"}, "colgroup": {"span"},
    "table": {"width", "border", "cellpadding", "cellspacing"},
    "time": {"datetime"}, "details": {"open", "name"},
}
_ATTRIBUTE = re.compile(
    r"""\s+([A-Za-z_:][A-Za-z0-9_:.-]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'`=<>]+)))?"""
)
_CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\r\n\f]?|\\([^\r\n\f])")


def is_html_path(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in {".html", ".htm"}


def _fail(message="올바르게 닫힌 정적 HTML/CSS 문서를 사용해 주세요."):
    raise ValueError(message)


def _validate_css(value: str):
    # Decode escapes and comments before looking for executable or fetched CSS.
    value = re.sub(r"\\(?:\r\n|[\r\n\f])", "", value)
    value = _CSS_ESCAPE.sub(
        lambda match: chr(min(int(match[1], 16), 0x10FFFF)) if match[1] else match[2], value,
    )
    value = re.sub(r"/\*.*?\*/", "", value, flags=re.DOTALL).lower()
    if re.search(
        r"@\s*(?:import|namespace)\b|(?:expression|url|(?:-webkit-)?image-set)\s*\("
        r"|(?:^|[;{])\s*(?:behavior|-moz-binding)\s*:|(?:javascript|vbscript)\s*:",
        value,
    ):
        _fail("외부 요청이나 실행 코드가 없는 인라인 CSS를 사용해 주세요.")


def _validate_url(value: str):
    normalized = re.sub(r"[\x00-\x20\x7f]+", "", value)
    try:
        parsed = urlsplit(normalized)
    except ValueError:
        _fail("안전한 HTML 링크를 사용해 주세요.")
    if "\\" in normalized or parsed.scheme.lower() not in {"", "http", "https", "mailto", "tel"}:
        _fail("안전한 HTML 링크를 사용해 주세요.")


def _source_ids(value: str | None) -> list[str]:
    try:
        result = json.loads(value or "")
    except (TypeError, ValueError, RecursionError):
        _fail("data-source-ids는 참고자료 ID의 JSON 문자열 배열이어야 합니다.")
    if (
        not isinstance(result, list) or len(result) > 50
        or any(not isinstance(item, str) or not item.strip() or len(item) > 100 for item in result)
        or len(set(result)) != len(result)
    ):
        _fail("data-source-ids는 중복 없는 참고자료 ID의 JSON 문자열 배열이어야 합니다.")
    return result


@dataclass
class _Element:
    tag: str
    start: int
    start_end: int
    attributes_end: int
    end: int
    attrs: dict[str, str | None]
    attr_spans: dict[str, tuple[int, int]]
    editable: bool


class _DocumentParser(HTMLParser):
    def __init__(self, source: str, fragment: bool = False):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.fragment = fragment
        self.lines = [0, *[index + 1 for index, char in enumerate(source) if char == "\n"]]
        self.elements: list[_Element] = []
        self.stack: list[_Element] = []
        self.structural: set[str] = set()
        self.doctype = False

    def _source_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def _attrs(self, tag, parsed, raw, offset):
        start = re.match(r"<[A-Za-z][A-Za-z0-9]*", raw)
        if start is None:
            _fail()
        position = start.end()
        attrs = {}
        spans = {}
        while not re.fullmatch(r"\s*/?>", raw[position:]):
            match = _ATTRIBUTE.match(raw, position)
            if match is None:
                _fail()
            name = match[1].lower()
            if name in attrs:
                _fail("HTML 속성이 중복되었습니다.")
            value = next((item for item in match.groups()[1:] if item is not None), None)
            # HTMLParser and the source lexer must agree, including unquoted values.
            value = html.unescape(value) if value is not None else None
            attrs[name] = value
            spans[name] = (offset + match.start(1), offset + match.end())
            position = match.end()
            if (
                name.startswith("on") or ":" in name
                or (name not in _GLOBAL_ATTRIBUTES and name not in _TAG_ATTRIBUTES.get(tag, set())
                    and not name.startswith(("data-", "aria-")))
            ):
                _fail("실행 동작이나 지원하지 않는 HTML 속성은 사용할 수 없습니다.")
            if name in {"href", "src", "cite"} and value is not None:
                _validate_url(value)
            if name == "style":
                _validate_css(value or "")
            if name == "data-source-ids":
                _source_ids(value)
            if tag == "meta" and name == "charset" and (value or "").lower() not in {"utf-8", "utf8"}:
                _fail("HTML 문자는 UTF-8이어야 합니다.")
            if tag == "style" and name == "type" and (value or "").lower() != "text/css":
                _fail("정적 CSS만 사용할 수 있습니다.")
        if list(attrs.items()) != parsed:
            _fail()
        return attrs, spans, offset + position

    def _start(self, tag, attrs, self_closing=False):
        if tag not in _ALLOWED or (self_closing and tag not in _VOID):
            _fail("정적 HTML 요소만 사용할 수 있으며 닫는 태그가 필요합니다.")
        if len(self.stack) >= 100:
            _fail("HTML 요소의 중첩은 100단계 이내여야 합니다.")
        ancestors = [node.tag for node in self.stack]
        parent = ancestors[-1] if ancestors else None
        if tag in {"html", "head", "body"}:
            if tag in self.structural or (tag == "html" and (self.stack or self.elements)):
                _fail()
            if tag != "html" and parent not in {None, "html"}:
                _fail()
            if tag == "head" and "body" in self.structural:
                _fail()
            self.structural.add(tag)
        elif "html" in self.structural and not self.stack:
            _fail()
        if (
            (parent == "html" and tag not in {"head", "body"})
            or ("head" in ancestors and tag not in {"title", "meta", "style"})
            or parent in {"title", "style"}
            or ("p" in ancestors and tag in _BLOCK)
            or (tag == "a" and "a" in ancestors)
            or (tag in {"h1", "h2", "h3", "h4", "h5", "h6"}
                and any(item in {"h1", "h2", "h3", "h4", "h5", "h6"} for item in ancestors))
            or (parent in _TABLE_CHILDREN and tag not in _TABLE_CHILDREN[parent])
            or (tag == "table" and "caption" in ancestors)
            or (parent is not None and tag in _REQUIRED_PARENT and parent not in _REQUIRED_PARENT[tag])
            or (parent is None and not self.fragment and tag in _REQUIRED_PARENT)
        ):
            _fail("브라우저가 요소를 자동 이동하지 않도록 HTML 중첩을 확인해 주세요.")
        raw = self.get_starttag_text()
        offset = self._source_offset()
        attributes, spans, attributes_end = self._attrs(tag, attrs, raw, offset)
        element = _Element(
            tag=tag, start=offset, start_end=offset + len(raw), attributes_end=attributes_end,
            end=offset + len(raw), attrs=attributes, attr_spans=spans,
            editable=tag not in _NON_EDITABLE and "head" not in ancestors,
        )
        self.elements.append(element)
        if tag not in _VOID:
            self.stack.append(element)

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def handle_endtag(self, tag):
        offset = self._source_offset()
        match = re.match(r"</[A-Za-z][A-Za-z0-9]*\s*>", self.source[offset:])
        if not self.stack or self.stack[-1].tag != tag or match is None:
            _fail()
        element = self.stack.pop()
        element.end = offset + match.end()
        if tag == "style":
            _validate_css(self.source[element.start_end:offset])

    def _text(self, data, escaped=False):
        parent = self.stack[-1].tag if self.stack else None
        if (
            (parent != "style" and not escaped and "<" in data)
            or (parent in {"html", "head", *_TABLE_CHILDREN} and data.strip(" \t\r\n\f"))
            or (not self.stack and "html" in self.structural and data.strip("\ufeff \t\r\n\f"))
        ):
            _fail()

    def handle_data(self, data):
        self._text(data)

    def handle_entityref(self, name):
        self._text(html.unescape("&" + name + ";"), escaped=True)

    def handle_charref(self, name):
        self._text(html.unescape("&#" + name + ";"), escaped=True)

    def handle_comment(self, data):
        if "--" in data or not self.source.startswith("<!--" + data + "-->", self._source_offset()):
            _fail()

    def handle_decl(self, decl):
        if self.elements or self.doctype or not re.fullmatch(r"doctype\s+html", decl, re.IGNORECASE):
            _fail("HTML5 doctype만 사용할 수 있습니다.")
        self.doctype = True

    def unknown_decl(self, data):
        _fail()

    def handle_pi(self, data):
        _fail()


def _parse(content: str, *, fragment: bool = False) -> list[_Element]:
    if not isinstance(content, str) or "\x00" in content:
        _fail()
    content.encode("utf-8")
    parser = _DocumentParser(content, fragment)
    try:
        parser.feed(content)
        parser.close()
    except AssertionError:
        _fail()
    if parser.stack:
        _fail()
    return parser.elements


def validate_html(content: str, source_ids: set[str] | None = None, *, fragment: bool = False):
    """Validate structure and optional provenance without changing any bytes."""
    elements = _parse(content, fragment=fragment)
    ids = [element.attrs["data-oc-id"] for element in elements if "data-oc-id" in element.attrs]
    if any(value is None or not _NODE_ID.fullmatch(value) for value in ids) or len(set(ids)) != len(ids):
        _fail("HTML 영역 ID는 고유한 영문자, 숫자, 밑줄 또는 하이픈이어야 합니다.")
    if source_ids is not None:
        for element in elements:
            if "data-source-ids" in element.attrs and set(_source_ids(element.attrs["data-source-ids"])) - source_ids:
                _fail("HTML 영역이 프로젝트에 없는 참고자료 ID를 사용했습니다.")
    return elements


def html_source_ids(content: str) -> set[str]:
    """Return author-provided provenance identities from an immutable base."""
    return {
        source_id
        for element in _parse(content)
        if "data-source-ids" in element.attrs
        for source_id in _source_ids(element.attrs["data-source-ids"])
    }


def _prepare(content: str, reserved_ids: set[str] | None = None, *, fragment: bool = False) -> str:
    elements = _parse(content, fragment=fragment)
    used = set(reserved_ids or ())
    first = {}
    for index, element in enumerate(elements):
        value = element.attrs.get("data-oc-id")
        if value is not None and _NODE_ID.fullmatch(value) and value not in used:
            used.add(value)
            first[value] = index
    edits = []
    for index, element in enumerate(elements):
        value = element.attrs.get("data-oc-id")
        if not element.editable and "data-oc-id" not in element.attrs:
            continue
        if value is not None and first.get(value) == index:
            continue
        serial = 0
        while True:
            node_id = "oc-" + hashlib.sha256(f"{element.tag}:{element.start}:{serial}".encode()).hexdigest()[:16]
            if node_id not in used:
                break
            serial += 1
        used.add(node_id)
        if "data-oc-id" in element.attr_spans:
            start, end = element.attr_spans["data-oc-id"]
            edits.append((start, end, f'data-oc-id="{node_id}"'))
        else:
            # A slash immediately before ">" can belong to an unquoted value.
            # Insert after the parsed attribute token, never by guessing at "/>".
            position = element.attributes_end
            edits.append((position, position, f' data-oc-id="{node_id}"'))
    parts = []
    previous = 0
    for start, end, replacement in edits:
        parts.extend((content[previous:start], replacement))
        previous = end
    parts.append(content[previous:])
    normalized = "".join(parts)
    validate_html(normalized, fragment=fragment)
    return normalized


def prepare_html(content: str) -> str:
    """Return static HTML with persistent unique IDs, retaining source formatting."""
    return _prepare(content)


def html_citation_text(content: str) -> str:
    """Project HTML for citation checks, excluding only same-document navigation.

    This projection is never saved or rendered. External links, image sources,
    link labels and all other source bytes still pass through the existing
    citation validator. A selected table/list element may be a contextual fragment.
    """
    parts = []
    previous = 0
    for element in _parse(content, fragment=True):
        href = element.attrs.get("href")
        if element.tag == "a" and href is not None and href.lstrip(" \t\r\n\f").startswith("#"):
            start, end = element.attr_spans["href"]
            parts.append(content[previous:start])
            previous = end
    parts.append(content[previous:])
    return "".join(parts)


def html_selection(content: str, node_id: str) -> dict:
    """Resolve one editable element's exact Python span and original source."""
    if not isinstance(node_id, str) or not _NODE_ID.fullmatch(node_id):
        _fail("선택한 HTML 영역 ID를 확인해 주세요.")
    elements = validate_html(content)
    matches = [element for element in elements if element.editable and element.attrs.get("data-oc-id") == node_id]
    if len(matches) != 1:
        _fail("선택한 HTML 영역이 문서에 없습니다.")
    element = matches[0]
    return {"start": element.start, "end": element.end, "text": content[element.start:element.end], "nodeId": node_id}


def replace_html_selection(content: str, selection: dict, replacement: str, source_ids: set[str] | None = None) -> str:
    """Normalize only the replacement subtree and preserve all outside bytes."""
    resolved = html_selection(content, selection.get("nodeId"))
    if any(selection.get(key) != resolved[key] for key in ("start", "end", "text", "nodeId")):
        _fail("선택한 HTML 영역과 원문이 다릅니다.")
    nodes = _parse(replacement, fragment=True)
    if (
        not nodes or not nodes[0].editable or nodes[0].start != 0 or nodes[0].end != len(replacement)
        or nodes[0].attrs.get("data-oc-id") != resolved["nodeId"]
    ):
        _fail("선택한 요소 전체를 교체하고 루트 data-oc-id를 유지해 주세요.")
    if any(node.tag == "style" for node in nodes):
        _fail("영역 수정은 style 속성을 사용해 주세요. 전역 CSS 수정은 문서 전체 요청이 필요합니다.")
    outside_ids = {
        node.attrs["data-oc-id"] for node in _parse(content)
        if "data-oc-id" in node.attrs and not (resolved["start"] <= node.start < resolved["end"])
    }
    normalized = _prepare(replacement, outside_ids, fragment=True)
    result = content[:resolved["start"]] + normalized + content[resolved["end"]:]
    validate_html(result, source_ids)
    return result
