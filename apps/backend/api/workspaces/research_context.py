"""Snapshot the project material selected for one research request."""

MAX_CONTEXT_CHARACTERS = 30000
MAX_DOCUMENT_CHARACTERS = 12000


def context_excerpt(content: str, limit: int) -> str:
    """Choose which parts of a long source the researchers should read.

    Short documents stay exact. Long documents must fit `limit`, including any
    omission marker. Keeping both the introduction and conclusion is the default
    proposed policy; callers separately record that the snapshot was shortened.
    """
    if len(content) <= limit:
        return content
    marker = "\n\n[중간 내용 생략 / excerpt shortened]\n\n"
    if limit <= len(marker):
        return content[:max(0, limit)]
    available = limit - len(marker)
    head = available * 2 // 3
    tail = available - head
    return content[:head] + marker + content[-tail:]


def snapshot_context(files, paths: list[str]) -> list[dict]:
    """Read only selected, authorized files while the caller holds the project lock."""
    paths = list(dict.fromkeys(paths))
    remaining = MAX_CONTEXT_CHARACTERS
    context = []
    for index, path in enumerate(paths):
        document = files.read(path)
        allowance = min(MAX_DOCUMENT_CHARACTERS, remaining // (len(paths) - index))
        excerpt = context_excerpt(document["content"], allowance)
        remaining -= len(excerpt)
        context.append({
            "path": document["path"], "version": document["version"],
            "content": excerpt, "truncated": excerpt != document["content"],
        })
    return context
