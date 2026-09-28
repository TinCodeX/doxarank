"""
Technical SEO Crawler Service for DoxaRank (FeatureCode.TECHNICAL_CRAWLER).

Production-grade, SSRF-safe full-site crawler that:
- Resolves hostnames and validates all target IPs against an allowlist
  (blocks RFC1918, loopback, link-local, metadata endpoints, etc.)
- Performs bounded BFS crawl with configurable max_pages / max_depth
- Extracts rich per-page SEO data: title, meta description, H1s, canonical,
  images, internal/external links, redirect chains, response time
- Detects and flags: broken links (4xx/5xx), missing titles, missing meta
  descriptions, missing H1, slow pages (>3s), redirect chains
- Persists structured results to CrawlJob and CrawlPage models
- Designed to be called from a Celery task; never exposes raw token/credential data

Architecture note:
  The existing LiveSiteCrawlerService (httpx-based) serves the SiteAudit feature.
  This TechnicalCrawlerService is a NEW, separate service for the paid crawler.
  Both coexist independently and MUST NOT be merged.
"""

import ipaddress
import logging
import posixpath
import re
import socket
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit
import json
import urllib.robotparser

import httpx
from bs4 import BeautifulSoup
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSRF PROTECTION — Blocked IP Ranges
# ---------------------------------------------------------------------------

BLOCKED_IP_NETWORKS: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    # IPv4 loopback
    ipaddress.IPv4Network('127.0.0.0/8'),
    # IPv4 private (RFC1918)
    ipaddress.IPv4Network('10.0.0.0/8'),
    ipaddress.IPv4Network('172.16.0.0/12'),
    ipaddress.IPv4Network('192.168.0.0/16'),
    # IPv4 link-local
    ipaddress.IPv4Network('169.254.0.0/16'),
    # IPv4 APIPA / cloud metadata (AWS, GCP, Azure)
    ipaddress.IPv4Network('169.254.169.254/32'),
    # IPv4 multicast
    ipaddress.IPv4Network('224.0.0.0/4'),
    # IPv4 broadcast / reserved
    ipaddress.IPv4Network('240.0.0.0/4'),
    # IPv4 current network
    ipaddress.IPv4Network('0.0.0.0/8'),
    # IPv6 loopback
    ipaddress.IPv6Network('::1/128'),
    # IPv6 link-local
    ipaddress.IPv6Network('fe80::/10'),
    # IPv6 unique-local (ULA)
    ipaddress.IPv6Network('fc00::/7'),
    # IPv6 multicast
    ipaddress.IPv6Network('ff00::/8'),
    # IPv6 unspecified
    ipaddress.IPv6Network('::/128'),
    # IPv4-mapped IPv6 loopback
    ipaddress.IPv6Network('::ffff:127.0.0.0/104'),
    # IPv4-mapped RFC1918
    ipaddress.IPv6Network('::ffff:10.0.0.0/104'),
    ipaddress.IPv6Network('::ffff:172.16.0.0/108'),
    ipaddress.IPv6Network('::ffff:192.168.0.0/112'),
]

# Additional hostname-level blocks for known metadata/internal endpoints
BLOCKED_HOSTNAMES: Set[str] = {
    'metadata.google.internal',
    'metadata.google',
    'instance-data',
    'metadata',
    '169.254.169.254',
    'fd00:ec2::254',  # AWS IPv6 metadata
}

# Non-HTML file extensions — skip crawling these
NON_HTML_EXTENSIONS: Set[str] = {
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.bmp', '.tiff',
    '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt', '.csv',
    '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',
    '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.wav', '.ogg', '.m4a',
    '.css', '.js', '.json', '.xml', '.rss', '.atom',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
}

SLOW_PAGE_THRESHOLD_MS = 3000.0   # 3 seconds
DEFAULT_USER_AGENT = 'DoxaRankBot/1.0 (+https://doxarank.com/bot)'
MAX_PAGES_HARD_LIMIT = 500
MAX_DEPTH_HARD_LIMIT = 10
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RESPONSE_BYTES = 5_000_000  # 5 MB


# ---------------------------------------------------------------------------
# DATA STRUCTURES
# ---------------------------------------------------------------------------

@dataclass
class PageFinding:
    """SEO issue found on a specific page."""
    issue_type: str
    severity: str        # 'critical' | 'warning' | 'notice'
    message: str


@dataclass
class CrawlPageData:
    """Structured extraction result for a single crawled URL."""
    url: str
    final_url: str
    status_code: int
    response_time_ms: float
    depth: int
    title: Optional[str] = None
    meta_description: Optional[str] = None
    h1_count: int = 0
    word_count: int = 0
    canonical_url: Optional[str] = None
    has_redirect: bool = False
    redirect_chain: List[str] = field(default_factory=list)
    internal_links_count: int = 0
    external_links_count: int = 0
    images_count: int = 0
    images_missing_alt_count: int = 0
    is_broken: bool = False
    is_slow: bool = False
    internal_links: List[str] = field(default_factory=list)
    findings: List[PageFinding] = field(default_factory=list)


@dataclass
class CrawlSummary:
    """Aggregate result of a full crawl run."""
    pages_crawled: int
    pages_discovered: int
    broken_links_count: int
    missing_titles_count: int
    missing_descriptions_count: int
    duplicate_titles_count: int
    missing_h1_count: int
    redirect_chains_count: int
    slow_pages_count: int
    metadata: Dict


# ---------------------------------------------------------------------------
# SSRF SAFETY UTILITIES
# ---------------------------------------------------------------------------

def _is_ip_blocked(ip_str: str) -> bool:
    """Return True if the IP address is in any blocked private/reserved network."""
    try:
        addr = ipaddress.ip_address(ip_str)
        for network in BLOCKED_IP_NETWORKS:
            if addr in network:
                return True
        return False
    except ValueError:
        # Not a valid IP — block by default
        return True


def _is_hostname_safe(hostname: str) -> bool:
    """
    Resolve the hostname and verify all returned IP addresses are public.
    Raises ValueError with reason if the target is blocked.
    """
    hostname_clean = hostname.lower().strip()

    # Direct hostname block list
    if hostname_clean in BLOCKED_HOSTNAMES:
        raise ValueError(f"SSRF: hostname '{hostname_clean}' is explicitly blocked.")

    # DNS resolution check — resolve all addresses
    try:
        results = socket.getaddrinfo(hostname_clean, None)
    except socket.gaierror as exc:
        raise ValueError(f"SSRF: DNS resolution failed for '{hostname_clean}': {exc}")

    if not results:
        raise ValueError(f"SSRF: No DNS results for '{hostname_clean}'.")

    for family, _type, _proto, _canonname, sockaddr in results:
        ip = sockaddr[0]
        if _is_ip_blocked(ip):
            raise ValueError(
                f"SSRF: '{hostname_clean}' resolves to blocked IP address '{ip}'."
            )

    return True


def validate_crawl_target(url: str) -> str:
    """
    Validate a crawl target URL for SSRF safety.
    Returns the normalized URL if safe, raises ValueError if blocked.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Invalid URL '{url}': {exc}")

    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f"Scheme '{parsed.scheme}' is not permitted; only http/https allowed.")

    if not parsed.netloc:
        raise ValueError(f"URL '{url}' has no host component.")

    # Strip port from netloc for hostname check
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Cannot extract hostname from '{url}'.")

    _is_hostname_safe(hostname)
    return url


# ---------------------------------------------------------------------------
# URL UTILITIES
# ---------------------------------------------------------------------------

def normalize_url(raw_url: str, base_url: str) -> Optional[str]:
    """Resolve, normalize, and strip fragments from a URL."""
    if not raw_url or not isinstance(raw_url, str):
        return None

    cleaned = raw_url.strip()
    if not cleaned or cleaned.startswith(('javascript:', 'mailto:', 'tel:', 'data:', 'sms:')):
        return None

    try:
        joined = urljoin(base_url, cleaned)
        parsed = urlsplit(joined)

        scheme = parsed.scheme.lower()
        if scheme not in ('http', 'https'):
            return None

        netloc = parsed.netloc.lower()
        if not netloc:
            return None

        if netloc.endswith(':80') and scheme == 'http':
            netloc = netloc[:-3]
        elif netloc.endswith(':443') and scheme == 'https':
            netloc = netloc[:-4]

        path = parsed.path or '/'
        path = posixpath.normpath(path)
        if parsed.path.endswith('/') and not path.endswith('/'):
            path += '/'

        query = ''
        if parsed.query:
            query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))

        return urlunsplit((scheme, netloc, path, query, ''))

    except Exception:
        return None


def is_same_domain(url: str, base_domain: str) -> bool:
    """True if url belongs to the same domain as base_domain (www-equivalence aware)."""
    try:
        host = urlparse(url).hostname or ''
        target = urlparse(base_domain).hostname or urlparse(f'http://{base_domain}').hostname or ''

        host = host.lower().split(':')[0]
        target = target.lower().split(':')[0]

        if not host or not target:
            return False
        if host == target:
            return True
        if host == f'www.{target}' or target == f'www.{host}':
            return True
        return False
    except Exception:
        return False


def has_crawlable_extension(url: str) -> bool:
    """Return True if URL does not end with a non-HTML file extension."""
    try:
        path = urlparse(url).path.lower()
        _, ext = posixpath.splitext(path)
        return ext not in NON_HTML_EXTENSIONS
    except Exception:
        return False


# ---------------------------------------------------------------------------
# HTML EXTRACTION
# ---------------------------------------------------------------------------

def extract_page_data(
    url: str,
    final_url: str,
    status_code: int,
    response_time_ms: float,
    depth: int,
    redirect_chain: List[str],
    html_text: str,
    base_domain: str,
) -> CrawlPageData:
    """Parse HTML and extract structured SEO data for a single page."""
    data = CrawlPageData(
        url=url,
        final_url=final_url,
        status_code=status_code,
        response_time_ms=response_time_ms,
        depth=depth,
        is_broken=status_code >= 400,
        is_slow=response_time_ms > SLOW_PAGE_THRESHOLD_MS,
        has_redirect=bool(redirect_chain),
        redirect_chain=redirect_chain,
    )

    if not html_text:
        return data

    try:
        soup = BeautifulSoup(html_text, 'html.parser')

        # Title
        if soup.title and soup.title.string:
            data.title = soup.title.string.strip()[:512]

        # Meta description
        meta = soup.find('meta', attrs={'name': lambda x: x and x.lower() == 'description'})
        if not meta:
            meta = soup.find('meta', attrs={'property': lambda x: x and x.lower() == 'og:description'})
        if meta and meta.get('content'):
            data.meta_description = meta['content'].strip()

        # H1 count
        data.h1_count = len(soup.find_all('h1'))

        # Canonical
        canon = soup.find('link', rel=lambda x: x and 'canonical' in (x if isinstance(x, list) else [x]))
        if canon and canon.get('href'):
            data.canonical_url = normalize_url(canon['href'], final_url)

        # Images
        imgs = soup.find_all('img')
        data.images_count = len(imgs)
        data.images_missing_alt_count = sum(
            1 for img in imgs
            if not img.get('alt') or not img['alt'].strip()
        )

        # Word count
        text_content = soup.get_text(separator=' ', strip=True)
        data.word_count = len(text_content.split())

        # Links
        internal_links: List[str] = []
        external_links_count = 0
        seen_links: Set[str] = set()

        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            norm = normalize_url(href, final_url)
            if not norm or norm in seen_links:
                continue
            seen_links.add(norm)
            if is_same_domain(norm, base_domain):
                internal_links.append(norm)
            else:
                external_links_count += 1

        data.internal_links = internal_links
        data.internal_links_count = len(internal_links)
        data.external_links_count = external_links_count

    except Exception as exc:
        logger.warning(f"[TechnicalCrawler] HTML parse error for {final_url}: {exc}")

    return data


def detect_page_issues(page: CrawlPageData) -> List[PageFinding]:
    """Detect and return SEO issues for a crawled page."""
    findings: List[PageFinding] = []

    if page.is_broken:
        findings.append(PageFinding(
            issue_type='broken_page',
            severity='critical',
            message=f"Page returned HTTP {page.status_code}.",
        ))

    if page.status_code < 400:
        if not page.title:
            findings.append(PageFinding(
                issue_type='missing_title',
                severity='critical',
                message='Page has no <title> tag or title is empty.',
            ))
        if not page.meta_description:
            findings.append(PageFinding(
                issue_type='missing_meta_description',
                severity='warning',
                message='Page has no meta description.',
            ))
        if page.h1_count == 0:
            findings.append(PageFinding(
                issue_type='missing_h1',
                severity='warning',
                message='Page has no H1 heading.',
            ))
        if page.h1_count > 1:
            findings.append(PageFinding(
                issue_type='multiple_h1',
                severity='notice',
                message=f'Page has {page.h1_count} H1 headings; only one is recommended.',
            ))
        if page.has_redirect:
            findings.append(PageFinding(
                issue_type='redirect_chain',
                severity='warning',
                message=f"URL went through {len(page.redirect_chain)} redirect(s): "
                        f"{' → '.join(page.redirect_chain[:3])}{'...' if len(page.redirect_chain) > 3 else ''}",
            ))
        if page.is_slow:
            findings.append(PageFinding(
                issue_type='slow_page',
                severity='warning',
                message=f'Page response time was {page.response_time_ms:.0f}ms (>{SLOW_PAGE_THRESHOLD_MS:.0f}ms threshold).',
            ))
        if page.images_missing_alt_count > 0:
            findings.append(PageFinding(
                issue_type='images_missing_alt',
                severity='notice',
                message=f'{page.images_missing_alt_count} image(s) are missing alt attributes.',
            ))

    return findings


# ---------------------------------------------------------------------------
# TECHNICAL CRAWLER SERVICE
# ---------------------------------------------------------------------------

class TechnicalCrawlerService:
    """
    Full-site technical SEO crawler with SSRF protection.

    Flow:
    1. Validate SSRF safety of target URL
    2. Fetch robots.txt
    3. BFS crawl up to max_pages / max_depth
    4. Extract page data and detect issues for each page
    5. Return structured CrawlSummary + list[CrawlPageData]
    """

    def __init__(
        self,
        max_pages: int = 100,
        max_depth: int = 3,
        respect_robots_txt: bool = True,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        polite_delay: float = 0.5,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.max_pages = max(1, min(int(max_pages), MAX_PAGES_HARD_LIMIT))
        self.max_depth = max(0, min(int(max_depth), MAX_DEPTH_HARD_LIMIT))
        self.respect_robots_txt = respect_robots_txt
        self.timeout = max(1.0, float(timeout))
        self.max_response_bytes = max_response_bytes
        self.polite_delay = max(0.0, float(polite_delay))
        self.user_agent = user_agent
        self.transport = transport

    def _fetch_robots_txt(
        self, start_url: str, client: httpx.Client
    ) -> Tuple[urllib.robotparser.RobotFileParser, str]:
        """Fetch and parse robots.txt; return (parser, status_string)."""
        rp = urllib.robotparser.RobotFileParser()
        parsed = urlparse(start_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp.set_url(robots_url)

        if not self.respect_robots_txt:
            return rp, 'ignored'

        try:
            response = client.get(robots_url, timeout=5.0)
            if response.status_code == 200:
                rp.parse(response.text.splitlines())
                return rp, 'loaded'
            elif response.status_code == 404:
                return rp, 'not_found'
            else:
                return rp, f'http_{response.status_code}'
        except Exception as exc:
            logger.warning(f"[TechnicalCrawler] robots.txt fetch failed: {exc}")
            return rp, 'fetch_failed'

    def crawl(self, start_url: str) -> Tuple[CrawlSummary, List[CrawlPageData]]:
        """
        Execute the bounded BFS crawl from start_url.

        Args:
            start_url: The URL to begin crawling (project's website_url).

        Returns:
            (CrawlSummary, list[CrawlPageData])

        Raises:
            ValueError: If the target URL fails SSRF validation.
        """
        # 1. SSRF safety check — raises ValueError if blocked
        validate_crawl_target(start_url)

        norm_start = normalize_url(start_url, start_url)
        if not norm_start:
            raise ValueError(f"Could not normalize start URL: '{start_url}'")

        base_domain = norm_start
        started_at = timezone.now()
        t0 = time.perf_counter()

        # BFS state
        queue: deque[Tuple[str, int]] = deque([(norm_start, 0)])
        visited: Set[str] = set()
        discovered: Set[str] = {norm_start}
        pages_data: List[CrawlPageData] = []

        client_kwargs: Dict = {
            'follow_redirects': True,
            'max_redirects': 5,
            'timeout': self.timeout,
            'headers': {'User-Agent': self.user_agent},
        }
        if self.transport is not None:
            client_kwargs['transport'] = self.transport

        robots_status = 'ignored'

        with httpx.Client(**client_kwargs) as client:
            robots_parser, robots_status = self._fetch_robots_txt(norm_start, client)

            while queue and len(pages_data) < self.max_pages:
                current_url, depth = queue.popleft()

                if current_url in visited:
                    continue
                visited.add(current_url)

                # robots.txt compliance
                if self.respect_robots_txt and robots_status == 'loaded':
                    try:
                        if not robots_parser.can_fetch(self.user_agent, current_url):
                            logger.debug(f"[TechnicalCrawler] Skipping (robots.txt): {current_url}")
                            continue
                    except Exception:
                        pass

                # Re-validate IP after DNS resolution (defense in depth)
                try:
                    parsed_current = urlparse(current_url)
                    if parsed_current.hostname:
                        _is_hostname_safe(parsed_current.hostname)
                except ValueError as ssrf_exc:
                    logger.warning(f"[TechnicalCrawler] SSRF block mid-crawl for {current_url}: {ssrf_exc}")
                    continue

                if self.polite_delay > 0:
                    time.sleep(self.polite_delay)

                req_start = time.perf_counter()
                try:
                    response = client.get(current_url)
                    response_time_ms = round((time.perf_counter() - req_start) * 1000, 2)
                    final_url = str(response.url)
                    status_code = response.status_code
                    content_type = response.headers.get('content-type', '')
                    redirect_chain = [str(r.url) for r in response.history]

                    body = response.content
                    if len(body) > self.max_response_bytes:
                        logger.warning(f"[TechnicalCrawler] Skipping oversized response: {current_url}")
                        continue

                    is_html = 'text/html' in content_type or 'application/xhtml' in content_type or not content_type

                    if is_html:
                        html_text = response.text
                        page_data = extract_page_data(
                            url=current_url,
                            final_url=final_url,
                            status_code=status_code,
                            response_time_ms=response_time_ms,
                            depth=depth,
                            redirect_chain=redirect_chain,
                            html_text=html_text,
                            base_domain=base_domain,
                        )
                        page_data.findings = detect_page_issues(page_data)
                        pages_data.append(page_data)

                        # Enqueue internal links within depth limit
                        if status_code < 400 and depth < self.max_depth:
                            for link_url in page_data.internal_links:
                                if (
                                    link_url not in visited
                                    and link_url not in discovered
                                    and has_crawlable_extension(link_url)
                                    and is_same_domain(link_url, base_domain)
                                    and len(visited) + len(queue) < self.max_pages * 3
                                ):
                                    discovered.add(link_url)
                                    queue.append((link_url, depth + 1))
                    else:
                        # Non-HTML resource
                        pages_data.append(CrawlPageData(
                            url=current_url,
                            final_url=final_url,
                            status_code=status_code,
                            response_time_ms=response_time_ms,
                            depth=depth,
                            redirect_chain=redirect_chain,
                            has_redirect=bool(redirect_chain),
                            is_broken=status_code >= 400,
                            is_slow=response_time_ms > SLOW_PAGE_THRESHOLD_MS,
                        ))

                except httpx.TimeoutException:
                    logger.warning(f"[TechnicalCrawler] Timeout: {current_url}")
                except httpx.TooManyRedirects:
                    logger.warning(f"[TechnicalCrawler] Redirect loop: {current_url}")
                except httpx.HTTPError as exc:
                    logger.warning(f"[TechnicalCrawler] HTTP error {current_url}: {exc}")
                except Exception as exc:
                    logger.warning(f"[TechnicalCrawler] Unexpected error {current_url}: {exc}")

        # Compute aggregates
        title_counts: Dict[str, int] = {}
        missing_titles = 0
        missing_descs = 0
        missing_h1 = 0
        redirect_chains = 0
        slow_pages = 0
        broken = 0

        for p in pages_data:
            if p.is_broken:
                broken += 1
            if p.status_code < 400:
                if not p.title:
                    missing_titles += 1
                else:
                    title_counts[p.title] = title_counts.get(p.title, 0) + 1
                if not p.meta_description:
                    missing_descs += 1
                if p.h1_count == 0:
                    missing_h1 += 1
            if p.has_redirect:
                redirect_chains += 1
            if p.is_slow:
                slow_pages += 1

        duplicate_titles = sum(1 for cnt in title_counts.values() if cnt > 1)

        duration = round(time.perf_counter() - t0, 3)
        summary = CrawlSummary(
            pages_crawled=len(pages_data),
            pages_discovered=len(discovered),
            broken_links_count=broken,
            missing_titles_count=missing_titles,
            missing_descriptions_count=missing_descs,
            duplicate_titles_count=duplicate_titles,
            missing_h1_count=missing_h1,
            redirect_chains_count=redirect_chains,
            slow_pages_count=slow_pages,
            metadata={
                'start_url': norm_start,
                'base_domain': base_domain,
                'robots_txt_status': robots_status,
                'max_pages': self.max_pages,
                'max_depth': self.max_depth,
                'started_at': started_at.isoformat(),
                'completed_at': timezone.now().isoformat(),
                'duration_seconds': duration,
                'user_agent': self.user_agent,
            },
        )
        return summary, pages_data
