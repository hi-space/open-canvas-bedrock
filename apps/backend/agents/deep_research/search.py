"""Web search with full-page content: Tavily `advanced` search with raw markdown per result."""
import asyncio
import logging
import os
from urllib.parse import urlsplit, urlunsplit

from tavily import AsyncTavilyClient

logger = logging.getLogger(__name__)

# Enough of a page to carry its argument and numbers; extraction sees several sources per question.
MAX_SOURCE_CHARS = 14000


class SearchUnavailable(RuntimeError):
    pass


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def get_client() -> AsyncTavilyClient:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise SearchUnavailable("Deep research needs TAVILY_API_KEY in apps/backend/.env.")
    return AsyncTavilyClient(api_key=key)


async def search_one(client: AsyncTavilyClient, query: str, max_results: int) -> list[dict]:
    try:
        response = await client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_raw_content="markdown",
            timeout=60,
        )
    except Exception as error:  # one failed query must not end the round
        logger.warning("search failed for %r: %s", query, error)
        return []
    results = []
    for item in response.get("results", []):
        url = item.get("url")
        if not url:
            continue
        content = (item.get("raw_content") or item.get("content") or "").strip()
        if len(content) < 200:  # paywalls, cookie walls, empty renders
            content = (item.get("content") or content).strip()
        results.append({
            "url": url,
            "title": (item.get("title") or url).strip(),
            "content": content[:MAX_SOURCE_CHARS],
            "snippet": (item.get("content") or "")[:600],
            "publishedDate": item.get("published_date") or "",
            "score": item.get("score") or 0,
        })
    return results


async def search_many(queries: list[str], max_results: int) -> list[list[dict]]:
    client = get_client()
    return await asyncio.gather(*(search_one(client, q, max_results) for q in queries))
