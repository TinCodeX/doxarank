import logging
import re
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple, Set, Union
from urllib.parse import urlparse

from django.db.models import Sum, Avg, Count, Min, Max
from django.utils import timezone
from apps.projects.models import Project
from apps.seo.models import (
    Keyword, KeywordRanking, SiteAudit, AuditIssue, AuditStatus, IssueSeverity,
    SearchConsoleConnection, SearchAnalyticsData,
    SEOInsight, InsightSeverity, InsightStatus, InsightSource, InsightType
)
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, get_event_publisher, AgentEventPublisher
)

logger = logging.getLogger(__name__)


class CandidateInsight:
    """Helper data container for insights produced by rules before persistence."""
    def __init__(
        self,
        fingerprint: str,
        insight_type: str,
        severity: str,
        title: str,
        description: str,
        recommendation: str,
        source: str,
        related_keyword=None,
        related_url: str = '',
        metadata: dict = None
    ):
        self.fingerprint = fingerprint
        self.insight_type = insight_type
        self.severity = severity
        self.title = title
        self.description = description
        self.recommendation = recommendation
        self.source = source
        self.related_keyword = related_keyword
        self.related_url = related_url or ''
        self.metadata = metadata or {}


class SEOIntelligenceService:
    """
    Deterministic, rule-based intelligence service for DoxaRank.
    Analyzes existing project data across:
    - Tracked keyword ranking observations
    - Google Search Console performance analytics
    - Site audit crawl issues
    
    Generates structured, actionable SEO insights with idempotent deduplication.
    """

    def __init__(self, project: Project):
        self.project = project

    def analyze(self) -> dict:
        """
        Execute all deterministic intelligence rules for the project,
        deduplicate results, persist new and updated insights, and return summary metrics.
        """
        candidates: list[CandidateInsight] = []

        # 1. Ranking movement rules (Drop, Improvement, Page 2)
        candidates.extend(self._evaluate_ranking_rules())

        # 2. Google Search Console analytics rules (High Imp/Low CTR, Performance Declines)
        candidates.extend(self._evaluate_search_console_rules())

        # 3. Technical SEO Audit rules (Critical / Warning audit issues)
        candidates.extend(self._evaluate_technical_audit_rules())

        # Persist and deduplicate candidate insights
        created_count = 0
        updated_count = 0

        for cand in candidates:
            existing = SEOInsight.objects.filter(
                project=self.project,
                fingerprint=cand.fingerprint
            ).first()

            if existing:
                # Update attributes while preserving user workflow status if dismissed/resolved
                existing.insight_type = cand.insight_type
                existing.severity = cand.severity
                existing.title = cand.title
                existing.description = cand.description
                existing.recommendation = cand.recommendation
                existing.source = cand.source
                existing.related_keyword = cand.related_keyword
                existing.related_url = cand.related_url
                existing.metadata = cand.metadata
                existing.save(update_fields=[
                    'insight_type', 'severity', 'title', 'description',
                    'recommendation', 'source', 'related_keyword', 'related_url',
                    'metadata', 'updated_at'
                ])
                updated_count += 1
            else:
                SEOInsight.objects.create(
                    project=self.project,
                    fingerprint=cand.fingerprint,
                    insight_type=cand.insight_type,
                    severity=cand.severity,
                    title=cand.title,
                    description=cand.description,
                    recommendation=cand.recommendation,
                    status=InsightStatus.OPEN,
                    source=cand.source,
                    related_keyword=cand.related_keyword,
                    related_url=cand.related_url,
                    metadata=cand.metadata,
                    detected_at=timezone.now()
                )
                created_count += 1

        total_open = SEOInsight.objects.filter(
            project=self.project,
            status=InsightStatus.OPEN
        ).count()

        return {
            'created': created_count,
            'updated': updated_count,
            'resolved': 0,
            'total_open': total_open
        }

    # =========================================================================
    # Rule Evaluators
    # =========================================================================

    def _evaluate_ranking_rules(self) -> list[CandidateInsight]:
        """
        Evaluates ranking observations for project keywords:
        - Rule A: Ranking Drop (>= 3 position decline)
        - Rule B: Ranking Improvement (>= 3 position gain)
        - Rule C: Page Two Keyword (Current position 11-20)
        """
        candidates: list[CandidateInsight] = []
        keywords = Keyword.objects.filter(project=self.project)

        for kw in keywords:
            rankings = list(KeywordRanking.objects.filter(keyword=kw).order_by('-recorded_at')[:2])
            if not rankings:
                continue

            latest = rankings[0]
            latest_pos = latest.position

            # Rule C: Page Two Opportunity (Positions 11–20)
            if 11 <= latest_pos <= 20:
                candidates.append(CandidateInsight(
                    fingerprint=f"page_two_keyword:kw_{kw.id}",
                    insight_type=InsightType.PAGE_TWO_KEYWORD,
                    severity=InsightSeverity.OPPORTUNITY,
                    title=f'Page 2 Opportunity: "{kw.keyword}" at #{latest_pos}',
                    description=(
                        f'"{kw.keyword}" is ranking at #{latest_pos} on page 2. '
                        f'Keywords on page 2 represent immediate high-leverage opportunities to push into page 1.'
                    ),
                    recommendation=(
                        'Optimize on-page headers (H1/H2), enrich topical depth, build targeted internal links '
                        'from high-authority pages, and target search intent snippets.'
                    ),
                    source=InsightSource.RANKING,
                    related_keyword=kw,
                    related_url=latest.ranking_url or '',
                    metadata={
                        'keyword_id': kw.id,
                        'keyword': kw.keyword,
                        'current_position': latest_pos,
                        'ranking_url': latest.ranking_url or '',
                        'recorded_at': latest.recorded_at.isoformat()
                    }
                ))

            # Rules A & B: Requires at least 2 historical ranking observations
            if len(rankings) >= 2:
                prev = rankings[1]
                prev_pos = prev.position

                # Rule A: Ranking Drop
                if latest_pos > prev_pos and (latest_pos - prev_pos) >= 3:
                    drop = latest_pos - prev_pos
                    is_critical = (drop >= 10) or (prev_pos <= 10 and latest_pos > 20)
                    severity = InsightSeverity.CRITICAL if is_critical else InsightSeverity.WARNING

                    candidates.append(CandidateInsight(
                        fingerprint=f"ranking_drop:kw_{kw.id}",
                        insight_type=InsightType.RANKING_DROP,
                        severity=severity,
                        title=f'Ranking Drop for "{kw.keyword}" (-{drop} positions)',
                        description=(
                            f'Ranking for "{kw.keyword}" dropped {drop} positions '
                            f'from #{prev_pos} to #{latest_pos}.'
                        ),
                        recommendation=(
                            'Inspect recent landing page changes, evaluate competitor SERP enhancements, '
                            'verify search intent alignment, and check for lost backlinks or technical crawl issues.'
                        ),
                        source=InsightSource.RANKING,
                        related_keyword=kw,
                        related_url=latest.ranking_url or '',
                        metadata={
                            'keyword_id': kw.id,
                            'keyword': kw.keyword,
                            'previous_position': prev_pos,
                            'current_position': latest_pos,
                            'position_drop': drop,
                            'recorded_at': latest.recorded_at.isoformat()
                        }
                    ))

                # Rule B: Ranking Improvement
                elif latest_pos < prev_pos and (prev_pos - latest_pos) >= 3:
                    gain = prev_pos - latest_pos
                    severity = InsightSeverity.OPPORTUNITY if latest_pos <= 10 else InsightSeverity.INFO

                    candidates.append(CandidateInsight(
                        fingerprint=f"ranking_improvement:kw_{kw.id}",
                        insight_type=InsightType.RANKING_IMPROVEMENT,
                        severity=severity,
                        title=f'Ranking Improvement for "{kw.keyword}" (+{gain} positions)',
                        description=(
                            f'Ranking for "{kw.keyword}" improved {gain} positions '
                            f'from #{prev_pos} to #{latest_pos}.'
                        ),
                        recommendation=(
                            'Maintain ranking momentum: reinforce internal links, optimize title tag CTR, '
                            'and update supporting content regularly.'
                        ),
                        source=InsightSource.RANKING,
                        related_keyword=kw,
                        related_url=latest.ranking_url or '',
                        metadata={
                            'keyword_id': kw.id,
                            'keyword': kw.keyword,
                            'previous_position': prev_pos,
                            'current_position': latest_pos,
                            'position_gain': gain,
                            'recorded_at': latest.recorded_at.isoformat()
                        }
                    ))

        return candidates

    def _evaluate_search_console_rules(self) -> list[CandidateInsight]:
        """
        Evaluates Google Search Console performance data:
        - Rule D: High Impressions + Low CTR
        - Rule E: Declining GSC Performance (Clicks or Impressions drop >= 15%)
        """
        candidates: list[CandidateInsight] = []
        gsc_conn = SearchConsoleConnection.objects.filter(
            project=self.project,
            is_connected=True
        ).first()

        if not gsc_conn:
            return candidates

        analytics_qs = SearchAnalyticsData.objects.filter(connection=gsc_conn)
        if not analytics_qs.exists():
            return candidates

        # --- Rule D: High Impressions + Low CTR per query ---
        query_aggregates = analytics_qs.exclude(query='').values('query').annotate(
            total_impressions=Sum('impressions'),
            total_clicks=Sum('clicks'),
            avg_pos=Avg('position')
        ).filter(total_impressions__gte=50)

        for item in query_aggregates:
            imp = item['total_impressions']
            clk = item['total_clicks']
            avg_pos = float(item['avg_pos']) if item['avg_pos'] is not None else 0.0
            ctr = (clk / imp) if imp > 0 else 0.0

            # Low CTR threshold: < 3.0% (0.03) for queries with >= 50 impressions
            if ctr < 0.03:
                ctr_pct = round(ctr * 100, 2)
                q_name = item['query']
                candidates.append(CandidateInsight(
                    fingerprint=f"high_impressions_low_ctr:query_{q_name}",
                    insight_type=InsightType.HIGH_IMPRESSIONS_LOW_CTR,
                    severity=InsightSeverity.OPPORTUNITY,
                    title=f'High Impressions, Low CTR: "{q_name}"',
                    description=(
                        f'Query "{q_name}" generated {imp:,} search impressions but only '
                        f'{clk:,} clicks ({ctr_pct}% CTR) with an average position of #{avg_pos:.1f}.'
                    ),
                    recommendation=(
                        'Rewrite title tags and meta descriptions to include compelling value hooks, '
                        'target featured snippets, and ensure strong search intent alignment.'
                    ),
                    source=InsightSource.SEARCH_CONSOLE,
                    metadata={
                        'query': q_name,
                        'impressions': imp,
                        'clicks': clk,
                        'ctr_percent': ctr_pct,
                        'avg_position': round(avg_pos, 1)
                    }
                ))

        # --- Rule E: Period-over-Period Performance Decline ---
        date_stats = analytics_qs.aggregate(min_date=Min('date'), max_date=Max('date'))
        min_d = date_stats.get('min_date')
        max_d = date_stats.get('max_date')

        if min_d and max_d and min_d != max_d:
            total_days = (max_d - min_d).days
            if total_days >= 2:
                mid_point = min_d + timezone.timedelta(days=total_days // 2)

                prior_agg = analytics_qs.filter(date__lte=mid_point).aggregate(
                    clicks=Sum('clicks'),
                    impressions=Sum('impressions')
                )
                recent_agg = analytics_qs.filter(date__gt=mid_point).aggregate(
                    clicks=Sum('clicks'),
                    impressions=Sum('impressions')
                )

                p_clicks = prior_agg.get('clicks') or 0
                r_clicks = recent_agg.get('clicks') or 0
                p_imp = prior_agg.get('impressions') or 0
                r_imp = recent_agg.get('impressions') or 0

                # Check clicks decline (>= 15%)
                if p_clicks >= 10 and r_clicks < p_clicks:
                    clicks_drop_ratio = (p_clicks - r_clicks) / p_clicks
                    if clicks_drop_ratio >= 0.15:
                        drop_pct = round(clicks_drop_ratio * 100, 1)
                        severity = InsightSeverity.CRITICAL if drop_pct >= 30 else InsightSeverity.WARNING
                        candidates.append(CandidateInsight(
                            fingerprint='declining_clicks:gsc_summary',
                            insight_type=InsightType.DECLINING_CLICKS,
                            severity=severity,
                            title=f'Search Traffic Decline: Organic Clicks Down {drop_pct}%',
                            description=(
                                f'Total organic search clicks decreased from {p_clicks:,} to {r_clicks:,} '
                                f'({drop_pct}% decline) across observation periods.'
                            ),
                            recommendation=(
                                'Review top lost queries and pages in Google Search Console, inspect recent site changes, '
                                'and check for indexing issues or Google algorithmic updates.'
                            ),
                            source=InsightSource.SEARCH_CONSOLE,
                            metadata={
                                'metric': 'clicks',
                                'previous_clicks': p_clicks,
                                'recent_clicks': r_clicks,
                                'decline_percent': drop_pct
                            }
                        ))

                # Check impressions decline (>= 15%)
                if p_imp >= 50 and r_imp < p_imp:
                    imp_drop_ratio = (p_imp - r_imp) / p_imp
                    if imp_drop_ratio >= 0.15:
                        drop_pct = round(imp_drop_ratio * 100, 1)
                        candidates.append(CandidateInsight(
                            fingerprint='declining_impressions:gsc_summary',
                            insight_type=InsightType.DECLINING_IMPRESSIONS,
                            severity=InsightSeverity.WARNING,
                            title=f'Search Visibility Decline: Impressions Down {drop_pct}%',
                            description=(
                                f'Total search impressions dropped from {p_imp:,} to {r_imp:,} '
                                f'({drop_pct}% decrease) across observation periods.'
                            ),
                            recommendation=(
                                'Verify sitemaps and indexation status in Google Search Console, check for technical errors, '
                                'and assess query visibility trends.'
                            ),
                            source=InsightSource.SEARCH_CONSOLE,
                            metadata={
                                'metric': 'impressions',
                                'previous_impressions': p_imp,
                                'recent_impressions': r_imp,
                                'decline_percent': drop_pct
                            }
                        ))

        return candidates

    def _evaluate_technical_audit_rules(self) -> list[CandidateInsight]:
        """
        Evaluates unresolved critical and warning issues from the latest site audit:
        - Rule F: Technical SEO Issues
        """
        candidates: list[CandidateInsight] = []
        latest_audit = SiteAudit.objects.filter(
            project=self.project,
            status=AuditStatus.COMPLETED
        ).order_by('-created_at').first()

        if not latest_audit:
            return candidates

        issues = AuditIssue.objects.filter(
            audit=latest_audit,
            severity__in=[IssueSeverity.CRITICAL, IssueSeverity.WARNING]
        )

        for issue in issues:
            severity = InsightSeverity.CRITICAL if issue.severity == IssueSeverity.CRITICAL else InsightSeverity.WARNING
            fingerprint = f"tech_seo_issue:{issue.issue_type}:{issue.page_url or 'site_wide'}"

            candidates.append(CandidateInsight(
                fingerprint=fingerprint,
                insight_type=InsightType.TECHNICAL_SEO_ISSUE,
                severity=severity,
                title=f'Technical SEO Issue: {issue.title}',
                description=f'Site audit identified {issue.severity.upper()} issue: {issue.description}',
                recommendation=issue.recommendation or 'Resolve this technical SEO issue to improve crawlability and search ranking performance.',
                source=InsightSource.SITE_AUDIT,
                related_url=issue.page_url or '',
                metadata={
                    'audit_id': latest_audit.id,
                    'issue_id': issue.id,
                    'issue_type': issue.issue_type,
                    'issue_severity': issue.severity,
                    'page_url': issue.page_url or ''
                }
            ))

        return candidates


# =============================================================================
# URL NORMALIZATION HELPER FOR EVIDENCE MATCHING
# =============================================================================

def normalize_url_path_for_matching(url: Optional[str]) -> str:
    """
    Normalizes a URL or path for consistent mapping across GSC analytics and SiteAudit issues.
    - Strips scheme and default ports.
    - Normalizes lowercase host and path.
    - Removes trailing slashes.
    """
    if not url or not isinstance(url, str):
        return ""
    clean = url.strip()
    if not clean:
        return ""
    try:
        parsed = urlparse(clean)
        path = parsed.path or "/"
        netloc = (parsed.netloc or "").lower().split(':')[0]
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        if netloc:
            return f"{netloc}{path}"
        return path
    except Exception:
        return clean.rstrip("/").lower()


class OpportunityType:
    LOW_CTR_HIGH_IMPRESSIONS = "LOW_CTR_HIGH_IMPRESSIONS"
    RANKING_TECHNICAL_DECAY = "RANKING_TECHNICAL_DECAY"
    HIGH_VALUE_PAGE_MAINTENANCE = "HIGH_VALUE_PAGE_MAINTENANCE"
    QUERY_PAGE_OPPORTUNITY = "QUERY_PAGE_OPPORTUNITY"


@dataclass
class SEOCorrelationOpportunity:
    """
    Structured, deterministic SEO opportunity produced by correlating
    Google Search Console search analytics with live Site Audit diagnostics.
    """
    type: str
    severity: str  # 'critical', 'high', 'warning', 'medium', 'low', 'info'
    confidence: float  # 0.0 to 1.0
    title: str
    explanation: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    recommended_action: str = ""
    suggested_action_type: Optional[str] = None
    target_url: Optional[str] = None
    target_query: Optional[str] = None
    affected_pages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize opportunity to JSON-compatible dictionary."""
        return {
            "type": self.type,
            "severity": self.severity,
            "confidence": round(self.confidence, 2),
            "title": self.title,
            "explanation": self.explanation,
            "evidence": self.evidence,
            "recommended_action": self.recommended_action,
            "suggested_action_type": self.suggested_action_type,
            "target_url": self.target_url,
            "target_query": self.target_query,
            "affected_pages": self.affected_pages
        }


class SEOCorrelationIntelligenceService:
    """
    Live SEO Intelligence Correlation Service for DoxaRank.
    Correlates Google Search Console performance data with live website audit issues
    to identify prioritized, high-leverage SEO opportunities.
    """

    ONPAGE_SNIPPET_ISSUES = {
        'missing_title', 'short_title', 'long_title',
        'missing_meta_description', 'short_meta_description', 'long_meta_description',
        'missing_h1', 'multiple_h1'
    }

    TECHNICAL_CRAWL_ISSUES = {
        'broken_internal_link', 'broken_link', 'crawl_error',
        'missing_canonical', 'canonical_mismatch',
        'redirect_chain', 'redirect_loop', 'redirecting_internal_link',
        'slow_response', 'missing_structured_data', 'missing_image_alt'
    }

    def __init__(
        self,
        project: Project,
        publisher: Optional[AgentEventPublisher] = None
    ):
        if not project or not project.id:
            raise ValueError("Valid Project context is required for SEOCorrelationIntelligenceService.")
        self.project = project
        self.publisher = publisher or get_event_publisher()

    def _emit_event(
        self,
        event_type: Union[AgentEventType, str],
        payload: Dict[str, Any],
        run_id: Optional[int] = None
    ) -> None:
        """Safely emit an AgentEvent if publisher is active."""
        try:
            event = AgentEvent(
                event_type=event_type,
                run_id=run_id or 0,
                project_id=self.project.id,
                payload=payload
            )
            self.publisher.publish(event)
        except Exception as exc:
            logger.debug(f"[SEOCorrelationIntelligenceService] Event emission skipped/failed: {exc}")

    @staticmethod
    def _safe_int(val: Any) -> int:
        try:
            return int(val) if val is not None else 0
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _safe_float(val: Any) -> float:
        try:
            return float(val) if val is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    def analyze_correlated_opportunities(
        self,
        page_rows: Optional[List[Dict[str, Any]]] = None,
        query_rows: Optional[List[Dict[str, Any]]] = None,
        combined_rows: Optional[List[Dict[str, Any]]] = None,
        audit_id: Optional[int] = None,
        min_impressions: int = 20,
        limit: int = 10,
        page_filter: Optional[str] = None,
        sync_to_insights: bool = False,
        run_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute deterministic cross-source correlation between GSC performance and SiteAudit diagnostics.
        """
        # 1. Emit start event
        self._emit_event(
            AgentEventType.SEO_INTELLIGENCE_STARTED,
            {"min_impressions": min_impressions, "limit": limit, "page_filter": page_filter},
            run_id=run_id
        )

        gsc_connected = False
        audit_available = False

        # 2. Fetch or prepare GSC data
        pages = page_rows
        queries = query_rows
        combined = combined_rows

        if pages is None and combined is None:
            pages, queries, combined, gsc_connected = self._fetch_gsc_data(min_impressions)
        else:
            gsc_connected = bool(pages or combined or queries)

        pages = pages or []
        queries = queries or []
        combined = combined or []

        # Filter pages if page_filter provided
        if page_filter:
            norm_filter = page_filter.strip().lower()
            pages = [p for p in pages if norm_filter in str(p.get("page", "")).lower()]
            combined = [c for c in combined if norm_filter in str(c.get("page", "")).lower()]

        # 3. Fetch SiteAudit and AuditIssues
        audit_qs = SiteAudit.objects.filter(project=self.project)
        if audit_id:
            audit = audit_qs.filter(id=audit_id).first()
        else:
            audit = audit_qs.order_by('-created_at').first()

        issues_by_url: Dict[str, List[AuditIssue]] = {}
        all_issues: List[AuditIssue] = []

        if audit:
            audit_available = True
            all_issues = list(AuditIssue.objects.filter(audit=audit))
            for issue in all_issues:
                norm_p = normalize_url_path_for_matching(issue.page_url)
                if norm_p not in issues_by_url:
                    issues_by_url[norm_p] = []
                issues_by_url[norm_p].append(issue)

        # 4. Emit evidence collected event
        self._emit_event(
            AgentEventType.SEO_EVIDENCE_COLLECTED,
            {
                "gsc_connected": gsc_connected,
                "gsc_pages_count": len(pages),
                "gsc_combined_count": len(combined),
                "audit_available": audit_available,
                "audit_issues_count": len(all_issues),
                "distinct_pages_with_issues": len(issues_by_url)
            },
            run_id=run_id
        )

        # 5. Evaluate Correlation Rules
        opportunities: List[SEOCorrelationOpportunity] = []

        # Rule 1: High Impressions, Low CTR + Metadata/Snippet Issues
        r1_opps = self._correlate_low_ctr_high_impressions(pages, combined, issues_by_url, min_impressions)
        opportunities.extend(r1_opps)

        # Rule 2: Ranking Decay + Technical Crawl Defect
        r2_opps = self._correlate_ranking_technical_decay(pages, combined, issues_by_url, min_impressions)
        opportunities.extend(r2_opps)

        # Rule 3: High-Value Page Maintenance
        r3_opps = self._correlate_high_value_page_maintenance(pages, issues_by_url)
        opportunities.extend(r3_opps)

        # Rule 4: Query-to-Landing-Page Opportunity
        r4_opps = self._correlate_query_page_opportunities(combined, issues_by_url, min_impressions)
        opportunities.extend(r4_opps)

        # Emit detected events for opportunities
        for opp in opportunities:
            self._emit_event(
                AgentEventType.SEO_OPPORTUNITY_DETECTED,
                {
                    "type": opp.type,
                    "severity": opp.severity,
                    "title": opp.title,
                    "target_url": opp.target_url,
                    "confidence": opp.confidence
                },
                run_id=run_id
            )

        # Sort opportunities by severity and confidence descending
        severity_rank = {
            'critical': 5,
            'high': 4,
            'warning': 3,
            'opportunity': 2,
            'medium': 2,
            'info': 1,
            'low': 1
        }
        sorted_opps = sorted(
            opportunities,
            key=lambda o: (severity_rank.get(o.severity.lower(), 0), o.confidence),
            reverse=True
        )

        # Apply limit
        bounded_opps = sorted_opps[:max(1, limit)]

        # 6. Optional Persistence to SEOInsight
        persisted_count = 0
        if sync_to_insights and bounded_opps:
            persisted_count = self._sync_to_insights(bounded_opps)

        # 7. Emit completion event
        self._emit_event(
            AgentEventType.SEO_INTELLIGENCE_COMPLETED,
            {
                "total_opportunities": len(opportunities),
                "returned_opportunities": len(bounded_opps),
                "persisted_insights": persisted_count
            },
            run_id=run_id
        )

        return {
            "status": "success",
            "project_id": self.project.id,
            "gsc_connected": gsc_connected,
            "audit_available": audit_available,
            "total_opportunities_found": len(opportunities),
            "opportunities_count": len(bounded_opps),
            "opportunities": [o.to_dict() for o in bounded_opps],
            "persisted_insights_count": persisted_count
        }

    # =========================================================================
    # INTERNAL GSC DATA RETRIEVAL
    # =========================================================================

    def _fetch_gsc_data(self, min_impressions: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], bool]:
        """Fetch page and query analytics from live GoogleSearchConsoleService or local SearchAnalyticsData."""
        from apps.seo.services.google_search_console import GoogleSearchConsoleService

        pages: List[Dict[str, Any]] = []
        queries: List[Dict[str, Any]] = []
        combined: List[Dict[str, Any]] = []
        gsc_connected = False

        # First check connection
        conn = SearchConsoleConnection.objects.filter(project=self.project, is_connected=True).first()
        if not conn:
            return pages, queries, combined, False

        # Try live query via GoogleSearchConsoleService
        try:
            service = GoogleSearchConsoleService(project=self.project)
            end_date = timezone.now().date()
            start_date = end_date - timezone.timedelta(days=28)
            s_str = start_date.strftime("%Y-%m-%d")
            e_str = end_date.strftime("%Y-%m-%d")

            # 1. Top Pages
            pages_res = service.get_top_pages(start_date=s_str, end_date=e_str, limit=50)
            pages = pages_res.get("pages", [])

            # 2. Combined Query + Page
            comb_res = service.query_search_analytics(
                start_date=s_str,
                end_date=e_str,
                dimensions=["query", "page"],
                row_limit=100
            )
            combined = comb_res.get("rows", [])

            # 3. Top Queries
            queries_res = service.get_top_queries(start_date=s_str, end_date=e_str, limit=50)
            queries = queries_res.get("queries", [])

            gsc_connected = True
        except Exception as exc:
            logger.debug(f"[SEOCorrelationIntelligenceService] Live GSC fetch failed: {exc}. Falling back to DB.")
            # Fallback to local SearchAnalyticsData if available
            db_pages = SearchAnalyticsData.objects.filter(connection=conn).exclude(page='').values('page').annotate(
                total_clicks=Sum('clicks'),
                total_impressions=Sum('impressions'),
                avg_pos=Avg('position')
            ).filter(total_impressions__gte=min_impressions)

            for p in db_pages:
                imp = p['total_impressions']
                clk = p['total_clicks']
                ctr = (clk / imp) if imp > 0 else 0.0
                pages.append({
                    "page": p['page'],
                    "clicks": clk,
                    "impressions": imp,
                    "ctr": ctr,
                    "position": float(p['avg_pos']) if p['avg_pos'] is not None else 0.0
                })
            gsc_connected = bool(pages)

        return pages, queries, combined, gsc_connected

    # =========================================================================
    # CORRELATION RULE EVALUATORS
    # =========================================================================

    def _correlate_low_ctr_high_impressions(
        self,
        pages: List[Dict[str, Any]],
        combined: List[Dict[str, Any]],
        issues_by_url: Dict[str, List[AuditIssue]],
        min_impressions: int
    ) -> List[SEOCorrelationOpportunity]:
        """
        Rule 1: High impressions + low CTR correlated with on-page snippet/metadata defects.
        """
        opps: List[SEOCorrelationOpportunity] = []
        for p in pages:
            page_url = p.get("page") or p.get("keys", [""])[0] if isinstance(p.get("keys"), list) else p.get("page", "")
            if not page_url:
                continue

            imp = self._safe_int(p.get("impressions"))
            clk = self._safe_int(p.get("clicks"))
            pos = self._safe_float(p.get("position"))
            ctr = self._safe_float(p.get("ctr"))

            if imp < min_impressions or pos > 20.0:
                continue

            # Position CTR threshold: < 3.5% for Top 10, < 1.5% for Page 2
            max_expected_ctr = 0.035 if pos <= 10.0 else 0.015
            if ctr > max_expected_ctr:
                continue

            norm_url = normalize_url_path_for_matching(page_url)
            page_issues = issues_by_url.get(norm_url, [])
            matching_snippet_issues = [
                i.issue_type for i in page_issues if i.issue_type in self.ONPAGE_SNIPPET_ISSUES
            ]

            # Also check queries for this page
            page_queries = [
                c.get("query") for c in combined
                if normalize_url_path_for_matching(c.get("page")) == norm_url and c.get("query")
            ][:3]
            top_query_str = page_queries[0] if page_queries else None

            # Calculate confidence and severity
            confidence = 0.88 if matching_snippet_issues else 0.75
            is_critical = imp >= 1000 and pos <= 10.0
            severity = "critical" if is_critical else ("high" if imp >= 100 else "warning")

            issues_desc = ", ".join(matching_snippet_issues) if matching_snippet_issues else "sub-optimal SERP snippet metadata"
            ctr_pct = round(ctr * 100, 2)

            opps.append(SEOCorrelationOpportunity(
                type=OpportunityType.LOW_CTR_HIGH_IMPRESSIONS,
                severity=severity,
                confidence=confidence,
                title=f"Optimize SERP snippet for {page_url}",
                explanation=(
                    f"Page receives {imp:,} impressions with average position #{pos:.1f}, "
                    f"but achieves a low CTR of {ctr_pct}%. Site audit identified on-page snippet defects: {issues_desc}."
                ),
                evidence={
                    "impressions": imp,
                    "clicks": clk,
                    "ctr": round(ctr, 4),
                    "position": round(pos, 1),
                    "audit_issues": matching_snippet_issues,
                    "top_queries": page_queries
                },
                recommended_action="Review and rewrite meta title and meta description to include compelling value hooks and match user search intent.",
                suggested_action_type="update_meta_description" if any("description" in it for it in matching_snippet_issues) else "update_title",
                target_url=page_url,
                target_query=top_query_str,
                affected_pages=[page_url]
            ))

        return opps

    def _correlate_ranking_technical_decay(
        self,
        pages: List[Dict[str, Any]],
        combined: List[Dict[str, Any]],
        issues_by_url: Dict[str, List[AuditIssue]],
        min_impressions: int
    ) -> List[SEOCorrelationOpportunity]:
        """
        Rule 2: Ranking friction (Page 2 or low clicks) correlated with technical crawl defects.
        """
        opps: List[SEOCorrelationOpportunity] = []
        for p in pages:
            page_url = p.get("page") or p.get("keys", [""])[0] if isinstance(p.get("keys"), list) else p.get("page", "")
            if not page_url:
                continue

            imp = self._safe_int(p.get("impressions"))
            clk = self._safe_int(p.get("clicks"))
            pos = self._safe_float(p.get("position"))

            # Check pages ranking between 8.0 and 30.0 or experiencing traffic bottlenecks
            if imp < max(10, min_impressions // 2):
                continue

            norm_url = normalize_url_path_for_matching(page_url)
            page_issues = issues_by_url.get(norm_url, [])
            tech_issues = [
                i.issue_type for i in page_issues
                if i.issue_type in self.TECHNICAL_CRAWL_ISSUES or i.severity in [IssueSeverity.CRITICAL, IssueSeverity.WARNING]
            ]

            if not tech_issues:
                continue

            has_critical = any(i.severity == IssueSeverity.CRITICAL for i in page_issues)
            severity = "critical" if has_critical else "high"
            confidence = 0.86

            tech_str = ", ".join(tech_issues[:4])

            opps.append(SEOCorrelationOpportunity(
                type=OpportunityType.RANKING_TECHNICAL_DECAY,
                severity=severity,
                confidence=confidence,
                title=f"Resolve technical crawl blockers on {page_url}",
                explanation=(
                    f"Page has ranking friction (average position #{pos:.1f}, {imp:,} impressions) "
                    f"while suffering from technical crawl/canonical defects: {tech_str}."
                ),
                evidence={
                    "impressions": imp,
                    "clicks": clk,
                    "position": round(pos, 1),
                    "audit_issues": tech_issues
                },
                recommended_action=f"Resolve {len(tech_issues)} technical audit defects on {page_url} to ensure clean search engine crawling and canonical indexing.",
                suggested_action_type="fix_canonical" if any("canonical" in it for it in tech_issues) else "fix_technical",
                target_url=page_url,
                affected_pages=[page_url]
            ))

        return opps

    def _correlate_high_value_page_maintenance(
        self,
        pages: List[Dict[str, Any]],
        issues_by_url: Dict[str, List[AuditIssue]]
    ) -> List[SEOCorrelationOpportunity]:
        """
        Rule 3: High-traffic landing pages correlated with any technical SEO warnings to protect search equity.
        """
        opps: List[SEOCorrelationOpportunity] = []
        if not pages:
            return opps

        # Determine high-traffic thresholds
        sorted_by_clicks = sorted(pages, key=lambda x: self._safe_int(x.get("clicks")), reverse=True)
        top_tier = sorted_by_clicks[:max(3, len(sorted_by_clicks) // 5)]

        for p in top_tier:
            page_url = p.get("page") or p.get("keys", [""])[0] if isinstance(p.get("keys"), list) else p.get("page", "")
            if not page_url:
                continue

            clk = self._safe_int(p.get("clicks"))
            imp = self._safe_int(p.get("impressions"))
            pos = self._safe_float(p.get("position"))

            if clk < 5 and imp < 100:
                continue

            norm_url = normalize_url_path_for_matching(page_url)
            page_issues = issues_by_url.get(norm_url, [])
            if not page_issues:
                continue

            has_critical = any(i.severity == IssueSeverity.CRITICAL for i in page_issues)
            severity = "critical" if has_critical else "high"
            issue_types = [i.issue_type for i in page_issues]

            opps.append(SEOCorrelationOpportunity(
                type=OpportunityType.HIGH_VALUE_PAGE_MAINTENANCE,
                severity=severity,
                confidence=0.92,
                title=f"High-priority technical maintenance for top page {page_url}",
                explanation=(
                    f"Page is a top organic traffic asset ({clk:,} clicks, {imp:,} impressions), "
                    f"but contains technical SEO issues: {', '.join(issue_types[:3])}. Technical decay on core assets creates major revenue risk."
                ),
                evidence={
                    "clicks": clk,
                    "impressions": imp,
                    "position": round(pos, 1),
                    "audit_issues": issue_types
                },
                recommended_action="Prioritize technical remediations on this top-performing URL before working on lower-traffic assets.",
                suggested_action_type="fix_technical",
                target_url=page_url,
                affected_pages=[page_url]
            ))

        return opps

    def _correlate_query_page_opportunities(
        self,
        combined: List[Dict[str, Any]],
        issues_by_url: Dict[str, List[AuditIssue]],
        min_impressions: int
    ) -> List[SEOCorrelationOpportunity]:
        """
        Rule 4: High-leverage search queries correlated with on-page landing page gaps.
        """
        opps: List[SEOCorrelationOpportunity] = []
        for c in combined:
            query = c.get("query")
            page_url = c.get("page")
            if not query or not page_url:
                continue

            imp = self._safe_int(c.get("impressions"))
            clk = self._safe_int(c.get("clicks"))
            pos = self._safe_float(c.get("position"))

            # Target high-intent queries between positions 4.0 and 20.0 with notable volume
            if imp < min_impressions or not (3.5 <= pos <= 20.0):
                continue

            norm_url = normalize_url_path_for_matching(page_url)
            page_issues = issues_by_url.get(norm_url, [])
            if not page_issues:
                continue

            issue_types = [i.issue_type for i in page_issues]

            opps.append(SEOCorrelationOpportunity(
                type=OpportunityType.QUERY_PAGE_OPPORTUNITY,
                severity="opportunity",
                confidence=0.85,
                title=f"Optimize {page_url} for query '{query}'",
                explanation=(
                    f"Query '{query}' generates {imp:,} impressions at position #{pos:.1f}. "
                    f"Landing page {page_url} has on-page gaps ({', '.join(issue_types[:3])}) preventing it from reaching Top 3."
                ),
                evidence={
                    "query": query,
                    "landing_page": page_url,
                    "impressions": imp,
                    "clicks": clk,
                    "position": round(pos, 1),
                    "audit_issues": issue_types
                },
                recommended_action=f"Enrich landing page {page_url} content and headings to explicitly target '{query}' and resolve identified audit issues.",
                suggested_action_type="optimize_content",
                target_url=page_url,
                target_query=query,
                affected_pages=[page_url]
            ))

        return opps

    # =========================================================================
    # PERSISTENCE SYNC
    # =========================================================================

    def _sync_to_insights(self, opportunities: List[SEOCorrelationOpportunity]) -> int:
        """Idempotently persist correlated opportunities to SEOInsight records."""
        count = 0
        type_mapping = {
            OpportunityType.LOW_CTR_HIGH_IMPRESSIONS: InsightType.HIGH_IMPRESSIONS_LOW_CTR,
            OpportunityType.RANKING_TECHNICAL_DECAY: InsightType.TECHNICAL_SEO_ISSUE,
            OpportunityType.HIGH_VALUE_PAGE_MAINTENANCE: InsightType.TECHNICAL_SEO_ISSUE,
            OpportunityType.QUERY_PAGE_OPPORTUNITY: InsightType.PAGE_TWO_KEYWORD,
        }

        sev_mapping = {
            'critical': InsightSeverity.CRITICAL,
            'high': InsightSeverity.WARNING,
            'warning': InsightSeverity.WARNING,
            'opportunity': InsightSeverity.OPPORTUNITY,
            'medium': InsightSeverity.OPPORTUNITY,
            'low': InsightSeverity.INFO,
            'info': InsightSeverity.INFO,
        }

        for opp in opportunities:
            fingerprint = f"correlated_opp:{opp.type}:{opp.target_url or 'site'}:{opp.target_query or ''}"
            itype = type_mapping.get(opp.type, InsightType.CONTENT_OPPORTUNITY)
            isev = sev_mapping.get(opp.severity.lower(), InsightSeverity.OPPORTUNITY)
            source = (
                InsightSource.SEARCH_CONSOLE
                if opp.type in (OpportunityType.LOW_CTR_HIGH_IMPRESSIONS, OpportunityType.QUERY_PAGE_OPPORTUNITY)
                else InsightSource.SITE_AUDIT
            )

            SEOInsight.objects.update_or_create(
                project=self.project,
                fingerprint=fingerprint,
                defaults={
                    'insight_type': itype,
                    'severity': isev,
                    'title': opp.title,
                    'description': opp.explanation,
                    'recommendation': opp.recommended_action,
                    'status': InsightStatus.OPEN,
                    'source': source,
                    'related_url': opp.target_url or '',
                    'metadata': opp.to_dict(),
                    'detected_at': timezone.now()
                }
            )
            count += 1

        return count
