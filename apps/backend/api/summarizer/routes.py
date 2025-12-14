"""
FastAPI routes for summarizer agent.
"""
from fastapi import APIRouter
from api.summarizer.models import SummarizerRequest
from api.summarizer.service import summarize

router = APIRouter()


@router.post("/summarize")
async def summarize_endpoint(request: SummarizerRequest):
    """Summarize conversation messages."""
    result = await summarize(
        messages=request.messages,
        thread_id=request.threadId,
        config=request.config
    )
    return result
