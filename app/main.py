"""FastAPI Application entrypoint for AI-Powered Website Link Analysis API."""

import datetime
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.exceptions import (
    AppException,
    ContentTooLargeError,
    InvalidUrlError,
    LLMQuotaError,
    LLMServiceError,
    SSRFSecurityError,
    WebsiteExtractionError,
)
from app.schemas import (
    ErrorResponse,
    HealthResponse,
    LinkAnalysisRequest,
    LinkAnalysisResponse,
)
from app.services.analysis_service import AnalysisService

# Setup Logging
settings = get_settings()
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info(f"Starting {settings.APP_NAME} v{__version__} on {settings.HOST}:{settings.PORT}")
    logger.info(f"LLM Provider: {settings.LLM_PROVIDER} (Model: {settings.LLM_MODEL})")
    logger.info(f"Cache Enabled: {settings.CACHE_ENABLED} (TTL: {settings.CACHE_TTL_SECONDS}s)")
    yield
    logger.info("Shutting down application...")


# FastAPI Application instance
app = FastAPI(
    title=settings.APP_NAME,
    version=__version__,
    description=(
        "Production-grade FastAPI service that analyzes target website URLs, "
        "extracts grounded content with robust SSRF protections, and generates "
        "comprehensive business intelligence, competitor profiles, SEO audits, "
        "and target audience breakdowns using LLMs."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Enable CORS for API consumers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================================
# Exception Handlers
# =====================================================================

@app.exception_handler(InvalidUrlError)
async def invalid_url_handler(request: Request, exc: InvalidUrlError):
    """Handle URL syntax or format validation failures."""
    logger.warning(f"URL Validation Error: {exc.message}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.message},
    )


@app.exception_handler(SSRFSecurityError)
async def ssrf_security_handler(request: Request, exc: SSRFSecurityError):
    """Handle SSRF security blocks."""
    logger.warning(f"Security Alert (SSRF Block): {exc.message}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": f"Security restriction: {exc.message}"},
    )


@app.exception_handler(WebsiteExtractionError)
async def website_extraction_handler(request: Request, exc: WebsiteExtractionError):
    """Handle external website retrieval or parsing errors."""
    logger.error(f"Website Extraction Failure: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.exception_handler(ContentTooLargeError)
async def content_too_large_handler(request: Request, exc: ContentTooLargeError):
    """Handle payload size limit breaches."""
    logger.warning(f"Content Too Large: {exc.message}")
    return JSONResponse(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        content={"detail": exc.message},
    )


@app.exception_handler(LLMQuotaError)
async def llm_quota_handler(request: Request, exc: LLMQuotaError):
    """Handle LLM rate limits."""
    logger.error(f"LLM Quota Exceeded: {exc.message}")
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "LLM provider rate limit exceeded. Please try again shortly."},
    )


@app.exception_handler(LLMServiceError)
async def llm_service_handler(request: Request, exc: LLMServiceError):
    """Handle LLM service processing failures."""
    logger.error(f"LLM Service Error: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": f"AI Analysis Error: {exc.message}"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic request body validation failures with clean messages."""
    errors = exc.errors()
    msg = errors[0].get("msg") if errors else "Invalid request data."
    # Extract clean message if it came from our custom validator
    if "Value error, " in msg:
        msg = msg.replace("Value error, ", "")
    logger.warning(f"Validation Error: {msg}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": msg},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all safety net: Log stack trace internally without leaking to client."""
    logger.exception(f"Unhandled Server Error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred while processing the request."},
    )


# =====================================================================
# API Endpoints
# =====================================================================

@app.get(
    "/",
    tags=["Root"],
    summary="Root Service Status",
    description="Welcome endpoint with links to documentation and health status.",
)
async def root():
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": __version__,
        "documentation": "/docs",
        "health": "/health",
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="API Health Check",
    description="Returns service availability, application name, version, and server timestamp.",
)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        app=settings.APP_NAME,
        version=__version__,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )


@app.post(
    "/link-analysis",
    response_model=LinkAnalysisResponse,
    status_code=status.HTTP_200_OK,
    tags=["Analysis"],
    summary="Analyze Website Link",
    description=(
        "Accepts a target website URL, extracts cleaned content with SSRF safeguards, "
        "processes it via an LLM, and returns structured 5-section business intelligence."
    ),
    responses={
        200: {"model": LinkAnalysisResponse, "description": "Successful analysis"},
        400: {"model": ErrorResponse, "description": "Invalid URL or SSRF security restriction"},
        413: {"model": ErrorResponse, "description": "Website content exceeds size limit"},
        429: {"model": ErrorResponse, "description": "LLM rate limit reached"},
        502: {"model": ErrorResponse, "description": "External website or LLM extraction failure"},
    },
)
async def analyze_link(payload: LinkAnalysisRequest):
    """Perform website link analysis."""
    service = AnalysisService()
    return await service.analyze_url(payload.url)
