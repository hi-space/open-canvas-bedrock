"""
FastAPI routes for Firecrawl web scraping.
"""
from fastapi import APIRouter
from api.firecrawl.models import FirecrawlScrapeRequest
from api.firecrawl.service import scrape_urls

router = APIRouter()


@router.post("/scrape")
async def scrape_endpoint(request: FirecrawlScrapeRequest):
    """Scrape URLs using Firecrawl."""
    result = scrape_urls(request.urls)
    return result
