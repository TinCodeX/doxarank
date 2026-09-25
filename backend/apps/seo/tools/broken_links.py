"""
DoxaRank Single-Page Broken Link Checker (Tool 9).

Performs lightweight, bounded, synchronous verification of hyperlinks on a single webpage.
Strictly scans only the target page; never initiates multi-page crawling or site audits.

Security:
- Comprehensive Anti-SSRF protection: rejects private IPs, loopback, link-local, cloud metadata.
- Strict DNS resolution checking to prevent DNS-rebinding attacks against private networks.
- Redirect protection: validates each redirect hop against SSRF rules before following.
- Resource limits: max response size (5MB), request timeouts, and max links limit per page (100).
- Safe HTML parsing using BeautifulSoup4.
"""

import time
import socket
import ipaddress
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Tuple, Set
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DISALLOWED_SCHEMES = {'file', 'ftp', 'javascript', 'data', 'mailto', 'tel', 'blob'}
DEFAULT_TIMEOUT_SECONDS = 8.0
MAX_RESPONSE_BYTES = 5_000_000  # 5 MB
MAX_LINKS_PER_PAGE = 100
MAX_WORKERS = 5

DISALLOWED_HOSTS: Set[str] = {
    'localhost', '127.0.0.1', '::1', '0.0.0.0', '169.254.169.254', 'metadata.google.internal'
}


def validate_ssrf_safe_url(url: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates that a URL is safe to query over the public internet.
    Performs scheme check, hostname check, and DNS resolution validation.
    Returns: (is_safe: bool, error_reason: Optional[str], resolved_ip: Optional[str])
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string.", None

    url_clean = url.strip()
    try:
        parsed = urlparse(url_clean)
    except Exception as exc:
        return False, f"Malformed URL: {exc}", None

    scheme = (parsed.scheme or '').lower()
    if scheme in DISALLOWED_SCHEMES or scheme not in ('http', 'https'):
        return False, f"Unsupported or dangerous URL scheme '{scheme}'. Only http and https are allowed.", None

    hostname = (parsed.hostname or '').lower().strip()
    if not hostname:
        return False, "URL is missing a valid hostname.", None

    if hostname in DISALLOWED_HOSTS or hostname.endswith('.local') or hostname.endswith('.internal'):
        return False, f"Target hostname '{hostname}' is forbidden (SSRF protection).", None

    # Check if hostname is an IP literal
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, f"Target IP '{hostname}' resolves to private or loopback network (SSRF protection).", str(ip)
        return True, None, str(ip)
    except ValueError:
        # Hostname is a domain name; perform DNS resolution check
        pass

    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            resolved_ip = ipaddress.ip_address(ip_str)
            if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local or resolved_ip.is_reserved or resolved_ip.is_multicast:
                return False, f"Hostname '{hostname}' resolves to private/internal IP '{ip_str}' (SSRF protection).", ip_str
        # If all resolved addresses are public
        primary_ip = addr_info[0][4][0] if addr_info else None
        return True, None, primary_ip
    except socket.gaierror as e:
        return False, f"DNS resolution failed for hostname '{hostname}': {str(e)}", None
    except Exception as e:
        return False, f"Address validation failed for hostname '{hostname}': {str(e)}", None


def safe_fetch_single_page(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    """
    Fetches the single target page with Anti-SSRF and size bounds.
    Does not automatically follow redirects into forbidden private hosts.
    """
    current_url = url
    max_redirects = 5

    for _ in range(max_redirects):
        is_safe, error, _ = validate_ssrf_safe_url(current_url)
        if not is_safe:
            raise ValueError(f"Blocked request to unsafe URL: {error}")

        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            headers = {'User-Agent': 'DoxaRankBot/1.0 (+https://doxarank.com/bot; link-checker)'}
            with client.stream('GET', current_url, headers=headers) as response:
                # Redirect check
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get('location')
                    if not location:
                        raise ValueError(f"Redirect from {current_url} missing Location header.")
                    current_url = urljoin(current_url, location)
                    continue

                if response.status_code >= 400:
                    raise ValueError(f"Target page returned HTTP {response.status_code}.")

                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
                    raise ValueError(f"Target page is not HTML (Content-Type: '{content_type}').")

                # Bounded body reading
                content = b""
                for chunk in response.iter_bytes():
                    content += chunk
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise ValueError(f"Page content exceeds maximum allowed size of {MAX_RESPONSE_BYTES // 1_000_000}MB.")

                return content.decode('utf-8', errors='replace')

    raise ValueError(f"Too many redirects encountered while fetching {url}.")


def check_individual_link(
    target_url: str,
    link_url: str,
    anchor_text: str,
    target_hostname: str,
    timeout: float = 6.0
) -> Dict[str, Any]:
    """
    Evaluates reachability of a single extracted link.
    Validates against SSRF, tests with HEAD/GET, and computes response time.
    """
    parsed_link = urlparse(link_url)
    is_internal = (parsed_link.hostname or '').lower() == target_hostname

    # 1. Anti-SSRF check on the link
    is_safe, error, _ = validate_ssrf_safe_url(link_url)
    if not is_safe:
        return {
            'url': link_url,
            'anchor_text': anchor_text,
            'status_code': None,
            'is_internal': is_internal,
            'is_broken': True,
            'error_type': 'SSRF_BLOCKED',
            'error_message': error,
            'response_time_ms': 0.0,
        }

    # 2. Check reachability via HTTP HEAD (fallback to GET on 405 Method Not Allowed)
    start_time = time.perf_counter()
    headers = {'User-Agent': 'DoxaRankBot/1.0 (+https://doxarank.com/bot; link-checker)'}

    current_url = link_url
    max_hops = 3

    for _ in range(max_hops):
        # Re-verify each hop for SSRF
        is_safe, error, _ = validate_ssrf_safe_url(current_url)
        if not is_safe:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return {
                'url': link_url,
                'anchor_text': anchor_text,
                'status_code': None,
                'is_internal': is_internal,
                'is_broken': True,
                'error_type': 'REDIRECT_SSRF_BLOCKED',
                'error_message': f"Redirect destination blocked: {error}",
                'response_time_ms': elapsed_ms,
            }

        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                res = client.head(current_url, headers=headers)
                if res.status_code == 405:  # Method Not Allowed for HEAD, try GET
                    res = client.get(current_url, headers=headers)

                if res.status_code in (301, 302, 303, 307, 308):
                    loc = res.headers.get('location')
                    if loc:
                        current_url = urljoin(current_url, loc)
                        continue

                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
                is_broken = res.status_code >= 400
                error_type = f"HTTP_{res.status_code}" if is_broken else None

                return {
                    'url': link_url,
                    'anchor_text': anchor_text,
                    'status_code': res.status_code,
                    'is_internal': is_internal,
                    'is_broken': is_broken,
                    'error_type': error_type,
                    'error_message': None,
                    'response_time_ms': elapsed_ms,
                }
        except httpx.TimeoutException:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return {
                'url': link_url,
                'anchor_text': anchor_text,
                'status_code': None,
                'is_internal': is_internal,
                'is_broken': True,
                'error_type': 'TIMEOUT',
                'error_message': f"Request timed out after {timeout}s",
                'response_time_ms': elapsed_ms,
            }
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return {
                'url': link_url,
                'anchor_text': anchor_text,
                'status_code': None,
                'is_internal': is_internal,
                'is_broken': True,
                'error_type': 'CONNECTION_ERROR',
                'error_message': str(e),
                'response_time_ms': elapsed_ms,
            }

    # Exceeded hops
    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
    return {
        'url': link_url,
        'anchor_text': anchor_text,
        'status_code': None,
        'is_internal': is_internal,
        'is_broken': True,
        'error_type': 'TOO_MANY_REDIRECTS',
        'error_message': 'Exceeded maximum redirect hops',
        'response_time_ms': elapsed_ms,
    }


class SinglePageBrokenLinkChecker:
    """
    Domain service for Tool 9: Single-Page Broken Link Checker.
    """

    @classmethod
    def check_page(
        cls,
        url: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_links: int = MAX_LINKS_PER_PAGE
    ) -> Dict[str, Any]:
        """
        Fetches the target HTML page, extracts links, checks their HTTP status,
        and aggregates summary counts and link-level diagnostics.
        """
        url = (url or '').strip()
        if not url:
            raise ValueError("Target webpage URL is required for link checking.")

        # 1. Anti-SSRF check on target URL
        is_safe, error, _ = validate_ssrf_safe_url(url)
        if not is_safe:
            raise ValueError(f"Invalid target URL: {error}")

        target_hostname = (urlparse(url).hostname or '').lower()

        # 2. Fetch page HTML safely
        html_content = safe_fetch_single_page(url, timeout=timeout)

        # 3. Extract anchor links
        soup = BeautifulSoup(html_content, 'html.parser')
        discovered_links: List[Tuple[str, str]] = []
        seen_urls: Set[str] = set()

        for a_tag in soup.find_all('a', href=True):
            raw_href = a_tag.get('href', '').strip()
            if not raw_href or raw_href.startswith('#') or raw_href.startswith('javascript:'):
                continue
            if raw_href.startswith('mailto:') or raw_href.startswith('tel:'):
                continue

            resolved_url = urljoin(url, raw_href)
            # Remove fragment
            if '#' in resolved_url:
                resolved_url = resolved_url.split('#')[0]

            if resolved_url in seen_urls:
                continue
            seen_urls.add(resolved_url)

            anchor_text = a_tag.get_text(separator=' ', strip=True) or '[No Anchor Text]'
            if len(anchor_text) > 100:
                anchor_text = anchor_text[:97] + '...'

            discovered_links.append((resolved_url, anchor_text))
            if len(discovered_links) >= max_links:
                break

        # 4. Check reachability concurrently with thread pool
        results: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_link = {
                executor.submit(
                    check_individual_link, url, link_url, text, target_hostname
                ): link_url
                for link_url, text in discovered_links
            }
            for future in as_completed(future_to_link):
                try:
                    res = future.result()
                    results.append(res)
                except Exception as e:
                    link_url = future_to_link[future]
                    results.append({
                        'url': link_url,
                        'anchor_text': '[Unknown]',
                        'status_code': None,
                        'is_internal': False,
                        'is_broken': True,
                        'error_type': 'WORKER_ERROR',
                        'error_message': str(e),
                        'response_time_ms': 0.0,
                    })

        # Sort results: broken first, then by URL
        results.sort(key=lambda r: (not r['is_broken'], r['url']))

        # 5. Aggregate metrics
        total_links = len(results)
        internal_count = sum(1 for r in results if r['is_internal'])
        external_count = total_links - internal_count
        broken_count = sum(1 for r in results if r['is_broken'])
        healthy_count = total_links - broken_count

        return {
            'target_url': url,
            'total_links': total_links,
            'internal_links': internal_count,
            'external_links': external_count,
            'broken_links': broken_count,
            'healthy_links': healthy_count,
            'summary': {
                'total_links': total_links,
                'internal_links': internal_count,
                'external_links': external_count,
                'broken_links': broken_count,
                'healthy_links': healthy_count,
                'has_broken_links': broken_count > 0,
            },
            'links': results,
        }
