"""AgentCore HTTP entry point. The runtime service enforces AWS IAM access."""
import json
import logging
import threading

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from workspace_agent.agent import AgentError, run_agent
from workspace_agent.models import Invocation
from workspace_agent.tools import ToolError


logger = logging.getLogger(__name__)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
MAX_INVOCATION_BYTES = 2 * 1024 * 1024
# The runtime's idle timeout (60 s) also ends sessions that report "Healthy"
# while a request runs, so a model turn longer than that would be lost.
_active_invocations = 0
_active_lock = threading.Lock()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("Non-finite JSON number")


@app.get("/ping")
def ping():
    # Omit the optional timestamp: changing it for each ping keeps otherwise
    # idle runtime sessions alive until their maximum lifetime.
    return {"status": "HealthyBusy" if _active_invocations else "Healthy"}


def _run_tracked(payload):
    global _active_invocations
    with _active_lock:
        _active_invocations += 1
    try:
        return run_agent(payload)
    finally:
        with _active_lock:
            _active_invocations -= 1


@app.post("/invocations")
async def invocations(request: Request):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Send an application/json workspace invocation.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_INVOCATION_BYTES:
            raise HTTPException(413, "The workspace invocation exceeds the 2 MiB limit.")
        body.extend(chunk)
    try:
        payload = json.loads(body, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        Invocation.model_validate(payload)
    except (ValueError, TypeError, RecursionError) as error:
        raise HTTPException(422, "Invalid workspace invocation. Check its fields and context limits.") from error
    try:
        return await run_in_threadpool(_run_tracked, payload)
    except (AgentError, ToolError) as error:
        logger.warning(
            "Workspace invocation failed (stage=run_agent, error=%s, cause=%s)",
            type(error).__name__,
            type(error.__cause__).__name__ if error.__cause__ is not None else "none",
        )
        raise HTTPException(502, str(error)) from error
    except Exception as error:
        # Exception strings and tracebacks may contain document/request data.
        logger.warning("Workspace invocation failed (%s)", type(error).__name__)
        raise HTTPException(502, "The workspace agent could not finish. Retry this request.") from error
