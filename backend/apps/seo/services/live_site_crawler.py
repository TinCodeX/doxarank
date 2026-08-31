"""
Live Website Crawler Foundation for DoxaRank (Milestone 4, Phase 4.2.1).

Provides safe, bounded, deterministic website crawling using httpx and BeautifulSoup4.
Features:
- Strict same-domain and scheme restriction.
- URL normalization, fragment removal, and non-HTML asset filtering.
- robots.txt compliance with safe fallbacks.
- Configurable boundaries: max_pages, max_depth, timeout, max_response_size, polite_delay.
- Resilient error handling (failure on a single URL never halts the crawl).
- Comprehensive structured HTML extraction: title, meta description, H1-H6 headings,
  canonical tags, image src/alt, internal/external links, and JSON-LD blocks.
- Output encapsulated in strongly-typed dataclasses.
"""

import logging
import posixpath
import time
import json
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Set, Any, Tuple
from urllib.parse import urlparse, urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
import urllib.robotparser

import httpx
from bs4 import BeautifulSoup
from django.utils import timezone

from apps.projects.models import Project

logger = logging.getLogger(__name__)

# File extensions that should NOT be crawled as HTML pages
NON_HTML_EXTENSIONS: Set[str] = {
    # Images
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.bmp', '.tiff',
    # Documents
    '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt', '.csv',
    # Archives
    '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',
    # Media
    '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.wav', '.ogg', '.m4a',
    # Code & styles
    '.css', '.js', '.json', '.xml', '.rss', '.atom',
    # Fonts
    '.woff', '.woff2', '.ttf', '.eot', '.otf'
}

DEFAULT_USER_AGENT = "DoxaRankBot/1.0 (+https://doxarank.com/bot)"
DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_DEPTH = 3
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RESPONSE_SIZE = 5_000_000  # 5 MB


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PageCrawlResult:
    """Structured extraction results for a single crawled URL."""
    url: str
    final_url: str
    status_code: int
    response_time_ms: float
    content_type: str = ""
    title: Optional[str] = None
    meta_description: Optional[str] = None
    headings: Dict[str, List[str]] = field(default_factory=lambda: {
        "h1": [], "h2": [], "h3": [], "h4": [], "h5": [], "h6": []
    })
    canonical: Optional[str] = None
    images: List[Dict[str, Any]] = field(default_factory=list)
    internal_links: List[Dict[str, Any]] = field(default_factory=list)
    external_links: List[Dict[str, Any]] = field(default_factory=list)
    json_ld: List[Any] = field(default_factory=list)
    word_count: int = 0
    redirect_chain: List[str] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CrawlError:
    """Represents an error encountered while fetching or parsing a URL."""
    url: str
    error_type: str
    message: str
    status_code: Optional[int] = None
    timestamp: str = field(default_factory=lambda: timezone.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CrawlMetadata:
    """High-level metadata regarding the crawl configuration and execution."""
    start_url: str
    base_domain: str
    user_agent: str
    max_pages: int
    max_depth: int
    robots_txt_status: str
    started_at: str
    completed_at: str
    duration_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CrawlResult:
    """Complete aggregated result of a live site crawl session."""
    start_url: str
    metadata: CrawlMetadata
    pages_crawled: int
    pages_discovered: int
    duration_seconds: float
    errors: List[CrawlError] = field(default_factory=list)
    pages: List[PageCrawlResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_url": self.start_url,
            "metadata": self.metadata.to_dict(),
            "pages_crawled": self.pages_crawled,
            "pages_discovered": self.pages_discovered,
            "duration_seconds": self.duration_seconds,
            "errors": [e.to_dict() for e in self.errors],
            "pages": [p.to_dict() for p in self.pages]
        }


# =============================================================================
# LIVE SITE CRAWLER SERVICE
# =============================================================================

class LiveSiteCrawlerService:
    """
    Production-grade website crawler service for technical SEO auditing.
    Safely crawls and parses target website pages within strict boundaries.
    """

    def __init__(
        self,
        project: Optional[Project] = None,
        user_agent: str = DEFAULT_USER_AGENT,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_depth: int = DEFAULT_MAX_DEPTH,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_size: int = DEFAULT_MAX_RESPONSE_SIZE,
        polite_delay: float = 0.0,
        respect_robots_txt: bool = True,
        transport: Optional[httpx.BaseTransport] = None
    ):
        self.project = project
        self.user_agent = user_agent
        self.max_pages = max(1, min(max_pages, 200))
        self.max_depth = max(0, min(max_depth, 10))
        self.timeout = max(1.0, float(timeout))
        self.max_response_size = max_response_size
        self.polite_delay = max(0.0, float(polite_delay))
        self.respect_robots_txt = respect_robots_txt
        self.transport = transport

    # =========================================================================
    # URL HANDLING & NORMALIZATION
    # =========================================================================

    @staticmethod
    def normalize_url(raw_url: str, base_url: str) -> Optional[str]:
        """
        Normalize and resolve relative or absolute URLs.
        - Strips fragments (#...).
        - Normalizes scheme and host to lowercase.
        - Removes duplicate slashes in path.
        - Strips invalid schemes (mailto:, javascript:, tel:, data:).
        - Returns None for unparseable or non-HTTP(S) URLs.
        """
        if not raw_url or not isinstance(raw_url, str):
            return None

        cleaned = raw_url.strip()
        if not cleaned or cleaned.startswith(('javascript:', 'mailto:', 'tel:', 'data:', 'sms:')):
            return None

        try:
            # Resolve relative URLs against base_url
            joined = urljoin(base_url, cleaned)
            parsed = urlsplit(joined)

            scheme = parsed.scheme.lower()
            if scheme not in ('http', 'https'):
                return None

            netloc = parsed.netloc.lower()
            if not netloc:
                return None

            # Remove standard default ports if explicitly provided
            if netloc.endswith(':80') and scheme == 'http':
                netloc = netloc[:-3]
            elif netloc.endswith(':443') and scheme == 'https':
                netloc = netloc[:-4]

            # Normalize path
            path = parsed.path
            if not path:
                path = '/'
            else:
                # Normalize double slashes and dot segments
                path = posixpath.normpath(path)
                if parsed.path.endswith('/') and not path.endswith('/'):
                    path += '/'

            # Deterministically sort query params if present
            query = ""
            if parsed.query:
                query_tuples = sorted(parse_qsl(parsed.query, keep_blank_values=True))
                query = urlencode(query_tuples)

            # Rebuild without fragment
            return urlunsplit((scheme, netloc, path, query, ''))

        except Exception as exc:
            logger.debug(f"Failed to normalize URL '{raw_url}' against '{base_url}': {exc}")
            return None

    @staticmethod
    def is_same_domain(url: str, base_domain: str) -> bool:
        """
        Determine whether a URL belongs to the target crawl domain.
        Supports full URLs, plain hostnames, exact match and www-prefix equivalence.
        """
        if not url or not base_domain:
            return False

        try:
            parsed_url = urlparse(url)
            host = (parsed_url.netloc or parsed_url.path or "").lower().split(':')[0]

            parsed_base = urlparse(base_domain)
            target = (parsed_base.netloc or parsed_base.path or "").lower().split(':')[0]

            if not host or not target:
                return False

            # Exact match
            if host == target:
                return True

            # www equivalence
            if host == f"www.{target}" or target == f"www.{host}":
                return True

            return False
        except Exception:
            return False

    @staticmethod
    def is_crawlable_extension(url: str) -> bool:
        """Check if the URL path ends with an obvious non-HTML file extension."""
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()
            _, ext = posixpath.splitext(path)
            return ext not in NON_HTML_EXTENSIONS
        except Exception:
            return False

    # =========================================================================
    # ROBOTS.TXT COMPLIANCE
    # =========================================================================

    def fetch_robots_txt(self, start_url: str, client: httpx.Client) -> Tuple[urllib.robotparser.RobotFileParser, str]:
        """
        Fetch and parse the robots.txt file for the target domain.
        Returns the parsed RobotFileParser and a status string.
        """
        rp = urllib.robotparser.RobotFileParser()
        parsed = urlparse(start_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp.set_url(robots_url)

        if not self.respect_robots_txt:
            return rp, "ignored"

        try:
            response = client.get(robots_url, timeout=5.0)
            if response.status_code == 200:
                rp.parse(response.text.splitlines())
                logger.info(f"Loaded and parsed robots.txt from {robots_url}")
                return rp, "loaded"
            elif response.status_code in (401, 403):
                # If access to robots.txt is forbidden, standard behavior is to disallow all
                logger.warning(f"robots.txt at {robots_url} returned {response.status_code}; fallback to allow all.")
                return rp, "access_denied"
            elif response.status_code == 404:
                # 404 means no restrictions
                logger.info(f"No robots.txt found at {robots_url} (404); allowing all crawl paths.")
                return rp, "not_found"
            else:
                logger.warning(f"robots.txt at {robots_url} returned status {response.status_code}; fallback to allow all.")
                return rp, f"http_{response.status_code}"
        except Exception as exc:
            logger.warning(f"Failed to fetch robots.txt at {robots_url} ({exc}); fallback to allow all.")
            return rp, "fetch_failed"

    # =========================================================================
    # HTML EXTRACTION (BeautifulSoup4)
    # =========================================================================

    def extract_html_features(
        self,
        url: str,
        final_url: str,
        status_code: int,
        response_time_ms: float,
        content_type: str,
        html_text: str,
        base_domain: str,
        redirect_chain: List[str]
    ) -> PageCrawlResult:
        """
        Parse raw HTML content using BeautifulSoup4 and extract structured SEO features.
        """
        result = PageCrawlResult(
            url=url,
            final_url=final_url,
            status_code=status_code,
            response_time_ms=response_time_ms,
            content_type=content_type,
            redirect_chain=redirect_chain
        )

        if not html_text:
            return result

        try:
            soup = BeautifulSoup(html_text, 'html.parser')

            # 1. Page Title
            if soup.title and soup.title.string:
                result.title = soup.title.string.strip()

            # 2. Meta Description
            desc_tag = soup.find('meta', attrs={'name': lambda x: x and x.lower() == 'description'})
            if not desc_tag:
                desc_tag = soup.find('meta', attrs={'property': lambda x: x and x.lower() == 'og:description'})
            if desc_tag and desc_tag.get('content'):
                result.meta_description = desc_tag['content'].strip()

            # 3. Headings H1..H6
            headings: Dict[str, List[str]] = {"h1": [], "h2": [], "h3": [], "h4": [], "h5": [], "h6": []}
            for level in range(1, 7):
                tag_name = f"h{level}"
                for h in soup.find_all(tag_name):
                    text = h.get_text(strip=True)
                    if text:
                        headings[tag_name].append(text)
            result.headings = headings

            # 4. Canonical URL
            canonical_tag = soup.find('link', rel=lambda x: x and 'canonical' in (x if isinstance(x, list) else [x]))
            if canonical_tag and canonical_tag.get('href'):
                resolved_canonical = self.normalize_url(canonical_tag['href'], final_url)
                result.canonical = resolved_canonical or canonical_tag['href'].strip()

            # 5. Images (<img src, alt>)
            images = []
            for img in soup.find_all('img'):
                src = img.get('src', '').strip()
                alt = img.get('alt', '')
                if alt is not None:
                    alt = alt.strip()
                resolved_src = self.normalize_url(src, final_url) if src else None
                images.append({
                    "src": src,
                    "resolved_url": resolved_src or src,
                    "alt": alt
                })
            result.images = images

            # 6. Hyperlinks (Internal vs External)
            internal_links = []
            external_links = []
            seen_links = set()

            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                    continue

                normalized_link = self.normalize_url(href, final_url)
                if not normalized_link:
                    continue

                link_text = a.get_text(strip=True)
                link_obj = {
                    "href": href,
                    "resolved_url": normalized_link,
                    "text": link_text
                }

                link_key = (normalized_link, link_text)
                if link_key in seen_links:
                    continue
                seen_links.add(link_key)

                if self.is_same_domain(normalized_link, base_domain):
                    internal_links.append(link_obj)
                else:
                    external_links.append(link_obj)

            result.internal_links = internal_links
            result.external_links = external_links

            # 7. JSON-LD Structured Data
            json_ld_blocks = []
            for script in soup.find_all('script', type='application/ld+json'):
                if script.string:
                    try:
                        raw_content = script.string.strip()
                        if raw_content:
                            parsed_json = json.loads(raw_content)
                            json_ld_blocks.append(parsed_json)
                    except Exception as json_err:
                        logger.debug(f"Malformed JSON-LD block on {final_url}: {json_err}")
            result.json_ld = json_ld_blocks

            # 8. Word Count
            text_content = soup.get_text(separator=' ', strip=True)
            words = [w for w in text_content.split() if w]
            result.word_count = len(words)

        except Exception as parse_exc:
            logger.warning(f"Error parsing HTML for {final_url}: {parse_exc}")
            result.error_message = f"HTML parse error: {str(parse_exc)}"

        return result

    # =========================================================================
    # CORE CRAWLER LOOP
    # =========================================================================

    def crawl(self, start_url: Optional[str] = None) -> CrawlResult:
        """
        Execute bounded BFS live site crawl starting from the designated URL or project website_url.
        """
        # Resolve target start URL
        target_url = start_url
        if not target_url and self.project:
            target_url = self.project.website_url

        if not target_url:
            raise ValueError("No start_url provided and project has no configured website_url.")

        normalized_start = self.normalize_url(target_url, target_url)
        if not normalized_start:
            raise ValueError(f"Invalid or unsupported start URL: '{target_url}'")

        parsed_start = urlparse(normalized_start)
        base_domain = parsed_start.netloc.lower()

        started_at = timezone.now()
        start_time_perf = time.perf_counter()

        # State tracking
        queue: deque[Tuple[str, int]] = deque([(normalized_start, 0)])
        visited_urls: Set[str] = set()
        discovered_urls: Set[str] = {normalized_start}
        crawled_pages: List[PageCrawlResult] = []
        errors: List[CrawlError] = []

        # Create HTTP client
        client_kwargs = {
            "follow_redirects": True,
            "max_redirects": 5,
            "timeout": self.timeout,
            "headers": {"User-Agent": self.user_agent}
        }
        if self.transport is not None:
            client_kwargs["transport"] = self.transport

        with httpx.Client(**client_kwargs) as client:
            # 1. Fetch & parse robots.txt
            robots_parser, robots_status = self.fetch_robots_txt(normalized_start, client)

            # 2. Bounded BFS Loop
            while queue and len(crawled_pages) < self.max_pages:
                current_url, current_depth = queue.popleft()

                if current_url in visited_urls:
                    continue
                visited_urls.add(current_url)

                # Check robots.txt permissions
                if self.respect_robots_txt and robots_status == "loaded":
                    try:
                        if not robots_parser.can_fetch(self.user_agent, current_url):
                            logger.info(f"Skipping {current_url} disallowed by robots.txt")
                            errors.append(CrawlError(
                                url=current_url,
                                error_type="robots_disallowed",
                                message=f"URL '{current_url}' is disallowed by robots.txt."
                            ))
                            continue
                    except Exception as rb_exc:
                        logger.debug(f"robots.txt evaluation error for {current_url}: {rb_exc}")

                # Polite delay between requests
                if self.polite_delay > 0:
                    time.sleep(self.polite_delay)

                # Fetch URL
                req_start = time.perf_counter()
                try:
                    response = client.get(current_url)
                    response_time_ms = round((time.perf_counter() - req_start) * 1000, 2)
                    final_url = str(response.url)
                    status_code = response.status_code
                    content_type = response.headers.get("content-type", "")

                    # Extract redirect chain if available
                    redirect_chain = [str(r.url) for r in response.history]

                    # Enforce max response size protection
                    body_bytes = response.content
                    if len(body_bytes) > self.max_response_size:
                        errors.append(CrawlError(
                            url=current_url,
                            error_type="response_too_large",
                            message=f"Response body ({len(body_bytes)} bytes) exceeded max limit of {self.max_response_size} bytes.",
                            status_code=status_code
                        ))
                        continue

                    # Process HTML responses
                    if "text/html" in content_type or "application/xhtml+xml" in content_type or not content_type:
                        html_text = response.text
                        page_result = self.extract_html_features(
                            url=current_url,
                            final_url=final_url,
                            status_code=status_code,
                            response_time_ms=response_time_ms,
                            content_type=content_type,
                            html_text=html_text,
                            base_domain=base_domain,
                            redirect_chain=redirect_chain
                        )
                        crawled_pages.append(page_result)

                        # Enqueue newly discovered internal links if within depth limit
                        if status_code < 400 and current_depth < self.max_depth:
                            for link in page_result.internal_links:
                                link_url = link["resolved_url"]
                                if (
                                    link_url not in visited_urls
                                    and link_url not in discovered_urls
                                    and self.is_crawlable_extension(link_url)
                                    and self.is_same_domain(link_url, base_domain)
                                ):
                                    discovered_urls.add(link_url)
                                    if len(visited_urls) + len(queue) < self.max_pages * 3:
                                        queue.append((link_url, current_depth + 1))
                    else:
                        # Non-HTML resource encountered
                        crawled_pages.append(PageCrawlResult(
                            url=current_url,
                            final_url=final_url,
                            status_code=status_code,
                            response_time_ms=response_time_ms,
                            content_type=content_type,
                            redirect_chain=redirect_chain
                        ))

                except httpx.TimeoutException as timeout_exc:
                    response_time_ms = round((time.perf_counter() - req_start) * 1000, 2)
                    logger.warning(f"Timeout crawling {current_url}: {timeout_exc}")
                    errors.append(CrawlError(
                        url=current_url,
                        error_type="timeout",
                        message=f"Request timed out after {self.timeout} seconds."
                    ))
                except httpx.TooManyRedirects as redir_exc:
                    logger.warning(f"Redirect loop on {current_url}: {redir_exc}")
                    errors.append(CrawlError(
                        url=current_url,
                        error_type="redirect_loop",
                        message="Too many redirects / redirect loop detected."
                    ))
                except httpx.HTTPError as http_exc:
                    logger.warning(f"HTTP error crawling {current_url}: {http_exc}")
                    errors.append(CrawlError(
                        url=current_url,
                        error_type="http_error",
                        message=str(http_exc)
                    ))
                except Exception as gen_exc:
                    logger.warning(f"Unexpected error crawling {current_url}: {gen_exc}")
                    errors.append(CrawlError(
                        url=current_url,
                        error_type="unexpected_error",
                        message=str(gen_exc)
                    ))

        completed_at = timezone.now()
        duration_seconds = round(time.perf_counter() - start_time_perf, 3)

        metadata = CrawlMetadata(
            start_url=normalized_start,
            base_domain=base_domain,
            user_agent=self.user_agent,
            max_pages=self.max_pages,
            max_depth=self.max_depth,
            robots_txt_status=robots_status,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            duration_seconds=duration_seconds
        )

        return CrawlResult(
            start_url=normalized_start,
            metadata=metadata,
            pages_crawled=len(crawled_pages),
            pages_discovered=len(discovered_urls),
            duration_seconds=duration_seconds,
            errors=errors,
            pages=crawled_pages
        )
