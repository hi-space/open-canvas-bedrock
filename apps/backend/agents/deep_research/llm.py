"""Model helpers: token-budgeted models, JSON calls with one repair round, bounded concurrency."""
import asyncio
import json
import logging
import re
from typing import Any, Awaitable, Iterable, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ValidationError

from core import bedrock_client
from core.models import get_model_definition
from core.utils import get_model_config

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# Bedrock throttles bursts; research fans out to many parallel calls.
_LLM_CONCURRENCY = asyncio.Semaphore(4)


def get_model(config: RunnableConfig, max_tokens: int):
    """The user's chosen model with an output budget clamped to that model's ceiling."""
    name = get_model_config(config)["modelName"]
    ceiling = get_model_definition(name)["config"]["maxTokens"]["max"]
    return bedrock_client.get_bedrock_model(config, max_tokens=min(max_tokens, ceiling))


def chunk_text(content: Any) -> str:
    """Streaming chunks must be joined without separators (get_string_from_content joins with newlines)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) and item.get("type", "text") == "text"
            else (item if isinstance(item, str) else "")
            for item in content
        )
    return ""


def _extract_json(text: str) -> Any:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("no JSON object in response")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


async def ainvoke_text(model, system: str, user: str) -> str:
    """Streamed internally: long answers stay under the client's read timeout, which a blocking call is not."""
    text, stop = "", None
    async with _LLM_CONCURRENCY:
        async for chunk in model.astream([SystemMessage(content=system), HumanMessage(content=user)]):
            text += chunk_text(chunk.content)
            stop = (chunk.response_metadata or {}).get("stopReason") or stop
    if stop and stop != "end_turn":
        logger.warning("model stopped with %s after %d chars", stop, len(text))
    return text.strip()


async def ainvoke_json(model, system: str, user: str, schema: type[T]) -> T:
    """Ask for JSON matching `schema`; on a parse or validation error, show the model its error once."""
    system = (
        f"{system}\n\nRespond with ONE JSON object only, no prose, matching this JSON schema:\n"
        f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
    )
    text = await ainvoke_text(model, system, user)
    try:
        return schema.model_validate(_extract_json(text))
    except (ValueError, ValidationError) as error:
        logger.warning("JSON repair for %s: %s", schema.__name__, str(error)[:300])
        repair = (
            f"{user}\n\n<previous-response>\n{text[:20000]}\n</previous-response>\n"
            f"The previous response was invalid: {str(error)[:1500]}\nReturn the corrected JSON object only."
        )
        text = await ainvoke_text(model, system, repair)
        try:
            return schema.model_validate(_extract_json(text))
        except (ValueError, ValidationError):
            logger.warning("JSON repair failed for %s; response began: %r", schema.__name__, text[:400])
            raise


async def gather_limited(tasks: Iterable[Awaitable[Any]]) -> list[Any]:
    """Run tasks concurrently, returning exceptions in place so one failure does not sink a research round."""
    return await asyncio.gather(*tasks, return_exceptions=True)
