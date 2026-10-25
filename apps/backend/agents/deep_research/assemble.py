"""Turn final sections into one Markdown document: numbered citations, figures, references."""
import logging
import re
from urllib.parse import urlsplit

from agents.deep_research.genres import GenreProfile

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


def link_citations(text: str, sources: dict, order: dict[str, int], max_cited: int | None = None) -> str:
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
            order.setdefault(sid, len(order) + 1)
            links.append(f"[[{order[sid]}]]({source['url']})")
        return "".join(links)

    linked = CITATION.sub(replace, text)
    return re.sub(r"[ \t]+(?=[.,;:])", "", linked)


def strip_citations(text: str) -> str:
    return re.sub(r"[ \t]*" + CITATION.pattern, "", text)


_URL = re.compile(r"https?://[^\s<>()\[\]\"']+")


def drop_unknown_urls(text: str, sources: dict) -> str:
    """Posts name sources as bare URLs; keep only URLs of sources that were actually read."""
    known = {s["url"].rstrip("/") for s in sources.values()}

    def keep(match: re.Match) -> str:
        url = match.group().rstrip(".,;!")
        if url.rstrip("/") in known:
            return match.group()
        logger.info("dropped unread URL %s", url)
        return match.group()[len(url):]

    return _URL.sub(keep, text)


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
             profile: GenreProfile, language: str, max_cited: int | None = None) -> str:
    """sections: [(section_id, markdown)] in order. Figures go after the section that planned them."""
    by_section = {}
    for figure in figures:
        by_section.setdefault(figure["section_id"], []).append(figure)
    order: dict[str, int] = {}
    parts = [] if profile.name == "linkedin" else [f"# {title}"]
    for section_id, text in sections:
        body = text.strip()
        if body.startswith("# "):  # writers sometimes repeat the document title; the document has one H1
            body = body.split("\n", 1)[1].strip() if "\n" in body else ""
        if profile.citation_style == "links":
            body = drop_unknown_urls(strip_citations(body), sources)
        else:
            body = link_citations(body, sources, order, max_cited)
        parts.append(body)
        parts.extend(figure_block(f, language) for f in by_section.get(section_id, []))
    if profile.citation_style == "numbered":
        refs = references(sources, order, profile, language)
        if refs:
            parts.append(refs)
    return "\n\n".join(p for p in parts if p) + "\n"
