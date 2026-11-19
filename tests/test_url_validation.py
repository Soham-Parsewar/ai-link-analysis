"""Unit tests for URL validation and normalization."""

import pytest
from app.exceptions import InvalidUrlError, SSRFSecurityError
from app.utils.url_validator import normalize_and_validate_url


def test_valid_https_url_normalization():
    """Verify standard HTTPS URL is normalized properly."""
    url = "https://example.com"
    normalized = normalize_and_validate_url(url)
    assert normalized == "https://example.com/"


def test_valid_http_url_normalization():
    """Verify standard HTTP URL is normalized properly."""
    url = "http://example.com/about"
    normalized = normalize_and_validate_url(url)
    assert normalized == "http://example.com/about"


def test_uppercase_scheme_and_host_normalization():
    """Verify uppercase scheme and hostname are converted to lowercase."""
    url = "HTTPS://EXAMPLE.COM/Path?query=1"
    normalized = normalize_and_validate_url(url)
    assert normalized.startswith("https://example.com/Path?query=1")


def test_reject_empty_or_whitespace_url():
    """Reject empty or whitespace strings."""
    with pytest.raises(InvalidUrlError) as exc_info:
        normalize_and_validate_url("")
    assert "cannot be empty" in str(exc_info.value)

    with pytest.raises(InvalidUrlError) as exc_info:
        normalize_and_validate_url("   ")
    assert "cannot be empty" in str(exc_info.value)


@pytest.mark.parametrize("disallowed_url", [
    "file:///etc/passwd",
    "file://c:/windows/system32",
    "ftp://ftp.example.com/file.txt",
    "javascript:alert('xss')",
    "data:text/html;base64,PHNjcmlwdD4=",
    "blob:http://example.com/guid",
    "mailto:user@example.com",
])
def test_reject_unsupported_schemes(disallowed_url: str):
    """Reject non-HTTP/HTTPS protocols."""
    with pytest.raises(InvalidUrlError) as exc_info:
        normalize_and_validate_url(disallowed_url)
    assert "Only HTTP and HTTPS URLs are permitted" in str(exc_info.value) or "Unsupported protocol" in str(exc_info.value)


def test_reject_url_with_credentials():
    """Reject URLs with embedded authentication credentials."""
    url = "https://user:password@example.com/dashboard"
    with pytest.raises(InvalidUrlError) as exc_info:
        normalize_and_validate_url(url)
    assert "credentials" in str(exc_info.value).lower()


def test_reject_missing_scheme():
    """Reject URLs without scheme."""
    with pytest.raises(InvalidUrlError):
        normalize_and_validate_url("example.com")


def test_reject_excessive_url_length():
    """Reject URLs exceeding maximum length limit."""
    long_url = "https://example.com/" + "a" * 2500
    with pytest.raises(InvalidUrlError) as exc_info:
        normalize_and_validate_url(long_url)
    assert "exceeds maximum limit" in str(exc_info.value)
