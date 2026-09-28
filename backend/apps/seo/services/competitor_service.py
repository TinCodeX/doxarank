"""
Competitor SERP Snapshot Service for DoxaRank (Original SRS Task: Weekly Competitor Snapshots).

Enables projects with an Agency subscription to track competitor SERP visibility
against Google Ethiopia (google.com.et) for tracked keywords.

Reuses:
- GoogleEtSerpClient (safe Google Ethiopia SERP fetching)
- SerpParser (organic extraction, domain normalization and matching)
- PlanEntitlementService (FeatureCode.COMPETITOR_SNAPSHOTS gating)
"""

import ipaddress
import logging
import re
import time
import urllib.parse
from typing import Dict, List, Optional, Set, Tuple, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.projects.models import Project
from apps.seo.models import (
    Keyword,
    Competitor,
    CompetitorSnapshot,
    CompetitorSnapshotJob,
    CompetitorSnapshotJobStatus,
    RankingResultStatus,
    Device,
    Language,
    Country,
)
from apps.seo.services.rank_tracker import (
    GoogleEtSerpClient,
    SerpParser,
    APPROVED_GOOGLE_HOSTS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSRF & DOMAIN VALIDATION PROTECTION
# ---------------------------------------------------------------------------

BLOCKED_IP_NETWORKS: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    # IPv4 loopback
    ipaddress.IPv4Network('127.0.0.0/8'),
    # IPv4 private (RFC1918)
    ipaddress.IPv4Network('10.0.0.0/8'),
    ipaddress.IPv4Network('172.16.0.0/12'),
    ipaddress.IPv4Network('192.168.0.0/16'),
    # IPv4 link-local & cloud metadata
    ipaddress.IPv4Network('169.254.0.0/16'),
    ipaddress.IPv4Network('169.254.169.254/32'),
    # IPv4 multicast / reserved / current
    ipaddress.IPv4Network('224.0.0.0/4'),
    ipaddress.IPv4Network('240.0.0.0/4'),
    ipaddress.IPv4Network('0.0.0.0/8'),
    # IPv6 loopback & link-local
    ipaddress.IPv6Network('::1/128'),
    ipaddress.IPv6Network('fe80::/10'),
    ipaddress.IPv6Network('fc00::/7'),
    ipaddress.IPv6Network('ff00::/8'),
    ipaddress.IPv6Network('::/128'),
    ipaddress.IPv6Network('::ffff:127.0.0.0/104'),
    ipaddress.IPv6Network('::ffff:10.0.0.0/104'),
    ipaddress.IPv6Network('::ffff:172.16.0.0/108'),
    ipaddress.IPv6Network('::ffff:192.168.0.0/112'),
]

BLOCKED_HOSTNAMES: Set[str] = {
    'localhost',
    'localhost.localdomain',
    'metadata.google.internal',
    'metadata.google',
    'instance-data',
    'metadata',
    '169.254.169.254',
    'fd00:ec2::254',
}

DANGEROUS_SCHEMES: Set[str] = {
    'file', 'ftp', 'gopher', 'data', 'javascript', 'vbscript', 'ldap', 'dict', 'sftp', 'ssh'
}


def validate_and_normalize_competitor_domain(
    domain_or_url: str,
    project: Optional[Project] = None
) -> Tuple[str, str]:
    """
    Validate and normalize a user-provided competitor domain or URL.

    Security & Validation checks:
    1. Rejects dangerous URL schemes (ftp, file, javascript, etc.)
    2. Extracts clean canonical domain name (lowercase, no www, no port, no path)
    3. Rejects localhost, private IPv4/IPv6 ranges, link-local, cloud metadata
    4. Enforces valid FQDN structure (must contain at least one dot, valid TLD/label chars)
    5. Prevents a project from tracking its own website as a competitor

    Returns:
        (canonical_domain, canonical_website_url)
        e.g. ("shega.co", "https://shega.co")
    """
    if not domain_or_url or not isinstance(domain_or_url, str):
        raise ValidationError("Competitor domain or URL must be a non-empty string.")

    raw = domain_or_url.strip()
    if len(raw) > 255:
        raise ValidationError("Competitor domain or URL cannot exceed 255 characters.")

    # Check for dangerous schemes
    raw_lower = raw.lower()
    for scheme in DANGEROUS_SCHEMES:
        if raw_lower.startswith(f"{scheme}:") or raw_lower.startswith(f"{scheme}/"):
            raise ValidationError(f"Invalid URL scheme '{scheme}'. Only HTTP/HTTPS domains are permitted.")

    # Add protocol if missing to enable urlparse
    if not raw_lower.startswith(('http://', 'https://')):
        url_for_parsing = f"https://{raw}"
    else:
        url_for_parsing = raw

    try:
        parsed = urllib.parse.urlparse(url_for_parsing)
    except Exception as exc:
        raise ValidationError(f"Invalid domain format: {exc}")

    if parsed.scheme.lower() not in ('http', 'https'):
        raise ValidationError(f"Scheme '{parsed.scheme}' is not permitted. Only HTTP/HTTPS domains are allowed.")

    hostname = (parsed.hostname or '').strip().lower().rstrip('.')
    if not hostname:
        raise ValidationError("Could not extract a valid domain name from the provided input.")

    # Check blocked hostnames
    if hostname in BLOCKED_HOSTNAMES:
        raise ValidationError(f"Host '{hostname}' is not a permitted public competitor domain.")

    # Check if host is an IP address
    try:
        ip_obj = ipaddress.ip_address(hostname)
        for net in BLOCKED_IP_NETWORKS:
            if ip_obj in net:
                raise ValidationError(f"IP address '{hostname}' is in a private, loopback, or reserved network.")
    except ValueError:
        # Not a raw IP address; continue domain validation
        pass

    # Domain structure check: must have at least one dot (e.g. example.com, shega.co)
    if '.' not in hostname:
        raise ValidationError(f"Domain '{hostname}' is not a valid fully-qualified domain name (must contain a dot).")

    # Reject invalid characters
    label_pattern = re.compile(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$', re.IGNORECASE)
    labels = hostname.split('.')
    for label in labels:
        if not label or not label_pattern.match(label):
            raise ValidationError(f"Domain '{hostname}' contains invalid DNS labels.")

    # Strip 'www.' prefix for canonical domain representation
    canonical_domain = hostname[4:] if hostname.startswith('www.') else hostname

    # If project is provided, verify competitor is not the project's own domain
    if project and project.website_url:
        proj_norm = SerpParser.normalize_domain(project.website_url)
        if canonical_domain == proj_norm:
            raise ValidationError(f"A project cannot add its own domain ('{canonical_domain}') as a competitor.")

    canonical_website_url = f"https://{canonical_domain}"
    return canonical_domain, canonical_website_url


# ---------------------------------------------------------------------------
# COMPETITOR SNAPSHOT SERVICE
# ---------------------------------------------------------------------------

class CompetitorSnapshotService:
    """
    Main service coordinating competitor SERP snapshots against Google Ethiopia (google.com.et).

    Execution flow for a project:
    1. Load all active project keywords and active competitors.
    2. For each keyword, fetch google.com.et SERP (single Google query per keyword).
    3. Parse top 100 organic results using SerpParser.
    4. Scan organic results for each competitor's domain.
    5. Save CompetitorSnapshot records:
       - position (1-100) if found, or None with NOT_FOUND status if outside top 100.
       - URL and title found in SERP.
    6. Transition CompetitorSnapshotJob state cleanly (PENDING -> RUNNING -> COMPLETED / PARTIAL_FAILURE).
    """

    def __init__(self, serp_client: Optional[GoogleEtSerpClient] = None):
        self.serp_client = serp_client or GoogleEtSerpClient(politeness_delay=0.5)

    def run_snapshot_for_project(
        self,
        project_id: int,
        job_id: Optional[int] = None
    ) -> CompetitorSnapshotJob:
        """
        Execute competitor SERP snapshots for all active keywords and competitors in a project.
        """
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            logger.error(f"[CompetitorSnapshot] Project #{project_id} not found.")
            if job_id:
                try:
                    job = CompetitorSnapshotJob.objects.get(id=job_id)
                    job.status = CompetitorSnapshotJobStatus.FAILED
                    job.error_message = f"Project #{project_id} does not exist."
                    job.completed_at = timezone.now()
                    job.save(update_fields=['status', 'error_message', 'completed_at'])
                    return job
                except CompetitorSnapshotJob.DoesNotExist:
                    pass
            raise

        # Retrieve or create snapshot job
        if job_id:
            try:
                job = CompetitorSnapshotJob.objects.get(id=job_id)
            except CompetitorSnapshotJob.DoesNotExist:
                job = CompetitorSnapshotJob.objects.create(
                    project=project,
                    trigger='manual',
                    status=CompetitorSnapshotJobStatus.PENDING,
                )
        else:
            job = CompetitorSnapshotJob.objects.create(
                project=project,
                trigger='manual',
                status=CompetitorSnapshotJobStatus.PENDING,
            )

        keywords = list(project.keywords.filter(is_active=True).order_by('id'))
        competitors = list(project.competitors.filter(is_active=True).order_by('id'))

        job.total_keywords = len(keywords)
        job.status = CompetitorSnapshotJobStatus.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=['total_keywords', 'status', 'started_at'])

        if not competitors:
            job.status = CompetitorSnapshotJobStatus.COMPLETED
            job.completed_at = timezone.now()
            job.error_message = "No active competitors found for this project."
            job.save(update_fields=['status', 'completed_at', 'error_message'])
            logger.info(f"[CompetitorSnapshot] Project #{project_id} has 0 active competitors. Job #{job.id} concluded.")
            return job

        if not keywords:
            job.status = CompetitorSnapshotJobStatus.COMPLETED
            job.completed_at = timezone.now()
            job.error_message = "No active keywords found for this project."
            job.save(update_fields=['status', 'completed_at', 'error_message'])
            logger.info(f"[CompetitorSnapshot] Project #{project_id} has 0 active keywords. Job #{job.id} concluded.")
            return job

        completed_count = 0
        failed_count = 0

        for kw_idx, keyword in enumerate(keywords):
            try:
                # 1. Fetch Google Ethiopia SERP for this keyword
                html = self.serp_client.fetch_serp(
                    keyword=keyword.keyword,
                    language=keyword.language,
                    device=keyword.device
                )

                # Check for Google bot block / CAPTCHA
                if "detected unusual traffic" in html or "id=\"captcha-form\"" in html or "recaptcha" in html:
                    raise RuntimeError("Google CAPTCHA / automated query block detected.")

                # 2. Extract organic results in ranking order
                organic_items = SerpParser.parse_organic_results(html)

                # 3. For each active competitor, evaluate rank position
                with transaction.atomic():
                    for competitor in competitors:
                        found_position: Optional[int] = None
                        found_url: str = ''
                        found_title: str = ''

                        for rank_idx, (url, title) in enumerate(organic_items, start=1):
                            if rank_idx > 100:
                                break
                            if SerpParser.domains_match(url, competitor.domain):
                                found_position = rank_idx
                                found_url = url
                                found_title = title or ''
                                break

                        result_status = (
                            RankingResultStatus.FOUND
                            if found_position is not None
                            else RankingResultStatus.NOT_FOUND
                        )

                        CompetitorSnapshot.objects.create(
                            competitor=competitor,
                            project=project,
                            keyword=keyword,
                            snapshot_job=job,
                            position=found_position,
                            ranking_url=found_url,
                            title=found_title,
                            result_status=result_status,
                            search_engine=keyword.search_engine or 'google',
                            search_domain=keyword.search_domain or 'google.com.et',
                            country=keyword.country or Country.ET,
                            language=keyword.language or Language.EN,
                            device=keyword.device or Device.DESKTOP,
                        )

                completed_count += 1

            except Exception as exc:
                logger.error(
                    f"[CompetitorSnapshot] Failed SERP check for keyword #{keyword.id} ('{keyword.keyword}'): {exc}"
                )
                failed_count += 1

                # Record error snapshots for each competitor so historical record is complete
                with transaction.atomic():
                    for competitor in competitors:
                        CompetitorSnapshot.objects.create(
                            competitor=competitor,
                            project=project,
                            keyword=keyword,
                            snapshot_job=job,
                            position=None,
                            ranking_url='',
                            title='',
                            result_status=RankingResultStatus.ERROR,
                            search_engine=keyword.search_engine or 'google',
                            search_domain=keyword.search_domain or 'google.com.et',
                            country=keyword.country or Country.ET,
                            language=keyword.language or Language.EN,
                            device=keyword.device or Device.DESKTOP,
                            error_message=str(exc)[:1000],
                        )

            # Update job progress periodically
            job.completed_keywords = completed_count
            job.failed_keywords = failed_count
            job.save(update_fields=['completed_keywords', 'failed_keywords'])

            # Polite delay between keywords if more remain
            if kw_idx < len(keywords) - 1:
                time.sleep(0.5)

        # Conclude job status
        if completed_count > 0 and failed_count == 0:
            job.status = CompetitorSnapshotJobStatus.COMPLETED
        elif completed_count > 0 and failed_count > 0:
            job.status = CompetitorSnapshotJobStatus.PARTIAL_FAILURE
        else:
            job.status = CompetitorSnapshotJobStatus.FAILED

        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'completed_at'])

        logger.info(
            f"[CompetitorSnapshot] Job #{job.id} for project #{project_id} finished: "
            f"status={job.status}, completed={completed_count}, failed={failed_count}."
        )
        return job

    @classmethod
    def get_latest_project_snapshots(cls, project_id: int) -> List[Dict[str, Any]]:
        """
        Return the most recent snapshot for each (competitor, keyword) pair in a project.
        Useful for dashboard matrix and competitor comparisons.
        """
        competitors = Competitor.objects.filter(project_id=project_id, is_active=True)
        keywords = Keyword.objects.filter(project_id=project_id, is_active=True)

        results = []
        for competitor in competitors:
            for kw in keywords:
                latest_snap = (
                    CompetitorSnapshot.objects
                    .filter(competitor=competitor, keyword=kw)
                    .order_by('-recorded_at')
                    .first()
                )
                results.append({
                    'competitor_id': competitor.id,
                    'competitor_name': competitor.name,
                    'competitor_domain': competitor.domain,
                    'keyword_id': kw.id,
                    'keyword': kw.keyword,
                    'position': latest_snap.position if latest_snap else None,
                    'ranking_url': latest_snap.ranking_url if latest_snap else '',
                    'title': latest_snap.title if latest_snap else '',
                    'result_status': latest_snap.result_status if latest_snap else 'not_checked',
                    'recorded_at': latest_snap.recorded_at if latest_snap else None,
                    'search_domain': latest_snap.search_domain if latest_snap else 'google.com.et',
                })

        return results
