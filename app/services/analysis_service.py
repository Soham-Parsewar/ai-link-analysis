"""Analysis orchestration service linking extraction, caching, and LLM processing."""

import datetime
import hashlib
import logging
import time
from typing import Optional

from app.config import Settings, get_settings
from app.schemas import (
    AnalysisMetadata,
    LinkAnalysisResponse,
)
from app.services.llm_service import BaseLLMProvider, get_llm_provider
from app.services.website_extractor import WebsiteExtractor
from app.utils.cache import analysis_cache

logger = logging.getLogger(__name__)


class AnalysisService:
    """End-to-end website link analysis orchestrator."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        extractor: Optional[WebsiteExtractor] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
    ):
        self.settings = settings or get_settings()
        self.extractor = extractor or WebsiteExtractor(self.settings)
        self.llm_provider = llm_provider or get_llm_provider(self.settings)

    async def analyze_url(self, target_url: str) -> LinkAnalysisResponse:
        """
        Execute end-to-end analysis of target website:
        URL -> Caching check -> Secure Extraction -> LLM Analysis -> Validation -> Response.
        """
        start_time = time.time()
        logger.info(f"Starting analysis for URL: {target_url}")

        # Check Cache before extraction if enabled
        url_cache_key = analysis_cache.generate_key(target_url)
        if self.settings.CACHE_ENABLED:
            cached_data = analysis_cache.get(url_cache_key)
            if cached_data:
                logger.info(f"Serving analysis from cache for URL: {target_url}")
                resp = LinkAnalysisResponse.model_validate(cached_data)
                resp.metadata.cached = True
                return resp

        # Step 1: Secure Website Content Extraction
        website_data = await self.extractor.extract(target_url)

        # Step 2: Content-based cache check (avoids LLM call if unchanged content exists)
        content_hash = hashlib.sha256(website_data.main_content.encode("utf-8")).hexdigest()
        combined_cache_key = analysis_cache.generate_key(target_url, content_hash)

        if self.settings.CACHE_ENABLED:
            cached_by_content = analysis_cache.get(combined_cache_key)
            if cached_by_content:
                logger.info(f"Serving analysis from content-hash cache for URL: {target_url}")
                resp = LinkAnalysisResponse.model_validate(cached_by_content)
                resp.metadata.cached = True
                return resp

        # Step 3: LLM Analysis
        brand_info, analysis_content = await self.llm_provider.generate_analysis(website_data)

        is_fallback = (
            self.settings.LLM_PROVIDER == "mock"
            or not self.settings.LLM_API_KEY
            or self.settings.LLM_API_KEY.strip() == ""
        )

        actual_provider = (
            "mock (heuristic_fallback)"
            if is_fallback
            else self.settings.LLM_PROVIDER
        )
        actual_model = (
            "grounded-heuristic-v1"
            if is_fallback
            else self.settings.LLM_MODEL
        )
        analysis_source = (
            "website_content_and_heuristic_fallback"
            if is_fallback
            else "website_content_and_ai"
        )

        # Assemble Warnings
        warnings: list[str] = []
        if is_fallback:
            warnings.append(
                "Running in heuristic fallback mode (no external LLM API key configured). "
                "Analysis generated via built-in grounded heuristic engine."
            )
        if website_data.content_truncated:
            warnings.append(
                f"Website content exceeded {self.settings.MAX_CONTENT_LENGTH} characters and was truncated for processing."
            )
        if not website_data.meta_description:
            warnings.append("Website had no meta description in HTML; recommended meta description was newly created.")
        if not website_data.h1_headings:
            warnings.append("No primary H1 heading detected on the website.")

        execution_duration = round(time.time() - start_time, 3)

        metadata = AnalysisMetadata(
            analysis_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            llm_provider=actual_provider,
            llm_model=actual_model,
            content_truncated=website_data.content_truncated,
            raw_content_chars=website_data.raw_content_length,
            analysis_source=analysis_source,
            warnings=warnings,
            cached=False,
            execution_time_seconds=execution_duration,
        )

        response = LinkAnalysisResponse(
            success=True,
            website=website_data.url,
            brand=brand_info,
            analysis=analysis_content,
            metadata=metadata,
        )

        # Step 4: Populate Cache
        if self.settings.CACHE_ENABLED:
            analysis_cache.set(url_cache_key, response.model_dump(), ttl=self.settings.CACHE_TTL_SECONDS)
            analysis_cache.set(combined_cache_key, response.model_dump(), ttl=self.settings.CACHE_TTL_SECONDS)

        logger.info(f"Analysis completed in {execution_duration}s for {target_url}")
        return response
