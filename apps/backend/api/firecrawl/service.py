"""
Business logic for Firecrawl web scraping.
"""
from typing import List, Dict, Any
import os
from urllib.parse import urlparse


def scrape_urls(urls: List[str]) -> Dict[str, Any]:
    """Scrape URLs using Firecrawl."""
    from core.exceptions import ValidationError
    
    # Check if FireCrawl API key is available
    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
    if not firecrawl_api_key:
        raise ValidationError("Firecrawl API key is missing")

    if not urls:
        raise ValidationError("`urls` is required.")

    # Import FireCrawlLoader
    try:
        from langchain_community.document_loaders import FireCrawlLoader
    except ImportError:
        from core.exceptions import InternalServerError
        raise InternalServerError(
            "FireCrawlLoader not available. Please install langchain-community."
        )

    context_documents = []

    for url in urls:
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

