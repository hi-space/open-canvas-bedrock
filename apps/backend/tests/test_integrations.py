"""Offline integration tests for dependency API migrations."""
import base64
import io
import os
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from firecrawl.v2.types import Document, DocumentMetadata

from api.firecrawl.service import scrape_urls
from core.utils import convert_pdf_to_text, get_string_from_content


class DependencyIntegrationTests(unittest.TestCase):
    def test_firecrawl_v2_document_becomes_a_context_document(self):
        document = Document(
            markdown="# Source\nVerified excerpt.",
            metadata=DocumentMetadata(title="Source title", source_url="https://example.com/source"),
        )
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"}):
            with patch("firecrawl.v2.client.FirecrawlClient.scrape", return_value=document):
                result = scrape_urls(["https://example.com/source"])
        self.assertEqual(result["documents"], [{
            "name": "example.com/source",
            "type": "text",
            "data": "# Source\nVerified excerpt.",
            "metadata": {"url": "https://example.com/source", "title": "Source title"},
        }])

    def test_empty_pdf_pages_are_supported_by_current_pypdf(self):
        pdf = PdfWriter()
        pdf.add_blank_page(width=200, height=200)
        data = io.BytesIO()
        pdf.write(data)
        encoded = base64.b64encode(data.getvalue()).decode("ascii")
        self.assertEqual(convert_pdf_to_text(encoded), "")

    def test_adaptive_thinking_does_not_become_canvas_reply_text(self):
        content = [
            {"type": "reasoning_content", "reasoning_content": {"text": "internal", "signature": "private"}},
            {"type": "reasoning", "text": "internal"},
            {"type": "text", "text": "사용자에게 보이는 답변"},
        ]
        self.assertEqual(get_string_from_content(content), "사용자에게 보이는 답변")


if __name__ == "__main__":
    unittest.main()
