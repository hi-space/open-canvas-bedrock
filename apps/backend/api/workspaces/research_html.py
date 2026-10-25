"""Render completed research as an editable, static HTML publication."""
import html
import json

from markdown_it import MarkdownIt

from api.workspaces.html_documents import prepare_html
from api.writing.service import _normalize_link

_STYLE = """
:root { color-scheme: light; --ink: #23342f; --muted: #62746c; --accent: #246a56; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; color: var(--ink); background: #f1efe7;
  font-family: "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  line-height: 1.85; overflow-wrap: anywhere; }
main { max-width: 1080px; margin: 48px auto; padding: 56px 72px 64px;
  background: #fffefa; border-top: 5px solid var(--accent);
  box-shadow: 0 12px 48px #23342f0a; }
header { padding-bottom: 28px; border-bottom: 1px solid #d8ded4; margin-bottom: 32px; }
.report-kicker { color: var(--accent); font-size: 12px; letter-spacing: .16em;
  font-weight: 700; text-transform: uppercase; }
h1, h2, h3 { font-family: "Iowan Old Style", "Noto Serif KR", Georgia, serif;
  color: #19392f; line-height: 1.4; overflow-wrap: anywhere; }
h1 { font-size: clamp(28px, 4vw, 44px); letter-spacing: -.025em; margin: 18px 0 12px; }
h2 { font-size: 26px; margin: 48px 0 18px; padding-top: 12px; }
h3 { font-size: 21px; margin-top: 32px; }
p { margin: 0 0 20px; }
a { color: var(--accent); text-underline-offset: 3px; }
nav { border-left: 3px solid #b5c8b9; padding: 4px 0 4px 22px; margin: 28px 0 36px; }
nav p { color: var(--muted); font-size: 13px; margin-bottom: 8px; font-weight: 700; }
nav ol { margin: 0; padding-left: 20px; columns: 2; column-gap: 36px; font-size: 14px; }
nav li { break-inside: avoid; padding-bottom: 5px; }
blockquote { margin: 24px 0; padding: 20px 24px; background: #edf3eb;
  border-left: 3px solid var(--accent); }
blockquote p:last-child { margin-bottom: 0; }
.report-table { max-width: 100%; overflow-x: auto; margin: 24px 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #d8ded4; vertical-align: top; }
th { background: #e8eee5; color: #19392f; }
tbody tr:nth-child(even) { background: #f6f7f1; }
pre { max-width: 100%; overflow-x: auto; background: #21382f; color: #edf3eb;
  padding: 22px; border-radius: 4px; font-size: 13px; line-height: 1.65; }
code { font-family: "SFMono-Regular", Consolas, monospace; font-size: .88em; }
:not(pre) > code { background: #edf0e8; padding: 2px 5px; border-radius: 3px; }
img { display: block; max-width: 100%; height: auto; margin: 30px auto 12px; }
p:has(> em:only-child) { color: var(--muted); font-size: 13px; }
hr { border: 0; border-top: 1px solid #d8ded4; margin: 36px 0; }
li { margin-bottom: 7px; }
@media (max-width: 680px) {
  main { margin: 0; padding: 28px 20px 40px; box-shadow: none; }
  nav ol { columns: 1; }
  h2 { font-size: 23px; margin-top: 34px; }
  th, td { padding: 10px; min-width: 100px; }
}
@media print {
  body { background: white; }
  main { margin: 0; max-width: none; padding: 0; box-shadow: none; border: 0; }
  nav { display: none; }
  img, table, pre { break-inside: avoid; }
  pre { white-space: pre-wrap; }
}
"""


def render_research_html(
    markdown: str, title: str, *, sources: list[dict], genre: str, language: str = "ko",
) -> str:
    """Convert research without asking a model to restate its facts or citations."""
    md = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    source_ids = {_normalize_link(source["url"]): source["id"] for source in sources}

    def link_open(renderer, tokens, index, options, environment):
        token = tokens[index]
        source_id = source_ids.get(_normalize_link(token.attrGet("href") or ""))
        if source_id:
            token.attrSet("data-source-ids", json.dumps([source_id], ensure_ascii=False))
        return renderer.renderToken(tokens, index, options, environment)

    def table_open(renderer, tokens, index, options, environment):
        return '<div class="report-table">\n' + renderer.renderToken(tokens, index, options, environment)

    def table_close(renderer, tokens, index, options, environment):
        return renderer.renderToken(tokens, index, options, environment) + "</div>\n"

    md.add_render_rule("link_open", link_open)
    md.add_render_rule("table_open", table_open)
    md.add_render_rule("table_close", table_close)
    environment = {}
    tokens = md.parse(markdown, environment)
    headings = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h2":
            target = f"research-section-{len(headings) + 1}"
            token.attrSet("id", target)
            label = tokens[index + 1].content
            headings.append((target, label))
    if tokens and tokens[0].type == "heading_open" and tokens[0].tag == "h1":
        heading = md.renderer.render(tokens[:3], md.options, environment)
        tokens = tokens[3:]
    else:
        heading = f"<h1>{html.escape(title)}</h1>"
    navigation = ""
    korean = language.lower().startswith("ko")
    if len(headings) >= 3:
        items = "".join(
            f'<li><a href="#{target}">{html.escape(label)}</a></li>' for target, label in headings
        )
        label = "이 글의 내용" if korean else "In this report"
        navigation = f'<nav aria-label="{label}"><p>{label}</p><ol>{items}</ol></nav>'
    labels = {"paper": "Research paper", "blog": "Research journal", "linkedin": "Research brief"}
    body = md.renderer.render(tokens, md.options, environment)
    document = (
        f'<!doctype html>\n<html lang="{html.escape(language, quote=True)}"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f'<body><main><header><p class="report-kicker">{labels.get(genre, "Research")}</p>'
        f"{heading}</header>{navigation}<article>{body}</article></main></body></html>"
    )
    return prepare_html(document)
