"""
State definition for Open Canvas graph.
"""
from typing import TypedDict, List, Optional, Any, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class OpenCanvasState(TypedDict):
    """State for Open Canvas graph."""
    messages: Annotated[List[BaseMessage], add_messages]
    _messages: Annotated[List[BaseMessage], add_messages]
    artifact: Optional[Any]
    next: Optional[str]
    highlightedText: Optional[Any]
    language: Optional[str]
    artifactLength: Optional[str]
    regenerateWithEmojis: Optional[bool]
    readingLevel: Optional[str]
    portLanguage: Optional[str]
    customQuickActionId: Optional[str]
    webSearchEnabled: Optional[bool]
    webSearchResults: Optional[List[dict]]

