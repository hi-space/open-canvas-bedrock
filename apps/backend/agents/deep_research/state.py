"""
State definition for the deep research writer graph.
"""
from typing import TypedDict, List, Optional, Any, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class DeepResearchState(TypedDict, total=False):
    """State for deep research. Research artifacts are plain dicts so they serialize into SSE events."""
    # Status first: the canvas UI shows the first short string of a node's output as its progress line.
    researchStatus: str
    messages: Annotated[List[BaseMessage], add_messages]
    projectContext: List[dict]  # server snapshots: path, version, content, truncated
    suppliedSources: List[dict]  # registered reference excerpts, not instructions
    genre: str
    maxCitedSources: Optional[int]  # set by destinations with a source limit (project workspaces)
    brief: dict             # title, audience, thesis, language, questions[{id, question, queries}]
    sources: dict           # "S1" -> {id, url, title, content, publishedDate}
    findings: List[dict]    # {id, question_id, claim, detail, quote, sources}
    pendingQueries: List[dict]  # {question_id, query}
    extracted: List[str]    # "Q1:S3" pairs already read, so later rounds read only new sources
    round: int
    gaps: List[str]
    outline: dict           # title, sections[{id, heading, goal, points, finding_ids, words, figure}]
    figures: List[dict]     # {section_id, number, caption, url}
    drafts: dict            # section_id -> markdown
    reviewNotes: dict       # section_id -> notes; "_global" -> notes
    runId: str              # names the figure asset directory
    assetOwner: Optional[str]  # owner key whose session may read the figures
    artifact: Optional[Any]
