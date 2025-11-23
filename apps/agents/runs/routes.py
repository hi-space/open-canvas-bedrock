"""
FastAPI routes for LangSmith runs management (feedback and sharing).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from langsmith import Client
from langsmith.schemas import Feedback
import os

router = APIRouter()

# Initialize LangSmith client
def get_langsmith_client() -> Client:
    """Get LangSmith client instance."""
    api_key = os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="LANGCHAIN_API_KEY environment variable is not set"
        )
    return Client(api_key=api_key)


class FeedbackRequest(BaseModel):
    """Request model for creating feedback."""
    runId: str
    feedbackKey: str
    score: float
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    """Response model for feedback."""
    success: bool
    feedback: dict


@router.post("/feedback", response_model=FeedbackResponse)
async def create_feedback(request: FeedbackRequest):
    """Create feedback for a LangSmith run."""
    try:
        ls_client = get_langsmith_client()
        
        # LangSmith Client.create_feedback is synchronous
        feedback = ls_client.create_feedback(
            request.runId,
            request.feedbackKey,
            score=request.score,
            comment=request.comment
        )
        
        # Convert feedback to dict
        if hasattr(feedback, 'dict'):
            feedback_dict = feedback.dict()
        elif hasattr(feedback, 'model_dump'):
            feedback_dict = feedback.model_dump()
        else:
            feedback_dict = dict(feedback) if hasattr(feedback, '__dict__') else str(feedback)
        
        return FeedbackResponse(
            success=True,
            feedback=feedback_dict
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create feedback: {str(e)}"
        )


@router.get("/feedback")
async def get_feedback(runId: str, feedbackKey: str):
    """Get feedback for a LangSmith run."""
    try:
        ls_client = get_langsmith_client()
        
        # LangSmith Client.list_feedback returns an iterator
        # Note: feedback_key is singular, not feedback_keys
        run_feedback: List[Feedback] = []
        for feedback in ls_client.list_feedback(
            run_ids=[runId],
            feedback_key=[feedbackKey]
        ):
            run_feedback.append(feedback)
        
        # Convert feedback objects to dicts
        feedback_list = []
        for fb in run_feedback:
            if hasattr(fb, 'dict'):
                feedback_list.append(fb.dict())
            elif hasattr(fb, 'model_dump'):
                feedback_list.append(fb.model_dump())
            elif hasattr(fb, '__dict__'):
                feedback_list.append(dict(fb))
            else:
                feedback_list.append(str(fb))
        
        return {
            "feedback": feedback_list
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch feedback: {str(e)}"
        )


class ShareRunRequest(BaseModel):
    """Request model for sharing a run."""
    runId: str


class ShareRunResponse(BaseModel):
    """Response model for sharing a run."""
    sharedRunURL: str


MAX_RETRIES = 5
RETRY_DELAY = 5  # seconds


def share_run_with_retry(
    ls_client: Client,
    run_id: str
) -> str:
    """Share a run with retry logic."""
    import time
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # LangSmith Client.share_run is synchronous
            shared_url = ls_client.share_run(run_id)
            return shared_url
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise e
            print(f"Attempt {attempt} failed. Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)
    
    raise Exception("Max retries reached")


@router.post("/share", response_model=ShareRunResponse)
async def share_run(request: ShareRunRequest):
    """Share a LangSmith run and get a public URL."""
    try:
        ls_client = get_langsmith_client()
        # Run synchronous function in thread pool to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        shared_run_url = await loop.run_in_executor(
            None, 
            share_run_with_retry, 
            ls_client, 
            request.runId
        )
        
        return ShareRunResponse(sharedRunURL=shared_run_url)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to share run after {MAX_RETRIES} attempts: {str(e)}"
        )

