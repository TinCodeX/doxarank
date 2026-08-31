"""
Deterministic SEO Audit Rule Engine for DoxaRank (Milestone 4, Phase 4.2.2).

Evaluates structured CrawlResult datasets from LiveSiteCrawlerService against
deterministic SEO rules, calculates a standardized 0–100 health score, and
persists findings into SiteAudit and AuditIssue models.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Set
from django.db import transaction
from django.utils import timezone

from apps.projects.models import Project
from apps.seo.models import (
    SiteAudit, AuditIssue, AuditStatus, IssueSeverity
)
from apps.seo.services.live_site_crawler import (
    CrawlResult, PageCrawlResult, LiveSiteCrawlerService
)

logger = logging.getLogger(__name__)

# =============================================================================
# STABLE RULE CODES
# =============================================================================

MISSING_TITLE = "missing_title"
LONG_TITLE = "long_title"
SHORT_TITLE = "short_title"
MISSING_META_DESCRIPTION = "missing_meta_description"
LONG_META_DESCRIPTION = "long_meta_description"
SHORT_META_DESCRIPTION = "short_meta_description"
MISSING_H1 = "missing_h1"
MULTIPLE_H1 = "multiple_h1"
MISSING_IMAGE_ALT = "missing_image_alt"
MISSING_CANONICAL = "missing_canonical"
CANONICAL_MISMATCH = "canonical_mismatch"
BROKEN_INTERNAL_LINK = "broken_internal_link"
REDIRECTING_INTERNAL_LINK = "redirecting_internal_link"
REDIRECT_CHAIN = "redirect_chain"
REDIRECT_LOOP = "redirect_loop"
CRAWL_ERROR = "crawl_error"
SLOW_RESPONSE = "slow_response"
MISSING_STRUCTURED_DATA = "missing_structured_data"

# Standard Thresholds
MAX_TITLE_LENGTH = 60
MIN_TITLE_LENGTH = 10
MAX_META_DESC_LENGTH = 160
MIN_META_DESC_LENGTH = 50
SLOW_RESPONSE_THRESHOLD_MS = 1500.0


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class AuditFinding:
    """Individual SEO issue identified on a crawled URL or sitewide asset."""
    rule_code: str
    severity: str  # 'critical', 'warning', 'notice'
    title: str
    description: str
    page_url: Optional[str] = None
    recommendation: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditResult:
    """Aggregated evaluation result containing site health score and findings."""
    health_score: int
    total_pages_crawled: int
    critical_count: int
    warning_count: int
    notice_count: int
    findings: List[AuditFinding] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "health_score": self.health_score,
            "total_pages_crawled": self.total_pages_crawled,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "notice_count": self.notice_count,
            "findings": [f.to_dict() for f in self.findings],
            "summary": self.summary
        }


# =============================================================================
# SEO AUDIT ENGINE
# =============================================================================

class SEOAuditEngine:
    """
    Deterministic rule-based SEO audit engine.
    Inspects structured CrawlResult facts without AI hallucination.
    """

    def evaluate(self, crawl_result: CrawlResult) -> AuditResult:
        """
        Evaluate all deterministic SEO rules against the crawled pages and crawl errors.
        Returns an AuditResult with calculated health score and individual findings.
        """
        findings: List[AuditFinding] = []
        base_domain = crawl_result.metadata.base_domain

        # 1. Evaluate Crawl Errors (timeouts, socket errors, redirect loops)
        for error in crawl_result.errors:
            if error.error_type == "redirect_loop":
                findings.append(AuditFinding(
                    rule_code=REDIRECT_LOOP,
                    severity=IssueSeverity.CRITICAL,
                    title="Infinite redirect loop detected",
                    description=f"URL '{error.url}' resulted in an infinite redirect loop, preventing search engine indexing.",
                    page_url=error.url,
                    recommendation="Fix server-side or .htaccess rewrite rules to break circular redirect loops.",
                    evidence={"error_type": error.error_type, "message": error.message}
                ))
            elif error.error_type == "robots_disallowed":
                # Intentionally not a site defect, logged for context if needed
                continue
            else:
                findings.append(AuditFinding(
                    rule_code=CRAWL_ERROR,
                    severity=IssueSeverity.CRITICAL,
                    title=f"Crawl error: {error.error_type}",
                    description=f"Failed to fetch '{error.url}': {error.message}",
                    page_url=error.url,
                    recommendation="Verify server DNS, firewall, SSL certificate, and server resource allocation.",
                    evidence={"error_type": error.error_type, "message": error.message}
                ))

        # 2. Evaluate Individual Crawled Pages
        for page in crawl_result.pages:
            self._evaluate_page(page, base_domain, findings)

        # 3. Calculate Severity Counts
        critical_count = sum(1 for f in findings if f.severity == IssueSeverity.CRITICAL)
        warning_count = sum(1 for f in findings if f.severity == IssueSeverity.WARNING)
        notice_count = sum(1 for f in findings if f.severity == IssueSeverity.NOTICE)

        # 4. Calculate Deterministic Health Score (0 - 100)
        health_score = self.calculate_health_score(
            critical_count=critical_count,
            warning_count=warning_count,
            notice_count=notice_count,
            total_pages=len(crawl_result.pages),
            has_errors=bool(crawl_result.errors)
        )

        summary = (
            f"Audit completed for {crawl_result.start_url}. "
            f"Health Score: {health_score}/100. "
            f"Pages evaluated: {len(crawl_result.pages)}. "
            f"Identified {critical_count} critical issue(s), "
            f"{warning_count} warning(s), and {notice_count} notice(s)."
        )

        return AuditResult(
            health_score=health_score,
            total_pages_crawled=len(crawl_result.pages),
            critical_count=critical_count,
            warning_count=warning_count,
            notice_count=notice_count,
            findings=findings,
            summary=summary
        )

    def _evaluate_page(self, page: PageCrawlResult, base_domain: str, findings: List[AuditFinding]) -> None:
        """Evaluate deterministic rules for a single PageCrawlResult."""
        url = page.url
        status_code = page.status_code

        # --- Rule: Broken Internal Link (4xx / 5xx) ---
        if status_code >= 400:
            severity = IssueSeverity.CRITICAL
            title = f"Broken page returning HTTP {status_code}"
            desc = f"The URL '{url}' returned HTTP status code {status_code}."
            rec = "Repair the broken page or configure a 301 redirect to a relevant, working page."
            findings.append(AuditFinding(
                rule_code=BROKEN_INTERNAL_LINK,
                severity=severity,
                title=title,
                description=desc,
                page_url=url,
                recommendation=rec,
                evidence={"status_code": status_code, "final_url": page.final_url}
            ))
            return  # Do not evaluate missing titles/meta on 404/500 error pages

        # --- Rule: Redirect Chain (Length >= 2) ---
        if len(page.redirect_chain) >= 2:
            findings.append(AuditFinding(
                rule_code=REDIRECT_CHAIN,
                severity=IssueSeverity.WARNING,
                title="Multiple HTTP redirect hops in chain",
                description=f"URL '{url}' goes through {len(page.redirect_chain)} redirects before reaching '{page.final_url}'.",
                page_url=url,
                recommendation="Update internal links and server redirects to point directly to the destination URL.",
                evidence={"redirect_chain": page.redirect_chain, "final_url": page.final_url}
            ))

        # --- Rule: Response Speed ---
        if page.response_time_ms > SLOW_RESPONSE_THRESHOLD_MS:
            findings.append(AuditFinding(
                rule_code=SLOW_RESPONSE,
                severity=IssueSeverity.WARNING,
                title=f"Slow server response time ({page.response_time_ms} ms)",
                description=f"Page response time of {page.response_time_ms} ms exceeds recommended threshold of {SLOW_RESPONSE_THRESHOLD_MS} ms.",
                page_url=url,
                recommendation="Optimize database queries, enable server caching (Redis/Varnish), and leverage a CDN.",
                evidence={"response_time_ms": page.response_time_ms, "threshold_ms": SLOW_RESPONSE_THRESHOLD_MS}
            ))

        # --- Rule: Page Title ---
        title = (page.title or "").strip()
        if not title:
            findings.append(AuditFinding(
                rule_code=MISSING_TITLE,
                severity=IssueSeverity.CRITICAL,
                title="Missing HTML page title tag",
                description=f"Page '{url}' does not have a <title> tag.",
                page_url=url,
                recommendation="Add a unique, keyword-rich <title> tag between 10 and 60 characters.",
                evidence={"title": None}
            ))
        else:
            title_len = len(title)
            if title_len > MAX_TITLE_LENGTH:
                findings.append(AuditFinding(
                    rule_code=LONG_TITLE,
                    severity=IssueSeverity.WARNING,
                    title=f"Page title is too long ({title_len} chars)",
                    description=f"Page title '{title[:50]}...' is {title_len} characters long, exceeding the SERP display limit of {MAX_TITLE_LENGTH} characters.",
                    page_url=url,
                    recommendation=f"Shorten the title tag to under {MAX_TITLE_LENGTH} characters to prevent SERP truncation.",
                    evidence={"title": title, "length": title_len, "max_length": MAX_TITLE_LENGTH}
                ))
            elif title_len < MIN_TITLE_LENGTH:
                findings.append(AuditFinding(
                    rule_code=SHORT_TITLE,
                    severity=IssueSeverity.NOTICE,
                    title=f"Page title is too short ({title_len} chars)",
                    description=f"Page title '{title}' is {title_len} characters long, which may not provide sufficient keyword context.",
                    page_url=url,
                    recommendation=f"Expand the title to at least {MIN_TITLE_LENGTH} characters with relevant primary keywords.",
                    evidence={"title": title, "length": title_len, "min_length": MIN_TITLE_LENGTH}
                ))

        # --- Rule: Meta Description ---
        meta_desc = (page.meta_description or "").strip()
        if not meta_desc:
            findings.append(AuditFinding(
                rule_code=MISSING_META_DESCRIPTION,
                severity=IssueSeverity.WARNING,
                title="Missing meta description tag",
                description=f"Page '{url}' does not have a meta description tag.",
                page_url=url,
                recommendation="Add a compelling meta description between 50 and 160 characters to optimize organic click-through rates.",
                evidence={"meta_description": None}
            ))
        else:
            desc_len = len(meta_desc)
            if desc_len > MAX_META_DESC_LENGTH:
                findings.append(AuditFinding(
                    rule_code=LONG_META_DESCRIPTION,
                    severity=IssueSeverity.NOTICE,
                    title=f"Meta description exceeds {MAX_META_DESC_LENGTH} characters",
                    description=f"Meta description is {desc_len} characters long and may be truncated on search result pages.",
                    page_url=url,
                    recommendation=f"Shorten the meta description to under {MAX_META_DESC_LENGTH} characters.",
                    evidence={"meta_description": meta_desc, "length": desc_len, "max_length": MAX_META_DESC_LENGTH}
                ))
            elif desc_len < MIN_META_DESC_LENGTH:
                findings.append(AuditFinding(
                    rule_code=SHORT_META_DESCRIPTION,
                    severity=IssueSeverity.NOTICE,
                    title=f"Meta description is under {MIN_META_DESC_LENGTH} characters",
                    description=f"Meta description is only {desc_len} characters long.",
                    page_url=url,
                    recommendation=f"Expand the meta description to at least {MIN_META_DESC_LENGTH} characters.",
                    evidence={"meta_description": meta_desc, "length": desc_len, "min_length": MIN_META_DESC_LENGTH}
                ))

        # --- Rule: Headings (H1) ---
        h1_headings = page.headings.get("h1", [])
        if len(h1_headings) == 0:
            findings.append(AuditFinding(
                rule_code=MISSING_H1,
                severity=IssueSeverity.CRITICAL,
                title="Missing main H1 heading",
                description=f"Page '{url}' does not contain any <h1> heading element.",
                page_url=url,
                recommendation="Add a single descriptive <h1> heading communicating the primary topic of the page.",
                evidence={"h1_count": 0}
            ))
        elif len(h1_headings) > 1:
            findings.append(AuditFinding(
                rule_code=MULTIPLE_H1,
                severity=IssueSeverity.WARNING,
                title=f"Multiple H1 headings detected ({len(h1_headings)} H1s)",
                description=f"Page '{url}' contains {len(h1_headings)} separate <h1> elements.",
                page_url=url,
                recommendation="Restructure headings to use a single top-level <h1>, and demote secondary headings to <h2>.",
                evidence={"h1_count": len(h1_headings), "h1_headings": h1_headings}
            ))

        # --- Rule: Image Alt Text ---
        if page.images:
            missing_alts = [img for img in page.images if not (img.get("alt") or "").strip()]
            if missing_alts:
                findings.append(AuditFinding(
                    rule_code=MISSING_IMAGE_ALT,
                    severity=IssueSeverity.WARNING,
                    title=f"{len(missing_alts)} image(s) missing alt text",
                    description=f"Found {len(missing_alts)} image(s) without descriptive alt attributes on '{url}'.",
                    page_url=url,
                    recommendation="Add informative, accessible alt text to all image tags.",
                    evidence={"missing_count": len(missing_alts), "images": missing_alts[:5]}
                ))

        # --- Rule: Canonical Tags ---
        canonical = (page.canonical or "").strip()
        if not canonical:
            findings.append(AuditFinding(
                rule_code=MISSING_CANONICAL,
                severity=IssueSeverity.NOTICE,
                title="Missing rel=canonical link tag",
                description=f"Page '{url}' has no canonical link tag defined.",
                page_url=url,
                recommendation="Specify an explicit <link rel='canonical' href='...'> to prevent duplicate content indexing.",
                evidence={"canonical": None}
            ))
        else:
            # Check canonical mismatch or cross-domain
            if not LiveSiteCrawlerService.is_same_domain(canonical, base_domain):
                findings.append(AuditFinding(
                    rule_code=CANONICAL_MISMATCH,
                    severity=IssueSeverity.WARNING,
                    title="Canonical URL points to external domain",
                    description=f"Canonical tag on '{url}' points outside site domain: '{canonical}'.",
                    page_url=url,
                    recommendation="Verify that the cross-domain canonical is intentional and not a configuration error.",
                    evidence={"canonical": canonical, "page_url": url, "base_domain": base_domain}
                ))

        # --- Rule: Structured Data (JSON-LD) ---
        if not page.json_ld:
            findings.append(AuditFinding(
                rule_code=MISSING_STRUCTURED_DATA,
                severity=IssueSeverity.NOTICE,
                title="No structured JSON-LD schema detected",
                description=f"Page '{url}' does not contain any JSON-LD structured data blocks.",
                page_url=url,
                recommendation="Implement Schema.org structured data (e.g. Article, Organization, Product) to earn rich SERP snippets.",
                evidence={"json_ld_count": 0}
            ))

    # =========================================================================
    # HEALTH SCORE CALCULATION
    # =========================================================================

    @staticmethod
    def calculate_health_score(
        critical_count: int,
        warning_count: int,
        notice_count: int,
        total_pages: int,
        has_errors: bool
    ) -> int:
        """
        Calculate a deterministic site health score between 0 and 100.
        Uses a weighted penalty system with graceful scaling.
        """
        if total_pages == 0:
            return 0 if has_errors else 100

        # Weighted penalty:
        # Critical issue: 15 points
        # Warning issue: 5 points
        # Notice issue: 1 point
        raw_penalty = (critical_count * 15) + (warning_count * 5) + (notice_count * 1)

        # Scale penalty based on total page volume to avoid disproportionate penalties on large sites
        if total_pages > 1:
            scale_factor = max(1.0, (total_pages ** 0.5) / 2.0)
            adjusted_penalty = raw_penalty / scale_factor
        else:
            adjusted_penalty = float(raw_penalty)

        score = 100.0 - adjusted_penalty
        return max(0, min(100, int(round(score))))

    # =========================================================================
    # PERSISTENCE (SiteAudit & AuditIssue)
    # =========================================================================

    def persist_audit(
        self,
        project: Project,
        crawl_result: CrawlResult,
        audit: Optional[SiteAudit] = None
    ) -> SiteAudit:
        """
        Evaluate CrawlResult and atomically persist SiteAudit and AuditIssue records.
        Guarantees idempotent deduplication and safe multi-tenant boundaries.
        """
        audit_result = self.evaluate(crawl_result)

        with transaction.atomic():
            # 1. Resolve or create SiteAudit record
            if audit is None:
                site_audit = SiteAudit.objects.create(
                    project=project,
                    status=AuditStatus.RUNNING,
                    started_at=timezone.now()
                )
            else:
                site_audit = audit

            site_audit.status = AuditStatus.COMPLETED
            site_audit.score = audit_result.health_score
            site_audit.completed_at = timezone.now()
            site_audit.error_message = None
            site_audit.save(update_fields=['status', 'score', 'completed_at', 'error_message', 'updated_at'])

            # 2. Clear old issues for this audit run (idempotent overwrite)
            site_audit.issues.all().delete()

            # 3. Bulk create AuditIssue records
            issues_to_create = []
            seen_issue_keys: Set[tuple] = set()

            for finding in audit_result.findings:
                key = (finding.rule_code, finding.page_url or "")
                if key in seen_issue_keys:
                    continue
                seen_issue_keys.add(key)

                issues_to_create.append(AuditIssue(
                    audit=site_audit,
                    issue_type=finding.rule_code,
                    severity=finding.severity,
                    title=finding.title[:255],
                    description=finding.description,
                    page_url=(finding.page_url or "")[:500] if finding.page_url else None,
                    recommendation=finding.recommendation
                ))

            if issues_to_create:
                AuditIssue.objects.bulk_create(issues_to_create)

            logger.info(
                f"[SEOAuditEngine] Persisted SiteAudit #{site_audit.id} for project #{project.id} "
                f"(Score: {site_audit.score}, Issues: {len(issues_to_create)})."
            )

            return site_audit
