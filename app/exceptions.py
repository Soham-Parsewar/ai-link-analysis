"""Custom domain exceptions for the application."""

from typing import Any, Optional


class AppException(Exception):
    """Base class for all application exceptions."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


class InvalidUrlError(AppException):
    """Raised when a URL fails validation checks."""

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message=message, status_code=400, details=details)


class SSRFSecurityError(AppException):
    """Raised when a URL targets restricted internal, private, or metadata IPs."""

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message=message, status_code=400, details=details)


class WebsiteExtractionError(AppException):
    """Raised when an external website cannot be retrieved or parsed."""

    def __init__(self, message: str, status_code: int = 502, details: Optional[Any] = None):
        super().__init__(message=message, status_code=status_code, details=details)


class ContentTooLargeError(AppException):
    """Raised when a target website exceeds allowable download or extraction size."""

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message=message, status_code=413, details=details)


class LLMServiceError(AppException):
    """Raised when an LLM provider request or parsing fails."""

    def __init__(self, message: str, status_code: int = 502, details: Optional[Any] = None):
        super().__init__(message=message, status_code=status_code, details=details)


class LLMQuotaError(AppException):
    """Raised when the LLM provider rate limits or exhausts quota."""

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message=message, status_code=429, details=details)
