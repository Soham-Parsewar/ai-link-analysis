"""URL validation and normalization module."""

import re
from urllib.parse import urlsplit, urlunsplit
from app.exceptions import InvalidUrlError
from app.utils.security import validate_hostname_ssrf

ALLOWED_SCHEMES = {"http", "https"}
MAX_URL_LENGTH = 2048


def normalize_and_validate_url(url: str) -> str:
    """
    Validate, sanitize, and normalize an incoming website URL.

    Requirements:
    - Must be non-empty string <= 2048 characters.
    - Only http:// and https:// schemes allowed.
    - Reject malformed URLs, missing hostnames, or embedded userinfo credentials.
    - Check hostname against SSRF restrictions.
    - Normalize scheme and hostname to lowercase.

    Returns:
        Clean, normalized URL string.

    Raises:
        InvalidUrlError: For malformed, empty, or unsupported URL formats.
        SSRFSecurityError: For internal, loopback, or private destination targets.
    """
    if not url or not isinstance(url, str):
        raise InvalidUrlError("Invalid website URL. URL cannot be empty.")

    cleaned_url = url.strip()
    if not cleaned_url:
        raise InvalidUrlError("Invalid website URL. URL cannot be empty or whitespace.")

    if len(cleaned_url) > MAX_URL_LENGTH:
        raise InvalidUrlError(f"URL length exceeds maximum limit of {MAX_URL_LENGTH} characters.")

    # Check for disallowed schemes early
    lower_prefix = cleaned_url.lower()
    for disallowed in ("file://", "ftp://", "javascript:", "data:", "blob:", "mailto:"):
        if lower_prefix.startswith(disallowed):
            raise InvalidUrlError(
                f"Unsupported protocol in URL. Only HTTP and HTTPS URLs are permitted. Received: '{disallowed}'"
            )

    try:
        parsed = urlsplit(cleaned_url)
    except Exception as e:
        raise InvalidUrlError(f"Malformed website URL: {str(e)}")

    scheme = parsed.scheme.lower()
    if not scheme:
        raise InvalidUrlError("Invalid website URL. Missing scheme (must start with http:// or https://).")

    if scheme not in ALLOWED_SCHEMES:
        raise InvalidUrlError(
            f"Invalid website URL scheme '{scheme}'. Only HTTP and HTTPS URLs are permitted."
        )

    if not parsed.netloc:
        raise InvalidUrlError("Invalid website URL. Missing host or domain name.")

    hostname = parsed.hostname
    if not hostname:
        raise InvalidUrlError("Invalid website URL. Unable to extract a valid hostname.")

    # Reject embedded authentication credentials (e.g., http://admin:pass@example.com)
    if parsed.username or parsed.password:
        raise InvalidUrlError("URLs containing user authentication credentials are not permitted.")

    # Validate port if specified
    if parsed.port is not None:
        if parsed.port < 1 or parsed.port > 65535:
            raise InvalidUrlError(f"Invalid port number: {parsed.port}")

    # Enforce SSRF validation on the resolved host
    validate_hostname_ssrf(hostname)

    # Normalize path (default to / if blank)
    path = parsed.path if parsed.path else "/"

    # Reconstruct normalized URL
    netloc = hostname.lower()
    if parsed.port and ((scheme == "http" and parsed.port != 80) or (scheme == "https" and parsed.port != 443)):
        netloc = f"{netloc}:{parsed.port}"

    normalized = urlunsplit((scheme, netloc, path, parsed.query, parsed.fragment))
    return normalized
