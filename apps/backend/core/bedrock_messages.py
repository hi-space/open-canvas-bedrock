"""Model-specific Converse history handling shared by both execution paths."""
from typing import Any

from core.models import REASONING_HISTORY_EXCLUDED_MODELS


def prepare_converse_messages(
    model_name: str, messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Kimi K3 rejects replayed reasoning; preserve text, tools, and saved history."""
    if model_name not in REASONING_HISTORY_EXCLUDED_MODELS:
        return messages

    prepared = []
    for message in messages:
        if message["role"] != "assistant":
            prepared.append(message)
            continue
        content = [block for block in message["content"] if "reasoningContent" not in block]
        if content:
            prepared.append({**message, "content": content})
    return prepared
