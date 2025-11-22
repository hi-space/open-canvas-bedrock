"""
FastAPI application for Open Canvas agents with AWS Bedrock support.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

load_dotenv()

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
from threads.routes import router as threads_router

app.include_router(open_canvas_router, prefix="/api/agent", tags=["agent"])
app.include_router(reflection_router, prefix="/api/reflection", tags=["reflection"])
app.include_router(thread_title_router, prefix="/api/thread-title", tags=["thread-title"])
app.include_router(summarizer_router, prefix="/api/summarizer", tags=["summarizer"])
app.include_router(web_search_router, prefix="/api/web-search", tags=["web-search"])
app.include_router(threads_router, prefix="/threads", tags=["threads"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

