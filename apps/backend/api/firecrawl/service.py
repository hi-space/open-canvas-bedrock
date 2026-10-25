"""
Business logic for Firecrawl web scraping.
"""
from typing import List, Dict, Any
import os
from urllib.parse import urlparse
from firecrawl import Firecrawl


def scrape_urls(urls: List[str]) -> Dict[str, Any]:
    """Scrape URLs using Firecrawl."""
    from core.exceptions import ValidationError
    
    # Check if FireCrawl API key is available
    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
    if not firecrawl_api_key:
        raise ValidationError("Firecrawl API key is missing")

    if not urls:
        raise ValidationError("`urls` is required.")

    client = Firecrawl(api_key=firecrawl_api_key, timeout=30, max_retries=1)
    context_documents = []

    for url in urls:
        try:
            doc = client.scrape(url, formats=["markdown"])
            
            if doc.markdown:
                # Extract URL components for naming
                parsed_url = urlparse(url)
                cleaned_url = f"{parsed_url.hostname}{parsed_url.path}"
                
                # Combine all page content
                text = doc.markdown
                title = doc.metadata.title if doc.metadata else None
                
                context_documents.append({
                    "name": cleaned_url,
                    "type": "text",
                    "data": text,
                    "metadata": {
                        "url": url,
                        "title": title or cleaned_url,
                    },
                })
        except Exception as url_error:
            print(f"Failed to scrape URL {url}: {url_error}", flush=True)
            # Continue processing other URLs even if one fails
            continue

    return {
        "success": bool(context_documents),
        "documents": context_documents
    }

