"""
FastAPI routes for Firecrawl web scraping.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os

router = APIRouter()


class FirecrawlScrapeRequest(BaseModel):
    """Request model for Firecrawl scraping."""
    urls: List[str]


@router.post("/scrape")
async def scrape(request: FirecrawlScrapeRequest):
    """Scrape URLs using Firecrawl."""
    try:
        # Check if FireCrawl API key is available
        firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
        if not firecrawl_api_key:
            raise HTTPException(
                status_code=400,
                detail="Firecrawl API key is missing"
            )

        if not request.urls:
            raise HTTPException(
                status_code=400,
                detail="`urls` is required."
            )

        # Import FireCrawlLoader
        try:
            from langchain_community.document_loaders import FireCrawlLoader
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="FireCrawlLoader not available. Please install langchain-community."
            )

        context_documents = []

        for url in request.urls:
            try:
                loader = FireCrawlLoader(
                    url=url,
                    mode="scrape",
                    api_key=firecrawl_api_key,
                    params={"formats": ["markdown"]}
                )
                docs = loader.load()
                
                if docs:
                    # Extract URL components for naming
                    from urllib.parse import urlparse
                    parsed_url = urlparse(url)
                    cleaned_url = f"{parsed_url.hostname}{parsed_url.path}"
                    
                    # Combine all page content
                    text = "\n".join([doc.page_content for doc in docs])
                    
                    context_documents.append({
                        "name": cleaned_url,
                        "type": "text",
                        "data": text,
                        "metadata": {
                            "url": url,
                        },
                    })
            except Exception as url_error:
                print(f"Failed to scrape URL {url}: {url_error}", flush=True)
                # Continue processing other URLs even if one fails
                continue

        return {
            "success": True,
            "documents": context_documents
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error scraping URLs: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Failed to scrape URLs: {str(e)}")

