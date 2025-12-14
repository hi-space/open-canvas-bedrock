"""
Business logic for LangSmith runs management (feedback and sharing).
"""
from typing import Dict, Any, List
from langsmith import Client
from langsmith.schemas import Feedback
import os
import time

MAX_RETRIES = 5
RETRY_DELAY = 5  # seconds


def get_langsmith_client() -> Client:
    """Get LangSmith client instance."""
    from core.exceptions import InternalServerError
    api_key = os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        raise InternalServerError("LANGCHAIN_API_KEY environment variable is not set")
    return Client(api_key=api_key)


def create_feedback(
    run_id: str,
    feedback_key: str,
    score: float,
    comment: str = None
) -> Dict[str, Any]:
    """Create feedback for a LangSmith run."""
    ls_client = get_langsmith_client()
    
    # LangSmith Client.create_feedback is synchronous
    feedback = ls_client.create_feedback(
        run_id,
        feedback_key,
        score=score,
        comment=comment
    )
    
    # Convert feedback to dict
    if hasattr(feedback, 'dict'):
        feedback_dict = feedback.dict()
    elif hasattr(feedback, 'model_dump'):
        feedback_dict = feedback.model_dump()
    else:
        feedback_dict = dict(feedback) if hasattr(feedback, '__dict__') else str(feedback)
    
    return feedback_dict


def get_feedback(run_id: str, feedback_key: str) -> List[Dict[str, Any]]:
    """Get feedback for a LangSmith run."""
    ls_client = get_langsmith_client()
    
    # LangSmith Client.list_feedback returns an iterator
    run_feedback: List[Feedback] = []
    for feedback in ls_client.list_feedback(
        run_ids=[run_id],
        feedback_key=[feedback_key]
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
    
    return feedback_list


def share_run_with_retry(ls_client: Client, run_id: str) -> str:
    """Share a run with retry logic."""
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


async def share_run(run_id: str) -> str:
    """Share a LangSmith run and get a public URL."""
    ls_client = get_langsmith_client()
    # Run synchronous function in thread pool to avoid blocking
    import asyncio
    loop = asyncio.get_event_loop()
    shared_run_url = await loop.run_in_executor(
        None, 
        share_run_with_retry, 
        ls_client, 
        run_id
    )
    return shared_run_url

