"""Integration and end-to-end tests for the /link-analysis API endpoint."""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.exceptions import ContentTooLargeError, LLMServiceError, WebsiteExtractionError


@patch("app.utils.url_validator.validate_hostname_ssrf")
@patch("app.utils.security.validate_hostname_ssrf")
def test_link_analysis_success_end_to_end(
    mock_ssrf1, mock_ssrf2, client: TestClient, mock_tech_html: str
):
    """Test full link-analysis pipeline with mocked HTML fetch and grounded analysis."""
    with patch(
        "app.services.website_extractor.WebsiteExtractor.fetch_html",
        new=AsyncMock(return_value=("https://cloudpulse.io/", mock_tech_html)),
    ):
        response = client.post("/link-analysis", json={"url": "https://cloudpulse.io"})
        assert response.status_code == 200, response.text
        data = response.json()

        # Envelope checks
        assert data["success"] is True
        assert data["website"] == "https://cloudpulse.io/"

        # Brand
        brand = data["brand"]
        assert "CloudPulse" in brand["name"]
        assert brand["category"]
        assert brand["summary"]
        assert len(brand["main_products"]) >= 1
        assert len(brand["main_services"]) >= 1

        # Analysis Sections
        analysis = data["analysis"]

        # Section 1: Competitor Analysis
        competitor_analysis = analysis["competitor_analysis"]
        assert competitor_analysis["brand_overview"]
        assert len(competitor_analysis["competitors"]) >= 3
        first_comp = competitor_analysis["competitors"][0]
        assert first_comp["name"]
        assert first_comp["overview"]
        assert first_comp["is_ai_suggested"] is True
        assert len(competitor_analysis["competitive_advantages"]) >= 1
        assert len(competitor_analysis["positioning_gaps"]) >= 1

        # Section 2: Target Search Queries (Exactly 5)
        search_queries = analysis["target_search_queries"]
        assert len(search_queries) == 5
        for q in search_queries:
            assert q["query"]
            assert len(q["platforms"]) >= 1
            assert q["search_intent"]
            assert q["business_relevance"]
            assert q["target_audience"]
            assert q["is_ai_suggested"] is True

        # Section 3: SEO Improvements
        seo = analysis["seo_improvements"]
        assert seo["primary_keyword"]
        assert len(seo["secondary_keywords"]) >= 1
        assert len(seo["long_tail_keywords"]) >= 1
        assert seo["seo_title"]["recommended_title"]
        assert seo["meta_description"]["recommended_meta_description"]
        assert len(seo["supporting_content"]) >= 1
        assert len(seo["technical_observations"]) >= 1

        # Section 4: Top 5 Services
        services = analysis["top_services"]
        assert 1 <= len(services) <= 5
        for s in services:
            assert s["service_name"]
            assert s["description"]
            assert s["target_industry"]
            assert s["main_benefit"]

        # Section 5: Target Audience
        audience = analysis["target_audience"]
        assert len(audience["primary_audience"]) >= 1
        assert len(audience["secondary_audience"]) >= 1
        assert len(audience["industry_segments"]) >= 1
        assert len(audience["pain_points"]) >= 1

        # Metadata
        meta = data["metadata"]
        assert meta["analysis_timestamp"]
        assert meta["llm_provider"]
        assert meta["llm_model"]
        assert meta["cached"] is False
        assert meta["execution_time_seconds"] >= 0


@patch("app.utils.url_validator.validate_hostname_ssrf")
@patch("app.utils.security.validate_hostname_ssrf")
def test_link_analysis_caching_behavior(
    mock_ssrf1, mock_ssrf2, client: TestClient, mock_tech_html: str
):
    """Verify second identical request is served directly from the cache."""
    with patch(
        "app.services.website_extractor.WebsiteExtractor.fetch_html",
        new=AsyncMock(return_value=("https://cached-site.com/", mock_tech_html)),
    ):
        # First request: un-cached
        res1 = client.post("/link-analysis", json={"url": "https://cached-site.com"})
        assert res1.status_code == 200
        assert res1.json()["metadata"]["cached"] is False

        # Second request: cached
        res2 = client.post("/link-analysis", json={"url": "https://cached-site.com"})
        assert res2.status_code == 200
        assert res2.json()["metadata"]["cached"] is True


def test_link_analysis_invalid_inputs(client: TestClient):
    """Verify endpoint rejects invalid payloads with 400 Bad Request."""
    # Missing URL
    r1 = client.post("/link-analysis", json={})
    assert r1.status_code == 400

    # Non-string URL
    r2 = client.post("/link-analysis", json={"url": 12345})
    assert r2.status_code == 400

    # Disallowed scheme
    r3 = client.post("/link-analysis", json={"url": "file:///etc/hosts"})
    assert r3.status_code == 400
    assert "Only HTTP and HTTPS URLs are permitted" in r3.json()["detail"] or "Unsupported protocol" in r3.json()["detail"]


@patch("app.utils.url_validator.validate_hostname_ssrf")
@patch("app.utils.security.validate_hostname_ssrf")
def test_link_analysis_website_404_error(mock_ssrf1, mock_ssrf2, client: TestClient):
    """Verify appropriate error response when target site is not found."""
    with patch(
        "app.services.website_extractor.WebsiteExtractor.extract",
        side_effect=WebsiteExtractionError("Website returned 404 Not Found", status_code=404),
    ):
        resp = client.post("/link-analysis", json={"url": "https://example-404.com"})
        assert resp.status_code == 404
        assert "404" in resp.json()["detail"]


@patch("app.utils.url_validator.validate_hostname_ssrf")
@patch("app.utils.security.validate_hostname_ssrf")
def test_link_analysis_content_too_large(mock_ssrf1, mock_ssrf2, client: TestClient):
    """Verify HTTP 413 when website exceeds size limit."""
    with patch(
        "app.services.website_extractor.WebsiteExtractor.extract",
        side_effect=ContentTooLargeError("Website HTML exceeded limit"),
    ):
        resp = client.post("/link-analysis", json={"url": "https://huge-site.com"})
        assert resp.status_code == 413
        assert "exceeded" in resp.json()["detail"].lower()


@patch("app.utils.url_validator.validate_hostname_ssrf")
@patch("app.utils.security.validate_hostname_ssrf")
def test_link_analysis_llm_failure(
    mock_ssrf1, mock_ssrf2, client: TestClient, mock_tech_html: str
):
    """Verify HTTP 502 when LLM service fails."""
    with patch(
        "app.services.website_extractor.WebsiteExtractor.fetch_html",
        new=AsyncMock(return_value=("https://example-llm-fail.com/", mock_tech_html)),
    ):
        with patch(
            "app.services.llm_service.GroundedMockProvider.generate_analysis",
            side_effect=LLMServiceError("Upstream model error"),
        ):
            resp = client.post("/link-analysis", json={"url": "https://example-llm-fail.com"})
            assert resp.status_code == 502
            assert "AI Analysis Error" in resp.json()["detail"]
