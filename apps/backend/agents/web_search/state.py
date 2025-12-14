"""
State definition for web search graph.
"""
from typing import TypedDict, List, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class WebSearchState(TypedDict):
    """State for web search."""
    messages: Annotated[List[BaseMessage], add_messages]
    query: Optional[str]
    webSearchResults: Optional[List[dict]]
    shouldSearch: bool

