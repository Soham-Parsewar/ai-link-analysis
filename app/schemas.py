"""Pydantic v2 schemas for API requests, responses, and website analysis models."""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.utils.url_validator import normalize_and_validate_url


# =====================================================================
# Request Schemas
# =====================================================================

class LinkAnalysisRequest(BaseModel):
    """Incoming request schema for link analysis."""

    url: str = Field(
        ...,
        description="The website URL to analyze (must be a valid HTTP or HTTPS URL).",
        examples=["https://example.com"],
    )

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, v: Any) -> str:
        """Validate, sanitize, and normalize URL."""
        if not isinstance(v, str):
            raise ValueError("URL must be a string.")
        return normalize_and_validate_url(v)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://example.com"
            }
        }
    )


# =====================================================================
# Extraction Data Schema
# =====================================================================

class WebsiteData(BaseModel):
    """Structured data extracted from an external website."""

    url: str
    title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    brand_name: Optional[str] = None
    h1_headings: list[str] = Field(default_factory=list)
    h2_headings: list[str] = Field(default_factory=list)
    h3_headings: list[str] = Field(default_factory=list)
    main_content: str = ""
    product_or_service_snippets: list[str] = Field(default_factory=list)
    contact_info: Optional[str] = None
    open_graph: dict[str, str] = Field(default_factory=dict)
    content_truncated: bool = False
    raw_content_length: int = 0


# =====================================================================
# Section 1: Brand & Competitor Analysis Schemas
# =====================================================================

class BrandInfo(BaseModel):
    """Core brand information derived from the website."""

    name: str = Field(..., description="Brand or organization name.")
    category: str = Field(..., description="Primary business category / sector.")
    summary: str = Field(..., description="Concise website-derived business summary.")
    main_products: list[str] = Field(default_factory=list, description="Primary products identified.")
    main_services: list[str] = Field(default_factory=list, description="Primary services identified.")
    target_market: str = Field(..., description="Identified market focus (e.g. B2B, B2C, SMB, Enterprise).")
    positioning: str = Field(..., description="Market positioning statement.")
    value_proposition: str = Field(..., description="Core value proposition communicated on the website.")
    strengths: list[str] = Field(default_factory=list, description="Key organizational or product strengths.")


class CompetitorItem(BaseModel):
    """Individual competitor profile."""

    name: str = Field(..., description="Competitor name.")
    overview: str = Field(..., description="Business overview of competitor.")
    main_products_or_services: list[str] = Field(default_factory=list, description="Competitor offerings.")
    target_market: str = Field(..., description="Target audience of competitor.")
    strengths: list[str] = Field(default_factory=list, description="Key competitor strengths.")
    weaknesses_or_gaps: list[str] = Field(default_factory=list, description="Competitor weaknesses or market gaps.")
    comparison: str = Field(..., description="Comparison with the submitted brand.")
    is_ai_suggested: bool = Field(
        default=True,
        description="Indicates this competitor was generated via AI market knowledge rather than verified on-site.",
    )


class CompetitorAnalysis(BaseModel):
    """Competitor vs Brand analysis section."""

    brand_overview: str = Field(..., description="Comprehensive overview of the submitted brand.")
    competitors: list[CompetitorItem] = Field(
        default_factory=list,
        description="Identified competitors (minimum 3 when reliable information is available).",
    )
    competitive_advantages: list[str] = Field(
        default_factory=list, description="Competitive advantages of the submitted brand."
    )
    positioning_gaps: list[str] = Field(
        default_factory=list, description="Identified market or positioning gaps."
    )
    differentiation_opportunities: list[str] = Field(
        default_factory=list, description="Opportunities to differentiate the brand from rivals."
    )
    improvement_recommendations: list[str] = Field(
        default_factory=list, description="Actionable recommendations to enhance market positioning."
    )


# =====================================================================
# Section 2: Top 5 Target Search Queries Schemas
# =====================================================================

class SearchQueryItem(BaseModel):
    """Individual target search query."""

    query: str = Field(..., description="Specific search query string.")
    platforms: list[str] = Field(
        ...,
        description="Relevant discovery platforms (Google Search, Facebook, Instagram, LinkedIn, X).",
    )
    search_intent: str = Field(
        ..., description="Search intent (e.g. Commercial, Informational, Service Discovery, B2B)."
    )
    business_relevance: str = Field(..., description="Why this query is directly relevant to the business.")
    target_audience: str = Field(..., description="Audience persona searching for this query.")
    query_type: str = Field(..., description="Category of query (e.g. Service-specific, B2B, Long-tail).")
    is_ai_suggested: bool = Field(
        default=True,
        description="Explicitly indicates this keyword suggestion is AI-modeled without API search volumes.",
    )


# =====================================================================
# Section 3: SEO Improvements Schemas
# =====================================================================

class SeoTitleRecommendation(BaseModel):
    """SEO title audit and recommendation."""

    current_title: Optional[str] = Field(None, description="Current website title found in HTML.")
    recommended_title: str = Field(..., description="Optimized SEO title recommendation.")
    reason: str = Field(..., description="Rationale for title improvement.")
    target_keyword: str = Field(..., description="Primary keyword targeted in the title.")


class SeoMetaRecommendation(BaseModel):
    """SEO meta description audit and recommendation."""

    current_meta_description: Optional[str] = Field(
        None, description="Current meta description from HTML."
    )
    recommended_meta_description: str = Field(
        ..., description="Concise, click-worthy recommended meta description."
    )
    explanation: str = Field(..., description="Explanation of improvements made.")


class SeoImprovements(BaseModel):
    """SEO recommendations section."""

    primary_keyword: str = Field(..., description="Single most critical organic target keyword.")
    secondary_keywords: list[str] = Field(default_factory=list, description="Supporting keywords.")
    long_tail_keywords: list[str] = Field(default_factory=list, description="High-intent long-tail phrases.")
    industry_keywords: list[str] = Field(default_factory=list, description="Industry and vertical terminology.")
    service_keywords: list[str] = Field(default_factory=list, description="Service-specific keywords.")
    seo_title: SeoTitleRecommendation = Field(..., description="Title tag audit and optimization.")
    meta_description: SeoMetaRecommendation = Field(..., description="Meta description audit and optimization.")
    supporting_content: list[str] = Field(
        default_factory=list,
        description="Recommended content assets (service pages, FAQs, comparison guides, blog topics).",
    )
    technical_observations: list[str] = Field(
        default_factory=list,
        description="Observations regarding title, meta, H1 presence, structure, and content density.",
    )


# =====================================================================
# Section 4: Top 5 Services Schemas
# =====================================================================

class ServiceItem(BaseModel):
    """Detailed profile of a core service offered by the business."""

    service_name: str = Field(..., description="Name of the service.")
    description: str = Field(..., description="Concise explanation of the service offering.")
    target_industry: str = Field(..., description="Target industry vertical.")
    target_customer: str = Field(..., description="Ideal customer persona or business profile.")
    main_benefit: str = Field(..., description="Key tangible outcome or benefit delivered.")
    evidence_from_website: Optional[str] = Field(
        None, description="Direct quote or textual reference from website confirming this service."
    )
    confidence_level: str = Field(
        default="high",
        description="Extraction confidence ('high', 'medium', 'inferred').",
    )
    is_inferred: bool = Field(
        default=False,
        description="True if inferred by AI; False if explicitly extracted from website text.",
    )


# =====================================================================
# Section 5: Target Audience Schemas
# =====================================================================

class TargetAudienceProfile(BaseModel):
    """Individual audience segment profile."""

    audience_name: str = Field(..., description="Name of audience group (e.g. Enterprise CTOs, SMB Owners).")
    business_type: str = Field(..., description="Business category (B2B, B2C, Startup, Enterprise).")
    industry: str = Field(..., description="Relevant industry.")
    company_size: Optional[str] = Field(None, description="Estimated company size (e.g. 10-50, 500+).")
    needs: list[str] = Field(default_factory=list, description="Primary requirements of this audience.")
    challenges: list[str] = Field(default_factory=list, description="Operational or technical bottlenecks.")
    interests: list[str] = Field(default_factory=list, description="Topics and solutions of high interest.")
    business_relevance: str = Field(..., description="Why the analyzed website solves their needs.")
    is_inferred: bool = Field(default=True, description="Indicates profile was inferred by AI model.")


class TargetAudience(BaseModel):
    """Comprehensive target audience identification section."""

    primary_audience: list[TargetAudienceProfile] = Field(
        default_factory=list, description="Core target customer profiles."
    )
    secondary_audience: list[TargetAudienceProfile] = Field(
        default_factory=list, description="Secondary or adjacent customer profiles."
    )
    industry_segments: list[str] = Field(default_factory=list, description="Key industry segments.")
    business_segments: list[str] = Field(default_factory=list, description="Business classifications.")
    customer_profiles: list[str] = Field(default_factory=list, description="General customer personas.")
    geographic_focus: Optional[str] = Field(
        None, description="Geographic or regional focus if supported by website content."
    )
    marketing_audience_segments: list[str] = Field(
        default_factory=list, description="Recommended targeting segments for digital campaigns."
    )
    pain_points: list[str] = Field(
        default_factory=list, description="Core customer pain points addressed by the business."
    )


# =====================================================================
# Aggregated Analysis & Response Schemas
# =====================================================================

class AnalysisContent(BaseModel):
    """Combined analysis payload containing all five core sections."""

    competitor_analysis: CompetitorAnalysis = Field(..., description="Section 1: Competitor vs Brand Analysis.")
    target_search_queries: list[SearchQueryItem] = Field(
        ..., description="Section 2: Top 5 Target Search Queries."
    )
    seo_improvements: SeoImprovements = Field(..., description="Section 3: SEO Improvements.")
    top_services: list[ServiceItem] = Field(
        ..., description="Section 4: Top 5 Services."
    )
    target_audience: TargetAudience = Field(..., description="Section 5: Target Audience Identification.")


class AnalysisMetadata(BaseModel):
    """Execution telemetry and data provenance metadata."""

    analysis_timestamp: str = Field(..., description="ISO 8601 timestamp of analysis completion.")
    llm_provider: str = Field(..., description="LLM provider utilized (e.g. openai, gemini, mock).")
    llm_model: str = Field(..., description="Specific model identifier.")
    content_truncated: bool = Field(
        default=False, description="Flag indicating if website text was truncated to fit limit."
    )
    raw_content_chars: int = Field(..., description="Total characters of cleaned content extracted.")
    analysis_source: str = Field(
        default="website_content_and_ai",
        description="Provenance of analysis data.",
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal notices or data limitation caveats."
    )
    cached: bool = Field(default=False, description="Whether this response was served from cache.")
    execution_time_seconds: float = Field(
        ..., description="Total processing time in seconds."
    )


class LinkAnalysisResponse(BaseModel):
    """Top-level API response envelope for POST /link-analysis."""

    success: bool = Field(default=True, description="Operation success indicator.")
    website: str = Field(..., description="Normalized target website URL.")
    brand: BrandInfo = Field(..., description="Website-derived brand profile.")
    analysis: AnalysisContent = Field(..., description="Detailed 5-section strategic analysis.")
    metadata: AnalysisMetadata = Field(..., description="Execution metadata.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "website": "https://example.com",
                "brand": {
                    "name": "Example Corp",
                    "category": "Technology Services",
                    "summary": "Example domain illustrating website link analysis API.",
                    "main_products": ["Cloud Platform"],
                    "main_services": ["Custom Engineering"],
                    "target_market": "Global Enterprise",
                    "positioning": "Scalable Digital Infrastructure",
                    "value_proposition": "Fast, resilient cloud computing for modern teams.",
                    "strengths": ["Enterprise scale", "High reliability"]
                },
                "analysis": {
                    "competitor_analysis": {
                        "brand_overview": "Provider of modern enterprise software.",
                        "competitors": [],
                        "competitive_advantages": ["Modern architecture"],
                        "positioning_gaps": ["Brand recognition"],
                        "differentiation_opportunities": ["Specialized AI integration"],
                        "improvement_recommendations": ["Highlight case studies"]
                    },
                    "target_search_queries": [],
                    "seo_improvements": {
                        "primary_keyword": "Enterprise Cloud Platform",
                        "secondary_keywords": [],
                        "long_tail_keywords": [],
                        "industry_keywords": [],
                        "service_keywords": [],
                        "seo_title": {
                            "current_title": "Example Domain",
                            "recommended_title": "Example Corp | Enterprise Cloud Solutions",
                            "reason": "Incorporates core offering and branding.",
                            "target_keyword": "Enterprise Cloud"
                        },
                        "meta_description": {
                            "current_meta_description": None,
                            "recommended_meta_description": "Discover high-performance enterprise cloud solutions.",
                            "explanation": "Added keyword-rich summary with clear call to action."
                        },
                        "supporting_content": [],
                        "technical_observations": []
                    },
                    "top_services": [],
                    "target_audience": {
                        "primary_audience": [],
                        "secondary_audience": [],
                        "industry_segments": [],
                        "business_segments": [],
                        "customer_profiles": [],
                        "geographic_focus": "Global",
                        "marketing_audience_segments": [],
                        "pain_points": []
                    }
                },
                "metadata": {
                    "analysis_timestamp": "2026-11-19T18:00:00Z",
                    "llm_provider": "openai",
                    "llm_model": "gpt-4o-mini",
                    "content_truncated": False,
                    "raw_content_chars": 1250,
                    "analysis_source": "website_content_and_ai",
                    "warnings": [],
                    "cached": False,
                    "execution_time_seconds": 1.25
                }
            }
        }
    )


class HealthResponse(BaseModel):
    """Health check endpoint response schema."""

    status: str = Field(default="healthy", description="API health status.")
    app: str = Field(..., description="Application name.")
    version: str = Field(..., description="Application version.")
    timestamp: str = Field(..., description="Current server time (ISO 8601).")


class ErrorResponse(BaseModel):
    """Standardized error envelope."""

    detail: str = Field(..., description="Human-readable description of the error.")
    error_code: Optional[str] = Field(None, description="Machine-readable error identifier.")
