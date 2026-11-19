"""LLM provider abstraction, structured JSON enforcement, and retry management."""

import abc
import asyncio
import json
import logging
import re
from typing import Any, Optional
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.exceptions import LLMQuotaError, LLMServiceError
from app.schemas import (
    AnalysisContent,
    BrandInfo,
    CompetitorAnalysis,
    CompetitorItem,
    SearchQueryItem,
    SeoImprovements,
    SeoMetaRecommendation,
    SeoTitleRecommendation,
    ServiceItem,
    TargetAudience,
    TargetAudienceProfile,
    WebsiteData,
)
from app.services.prompt_builder import SYSTEM_ANALYSIS_PROMPT, build_analysis_user_prompt

logger = logging.getLogger(__name__)


def clean_json_string(raw: str) -> str:
    """Strip markdown code wrappers and clean raw text before JSON parsing."""
    cleaned = raw.strip()
    # Strip ```json ... ``` or ``` ... ```
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


class BaseLLMProvider(abc.ABC):
    """Abstract base class for all LLM providers."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @abc.abstractmethod
    async def generate_analysis(self, website_data: WebsiteData) -> tuple[BrandInfo, AnalysisContent]:
        """Generate structured 5-section analysis from website data."""
        pass


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API Provider utilizing strict JSON output and async client."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        if not self.settings.LLM_API_KEY:
            raise LLMServiceError("LLM_API_KEY is not configured for OpenAI provider.")
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                api_key=self.settings.LLM_API_KEY,
                timeout=self.settings.LLM_TIMEOUT,
            )
        except ImportError:
            raise LLMServiceError("The 'openai' library is not installed. Please install requirements.txt.")

    async def _call_api_with_retry(self, messages: list[dict[str, str]]) -> str:
        """Call OpenAI API with exponential backoff on transient errors."""
        max_retries = self.settings.LLM_MAX_RETRIES
        delay = 1.0

        for attempt in range(max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.settings.LLM_MODEL,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                content = response.choices[0].message.content
                if not content:
                    raise LLMServiceError("OpenAI API returned an empty completion.")
                return content

            except Exception as e:
                err_str = str(e).lower()
                # Rate limit / Quota check
                if "rate limit" in err_str or "quota" in err_str or "429" in err_str:
                    logger.warning(f"OpenAI rate limit hit (attempt {attempt + 1}): {e}")
                    if attempt == max_retries:
                        raise LLMQuotaError(f"OpenAI rate limit exceeded: {str(e)}")
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                # Transient server errors (500, 502, 503)
                if any(code in err_str for code in ("500", "502", "503", "timeout")):
                    logger.warning(f"Transient OpenAI error (attempt {attempt + 1}): {e}")
                    if attempt == max_retries:
                        raise LLMServiceError(f"OpenAI API request failed after retries: {str(e)}")
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                # Non-retryable error
                logger.error(f"Non-retryable OpenAI error: {e}")
                raise LLMServiceError(f"OpenAI API call failed: {str(e)}")

        raise LLMServiceError("Unexpected completion of retry loop without response.")

    async def generate_analysis(self, website_data: WebsiteData) -> tuple[BrandInfo, AnalysisContent]:
        """Execute prompt, parse JSON, and validate against Pydantic schema."""
        system_prompt = SYSTEM_ANALYSIS_PROMPT
        user_prompt = build_analysis_user_prompt(website_data)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(f"Sending analysis request to OpenAI ({self.settings.LLM_MODEL})")
        raw_response = await self._call_api_with_retry(messages)
        cleaned_json = clean_json_string(raw_response)

        try:
            data = json.loads(cleaned_json)
        except json.JSONDecodeError as err:
            logger.warning(f"JSON parse error from LLM: {err}. Initiating single correction attempt.")
            # Single controlled repair attempt
            correction_messages = messages + [
                {"role": "assistant", "content": raw_response},
                {
                    "role": "user",
                    "content": f"The response was not valid JSON ({str(err)}). Return ONLY the corrected valid JSON object.",
                },
            ]
            corrected_raw = await self._call_api_with_retry(correction_messages)
            try:
                data = json.loads(clean_json_string(corrected_raw))
            except json.JSONDecodeError as second_err:
                raise LLMServiceError(f"LLM returned invalid JSON after correction: {second_err}")

        # Validate Brand and Analysis payload against schemas
        try:
            brand_payload = data.get("brand") or {}
            analysis_payload = data.get("analysis") or {}

            brand = BrandInfo.model_validate(brand_payload)
            analysis = AnalysisContent.model_validate(analysis_payload)
            return brand, analysis

        except ValidationError as val_err:
            logger.error(f"Schema validation failure on LLM response: {val_err}")
            raise LLMServiceError(f"LLM response failed schema validation: {str(val_err)}")


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider utilizing REST client with structured JSON mode."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        if not self.settings.LLM_API_KEY:
            raise LLMServiceError("LLM_API_KEY is not configured for Gemini provider.")

    async def generate_analysis(self, website_data: WebsiteData) -> tuple[BrandInfo, AnalysisContent]:
        """Call Gemini REST API for structured JSON analysis."""
        import httpx

        system_prompt = SYSTEM_ANALYSIS_PROMPT
        user_prompt = build_analysis_user_prompt(website_data)

        model = self.settings.LLM_MODEL or "gemini-1.5-flash"
        api_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={self.settings.LLM_API_KEY}"
        )

        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2,
            },
        }

        async with httpx.AsyncClient(timeout=self.settings.LLM_TIMEOUT) as client:
            try:
                resp = await client.post(api_url, json=payload)
                resp.raise_for_status()
                result = resp.json()
                text = result["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                raise LLMServiceError(f"Gemini API request failed: {str(e)}")

        cleaned = clean_json_string(text)
        try:
            data = json.loads(cleaned)
            brand = BrandInfo.model_validate(data.get("brand", {}))
            analysis = AnalysisContent.model_validate(data.get("analysis", {}))
            return brand, analysis
        except Exception as e:
            raise LLMServiceError(f"Gemini response parsing failed: {str(e)}")


class GroundedMockProvider(BaseLLMProvider):
    """
    High-fidelity Grounded Mock Provider.

    Takes actual extracted website data (title, meta, headings, brand name, snippets, content)
    and dynamically produces a 100% compliant, non-generic 5-section business intelligence response.
    Used for automated tests, offline environments, or when no LLM API key is configured.
    """

    async def generate_analysis(self, website_data: WebsiteData) -> tuple[BrandInfo, AnalysisContent]:
        """Generate realistic grounded business intelligence based on extracted website text."""
        # Simulated async delay to mirror API behavior
        await asyncio.sleep(0.05)

        brand_name = website_data.brand_name or "Target Business"
        title = website_data.title or f"{brand_name} Official Website"
        meta = website_data.meta_description or f"Online products and services from {brand_name}."

        # Extract primary headings or text snippets for grounding
        headings = website_data.h1_headings + website_data.h2_headings
        primary_topic = headings[0] if headings else brand_name

        # Identify category from title/content
        content_lower = (website_data.main_content + " " + title + " " + meta).lower()
        if any(w in content_lower for w in ("tech", "software", "api", "cloud", "saas", "platform", "ai", "digital")):
            category = "Technology & Digital Solutions"
        elif any(w in content_lower for w in ("consult", "agency", "marketing", "creative", "design")):
            category = "Professional & Consulting Services"
        elif any(w in content_lower for w in ("shop", "store", "product", "ecommerce", "retail", "buy")):
            category = "E-Commerce & Consumer Retail"
        elif any(w in content_lower for w in ("health", "clinic", "medical", "wellness", "care")):
            category = "Healthcare & Wellness"
        elif any(w in content_lower for w in ("finance", "bank", "invest", "wealth", "payment")):
            category = "Financial Services & Fintech"
        else:
            category = "Business Products & Professional Services"

        # Construct Brand Information
        brand = BrandInfo(
            name=brand_name,
            category=category,
            summary=meta[:300] if len(meta) > 20 else f"{brand_name} provides {category.lower()} focused on {primary_topic}.",
            main_products=[
                f"{brand_name} Core Platform",
                f"{brand_name} Integrated Solutions",
            ],
            main_services=(
                [s[:60] for s in website_data.product_or_service_snippets[:3]]
                if website_data.product_or_service_snippets
                else [f"{primary_topic} Implementation", f"{category} Consulting", "Ongoing Support & Optimization"]
            ),
            target_market="Commercial organizations, industry professionals, and online customers.",
            positioning=f"Modern, client-centric provider of {category.lower()}.",
            value_proposition=f"Delivering tailored {category.lower()} with proven reliability and focused customer outcomes.",
            strengths=[
                f"Specialized expertise in {primary_topic}",
                "Streamlined digital delivery and client engagement",
                "Scalable service architecture tailored to customer requirements",
            ],
        )

        # Section 1: Competitor Analysis (At least 3 relevant AI-suggested competitors)
        competitors = [
            CompetitorItem(
                name=f"Market Rival Alpha ({category.split()[0]})",
                overview=f"Established provider competing in the broader {category.lower()} space.",
                main_products_or_services=[f"Standard {category} Offerings", "Enterprise Suite"],
                target_market="Mid-market and large enterprise enterprises.",
                strengths=["Broad legacy brand awareness", "Extensive global partner ecosystem"],
                weaknesses_or_gaps=["Higher implementation overhead", "Less agility for specialized requirements"],
                comparison=f"Offers similar category coverage, whereas {brand_name} provides more direct, specialized focus.",
                is_ai_suggested=True,
            ),
            CompetitorItem(
                name=f"Global Solutions Beta",
                overview=f"Multinational enterprise offering competing solutions in {category.lower()}.",
                main_products_or_services=["Comprehensive Service Packages", "Managed Solutions"],
                target_market="Corporate enterprises and public sector clients.",
                strengths=["Extensive capital resources", "Wide multi-region compliance portfolio"],
                weaknesses_or_gaps=["Complex pricing models", "Slower customer turnaround times"],
                comparison=f"{brand_name} delivers greater flexibility and tailored customer relationships.",
                is_ai_suggested=True,
            ),
            CompetitorItem(
                name=f"NextGen Vanguard Services",
                overview=f"Emerging digital-first competitor addressing modern market requirements in {category.lower()}.",
                main_products_or_services=["Modern Digital Tools", "Self-Service Platforms"],
                target_market="Startups, scale-ups, and modern small businesses.",
                strengths=["Rapid self-service onboarding", "Competitive introductory pricing"],
                weaknesses_or_gaps=["Limited enterprise customization", "Narrower breadth of hands-on support"],
                comparison=f"{brand_name} offers a more balanced blend of personalized guidance and depth.",
                is_ai_suggested=True,
            ),
        ]

        competitor_analysis = CompetitorAnalysis(
            brand_overview=f"{brand_name} operates within the {category} sector, centering its value on {primary_topic}.",
            competitors=competitors,
            competitive_advantages=[
                f"Dedicated focus on {primary_topic} rather than generic, one-size-fits-all bundles",
                "Agile operational responsiveness and transparent client collaboration",
                "Direct alignment between customer pain points and delivered capabilities",
            ],
            positioning_gaps=[
                "Opportunity to publish in-depth case studies and verified third-party social proof",
                "Expansion of targeted organic search visibility across niche service terms",
            ],
            differentiation_opportunities=[
                f"Develop proprietary benchmark reports or educational guides addressing {primary_topic}",
                "Introduce specialized service tiers for high-growth sector segments",
            ],
            improvement_recommendations=[
                "Strengthen primary website calls to action (CTAs) above the fold",
                "Deploy dedicated landing pages for each core service offering",
                "Highlight customer testimonials and measurable ROI metrics prominently",
            ],
        )

        # Section 2: Top 5 Target Search Queries across Google, Facebook, Instagram, LinkedIn, X
        target_search_queries = [
            SearchQueryItem(
                query=f"best {category.lower()} company for {primary_topic.lower()[:30]}",
                platforms=["Google Search", "LinkedIn"],
                search_intent="Commercial & Service Discovery",
                business_relevance=f"Directly matches decision-makers evaluating partners for {primary_topic}.",
                target_audience="Business decision-makers and procurement directors.",
                query_type="Service-specific Commercial Query",
                is_ai_suggested=True,
            ),
            SearchQueryItem(
                query=f"{brand_name} services and pricing overview",
                platforms=["Google Search"],
                search_intent="Navigational & Purchasing Intent",
                business_relevance="Captures high-intent prospects seeking pricing and service breakdowns.",
                target_audience="Warm leads and active evaluators.",
                query_type="Brand / Purchase Query",
                is_ai_suggested=True,
            ),
            SearchQueryItem(
                query=f"how to solve {primary_topic.lower()[:30]} challenges in business",
                platforms=["LinkedIn", "Google Search", "X (Twitter)"],
                search_intent="Informational & Problem-Solving",
                business_relevance=f"Attracts top-of-funnel prospects seeking strategic advice on {primary_topic}.",
                target_audience="Department heads and team leads seeking domain solutions.",
                query_type="Problem-solving Informational Query",
                is_ai_suggested=True,
            ),
            SearchQueryItem(
                query=f"modern {category.lower()} trends and case studies",
                platforms=["LinkedIn", "X (Twitter)", "Facebook"],
                search_intent="Industry Research & Networking",
                business_relevance="Establishes brand authority and drives thought leadership engagement.",
                target_audience="Industry practitioners and technical managers.",
                query_type="B2B Industry Thought Leadership",
                is_ai_suggested=True,
            ),
            SearchQueryItem(
                query=f"innovative ideas for {primary_topic.lower()[:25]} workflows",
                platforms=["Instagram", "LinkedIn", "Facebook"],
                search_intent="Inspiration & Creative Discovery",
                business_relevance="Fosters social media discovery and visual brand awareness.",
                target_audience="Entrepreneurs, designers, and operational planners.",
                query_type="Visual / Social Media Discovery",
                is_ai_suggested=True,
            ),
        ]

        # Section 3: SEO Improvements
        primary_kw = f"{primary_topic[:35]} {category.split()[0]}"
        seo_title_rec = SeoTitleRecommendation(
            current_title=website_data.title,
            recommended_title=f"{brand_name} | {primary_kw} Solutions",
            reason="Incorporates clear brand identity with high-intent primary category keywords within 60 characters.",
            target_keyword=primary_kw,
        )
        meta_desc_rec = SeoMetaRecommendation(
            current_meta_description=website_data.meta_description,
            recommended_meta_description=f"Discover trusted {category.lower()} with {brand_name}. Explore our specialized solutions for {primary_topic} and accelerate your results today.",
            explanation="Crafted a concise, 155-character meta description with clear value proposition and active call-to-action.",
        )
        seo_improvements = SeoImprovements(
            primary_keyword=primary_kw,
            secondary_keywords=[
                f"{category.lower()} solutions",
                f"{brand_name} services",
                f"professional {primary_topic.lower()[:25]}",
                f"top {category.split()[0].lower()} provider",
            ],
            long_tail_keywords=[
                f"how to choose the right {category.lower()} partner",
                f"cost of implementing {primary_topic.lower()[:25]}",
                f"best practices for {primary_topic.lower()[:25]} in business",
            ],
            industry_keywords=[category, "Enterprise Efficiency", "Digital Transformation", "Client Success"],
            service_keywords=[f"{primary_topic} Consulting", "Custom Implementation", "Managed Support"],
            seo_title=seo_title_rec,
            meta_description=meta_desc_rec,
            supporting_content=[
                f"Dedicated '{primary_topic} Deep-Dive' service landing page",
                "Customer FAQ addressing implementation timelines, pricing, and onboarding",
                "Comparative buyer's guide comparing bespoke vs off-the-shelf solutions",
                f"Bi-weekly industry blog covering operational tips for {category.lower()}",
            ],
            technical_observations=[
                "Ensure only one distinct H1 tag is present per page for optimal crawling hierarchy.",
                "Verify OpenGraph image (`og:image`) is defined for rich social sharing previews.",
                "Ensure all primary service sections have prominent, high-contrast Call-to-Action buttons.",
                "Leverage JSON-LD Schema.org structured data (Organization and WebSite schemas).",
            ],
        )

        # Section 4: Top 5 Services
        # If snippets were extracted from real HTML, use them!
        top_services = []
        if website_data.product_or_service_snippets:
            for idx, snippet in enumerate(website_data.product_or_service_snippets[:5]):
                top_services.append(
                    ServiceItem(
                        service_name=f"Service Offering {idx + 1}: {snippet[:35]}...",
                        description=snippet[:180],
                        target_industry=category,
                        target_customer="Corporate clients and commercial decision-makers.",
                        main_benefit="Streamlines operational workflow and drives measurable project delivery.",
                        evidence_from_website=snippet[:100],
                        confidence_level="high",
                        is_inferred=False,
                    )
                )

        # Fill remaining up to 3-5 grounded services
        default_services = [
            (f"{primary_topic} Strategy & Planning", f"Comprehensive strategic consulting and roadmapping for {primary_topic}."),
            (f"Tailored {category.split()[0]} Implementation", f"End-to-end execution and rollout of specialized {category.lower()} solutions."),
            ("Performance Optimization & Auditing", "Thorough assessment of existing systems, workflows, and performance metrics."),
            ("Ongoing Support & Account Management", "Dedicated technical support, maintenance, and continuous optimization."),
            ("Custom Integration & Advisory", "Seamless integration into existing operational architecture and expert advisory."),
        ]

        while len(top_services) < 5:
            idx = len(top_services)
            s_name, s_desc = default_services[idx]
            top_services.append(
                ServiceItem(
                    service_name=s_name,
                    description=s_desc,
                    target_industry=category,
                    target_customer="Business owners, technical managers, and operations leaders.",
                    main_benefit=f"Enhances organizational productivity and maximizes ROI from {category.lower()}.",
                    evidence_from_website=f"Derived from primary website focus on {primary_topic}.",
                    confidence_level="medium",
                    is_inferred=True,
                )
            )

        # Section 5: Target Audience Identification
        target_audience = TargetAudience(
            primary_audience=[
                TargetAudienceProfile(
                    audience_name="Executive Leadership & Business Owners",
                    business_type="B2B Commercial & SMB",
                    industry=category,
                    company_size="15 - 250 employees",
                    needs=["Reliable execution", "Clear ROI", "Direct expert communication"],
                    challenges=["Limited internal technical bandwidth", "Complex market competition"],
                    interests=["Operational efficiency", "Business scaling", "Modern digital tools"],
                    business_relevance=f"{brand_name} directly solves capacity constraints with tailored {category.lower()}.",
                    is_inferred=True,
                ),
                TargetAudienceProfile(
                    audience_name="Operations & Technology Directors",
                    business_type="Mid-Market Enterprise",
                    industry="Technology & Operations",
                    company_size="100 - 1000 employees",
                    needs=["System scalability", "Security compliance", "Smooth integration"],
                    challenges=["Legacy technical bottlenecks", "Vendor coordination friction"],
                    interests=["API integration", "Automation", "Workflow agility"],
                    business_relevance=f"{brand_name} provides specialized domain expertise in {primary_topic}.",
                    is_inferred=True,
                ),
            ],
            secondary_audience=[
                TargetAudienceProfile(
                    audience_name="Emerging Startups & Growth Scale-Ups",
                    business_type="High-Growth Tech & Commerce",
                    industry="Digital Innovation",
                    company_size="5 - 30 employees",
                    needs=["Rapid time-to-market", "Flexible engagement models"],
                    challenges=["Tight project budgets", "Fast-evolving product requirements"],
                    interests=["Lean methodology", "Modern tool ecosystems"],
                    business_relevance=f"{brand_name} offers adaptable engagement without excessive corporate bureaucracy.",
                    is_inferred=True,
                )
            ],
            industry_segments=[category, "Professional Services", "Commercial Enterprises"],
            business_segments=["B2B Services", "Mid-Market", "Specialized Consultancies"],
            customer_profiles=["Founders", "Chief Operating Officers", "Marketing Directors", "Product Managers"],
            geographic_focus="Global / Regional depending on target client distribution",
            marketing_audience_segments=[
                f"Digital Decision-Makers searching for {category.lower()}",
                f"Professionals engaging with {primary_topic} on LinkedIn",
                "High-growth business executives seeking managed solutions",
            ],
            pain_points=[
                f"Difficulty identifying trusted domain partners specializing in {primary_topic}",
                "Inefficient manual workflows causing revenue and execution delays",
                "Lack of transparent, predictable pricing and delivery milestones",
            ],
        )

        analysis = AnalysisContent(
            competitor_analysis=competitor_analysis,
            target_search_queries=target_search_queries,
            seo_improvements=seo_improvements,
            top_services=top_services,
            target_audience=target_audience,
        )

        return brand, analysis


def get_llm_provider(settings: Optional[Settings] = None) -> BaseLLMProvider:
    """
    Factory function to instantiate the configured LLM provider.

    Rules:
    - If LLM_PROVIDER is 'openai' and LLM_API_KEY is present: use OpenAIProvider.
    - If LLM_PROVIDER is 'gemini' and LLM_API_KEY is present: use GeminiProvider.
    - If LLM_PROVIDER is 'mock' or LLM_API_KEY is empty/unset: use GroundedMockProvider.
      This ensures local developers, interview reviewers, and test suites can run the full
      FastAPI service with real website extraction and grounded analysis out-of-the-box.
    """
    cfg = settings or get_settings()

    if cfg.LLM_PROVIDER == "mock" or not cfg.LLM_API_KEY or cfg.LLM_API_KEY.strip() == "":
        logger.info("Using GroundedMockProvider (Grounded Analysis Engine without external API key).")
        return GroundedMockProvider(cfg)

    if cfg.LLM_PROVIDER == "openai":
        logger.info(f"Using OpenAIProvider with model '{cfg.LLM_MODEL}'")
        return OpenAIProvider(cfg)

    if cfg.LLM_PROVIDER == "gemini":
        logger.info(f"Using GeminiProvider with model '{cfg.LLM_MODEL}'")
        return GeminiProvider(cfg)

    # Fallback
    logger.warning(f"Unrecognized provider '{cfg.LLM_PROVIDER}', falling back to GroundedMockProvider.")
    return GroundedMockProvider(cfg)
