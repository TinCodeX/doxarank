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
    Resilient Google SERP HTML parser.
    Extracts organic results while filtering ads, sponsored elements, knowledge panels,
    featured snippets, and related question blocks.
    """

    # Elements and CSS identifiers that represent non-organic content
    NON_ORGANIC_CONTAINERS = [
        '#tads',
        '#bottomads',
        'div[data-text-ad]',
        '.kp-wholepage',
        '.knowledge-panel',
        '.osrp-blk',
        '.related-question-pair',
        'div[data-initq]',
        '#extrares',
        '.commercial-unit-desktop-top',
        '.commercial-unit-desktop-rhs',
    ]

    # Non-organic indicators in snippet text (English and Amharic)
    AD_LABELS = {
        'sponsored',
        'ad',
        'ads',
        'ማስታወቂያ',
    }

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
        Extract destination URL if wrapped in Google redirect (/url?q=...).
        Returns cleaned absolute HTTP/HTTPS URL or None if internal/invalid.
        """
        if not raw_url:
            return None

        # Google redirect handler: /url?q=https://example.com&sa=U...
        if raw_url.startswith('/url?'):
            parsed = urllib.parse.urlparse(raw_url)
            query_params = urllib.parse.parse_qs(parsed.query)
            target = query_params.get('q', [None])[0]
            if target:
                raw_url = target

        if not raw_url.startswith(('http://', 'https://')):
            return None

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
        host = (parsed.hostname or '').lower()
        if host.startswith('www.'):
            host = host[4:]
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
    def parse_organic_results(cls, html: str) -> List[Tuple[str, str]]:
        """
        Parse all organic (URL, title) entries from Google SERP HTML in ranking order.
        Filters ads, navigation, and non-organic widgets.
        """
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # 1. Remove obvious ad and non-organic containers from the DOM
        for selector in cls.NON_ORGANIC_CONTAINERS:
            for el in soup.select(selector):
                el.decompose()

        results: List[Tuple[str, str]] = []
        seen_urls = set()

        # 2. Strategy A: Standard Google organic containers (div.g, div.MjjYud, div[data-sokoban-container])
        containers = soup.select('div.g, div[data-sokoban-container], div.MjjYud')

        for container in containers:
            # Check if container has ad badges or text
            text_preview = container.get_text(separator=' ', strip=True).lower()
            if any(label in text_preview[:50] for label in cls.AD_LABELS):
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
        """
        if not html:
            return SerpResult(
                position=None,
                url=None,
                title=None,
                status=RankingResultStatus.ERROR,
                error_message="Empty SERP HTML received."
            )

        # Detect Google bot block / CAPTCHA page
        if "detected unusual traffic" in html or "id=\"captcha-form\"" in html or "recaptcha" in html:
            return SerpResult(
                position=None,
                url=None,
                title=None,
                status=RankingResultStatus.ERROR,
                error_message="Google CAPTCHA / automated query block detected."
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
    Enforces safe network boundaries, configurable politeness delays, and bounded retries.
    """

    def __init__(
        self,
        search_domain: str = 'google.com.et',
        timeout_seconds: float = 15.0,
        politeness_delay: float = 0.5,
        max_retries: int = 2
    ):
        self.search_domain = search_domain.lower().strip()
        if self.search_domain not in APPROVED_GOOGLE_HOSTS:
            raise ValueError(f"Target search domain '{search_domain}' is not in approved Google hosts.")

        self.timeout_seconds = timeout_seconds
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
        Amharic UTF-8 keywords are safely encoded without transliteration.
        """
        # Google hl: 'am' for Amharic, 'en' for English
        hl = 'am' if language == Language.AM else 'en'
        params = {
            'q': keyword.strip(),
            'hl': hl,
            'gl': 'et',       # Ethiopia country target
            'pws': '0',       # Disable personalized results
            'num': str(min(num_results, 100)),
        }
        encoded_query = urllib.parse.urlencode(params)
        return f"https://www.{self.search_domain}/search?{encoded_query}"

    def fetch_serp(
        self,
        keyword: str,
        language: str = 'en',
        device: str = 'desktop'
    ) -> str:
        """
        Fetch raw Google Ethiopia SERP HTML for a keyword.
        Applies retry with exponential backoff on transient errors.
        """
        url = self.build_search_url(keyword, language=language)
        ua = DEFAULT_MOBILE_UA if device == Device.MOBILE else DEFAULT_DESKTOP_UA
        accept_lang = "am,en;q=0.9,en-US;q=0.8" if language == Language.AM else "en-US,en;q=0.9,am;q=0.8"

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

        last_error = None
        for attempt in range(self.max_retries + 1):
            if attempt > 0 and self.politeness_delay > 0:
                time.sleep(self.politeness_delay * (2 ** (attempt - 1)))

            try:
                with httpx.Client(
                    headers=headers,
                    timeout=self.timeout_seconds,
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
                error_message=str(exc)[:1000]
            )

        with transaction.atomic():
            snapshot = KeywordRanking.objects.create(
                keyword=keyword,
                position=serp_result.position,
                ranking_url=serp_result.url,
                title=serp_result.title or '',
                result_status=serp_result.status,
                search_engine=keyword.search_engine,
                search_domain=keyword.search_domain or 'google.com.et',
                country=keyword.country,
                language=keyword.language,
                device=keyword.device,
                error_message=serp_result.error_message,
                recorded_at=now,
            )

        return snapshot

    def check_project_keywords(
        self,
        project,
        job: Optional[RankCheckJob] = None
    ) -> List[KeywordRanking]:
        """
        Run rank checks for all active keywords in a project.
        Updates RankCheckJob progress incrementally with error isolation.
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

        for kw in active_keywords:
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
