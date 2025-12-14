"""
State definition for reflection graph.
"""
from typing import TypedDict, List, Optional, Any, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ReflectionGraphState(TypedDict):
    """State for reflection graph."""
    messages: Annotated[List[BaseMessage], add_messages]
    artifact: Optional[Any]


