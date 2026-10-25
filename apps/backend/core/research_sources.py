"""Shared identity and provenance for supplied research evidence."""
import html
from urllib.parse import urlsplit, urlunsplit

from markdown_it import MarkdownIt

_markdown = MarkdownIt("commonmark")


def source_key(url: str) -> str:
    parts = urlsplit(_markdown.normalizeLink(html.unescape(url)))
    return urlunsplit((
        parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/",
        parts.query, parts.fragment,
    ))


def evidence_groups(sources: list[dict]) -> dict[str, list[dict]]:
    """Group usable excerpts, retaining every contributing registered identity."""
    groups: dict[str, list[dict]] = {}
    for source in sources:
        if not (source.get("excerpt") or "").strip():
            continue
        key = source_key(source["url"])
        group = groups.setdefault(key, [])
        if not any(item["id"] == source["id"] for item in group):
            group.append(source)
    return groups
