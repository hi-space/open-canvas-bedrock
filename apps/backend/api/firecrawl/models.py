"""
Request/Response models for Firecrawl API.
"""
from pydantic import BaseModel
from typing import List


class FirecrawlScrapeRequest(BaseModel):
    """Request model for Firecrawl scraping."""
    urls: List[str]

