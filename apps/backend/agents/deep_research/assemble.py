"""Turn final sections into one Markdown document: numbered citations, figures, references."""
import logging
import re
from typing import Callable
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline, autolink, backtick, escape, html_inline, image, link

from agents.deep_research.genres import GenreProfile
from core.research_sources import source_key

logger = logging.getLogger(__name__)

# [S3], [S3, S7], [S3; S7] — the writer's citation markers. Finding ids (F12) sometimes slip in; they are
# matched so they can be removed, never linked.
CITATION = re.compile(r"\[([SF]\d+(?:\s*[,;]\s*[SF]\d+)*)\]")


def _localized(language: str, ko: str, en: str) -> str:
    return ko if language.lower().startswith("ko") else en


def figure_label(language: str, number: int) -> str:
    return _localized(language, f"그림 {number}", f"Figure {number}")


def _domain(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def link_citations(
    text: str, sources: dict, order: dict[str, int], max_cited: int | None = None,
    allow_source: Callable[[dict], bool] | None = None,
) -> str:
    """Replace [S#] markers with [[n]](url), numbering sources by first use. Unknown ids are dropped, and so
    are sources beyond `max_cited` distinct ones (a destination that accepts only so many sources)."""
    def replace(match: re.Match) -> str:
        links = []
        for sid in re.split(r"\s*[,;]\s*", match.group(1)):
            if sid.startswith("F"):
                continue
            source = sources.get(sid)
            if not source:
                logger.info("dropped citation to unknown source %s", sid)
                continue
            if sid not in order and max_cited is not None and len(order) >= max_cited:
                continue
            if allow_source is not None and not allow_source(source):
                continue
            order.setdefault(sid, len(order) + 1)
            links.append(f"[[{order[sid]}]]({source['url']})")
        return "".join(links)

    linked = CITATION.sub(replace, text)
    return re.sub(r"[ \t]+(?=[.,;:])", "", linked)


def strip_citations(text: str) -> str:
    return re.sub(r"[ \t]*" + CITATION.pattern, "", text)


def drop_unknown_urls(text: str, sources: dict, allow_source: Callable[[dict], bool] | None = None) -> str:
    """Keep only URLs of sources that were actually read. Writers also link papers from memory, and the
    workspace rejects a whole document that cites an unread URL. Parser spans protect code and link
    syntax; edits only remove source bytes, preserving known links, formatting, BOM and line endings."""
    markdown = MarkdownIt("commonmark", {"inline_definitions": True})
    known = {markdown.normalizeLink(source["url"]).rstrip("/"): source for source in sources.values()}
    # Markdown parses normalized newlines. Keep boundary offsets into the original text so none of
    # that normalization is written back to the document.
    characters, original_offsets = [], [0]
    position = 0
    while position < len(text):
        character = text[position]
        position += 1
        if character == "\r":
            if position < len(text) and text[position] == "\n":
                position += 1
            character = "\n"
        characters.append(character)
        original_offsets.append(position)
    normalized = "".join(characters)
    environment = {}
    tokens = markdown.parse(normalized.removeprefix("\ufeff"), environment)
    line_offsets = [0, *[index + 1 for index, character in enumerate(normalized) if character == "\n"]]
    if line_offsets[-1] != len(normalized):
        line_offsets.append(len(normalized))
    removals = []

    def unread(url):
        if not url.lower().startswith(("http://", "https://")):
            return False
        source = known.get(markdown.normalizeLink(url).rstrip("/"))
        return source is None or (allow_source is not None and not allow_source(source))

    def scan_inline(start, end):
        state = StateInline(normalized[start:end], markdown, environment, [])
        while state.pos < state.posMax:
            position = state.pos
            marker = state.src[position]
            if marker == "`" and backtick(state, True):
                continue
            if marker == "\\" and escape(state, True):
                continue
            is_image = state.src.startswith("![", position)
            if marker == "[" or is_image:
                label_start = position + (2 if is_image else 1)
                label_end = markdown.helpers.parseLinkLabel(state, label_start - 1, not is_image)
                token_start = len(state.tokens)
                if label_end >= 0 and (image if is_image else link)(state, False):
                    token = next(token for token in state.tokens[token_start:] if token.type in {"image", "link_open"})
                    if unread(token.attrGet("src" if is_image else "href") or ""):
                        removals.extend(((start + position, start + label_start), (start + label_end, start + state.pos)))
                        scan_inline(start + label_start, start + label_end)
                    continue
            if marker == "<":
                token_start = len(state.tokens)
                if autolink(state, False):
                    if unread(state.tokens[token_start].attrGet("href") or ""):
                        removals.append((start + position, start + state.pos))
                    continue
                if html_inline(state, True):
                    continue
            if state.src[position:position + 8].lower().startswith(("http://", "https://")):
                limit = position
                while limit < state.posMax and not state.src[limit].isspace() and state.src[limit] not in "<>[]\"'`":
                    limit += 1
                destination = markdown.helpers.parseLinkDestination(state.src, position, limit)
                url_end = destination.pos if destination.ok else limit
                raw_url = state.src[position:url_end].rstrip(".,;!")
                if unread(markdown.utils.unescapeAll(raw_url)):
                    removals.append((start + position, start + position + len(raw_url)))
                state.pos = url_end
                continue
            state.pos = position + 1

    for token in tokens:
        if token.map is None:
            continue
        start, end = (line_offsets[line] for line in token.map)
        if token.type == "definition" and unread(token.meta["url"]):
            # Remove an unread reference definition, retaining its original line endings.
            for line in normalized[start:end].splitlines(keepends=True):
                removals.append((start, start + len(line.rstrip("\n"))))
                start += len(line)
        elif token.type in {"inline", "html_block"}:
            scan_inline(start, end)
    result, previous = [], 0
    for start, end in sorted(removals):
        result.append(text[previous:original_offsets[start]])
        previous = original_offsets[end]
    result.append(text[previous:])
    return "".join(result)


def references(sources: dict, order: dict[str, int], profile: GenreProfile, language: str) -> str:
    if not order:
        return ""
    heading = (
        _localized(language, "참고문헌", "References") if profile.name == "paper"
        else _localized(language, "참고 자료", "References")
    )
    lines = [f"## {heading}", ""]
    for sid, number in sorted(order.items(), key=lambda item: item[1]):
        source = sources[sid]
        date = f", {source['publishedDate'][:10]}" if source.get("publishedDate") else ""
        lines.append(f"{number}. [{source['title']}]({source['url']}) ({_domain(source['url'])}{date})")
    return "\n".join(lines)


def figure_block(figure: dict, language: str) -> str:
    label = figure_label(language, figure["number"])
    return f"![{label}. {figure['caption']}]({figure['url']})\n\n*{label}. {figure['caption']}*"


def assemble(title: str, sections: list[tuple[str, str]], figures: list[dict], sources: dict,
             profile: GenreProfile, language: str, max_cited: int | None = None,
             *, max_new_cited: int | None = None) -> str:
    """sections: [(section_id, markdown)] in order. Figures go after the section that planned them."""
    by_section = {}
    for figure in figures:
        by_section.setdefault(figure["section_id"], []).append(figure)
    order: dict[str, int] = {}
    new_sources: set[str] = set()

    def allow_source(source: dict) -> bool:
        if max_new_cited is None or source.get("origin") == "supplied":
            return True
        key = source_key(source["url"])
        if key in new_sources:
            return True
        if len(new_sources) >= max_new_cited:
            return False
        new_sources.add(key)
        return True

    parts = [] if profile.name == "linkedin" else [f"# {title}"]
    for section_id, text in sections:
        body = text.strip()
        if body.startswith("# "):  # writers sometimes repeat the document title; the document has one H1
            body = body.split("\n", 1)[1].strip() if "\n" in body else ""
        if profile.citation_style == "links":
            body = drop_unknown_urls(strip_citations(body), sources, allow_source)
        else:
            body = link_citations(drop_unknown_urls(body, sources, allow_source),
                                  sources, order, max_cited, allow_source)
        parts.append(body)
        parts.extend(figure_block(f, language) for f in by_section.get(section_id, []))
    if profile.citation_style == "numbered":
        refs = references(sources, order, profile, language)
        if refs:
            parts.append(refs)
    return "\n\n".join(p for p in parts if p) + "\n"
