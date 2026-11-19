"""Website extraction service with SSRF defense, streaming limits, and DOM cleaning."""

import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup, Comment
import httpx

from app.config import Settings, get_settings
from app.exceptions import (
    ContentTooLargeError,
    SSRFSecurityError,
    WebsiteExtractionError,
)
from app.schemas import WebsiteData
from app.utils.security import validate_url_security

logger = logging.getLogger(__name__)

# Elements to remove entirely from DOM
UNWANTED_TAGS = {
    "script",
    "style",
    "svg",
    "noscript",
    "iframe",
    "header",
    "footer",
    "nav",
    "form",
    "button",
    "link",
    "meta",
    "source",
    "track",
    "applet",
    "object",
    "embed",
    "audio",
    "video",
    "canvas",
}

# Substring matches in id/class attributes representing consent/popups
COOKIE_BANNER_KEYWORDS = (
    "cookie",
    "consent",
    "gdpr",
    "onetrust",
    "banner-cookie",
    "privacy-bar",
    "modal-backdrop",
    "newsletter-popup",
)


class WebsiteExtractor:
    """Secure website content extractor and sanitizer."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    async def fetch_html(self, target_url: str) -> tuple[str, str]:
        """
        Securely download HTML content with SSRF checks on every redirect and streaming size limits.

        Returns:
            Tuple of (final_url, html_text).
        """
        current_url = target_url
        max_redirects = 5
        redirect_count = 0

        # Validate initial URL
        validate_url_security(current_url)

        headers = {
            "User-Agent": self.settings.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        timeout = httpx.Timeout(
            connect=5.0,
            read=self.settings.REQUEST_TIMEOUT,
            write=5.0,
            pool=5.0,
        )

        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
            verify=True,
        ) as client:
            while redirect_count <= max_redirects:
                try:
                    logger.info(f"Fetching website: {current_url}")
                    async with client.stream("GET", current_url) as response:
                        # Check for redirect status
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("Location")
                            if not location:
                                raise WebsiteExtractionError("Redirect response missing Location header.")

                            # Resolve relative redirects
                            next_url = urljoin(current_url, location)
                            logger.info(f"Redirecting from {current_url} to {next_url}")

                            # Validate the destination for SSRF BEFORE following
                            validate_url_security(next_url)

                            current_url = next_url
                            redirect_count += 1
                            continue

                        # Check HTTP status
                        if response.status_code == 404:
                            raise WebsiteExtractionError(
                                f"Website returned 404 Not Found: {current_url}",
                                status_code=404,
                            )
                        if response.status_code == 403:
                            raise WebsiteExtractionError(
                                f"Access forbidden (HTTP 403). The website may be blocking automated requests: {current_url}",
                                status_code=502,
                            )
                        if response.status_code >= 400:
                            raise WebsiteExtractionError(
                                f"Website returned HTTP error {response.status_code}: {current_url}",
                                status_code=502,
                            )

                        # Validate Content-Type
                        content_type = response.headers.get("content-type", "").lower()
                        if content_type and not any(
                            t in content_type for t in ("text/html", "application/xhtml+xml", "text/plain")
                        ):
                            raise WebsiteExtractionError(
                                f"Unsupported content type '{content_type}'. Only HTML pages can be analyzed."
                            )

                        # Stream content with maximum size limit enforcement
                        chunks = []
                        total_bytes = 0
                        max_bytes = self.settings.max_html_bytes

                        async for chunk in response.aiter_bytes():
                            total_bytes += len(chunk)
                            if total_bytes > max_bytes:
                                raise ContentTooLargeError(
                                    f"Website HTML exceeded maximum limit of {self.settings.MAX_HTML_SIZE_MB}MB."
                                )
                            chunks.append(chunk)

                        raw_html = b"".join(chunks).decode(
                            response.encoding or "utf-8", errors="replace"
                        )
                        return current_url, raw_html

                except httpx.ConnectTimeout:
                    raise WebsiteExtractionError(f"Connection timed out while reaching '{current_url}'.")
                except httpx.ReadTimeout:
                    raise WebsiteExtractionError(f"Read timed out while downloading content from '{current_url}'.")
                except httpx.ConnectError as e:
                    raise WebsiteExtractionError(f"Could not establish connection to '{current_url}': {str(e)}")
                except httpx.RequestError as e:
                    raise WebsiteExtractionError(f"HTTP request failed for '{current_url}': {str(e)}")

            raise WebsiteExtractionError(f"Exceeded maximum redirect limit of {max_redirects}.")

    def parse_and_clean_html(self, final_url: str, html: str) -> WebsiteData:
        """Parse raw HTML with BeautifulSoup and extract structured business data."""
        if not html or not html.strip():
            raise WebsiteExtractionError("Target website returned an empty response body.")

        soup = BeautifulSoup(html, "html.parser")

        # 1. Extract Open Graph & Meta tags before decomposing head
        open_graph: dict[str, str] = {}
        for meta in soup.find_all("meta"):
            prop = meta.get("property") or meta.get("name")
            content = meta.get("content")
            if prop and content:
                open_graph[prop.lower()] = content.strip()

        # Meta description and keywords
        meta_description = open_graph.get("description") or open_graph.get("og:description")
        meta_keywords = open_graph.get("keywords")

        # Title extraction
        title: Optional[str] = None
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif "og:title" in open_graph:
            title = open_graph["og:title"]

        # Brand name inference from Open Graph, title, or hostname
        brand_name: Optional[str] = open_graph.get("og:site_name")
        if not brand_name and title:
            # Common title formats: "Company Name | Products", "Company Name - Tagline"
            parts = re.split(r"[\-|–—:|]", title)
            if parts and len(parts[0].strip()) > 1:
                brand_name = parts[0].strip()

        if not brand_name:
            # Derive from hostname (e.g. www.stripe.com -> Stripe)
            host = urlsplit(final_url).hostname or ""
            domain_parts = host.split(".")
            if len(domain_parts) >= 2:
                name_cand = domain_parts[-2] if domain_parts[-1] in ("com", "org", "net", "io", "ai", "co") else domain_parts[0]
                brand_name = name_cand.capitalize()

        # 2. Extract Headings (before modifying DOM)
        h1_headings = [h.get_text(strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)]
        h2_headings = [h.get_text(strip=True) for h in soup.find_all("h2") if h.get_text(strip=True)][:12]
        h3_headings = [h.get_text(strip=True) for h in soup.find_all("h3") if h.get_text(strip=True)][:12]

        # 3. Extract Contact Info (before removing header/footer/nav)
        contact_info_list: list[str] = []
        for mailto in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
            href = mailto.get("href", "")
            if href:
                contact_info_list.append(re.sub(r"^mailto:", "", href, flags=re.I).strip())
        for tel in soup.find_all("a", href=re.compile(r"^tel:", re.I)):
            href = tel.get("href", "")
            if href:
                contact_info_list.append(re.sub(r"^tel:", "", href, flags=re.I).strip())
        contact_info = ", ".join(sorted(set(contact_info_list))) if contact_info_list else None

        # 4. Clean unwanted tags & comments
        for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
            comment.extract()

        for tag in soup.find_all(list(UNWANTED_TAGS)):
            tag.decompose()

        # Remove cookie / consent / modal overlays
        for elem in soup.find_all(True):
            if not getattr(elem, "attrs", None):
                continue
            attrs = " ".join(filter(None, [
                elem.get("id", ""),
                " ".join(elem.get("class", [])) if isinstance(elem.get("class"), list) else str(elem.get("class", "")),
                elem.get("role", "")
            ])).lower()
            if any(kw in attrs for kw in COOKIE_BANNER_KEYWORDS):
                elem.decompose()

        # 5. Extract Product/Service Snippets
        product_snippets: list[str] = []
        for section in soup.find_all(["section", "div", "article", "li"]):
            if not getattr(section, "attrs", None):
                continue
            attrs = " ".join(filter(None, [
                section.get("id", ""),
                " ".join(section.get("class", [])) if isinstance(section.get("class"), list) else str(section.get("class", ""))
            ])).lower()
            if any(term in attrs for term in ("service", "product", "feature", "offering", "solution")):
                text = section.get_text(separator=" ", strip=True)
                if 30 < len(text) < 400 and text not in product_snippets:
                    product_snippets.append(text)
                if len(product_snippets) >= 8:
                    break

        # 6. Extract Main Content Text
        main_container = soup.find(["main", "article"]) or soup.find(role="main")
        if main_container:
            raw_text = main_container.get_text(separator="\n", strip=True)
        else:
            body = soup.find("body")
            raw_text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)

        # 7. Normalize whitespace and deduplicate repeated lines
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.splitlines()]
        seen = set()
        deduped_lines = []
        for line in lines:
            if line and len(line) > 3:
                line_lower = line.lower()
                if line_lower not in seen:
                    seen.add(line_lower)
                    deduped_lines.append(line)

        cleaned_content = "\n".join(deduped_lines)

        # Validation: check if page has meaningful content
        if len(cleaned_content) < 40 and not h1_headings and not h2_headings:
            raise WebsiteExtractionError(
                "Website content is insufficient or appears to be rendered via client-side JavaScript. "
                "Unable to extract meaningful textual data."
            )

        # Truncation check
        content_truncated = False
        raw_length = len(cleaned_content)
        if raw_length > self.settings.MAX_CONTENT_LENGTH:
            cleaned_content = cleaned_content[: self.settings.MAX_CONTENT_LENGTH].rsplit(" ", 1)[0]
            content_truncated = True

        return WebsiteData(
            url=final_url,
            title=title,
            meta_description=meta_description,
            meta_keywords=meta_keywords,
            brand_name=brand_name,
            h1_headings=h1_headings,
            h2_headings=h2_headings,
            h3_headings=h3_headings,
            main_content=cleaned_content,
            product_or_service_snippets=product_snippets,
            contact_info=contact_info,
            open_graph=open_graph,
            content_truncated=content_truncated,
            raw_content_length=raw_length,
        )

    async def extract(self, url: str) -> WebsiteData:
        """High-level method: Fetch URL and parse HTML into structured WebsiteData."""
        final_url, html = await self.fetch_html(url)
        return self.parse_and_clean_html(final_url, html)
