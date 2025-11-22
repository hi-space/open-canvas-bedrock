"""
Web search graph implementation.
"""
from typing import Dict, Any, Literal
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from web_search.state import WebSearchState
from bedrock_client import get_bedrock_model

CLASSIFIER_PROMPT = """You're a helpful AI assistant tasked with classifying the user's latest message.
The user has enabled web search for their conversation, however not all messages should be searched.

Analyze their latest message in isolation and determine if it warrants a web search to include additional context.

<message>
{message}
</message>"""


class ClassificationSchema(BaseModel):
    """Schema for message classification."""
    shouldSearch: bool = Field(description="Whether or not to search the web based on the user's latest message.")


async def classify_message_node(
    state: WebSearchState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Classify if message requires web search."""
    model = get_bedrock_model(config, temperature=0)
    
    messages = state.get("messages", [])
    if not messages:
        return {"shouldSearch": False}
    
    latest_message = messages[-1]
    latest_message_content = (
        latest_message.content if isinstance(latest_message.content, str) else str(latest_message.content)
    )
    
    formatted_prompt = CLASSIFIER_PROMPT.replace("{message}", latest_message_content)
    
    # Use structured output (simplified - may need adjustment based on Bedrock capabilities)
    response = await model.ainvoke([
        HumanMessage(content=formatted_prompt)
    ])
    
    # Parse response (simplified - in real implementation, use structured output)
    content = response.content if hasattr(response, "content") else str(response)
    should_search = "yes" in content.lower() or "true" in content.lower() or "search" in content.lower()
    
    return {
        "shouldSearch": should_search
    }


async def query_generator_node(
    state: WebSearchState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Generate search query from user message."""
    messages = state.get("messages", [])
    if not messages:
        return {"query": ""}
    
    latest_message = messages[-1]
    query = (
        latest_message.content if isinstance(latest_message.content, str) else str(latest_message.content)
    )
    
    return {"query": query}


async def search_node(
    state: WebSearchState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """Perform web search."""
    query = state.get("query", "")
    
    # Simplified web search implementation
    # In real implementation, you would use a web search API like Exa, Tavily, etc.
    # For now, return empty results
    web_search_results = []
    
    # Example: If you have Exa or another search service
    # import exa_py
    # exa = exa_py.Exa(api_key=os.getenv("EXA_API_KEY"))
    # results = exa.search(query, num_results=5)
    # web_search_results = [{"pageContent": r.text, "metadata": {"url": r.url, "title": r.title}} for r in results]
    
    return {
        "webSearchResults": web_search_results
    }


def search_or_end_conditional(state: WebSearchState) -> Literal["queryGenerator", "END"]:
    """Conditional routing based on shouldSearch."""
    if state.get("shouldSearch", False):
        return "queryGenerator"
    return END


# Build graph
builder = StateGraph(WebSearchState)
builder.add_node("classifyMessage", classify_message_node)
builder.add_node("queryGenerator", query_generator_node)
builder.add_node("search", search_node)
builder.add_edge(START, "classifyMessage")
builder.add_conditional_edges(
    "classifyMessage",
    search_or_end_conditional,
    {
        "queryGenerator": "queryGenerator",
        END: END,
    }
)
builder.add_edge("queryGenerator", "search")
builder.add_edge("search", END)

graph = builder.compile()
graph.name = "Web Search Graph"

