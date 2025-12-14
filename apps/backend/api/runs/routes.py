"""
FastAPI routes for LangSmith runs management (feedback and sharing).
"""
from fastapi import APIRouter
from api.runs.models import (
    FeedbackRequest,
    FeedbackResponse,
    ShareRunRequest,
    ShareRunResponse
)
from api.runs.service import (
    create_feedback,
    get_feedback,
    share_run,
    MAX_RETRIES,
)

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
async def create_feedback_endpoint(request: FeedbackRequest):
    """Create feedback for a LangSmith run."""
    feedback_dict = create_feedback(
        run_id=request.runId,
        feedback_key=request.feedbackKey,
        score=request.score,
        comment=request.comment
    )
    return FeedbackResponse(
        success=True,
        feedback=feedback_dict
    )


@router.get("/feedback")
async def get_feedback_endpoint(runId: str, feedbackKey: str):
    """Get feedback for a LangSmith run."""
    feedback_list = get_feedback(runId, feedbackKey)
    return {
        "feedback": feedback_list
    }


@router.post("/share", response_model=ShareRunResponse)
async def share_run_endpoint(request: ShareRunRequest):
    """Share a LangSmith run and get a public URL."""
    shared_run_url = await share_run(request.runId)
    return ShareRunResponse(sharedRunURL=shared_run_url)
