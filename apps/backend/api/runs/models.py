"""
Request/Response models for runs API.
"""
from pydantic import BaseModel
from typing import Optional


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


class ShareRunRequest(BaseModel):
    """Request model for sharing a run."""
    runId: str


class ShareRunResponse(BaseModel):
    """Response model for sharing a run."""
    sharedRunURL: str

