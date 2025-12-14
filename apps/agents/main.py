"""
FastAPI application for Open Canvas agents with AWS Bedrock support.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

load_dotenv()

# Configure LangSmith tracing if API key is available
# LANGCHAIN_TRACING_V2=true is sufficient for LangSmith tracing
langchain_api_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
if langchain_api_key:
    # Set LangSmith tracing environment variables
    os.environ["LANGCHAIN_API_KEY"] = langchain_api_key
    # LANGCHAIN_TRACING_V2 enables LangSmith tracing (v2 is the current version)
    os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2", "true")
    
    # Optional: Set LangSmith endpoint if provided
    if os.getenv("LANGSMITH_ENDPOINT"):
        os.environ["LANGSMITH_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT")
    
    # Optional: Set project name if provided
    if os.getenv("LANGSMITH_PROJECT"):
        os.environ["LANGSMITH_PROJECT"] = os.getenv("LANGSMITH_PROJECT")
else:
    print("Warning: LANGCHAIN_API_KEY or LANGSMITH_API_KEY not set. LangSmith tracing will be disabled.", flush=True)

app = FastAPI(title="Open Canvas Agents API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

# Import and include routers
from open_canvas.routes import router as open_canvas_router
from reflection.routes import router as reflection_router
from thread_title.routes import router as thread_title_router
from summarizer.routes import router as summarizer_router
from web_search.routes import router as web_search_router
from firecrawl_api.routes import router as firecrawl_router
from threads.routes import router as threads_router
from assistants.routes import router as assistants_router
from store.routes import router as store_router
from runs.routes import router as runs_router
from models_routes import router as models_router

app.include_router(open_canvas_router, prefix="/api/agent", tags=["agent"])
app.include_router(reflection_router, prefix="/api/reflection", tags=["reflection"])
app.include_router(thread_title_router, prefix="/api/thread-title", tags=["thread-title"])
app.include_router(summarizer_router, prefix="/api/summarizer", tags=["summarizer"])
app.include_router(web_search_router, prefix="/api/web-search", tags=["web-search"])
app.include_router(firecrawl_router, prefix="/api/firecrawl", tags=["firecrawl"])
app.include_router(threads_router, prefix="/api/threads", tags=["threads"])
app.include_router(assistants_router, prefix="/api/assistants", tags=["assistants"])
app.include_router(store_router, prefix="/api/store", tags=["store"])
app.include_router(runs_router, prefix="/api/runs", tags=["runs"])
app.include_router(models_router, prefix="/api/models", tags=["models"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

