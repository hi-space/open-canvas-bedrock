"""
State definition for thread title generation.
"""
from typing import TypedDict, List, Optional, Any, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class TitleGenerationState(TypedDict):
    """State for title generation."""
    messages: Annotated[List[BaseMessage], add_messages]
    artifact: Optional[Any]

