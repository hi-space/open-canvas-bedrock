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
from utils import get_string_from_content
import os
from tavily import TavilyClient

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
    
    # Parse response - handle both string and list content (Bedrock returns list of dicts)
    if hasattr(response, "content"):
        content = get_string_from_content(response.content)
    else:
        content = str(response)
    
    content_lower = content.lower()
    should_search = "yes" in content_lower or "true" in content_lower or "search" in content_lower
    
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
    """Perform web search using Tavily API."""
    query = state.get("query", "")
    
    if not query:
        return {"webSearchResults": []}
    
    # Get Tavily API key from environment variable
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    
    if not tavily_api_key:
        print("WARNING: TAVILY_API_KEY not found in environment variables. Returning empty search results.", flush=True)
        return {"webSearchResults": []}
    
    try:
        # Initialize Tavily client with latest API
        tavily_client = TavilyClient(api_key=tavily_api_key)
        
        # Perform search using latest Tavily API
        # The search method returns a dictionary with 'results' key
        response = tavily_client.search(
            query=query,
            max_results=5,
            search_depth="basic"  # Can be "basic" or "advanced"
        )
        
        # Transform Tavily results to match expected format
        # Latest Tavily API returns results in response['results']
        web_search_results = []
        results = response.get("results", []) if isinstance(response, dict) else []
        
        for result in results:
            web_search_results.append({
                "pageContent": result.get("content", ""),
                "metadata": {
                    "url": result.get("url", ""),
                    "title": result.get("title", ""),
                    "publishedDate": result.get("published_date", ""),
                    "author": result.get("author", ""),
                }
            })
        
        return {
            "webSearchResults": web_search_results
        }
    except Exception as e:
        print(f"Error performing web search with Tavily: {e}", flush=True)
        import traceback
        print(traceback.format_exc(), flush=True)
        # Return empty results on error
        return {"webSearchResults": []}


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

