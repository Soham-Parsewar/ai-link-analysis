"""Unit tests for WebsiteExtractor parsing, cleaning, and limits."""

import pytest
from unittest.mock import AsyncMock, patch

from app.config import Settings
from app.exceptions import (
    ContentTooLargeError,
    WebsiteExtractionError,
)
from app.services.website_extractor import WebsiteExtractor


def test_extractor_parses_sample_html(mock_tech_html: str):
    """Verify HTML parsing extracts metadata, headings, content, and contacts."""
    extractor = WebsiteExtractor()
    data = extractor.parse_and_clean_html("https://cloudpulse.io", mock_tech_html)

    assert data.url == "https://cloudpulse.io"
    assert "CloudPulse Technologies" in (data.title or "")
    assert "automated real-time cloud observability" in (data.meta_description or "")
    assert "CloudPulse" in (data.brand_name or "")

    # Headings
    assert len(data.h1_headings) >= 1
    assert "Unified Cloud Observability" in data.h1_headings[0]
    assert len(data.h2_headings) >= 1
    assert len(data.h3_headings) >= 1

    # Main text content & Noise cleaning
    assert "Unified Cloud Observability for Distributed Systems" in data.main_content
    # Script and style should be stripped
    assert "analytics tracker loaded" not in data.main_content
    assert "background: #fff" not in data.main_content
    # Cookie banner text should be decomposed
    assert "We use cookies to improve your browsing experience" not in data.main_content

    # Services
    assert len(data.product_or_service_snippets) >= 3

    # Contact info
    assert data.contact_info is not None
    assert "support@cloudpulse.io" in data.contact_info or "+1-800-555-0199" in data.contact_info


def test_extractor_handles_content_truncation():
    """Verify text truncation when content exceeds MAX_CONTENT_LENGTH."""
    custom_settings = Settings(MAX_CONTENT_LENGTH=200)
    extractor = WebsiteExtractor(custom_settings)

    long_html = f"""
    <html><body>
    <h1>Long Page</h1>
    <main><p>{'Observability platform metrics telemetry. ' * 50}</p></main>
    </body></html>
    """
    data = extractor.parse_and_clean_html("https://example.com", long_html)
    assert data.content_truncated is True
    assert len(data.main_content) <= 200


def test_extractor_rejects_empty_html():
    """Verify error on empty HTML response."""
    extractor = WebsiteExtractor()
    with pytest.raises(WebsiteExtractionError) as exc:
        extractor.parse_and_clean_html("https://example.com", "   ")
    assert "empty" in str(exc.value).lower()


def test_extractor_rejects_empty_body():
    """Verify error when page body contains virtually no content or headings."""
    extractor = WebsiteExtractor()
    with pytest.raises(WebsiteExtractionError) as exc:
        extractor.parse_and_clean_html("https://example.com", "<html><body><div></div></body></html>")
    assert "insufficient" in str(exc.value).lower() or "javascript" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_fetch_html_enforces_size_limit():
    """Verify ContentTooLargeError is raised when stream exceeds max_html_bytes."""
    custom_settings = Settings(MAX_HTML_SIZE_MB=1)
    extractor = WebsiteExtractor(custom_settings)

    # Mock streaming response yielding large chunks
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.encoding = "utf-8"

    async def mock_iter():
        for _ in range(30):
            yield b"X" * (1024 * 1024)  # 30 MB > 1 MB limit

    mock_resp.aiter_bytes = mock_iter

    class MockStreamContext:
        async def __aenter__(self):
            return mock_resp

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False

    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=MockStreamContext())

    with patch("httpx.AsyncClient", return_value=mock_client):
        with patch("app.utils.security.validate_hostname_ssrf"):
            with pytest.raises(ContentTooLargeError) as exc_info:
                await extractor.fetch_html("https://example.com/huge-file")
            assert "exceeded maximum limit" in str(exc_info.value).lower()
