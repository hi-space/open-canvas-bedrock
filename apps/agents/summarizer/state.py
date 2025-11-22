"""
State definition for summarizer graph.
"""
from typing import TypedDict, List, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class SummarizerState(TypedDict):
    """State for summarizer."""
    messages: Annotated[List[BaseMessage], add_messages]
    threadId: str

