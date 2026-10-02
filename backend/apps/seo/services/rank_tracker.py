"""
Rank Tracker Service for DoxaRank (Original SRS Task: Rank Tracker MVP).

Tracks Amharic and English keywords against Google Ethiopia (google.com.et).
Features:
- Configurable search target: google.com.et (Ethiopia, country code 'ET')
- Multi-lingual keyword support: English ('en') and Amharic ('am') with exact UTF-8 preservation
- Resilient organic SERP parser: filters ads, sponsored blocks, knowledge panels, carousels, PAA
- Organic position detection (1-100) or 'not_found' / null when outside top 100
- Position change tracking: current, previous, change (+/-), status (improved, declined, entered, dropped)
- Safe network behavior: SSRF protection (fixed approved Google domains only), timeout, bounded retry
- Celery-ready service methods with per-keyword error isolation
"""

import logging
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

import httpx
from bs4 import BeautifulSoup
from django.db import transaction
from django.utils import timezone

from apps.seo.models import (
    Keyword,
    KeywordRanking,
    RankingResultStatus,
    SearchEngine,
    Country,
    Language,
    Device,
    RankCheckJob,
    RankCheckJobStatus,
)

logger = logging.getLogger(__name__)

# Approved Google Ethiopia hostnames to prevent SSRF / arbitrary URL fetch abuse
APPROVED_GOOGLE_HOSTS = {
    'google.com.et',
    'www.google.com.et',
    'google.com',
    'www.google.com',
}

# Browser User-Agents for desktop and mobile Google SERP requests
DEFAULT_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
DEFAULT_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36"
)


@dataclass
class SerpResult:
    """Parsed result representation for a single target keyword in SERP."""
    position: Optional[int]
    url: Optional[str]
    title: Optional[str]
    status: str  # 'found', 'not_found', 'error'
    search_engine: str = 'google'
    search_domain: str = 'google.com.et'
    total_organic_found: int = 0
    error_message: str = ''


class SerpParser:
    """
    Resilient Google SERP HTML parser for Google Ethiopia (google.com.et).
    Extracts organic results while filtering ads, sponsored elements, knowledge panels,
    featured snippets, related question blocks (PAA), and navigation widgets.
    """

    # Elements and CSS identifiers that represent non-organic content
    NON_ORGANIC_CONTAINERS = [
        '#tads',
        '#bottomads',
        '#taw',
        'div[data-text-ad]',
        'div.uEierd',
        '.commercial-unit-desktop-top',
        '.commercial-unit-desktop-rhs',
        '.commercial-unit-mobile-top',
        '.commercial-unit-mobile-bottom',
        'div[data-ad-slot]',
        'div[aria-label="Ads"]',
        'div[aria-label="Sponsored"]',
        'div[aria-label="ማስታወቂያ"]',
        'div[aria-label="Beeksisa"]',
        '.kp-wholepage',
        '.knowledge-panel',
        '.osrp-blk',
        '#rhs',
        '#rhs_block',
        '#wp-tabs-container',
        '.related-question-pair',
        'div[data-initq]',
        'div[data-q]',
        'div.match-mod-horizontal',
        'div[jsname="yEVEwb"]',
        'div[jsname="N760b"]',
        '#extrares',
        '#searchform',
        '#top_nav',
        '#hdtb',
        '#foot',
        '#navcnt',
        '#fbar',
        '#footcnt',
        'g-scrolling-carousel',
        'div[data-attrid="images universal"]',
        '.ivg-i',
        'div[data-attrid="video universal"]',
        'div.o6juwe',
    ]

    # Non-organic indicators in snippet text (English, Amharic, and Oromo)
    AD_LABELS = {
        'sponsored',
        'ad',
        'ads',
        'ማስታወቂያ',
        'beeksisa',
        'beeksisaa',
    }
    AD_PATTERN = re.compile(r'\b(sponsored|ad|ads|ማስታወቂያ|beeksisa|beeksisaa)\b', re.IGNORECASE)

    # Domains to ignore as organic results (Google internal/service URLs)
    IGNORED_HOSTS = {
        'google.com',
        'www.google.com',
        'google.com.et',
        'www.google.com.et',
        'accounts.google.com',
        'support.google.com',
        'policies.google.com',
        'maps.google.com',
        'webcache.googleusercontent.com',
        'translate.google.com',
        'news.google.com',
        'youtube.com',
        'www.youtube.com',
    }

    @classmethod
    def clean_google_url(cls, raw_url: str) -> Optional[str]:
        """
        Extract destination URL if wrapped in Google redirect (/url?q=... or /url?url=...).
        Returns cleaned absolute HTTP/HTTPS URL or None if internal/invalid.
        """
        if not raw_url:
            return None

        # Google redirect handler: /url?q=https://example.com&sa=U... or /url?url=...
        if raw_url.startswith('/url?'):
            parsed = urllib.parse.urlparse(raw_url)
            query_params = urllib.parse.parse_qs(parsed.query)
            target = query_params.get('q', [None])[0] or query_params.get('url', [None])[0]
            if target:
                raw_url = target

        if not raw_url.startswith(('http://', 'https://')):
            return None

        # Strip URL fragments
        raw_url = raw_url.split('#')[0]

        parsed_target = urllib.parse.urlparse(raw_url)
        hostname = (parsed_target.hostname or '').lower()

        # Filter out Google internal hostnames
        if hostname in cls.IGNORED_HOSTS or hostname.endswith('.google.com') or hostname.endswith('.google.com.et'):
            return None

        return raw_url

    @classmethod
    def normalize_domain(cls, url_or_domain: str) -> str:
        """
        Normalize a website URL or domain into a clean canonical hostname for matching.
        E.g. 'https://www.addisinsight.net/path/' -> 'addisinsight.net'
        """
        if not url_or_domain:
            return ''

        text = url_or_domain.strip().lower()
        if not text.startswith(('http://', 'https://')):
            text = f"https://{text}"

        parsed = urllib.parse.urlparse(text)
        host = (parsed.hostname or '').lower().strip()
        if host.startswith('www.'):
            host = host[4:]
        host = host.split(':')[0].rstrip('.')
        return host

    @classmethod
    def domains_match(cls, candidate_url: str, target_domain: str) -> bool:
        """
        Check if a candidate URL matches the target website domain or subdomain.
        """
        if not candidate_url or not target_domain:
            return False

        candidate_norm = cls.normalize_domain(candidate_url)
        target_norm = cls.normalize_domain(target_domain)

        if not candidate_norm or not target_norm:
            return False

        return (
            candidate_norm == target_norm
            or candidate_norm.endswith(f".{target_norm}")
            or target_norm.endswith(f".{candidate_norm}")
        )

    @classmethod
    def validate_serp_response(cls, html: str) -> Tuple[bool, Optional[str]]:
        """
        Validate whether HTTP response contains a legitimate Google SERP structure
        rather than a consent screen, CAPTCHA, bot block, or malformed/unexpected HTML.
        Returns (is_valid, error_message).
        """
        if not html or not html.strip():
            return False, "Empty SERP HTML received."

        html_lower = html.lower()

        # 1. Detect Google Bot Block / CAPTCHA / Unusual Traffic
        if (
            "detected unusual traffic" in html_lower
            or 'id="captcha-form"' in html
            or 'recaptcha' in html_lower
            or '/sorry/index' in html_lower
            or "unusual traffic from your computer network" in html_lower
        ):
            return False, "Google automated query block / CAPTCHA detected."

        # 2. Detect Google Cookie Consent / Interstitial
        if (
            "consent.google.com" in html_lower
            or "before you continue to google" in html_lower
            or "consent-bump" in html_lower
            or 'action="https://consent.google.com' in html
            or 'id="cookiebubble"' in html_lower
        ):
            return False, "Google cookie consent interstitial returned instead of SERP."

        # 3. Detect Rate Limit / 429 indicators
        if "rate limit" in html_lower and "google" in html_lower:
            return False, "Google search rate limit response received."

        # 4. Check for valid Google SERP landmarks or valid zero-result indicators
        has_serp_landmarks = any(
            marker in html for marker in (
                'id="search"',
                'id="rso"',
                'id="center_col"',
                'id="rcnt"',
                'id="res"',
                'class="g"',
                'class="MjjYud"',
                'data-sokoban-container',
                'id="taw"',
                'id="tads"',
            )
        ) or (('<h3>' in html_lower or '<h3 ' in html_lower) and '<a' in html_lower)

        has_query_form = (
            ('<form' in html_lower and 'action="/search"' in html_lower)
            or 'name="q"' in html
        )

        has_no_results_marker = any(
            marker in html for marker in (
                "did not match any documents",
                "ምንም ውጤት አልተገኘም",
                "wanta walsimatu homaa hin arganne",
                "No results found for",
            )
        )

        if not (has_serp_landmarks or (has_query_form and has_no_results_marker)):
            return False, "Malformed or unexpected HTML: missing Google SERP landmarks."

        return True, None

    @classmethod
    def parse_organic_results(cls, html: str) -> List[Tuple[str, str]]:
        """
        Parse all organic (URL, title) entries from Google SERP HTML in ranking order.
        Filters ads, navigation, PAA, and non-organic widgets.
        """
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # 1. Remove obvious ad, PAA, knowledge panel, and non-organic containers from the DOM
        for selector in cls.NON_ORGANIC_CONTAINERS:
            for el in soup.select(selector):
                el.decompose()

        # Decompose any elements containing explicit ad labels
        for ad_el in soup.find_all(attrs={'aria-label': re.compile(r'^(Ads|Sponsored|ማስታወቂያ|Beeksisa)', re.I)}):
            ad_el.decompose()

        results: List[Tuple[str, str]] = []
        seen_urls = set()

        # 2. Strategy A: Standard Google organic containers (div.g, div.MjjYud, div[data-sokoban-container])
        containers = soup.select('div#rso div.g, div#rso div[data-sokoban-container], div#rso div.MjjYud, div.g, div[data-sokoban-container], div.MjjYud')

        for container in containers:
            # Check if container has ad badges or text
            text_preview = container.get_text(separator=' ', strip=True)
            if cls.AD_PATTERN.search(text_preview[:80]):
                continue

            # Find main ranking link with title
            link = container.find('a', href=True)
            if not link:
                continue

            clean_url = cls.clean_google_url(link['href'])
            if not clean_url or clean_url in seen_urls:
                continue

            # Extract title: prefer h3, fallback to link text
            h3 = container.find('h3')
            title = h3.get_text(strip=True) if h3 else link.get_text(strip=True)

            if clean_url and title:
                seen_urls.add(clean_url)
                results.append((clean_url, title))

        # 3. Strategy B (Fallback): If standard containers yielded 0 results, find all anchor tags wrapping h3
        if not results:
            for a_tag in soup.find_all('a', href=True):
                h3 = a_tag.find('h3')
                if not h3:
                    continue

                parent_text = (a_tag.parent.get_text(separator=' ', strip=True) if a_tag.parent else '')[:80]
                if cls.AD_PATTERN.search(parent_text):
                    continue

                clean_url = cls.clean_google_url(a_tag['href'])
                if not clean_url or clean_url in seen_urls:
                    continue

                title = h3.get_text(strip=True)
                if clean_url and title:
                    seen_urls.add(clean_url)
                    results.append((clean_url, title))

        return results

    @classmethod
    def parse_google_serp(cls, html: str, target_website: str) -> SerpResult:
        """
        Find position and metadata of target website in Google Ethiopia SERP.
        Returns SerpResult with position 1-100 if found, or None with 'not_found' status.
        If HTML is invalid, blocked, or malformed, returns 'error' status.
        """
        is_valid, validation_error = cls.validate_serp_response(html)
        if not is_valid:
            return SerpResult(
                position=None,
                url=None,
                title=None,
                status=RankingResultStatus.ERROR,
                error_message=validation_error or "SERP validation failed."
            )

        organic_items = cls.parse_organic_results(html)
        target_norm = cls.normalize_domain(target_website)

        for rank_idx, (url, title) in enumerate(organic_items, start=1):
            if rank_idx > 100:
                break
            if cls.domains_match(url, target_norm):
                return SerpResult(
                    position=rank_idx,
                    url=url,
                    title=title,
                    status=RankingResultStatus.FOUND,
                    total_organic_found=len(organic_items)
                )

        return SerpResult(
            position=None,
            url=None,
            title=None,
            status=RankingResultStatus.NOT_FOUND,
            total_organic_found=len(organic_items)
        )


class GoogleEtSerpClient:
    """
    Dedicated client for fetching SERP pages from Google Ethiopia (google.com.et).
    Enforces safe network boundaries, configurable politeness delays, explicit timeouts,
    and bounded retries.
    """

    def __init__(
        self,
        search_domain: str = 'google.com.et',
        timeout_seconds: float = 15.0,
        connect_timeout: float = 5.0,
        read_timeout: float = 10.0,
        write_timeout: float = 5.0,
        politeness_delay: float = 0.5,
        max_retries: int = 2
    ):
        self.search_domain = search_domain.lower().strip()
        if self.search_domain not in APPROVED_GOOGLE_HOSTS:
            raise ValueError(f"Target search domain '{search_domain}' is not in approved Google hosts.")

        self.timeout_seconds = timeout_seconds
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.politeness_delay = politeness_delay
        self.max_retries = max_retries

    def build_search_url(
        self,
        keyword: str,
        language: str = 'en',
        num_results: int = 100
    ) -> str:
        """
        Build fully-qualified Google Ethiopia search URL with correct query encoding.
        Supports English ('en'), Amharic ('am'), and Oromo ('om') with exact UTF-8 preservation.
        """
        clean_keyword = keyword.strip()
        lang_code = language.lower().strip() if language else 'en'

        # Google hl: 'am' for Amharic, 'om' for Oromo, 'en' for English
        if lang_code in (Language.AM, 'am'):
            hl = 'am'
        elif lang_code in (Language.OM, 'om'):
            hl = 'om'
        else:
            hl = 'en'

        params = {
            'q': clean_keyword,
            'hl': hl,
            'gl': 'et',       # Ethiopia country target
            'pws': '0',       # Disable personalized results
            'num': str(min(num_results, 100)),
        }
        encoded_query = urllib.parse.urlencode(params, encoding='utf-8')
        host = self.search_domain
        if not host.startswith('www.'):
            host = f"www.{host}"
        return f"https://{host}/search?{encoded_query}"

    def fetch_serp(
        self,
        keyword: str,
        language: str = 'en',
        device: str = 'desktop'
    ) -> str:
        """
        Fetch raw Google Ethiopia SERP HTML for a keyword.
        Applies retry with exponential backoff on transient network and rate-limit errors.
        """
        url = self.build_search_url(keyword, language=language)
        is_mobile = (device == Device.MOBILE)
        ua = DEFAULT_MOBILE_UA if is_mobile else DEFAULT_DESKTOP_UA

        lang_code = language.lower().strip() if language else 'en'
        if lang_code in (Language.AM, 'am'):
            accept_lang = "am,en;q=0.9,en-US;q=0.8"
        elif lang_code in (Language.OM, 'om'):
            accept_lang = "om,en;q=0.9,en-US;q=0.8"
        else:
            accept_lang = "en-US,en;q=0.9,am;q=0.8,om;q=0.7"

        headers = {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': accept_lang,
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        }
        if is_mobile:
            headers['Sec-CH-UA-Mobile'] = '?1'
            headers['Sec-CH-UA-Platform'] = '"Android"'
        else:
            headers['Sec-CH-UA-Mobile'] = '?0'
            headers['Sec-CH-UA-Platform'] = '"Windows"'

        client_timeout = httpx.Timeout(
            timeout=self.timeout_seconds,
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=self.write_timeout,
        )

        last_error = None
        for attempt in range(self.max_retries + 1):
            if attempt > 0 and self.politeness_delay > 0:
                backoff = self.politeness_delay * (2 ** (attempt - 1))
                time.sleep(backoff)

            try:
                with httpx.Client(
                    headers=headers,
                    timeout=client_timeout,
                    follow_redirects=True
                ) as client:
                    response = client.get(url)

                    if response.status_code == 200:
                        return response.text
                    elif response.status_code in (429, 503):
                        logger.warning(
                            f"[RankTracker] Rate limited (HTTP {response.status_code}) on Google search for '{keyword}'."
                        )
                        last_error = f"Google rate limit (HTTP {response.status_code})"
                        continue
                    else:
                        response.raise_for_status()

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning(
                    f"[RankTracker] Network/timeout error fetching SERP (attempt {attempt + 1}/{self.max_retries + 1}): {exc}"
                )
                last_error = str(exc)
            except Exception as exc:
                logger.error(f"[RankTracker] Unexpected error fetching SERP: {exc}")
                raise

        raise RuntimeError(f"Failed to fetch SERP for '{keyword}' after {self.max_retries + 1} attempts: {last_error}")


class RankTrackerService:
    """
    Main service orchestrating Google Ethiopia rank tracking, snapshot storage,
    position change calculations, and batch check jobs.
    """

    def __init__(self, serp_client: Optional[GoogleEtSerpClient] = None):
        self.serp_client = serp_client or GoogleEtSerpClient()

    def check_keyword(self, keyword: Keyword) -> KeywordRanking:
        """
        Execute SERP check for a single keyword against google.com.et and persist RankingSnapshot.
        Guarantees isolation: failures are recorded as error snapshots rather than throwing fatal exceptions.
        """
        now = timezone.now()
        target_website = keyword.project.website_url

        try:
            html = self.serp_client.fetch_serp(
                keyword=keyword.keyword,
                language=keyword.language,
                device=keyword.device
            )
            serp_result = SerpParser.parse_google_serp(html, target_website)
        except Exception as exc:
            logger.error(f"[RankTracker] Check failed for keyword #{keyword.id} ('{keyword.keyword}'): {exc}")
            serp_result = SerpResult(
                position=None,
                url=None,
                title=None,
                status=RankingResultStatus.ERROR,
                error_message=str(exc)[:500]
            )

        with transaction.atomic():
            snapshot, _ = KeywordRanking.objects.update_or_create(
                keyword=keyword,
                search_engine=keyword.search_engine,
                country=keyword.country,
                language=keyword.language,
                device=keyword.device,
                recorded_at=now,
                defaults={
                    'position': serp_result.position,
                    'ranking_url': serp_result.url,
                    'title': serp_result.title or '',
                    'result_status': serp_result.status,
                    'search_domain': keyword.search_domain or 'google.com.et',
                    'error_message': serp_result.error_message,
                }
            )

        return snapshot

    def check_project_keywords(
        self,
        project,
        job: Optional[RankCheckJob] = None
    ) -> List[KeywordRanking]:
        """
        Run rank checks for all active keywords in a project.
        Updates RankCheckJob progress incrementally with error isolation and politeness pacing.
        """
        active_keywords = list(project.keywords.filter(is_active=True).order_by('created_at'))
        total = len(active_keywords)

        if job:
            job.total_keywords = total
            job.status = RankCheckJobStatus.RUNNING
            job.started_at = timezone.now()
            job.save(update_fields=['total_keywords', 'status', 'started_at', 'updated_at'])

        snapshots: List[KeywordRanking] = []
        completed_count = 0
        failed_count = 0

        for idx, kw in enumerate(active_keywords):
            if idx > 0 and self.serp_client.politeness_delay > 0:
                time.sleep(self.serp_client.politeness_delay)

            try:
                snapshot = self.check_keyword(kw)
                snapshots.append(snapshot)
                if snapshot.result_status == RankingResultStatus.ERROR:
                    failed_count += 1
                else:
                    completed_count += 1
            except Exception as e:
                logger.error(f"[RankTracker] Keyword #{kw.id} crashed check: {e}")
                failed_count += 1
            finally:
                if job:
                    job.completed_keywords = completed_count
                    job.failed_keywords = failed_count
                    job.save(update_fields=['completed_keywords', 'failed_keywords', 'updated_at'])

        if job:
            if total == 0:
                job.status = RankCheckJobStatus.COMPLETED
            elif failed_count == total:
                job.status = RankCheckJobStatus.FAILED
                job.error_message = "All keyword ranking checks failed."
            elif failed_count > 0:
                job.status = RankCheckJobStatus.PARTIAL_FAILURE
                job.error_message = f"{failed_count} of {total} keyword checks failed."
            else:
                job.status = RankCheckJobStatus.COMPLETED
            job.completed_at = timezone.now()
            job.save(update_fields=['status', 'completed_at', 'error_message', 'updated_at'])

        return snapshots

    @classmethod
    def calculate_position_metrics(cls, keyword: Keyword) -> Dict[str, Any]:
        """
        Compute latest position, previous position, and delta metrics for a keyword.
        Examples:
        - Current: 5, Previous: 8 -> change: +3 (improved)
        - Current: 8, Previous: 5 -> change: -3 (declined)
        - Current: 20, Previous: None -> change: None, change_status: 'entered'
        - Current: None, Previous: 20 -> change: None, change_status: 'dropped'
        - Current: None, Previous: None -> change: None, change_status: 'not_found'
        """
        latest_rankings = list(keyword.rankings.order_by('-recorded_at')[:2])

        if not latest_rankings:
            return {
                'current_position': None,
                'previous_position': None,
                'change': None,
                'change_status': 'new',
                'ranking_url': None,
                'title': '',
                'last_checked_at': None,
                'result_status': 'not_checked',
            }

        current = latest_rankings[0]
        previous = latest_rankings[1] if len(latest_rankings) > 1 else None

        curr_pos = current.position
        prev_pos = previous.position if previous else None

        change = None
        change_status = 'new'

        if previous is None:
            if curr_pos is not None:
                change_status = 'entered'
            else:
                change_status = 'not_found'
        else:
            if curr_pos is not None and prev_pos is not None:
                # Rank 5 is better than Rank 8 -> change is +3
                change = prev_pos - curr_pos
                if change > 0:
                    change_status = 'improved'
                elif change < 0:
                    change_status = 'declined'
                else:
                    change_status = 'unchanged'
            elif curr_pos is not None and prev_pos is None:
                change_status = 'entered'
            elif curr_pos is None and prev_pos is not None:
                change_status = 'dropped'
            else:
                change_status = 'not_found'

        return {
            'current_position': curr_pos,
            'previous_position': prev_pos,
            'change': change,
            'change_status': change_status,
            'ranking_url': current.ranking_url,
            'title': current.title,
            'last_checked_at': current.recorded_at,
            'result_status': current.result_status,
        }

    @classmethod
    def get_project_ranking_summary(cls, project) -> List[Dict[str, Any]]:
        """
        Generate aggregate ranking summary for all keywords in a project.
        """
        keywords = project.keywords.all().order_by('-created_at')
        summary = []
        for kw in keywords:
            metrics = cls.calculate_position_metrics(kw)
            summary.append({
                'keyword_id': kw.id,
                'keyword': kw.keyword,
                'search_engine': kw.search_engine,
                'search_domain': kw.search_domain,
                'country': kw.country,
                'language': kw.language,
                'device': kw.device,
                'is_active': kw.is_active,
                'created_at': kw.created_at,
                **metrics,
            })
        return summary
