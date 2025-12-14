"""
Request/Response models for summarizer agent API.
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class SummarizerRequest(BaseModel):
    """Request model for summarizer."""
    messages: List[Dict[str, Any]]
    threadId: str
    config: Optional[Dict[str, Any]] = None

