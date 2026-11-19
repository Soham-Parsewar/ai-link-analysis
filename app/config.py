"""Application configuration module using pydantic-settings."""

from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings schema backed by environment variables."""

    # Server settings
    APP_NAME: str = "AI Website Link Analysis API"
    APP_ENV: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 4000

    # LLM Settings
    LLM_PROVIDER: Literal["openai", "gemini", "mock"] = "openai"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_MAX_RETRIES: int = 2
    LLM_TIMEOUT: float = 30.0

    # Website Extraction & Security Settings
    REQUEST_TIMEOUT: float = 15.0
    MAX_HTML_SIZE_MB: int = 2
    MAX_CONTENT_LENGTH: int = 12000
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 (AI-Link-Analyzer/1.0)"
    )

    # Caching Settings
    CACHE_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 3600

    # Logging Settings
    LOG_LEVEL: str = "INFO"

    @property
    def max_html_bytes(self) -> int:
        """Convert MAX_HTML_SIZE_MB into bytes."""
        return self.MAX_HTML_SIZE_MB * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached instance of Settings."""
    return Settings()
