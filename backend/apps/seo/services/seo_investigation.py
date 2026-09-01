"""
DoxaRank Autonomous SEO Opportunity Investigation & Decision Engine.

Provides deep, deterministic investigation of detected SEO opportunities by correlating:
- Live/stored Google Search Console metrics (impressions, clicks, CTR, position)
- Live/stored SiteAudit diagnostics (crawl issues, status codes, HTML/metadata defects)
- Target URL & Query specifics

Outputs a strongly typed, structured SEOInvestigationResult separating:
- Observed Facts (empirical data directly retrieved from GSC and SiteAudit)
- Inferences (reasoned interpretations derived from observed facts)
- Root Cause Classification (deterministic category and explanatory rationale)
- Confidence Scoring (deterministic 0.0 - 1.0 score and LOW/MEDIUM/HIGH rating)
- Impact, Effort, and Risk heuristics
- Structured Recommended Actions with explicit human-in-the-loop approval boundaries.
"""

import logging
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Union
from django.utils import timezone
from django.db.models import Sum, Avg

from apps.projects.models import Project
from apps.seo.models import (
    SiteAudit, AuditIssue, AuditStatus, IssueSeverity,
    SearchConsoleConnection, SearchAnalyticsData
)
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, get_event_publisher, AgentEventPublisher
)
from apps.seo.services.seo_intelligence import (
    OpportunityType, normalize_url_path_for_matching
)

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class InvestigationStatus(str, Enum):
    PENDING = "PENDING"
    INVESTIGATING = "INVESTIGATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


class InvestigationConfidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RootCauseCategory(str, Enum):
    CONTENT = "CONTENT"
    ON_PAGE_SEO = "ON_PAGE_SEO"
    TECHNICAL_SEO = "TECHNICAL_SEO"
    CTR = "CTR"
    INDEXING = "INDEXING"
    CANONICAL = "CANONICAL"
    PERFORMANCE = "PERFORMANCE"
    INTERNAL_LINKING = "INTERNAL_LINKING"
    SEARCH_INTENT = "SEARCH_INTENT"
    UNKNOWN = "UNKNOWN"


class ImpactEstimate(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EffortEstimate(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RiskLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class InvestigationActionType(str, Enum):
    OPTIMIZE_TITLE = "OPTIMIZE_TITLE"
    OPTIMIZE_META_DESCRIPTION = "OPTIMIZE_META_DESCRIPTION"
    FIX_MISSING_H1 = "FIX_MISSING_H1"
    FIX_CANONICAL = "FIX_CANONICAL"
    FIX_IMAGE_ALT = "FIX_IMAGE_ALT"
    FIX_BROKEN_LINK = "FIX_BROKEN_LINK"
    IMPROVE_CONTENT = "IMPROVE_CONTENT"
    INVESTIGATE_INDEXING = "INVESTIGATE_INDEXING"
    INVESTIGATE_PERFORMANCE = "INVESTIGATE_PERFORMANCE"
    MONITOR = "MONITOR"
    NO_ACTION = "NO_ACTION"


# =============================================================================
# STRUCTURED INVESTIGATION RESULT
# =============================================================================

@dataclass
class SEOInvestigationResult:
    """
    Strongly-typed, structured investigation outcome produced by SEOInvestigationService.
    Guarantees strict separation between observed facts, inferences, root causes, and recommendations.
    """
    investigation_id: str
    project_id: int
    opportunity_type: str
    target_url: Optional[str]
    target_query: Optional[str]
    status: str
    observed_facts: List[str] = field(default_factory=list)
    inferences: List[str] = field(default_factory=list)
    inferred_root_causes: List[str] = field(default_factory=list)
    root_cause_category: str = RootCauseCategory.UNKNOWN.value
    root_cause_reason: str = ""
    confidence_score: float = 0.0
    confidence_level: str = InvestigationConfidence.LOW.value
    severity: str = "medium"
    impact_estimate: str = ImpactEstimate.MEDIUM.value
    effort_estimate: str = EffortEstimate.MEDIUM.value
    risk_level: str = RiskLevel.LOW.value
    requires_human_approval: bool = True
    recommended_action: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    supporting_audit_issues: List[Dict[str, Any]] = field(default_factory=list)
    supporting_gsc_metrics: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result into a serializable dictionary."""
        return {
            "investigation_id": self.investigation_id,
            "project_id": self.project_id,
            "opportunity_type": self.opportunity_type,
            "target_url": self.target_url,
            "target_query": self.target_query,
            "status": self.status,
            "observed_facts": self.observed_facts,
            "inferences": self.inferences,
            "inferred_root_causes": self.inferred_root_causes,
            "root_cause_category": self.root_cause_category,
            "root_cause_reason": self.root_cause_reason,
            "confidence_score": round(self.confidence_score, 2),
            "confidence_level": self.confidence_level,
            "severity": self.severity,
            "impact_estimate": self.impact_estimate,
            "effort_estimate": self.effort_estimate,
            "risk_level": self.risk_level,
            "requires_human_approval": self.requires_human_approval,
            "recommended_action": self.recommended_action,
            "recommendations": self.recommendations,
            "supporting_audit_issues": self.supporting_audit_issues,
            "supporting_gsc_metrics": self.supporting_gsc_metrics,
            "evidence": self.evidence
        }


# =============================================================================
# INVESTIGATION SERVICE
# =============================================================================

class SEOInvestigationService:
    """
    Autonomous SEO Investigation Service for DoxaRank.
    Deep-dives into specific opportunities, collects supporting multi-source evidence,
    reasons over signals deterministically, and synthesizes structured recommendations
    while establishing clear human-in-the-loop approval boundaries.
    """

    VALID_OPPORTUNITY_TYPES = {
        OpportunityType.LOW_CTR_HIGH_IMPRESSIONS,
        OpportunityType.RANKING_TECHNICAL_DECAY,
        OpportunityType.HIGH_VALUE_PAGE_MAINTENANCE,
        OpportunityType.QUERY_PAGE_OPPORTUNITY,
        "LOW_CTR_HIGH_IMPRESSIONS",
        "RANKING_TECHNICAL_DECAY",
        "HIGH_VALUE_PAGE_MAINTENANCE",
        "QUERY_PAGE_OPPORTUNITY",
        "CONTENT_OPPORTUNITY",
        "TECHNICAL_SEO_ISSUE",
        "ON_PAGE_SEO",
        "PAGE_TWO_KEYWORD",
        "GENERAL_INVESTIGATION",
        "CANONICAL",
        "PERFORMANCE",
        "INTERNAL_LINKING",
        "INDEXING"
    }

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
            raise ValueError("Valid Project context is required for SEOInvestigationService.")
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
            logger.debug(f"[SEOInvestigationService] Event emission skipped/failed: {exc}")

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

    def investigate(
        self,
        opportunity_type: str,
        target_url: Optional[str] = None,
        target_query: Optional[str] = None,
        audit_id: Optional[int] = None,
        date_range_days: int = 28,
        run_id: Optional[int] = None
    ) -> SEOInvestigationResult:
        """
        Execute an autonomous, multi-source SEO investigation on a specific opportunity.
        Collects evidence, distinguishes observed facts from inferences, scores confidence,
        determines root cause, and generates structured recommended actions.
        """
        inv_id = f"inv_{uuid.uuid4().hex[:12]}"
        clean_opp_type = (opportunity_type or "").strip().upper()

        # 1. Validation & Start Event
        self._emit_event(
            AgentEventType.SEO_INVESTIGATION_STARTED,
            {
                "investigation_id": inv_id,
                "opportunity_type": clean_opp_type,
                "target_url": target_url,
                "target_query": target_query,
                "audit_id": audit_id
            },
            run_id=run_id
        )

        if not clean_opp_type or clean_opp_type not in self.VALID_OPPORTUNITY_TYPES:
            res = SEOInvestigationResult(
                investigation_id=inv_id,
                project_id=self.project.id,
                opportunity_type=clean_opp_type or "INVALID",
                target_url=target_url,
                target_query=target_query,
                status=InvestigationStatus.FAILED.value,
                observed_facts=["Invalid or unrecognized opportunity type specified."],
                inferences=["Investigation cannot proceed without a valid opportunity type."],
                inferred_root_causes=["Unrecognized opportunity type."],
                root_cause_category=RootCauseCategory.UNKNOWN.value,
                root_cause_reason=f"Opportunity type '{clean_opp_type}' is not supported by the investigation engine.",
                confidence_score=0.0,
                confidence_level=InvestigationConfidence.LOW.value,
                severity="low",
                impact_estimate=ImpactEstimate.LOW.value,
                effort_estimate=EffortEstimate.LOW.value,
                risk_level=RiskLevel.LOW.value,
                requires_human_approval=False,
                recommended_action={
                    "action_type": InvestigationActionType.NO_ACTION.value,
                    "description": "No action possible due to invalid opportunity type.",
                    "target_url": target_url or "",
                    "target_query": target_query or "",
                    "expected_benefit": "None",
                    "risk": RiskLevel.LOW.value,
                    "requires_human_approval": False
                }
            )
            return res

        # 2. Collect Evidence from GSC and SiteAudit
        gsc_metrics, gsc_connected = self._fetch_target_gsc_metrics(
            target_url=target_url,
            target_query=target_query,
            date_range_days=date_range_days
        )

        audit_issues, audit_summary, audit_available = self._fetch_target_audit_issues(
            target_url=target_url,
            audit_id=audit_id
        )

        self._emit_event(
            AgentEventType.SEO_INVESTIGATION_EVIDENCE_COLLECTED,
            {
                "investigation_id": inv_id,
                "gsc_connected": gsc_connected,
                "gsc_metrics_present": bool(gsc_metrics),
                "audit_available": audit_available,
                "audit_issues_count": len(audit_issues)
            },
            run_id=run_id
        )

        # 3. Separate Observed Facts and Inferences
        observed_facts: List[str] = []
        inferences: List[str] = []

        # Populate Observed Facts
        if gsc_connected and gsc_metrics:
            imp = gsc_metrics.get("impressions", 0)
            clicks = gsc_metrics.get("clicks", 0)
            ctr = gsc_metrics.get("ctr", 0.0)
            pos = gsc_metrics.get("position", 0.0)
            observed_facts.append(
                f"Google Search Console: {imp:,} impressions, {clicks:,} clicks, "
                f"{round(ctr * 100, 2)}% CTR, average position #{pos:.1f}."
            )
            if target_query:
                observed_facts.append(f"Target search query monitored: '{target_query}'.")
        elif gsc_connected:
            observed_facts.append("Google Search Console is connected, but no recorded impressions/clicks exist for this specific URL/query.")
        else:
            observed_facts.append("Google Search Console connection is not configured or inactive for this project.")

        if audit_available:
            if audit_issues:
                issue_names = [f"{i.get('issue_type')} ({i.get('severity')})" for i in audit_issues[:5]]
                observed_facts.append(
                    f"Site Audit diagnostics identified {len(audit_issues)} issues on target URL: {', '.join(issue_names)}."
                )
            else:
                observed_facts.append(f"Site Audit diagnostics found 0 technical issues for {target_url or 'the site'}.")
        else:
            observed_facts.append("No completed Site Audit crawl data is available for this project.")

        if target_url:
            observed_facts.append(f"Target URL evaluated: {target_url}")

        # 4. Formulate Inferences based on Facts
        if gsc_metrics and audit_issues:
            imp = gsc_metrics.get("impressions", 0)
            ctr = gsc_metrics.get("ctr", 0.0)
            pos = gsc_metrics.get("position", 0.0)
            has_snippet_issue = any(i.get('issue_type') in self.ONPAGE_SNIPPET_ISSUES for i in audit_issues)
            has_tech_issue = any(i.get('issue_type') in self.TECHNICAL_CRAWL_ISSUES or i.get('severity') == 'critical' for i in audit_issues)

            if imp >= 50 and pos <= 15.0 and ctr < 0.035 and has_snippet_issue:
                inferences.append(
                    "High SERP visibility with low CTR directly correlates with identified on-page snippet/metadata defects."
                )
            if pos >= 5.0 and has_tech_issue:
                inferences.append(
                    "Technical crawl/indexation defects are creating ranking resistance and dampening algorithmic authority."
                )
            if imp >= 500:
                inferences.append(
                    "This landing page represents a high-traffic asset where targeted fixes will generate substantial traffic recovery."
                )
        elif gsc_metrics:
            imp = gsc_metrics.get("impressions", 0)
            ctr = gsc_metrics.get("ctr", 0.0)
            pos = gsc_metrics.get("position", 0.0)
            if imp >= 50 and ctr < 0.02:
                inferences.append("SERP click-through rate is below expected baseline given search impression volume.")
            if 11.0 <= pos <= 20.0:
                inferences.append("Target asset is positioned on Page 2, representing high upside for ranking optimization.")
        elif audit_issues:
            crit_count = sum(1 for i in audit_issues if i.get('severity') == 'critical')
            if crit_count > 0:
                inferences.append(f"Contains {crit_count} critical technical issues that impair search engine crawling.")
            else:
                inferences.append("Contains on-page and technical warnings that should be resolved to maintain search quality.")
        else:
            inferences.append("Insufficient multi-source data to confirm a root cause; ongoing monitoring is recommended.")

        # 5. Root Cause Classification
        root_cause_cat, root_cause_reason = self._classify_root_cause(
            clean_opp_type, gsc_metrics, audit_issues, target_url, target_query
        )

        self._emit_event(
            AgentEventType.SEO_INVESTIGATION_ROOT_CAUSE_IDENTIFIED,
            {
                "investigation_id": inv_id,
                "root_cause_category": root_cause_cat.value,
                "root_cause_reason": root_cause_reason
            },
            run_id=run_id
        )

        # 6. Confidence Scoring
        confidence_score, confidence_level = self._calculate_confidence(
            gsc_connected=gsc_connected,
            gsc_metrics=gsc_metrics,
            audit_available=audit_available,
            audit_issues=audit_issues,
            target_url=target_url,
            target_query=target_query
        )

        # 7. Impact, Effort, Risk Classification
        impact_est, effort_est, risk_lvl, sev = self._classify_impact_effort_risk(
            clean_opp_type, gsc_metrics, audit_issues, root_cause_cat
        )

        # 8. Recommendation Generation
        rec_action, all_recs = self._generate_recommendations(
            root_cause_cat=root_cause_cat,
            clean_opp_type=clean_opp_type,
            target_url=target_url,
            target_query=target_query,
            audit_issues=audit_issues,
            gsc_metrics=gsc_metrics,
            risk_level=risk_lvl,
            confidence_level=confidence_level
        )

        self._emit_event(
            AgentEventType.SEO_INVESTIGATION_RECOMMENDATION_GENERATED,
            {
                "investigation_id": inv_id,
                "action_type": rec_action.get("action_type"),
                "requires_human_approval": rec_action.get("requires_human_approval"),
                "confidence_level": confidence_level
            },
            run_id=run_id
        )

        # 9. Final Result Assembly
        status_val = InvestigationStatus.COMPLETED.value
        requires_approval = rec_action.get("requires_human_approval", True)

        res = SEOInvestigationResult(
            investigation_id=inv_id,
            project_id=self.project.id,
            opportunity_type=clean_opp_type,
            target_url=target_url,
            target_query=target_query,
            status=status_val,
            observed_facts=observed_facts,
            inferences=inferences,
            inferred_root_causes=[root_cause_reason],
            root_cause_category=root_cause_cat.value,
            root_cause_reason=root_cause_reason,
            confidence_score=confidence_score,
            confidence_level=confidence_level.value,
            severity=sev,
            impact_estimate=impact_est.value,
            effort_estimate=effort_est.value,
            risk_level=risk_lvl.value,
            requires_human_approval=requires_approval,
            recommended_action=rec_action,
            recommendations=all_recs,
            supporting_audit_issues=audit_issues,
            supporting_gsc_metrics=gsc_metrics or {},
            evidence={
                "gsc": gsc_metrics,
                "audit_summary": audit_summary,
                "matched_issues_count": len(audit_issues)
            }
        )

        self._emit_event(
            AgentEventType.SEO_INVESTIGATION_COMPLETED,
            {
                "investigation_id": inv_id,
                "status": status_val,
                "confidence_score": round(confidence_score, 2),
                "root_cause_category": root_cause_cat.value,
                "action_type": rec_action.get("action_type")
            },
            run_id=run_id
        )

        return res

    # =========================================================================
    # EVIDENCE RETRIEVAL HELPERS
    # =========================================================================

    def _fetch_target_gsc_metrics(
        self,
        target_url: Optional[str],
        target_query: Optional[str],
        date_range_days: int = 28
    ) -> Tuple[Dict[str, Any], bool]:
        """Fetch targeted GSC metrics for a specific page and/or query."""
        from apps.seo.services.google_search_console import GoogleSearchConsoleService

        conn = SearchConsoleConnection.objects.filter(project=self.project, is_connected=True).first()
        if not conn:
            return {}, False

        norm_target_url = normalize_url_path_for_matching(target_url) if target_url else ""

        # Try live GSC API first
        try:
            service = GoogleSearchConsoleService(project=self.project)
            end_date = timezone.now().date()
            start_date = end_date - timezone.timedelta(days=max(7, date_range_days))
            s_str = start_date.strftime("%Y-%m-%d")
            e_str = end_date.strftime("%Y-%m-%d")

            dimensions = ["page"]
            if target_query:
                dimensions = ["query", "page"]

            res = service.query_search_analytics(
                start_date=s_str,
                end_date=e_str,
                dimensions=dimensions,
                row_limit=150
            )
            rows = res.get("rows", [])

            # Filter rows for target URL and query
            for r in rows:
                r_page = r.get("page", "")
                r_query = r.get("query", "")
                norm_r_page = normalize_url_path_for_matching(r_page)

                url_match = (not norm_target_url) or (norm_target_url in norm_r_page or norm_r_page in norm_target_url)
                query_match = (not target_query) or (target_query.lower() == r_query.lower())

                if url_match and query_match:
                    return {
                        "page": r_page,
                        "query": r_query or target_query,
                        "impressions": self._safe_int(r.get("impressions")),
                        "clicks": self._safe_int(r.get("clicks")),
                        "ctr": self._safe_float(r.get("ctr")),
                        "position": self._safe_float(r.get("position")),
                        "source": "live_gsc_api"
                    }, True

            # If specific combination not matched, check top page if target_url supplied
            if target_url:
                for r in rows:
                    norm_r_page = normalize_url_path_for_matching(r.get("page", ""))
                    if norm_target_url and (norm_target_url in norm_r_page or norm_r_page in norm_target_url):
                        return {
                            "page": r.get("page", ""),
                            "query": target_query or "",
                            "impressions": self._safe_int(r.get("impressions")),
                            "clicks": self._safe_int(r.get("clicks")),
                            "ctr": self._safe_float(r.get("ctr")),
                            "position": self._safe_float(r.get("position")),
                            "source": "live_gsc_api"
                        }, True

            return {}, True
        except Exception as exc:
            logger.debug(f"[SEOInvestigationService] Live GSC fetch failed: {exc}. Trying cached DB.")

        # Fallback to local SearchAnalyticsData
        try:
            qs = SearchAnalyticsData.objects.filter(connection=conn)
            if target_url:
                # Search by normalized path substring
                qs = qs.filter(page__icontains=norm_target_url.split('/')[-1] if '/' in norm_target_url else norm_target_url)
            if target_query:
                qs = qs.filter(query__iexact=target_query)

            aggregated = qs.aggregate(
                total_clicks=Sum('clicks'),
                total_impressions=Sum('impressions'),
                avg_pos=Avg('position')
            )

            imp = aggregated.get('total_impressions') or 0
            clicks = aggregated.get('total_clicks') or 0
            pos = aggregated.get('avg_pos') or 0.0

            if imp > 0 or clicks > 0:
                ctr = (clicks / imp) if imp > 0 else 0.0
                return {
                    "page": target_url or "",
                    "query": target_query or "",
                    "impressions": imp,
                    "clicks": clicks,
                    "ctr": ctr,
                    "position": float(pos),
                    "source": "stored_analytics_db"
                }, True

            return {}, True
        except Exception as exc:
            logger.debug(f"[SEOInvestigationService] DB GSC fetch failed: {exc}")
            return {}, True

    def _fetch_target_audit_issues(
        self,
        target_url: Optional[str],
        audit_id: Optional[int]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], bool]:
        """Fetch matching SiteAudit issues for target URL."""
        audit_qs = SiteAudit.objects.filter(project=self.project)
        if audit_id:
            audit = audit_qs.filter(id=audit_id).first()
        else:
            audit = audit_qs.order_by('-created_at').first()

        if not audit:
            return [], {}, False

        summary = {
            "audit_id": audit.id,
            "status": audit.status,
            "score": audit.score,
            "total_issues": audit.issues.count()
        }

        issues_qs = AuditIssue.objects.filter(audit=audit)
        matching_issues: List[Dict[str, Any]] = []

        norm_target = normalize_url_path_for_matching(target_url) if target_url else ""

        for issue in issues_qs:
            norm_page = normalize_url_path_for_matching(issue.page_url)
            # Match specific page or include if no target_url specified
            if not norm_target or (norm_target in norm_page or norm_page in norm_target):
                matching_issues.append({
                    "id": issue.id,
                    "issue_type": issue.issue_type,
                    "severity": issue.severity,
                    "title": issue.title,
                    "description": issue.description,
                    "recommendation": issue.recommendation,
                    "page_url": issue.page_url or ""
                })

        return matching_issues, summary, True

    # =========================================================================
    # REASONING & CLASSIFICATION
    # =========================================================================

    def _classify_root_cause(
        self,
        opportunity_type: str,
        gsc_metrics: Dict[str, Any],
        audit_issues: List[Dict[str, Any]],
        target_url: Optional[str],
        target_query: Optional[str]
    ) -> Tuple[RootCauseCategory, str]:
        """
        Deterministically classify the root cause and provide explanatory justification.
        """
        issue_types = {i.get("issue_type") for i in audit_issues}
        severities = {i.get("severity") for i in audit_issues}

        # 1. Canonical defects
        if any("canonical" in it for it in issue_types):
            return (
                RootCauseCategory.CANONICAL,
                "Canonical configuration mismatch or missing canonical tag causes search engines to split or dilute ranking authority."
            )

        # 2. Critical technical crawl blockers
        if any(it in ['broken_internal_link', 'broken_link', 'crawl_error', 'redirect_loop'] for it in issue_types) or 'critical' in severities:
            return (
                RootCauseCategory.TECHNICAL_SEO,
                "Technical crawl errors, HTTP failures, or redirect loops prevent search engine spiders from reliably indexing page content."
            )

        # 3. Performance bottlenecks
        if 'slow_response' in issue_types:
            return (
                RootCauseCategory.PERFORMANCE,
                "Sub-optimal server response time or Core Web Vitals latency creates crawl budget strain and degrades user experience."
            )

        # 4. On-Page Snippet & Meta gaps
        snippet_hits = issue_types.intersection(self.ONPAGE_SNIPPET_ISSUES)
        if snippet_hits:
            hit_list = ", ".join(snippet_hits)
            if opportunity_type in ["LOW_CTR_HIGH_IMPRESSIONS", OpportunityType.LOW_CTR_HIGH_IMPRESSIONS] or (gsc_metrics and gsc_metrics.get("ctr", 1.0) < 0.035):
                return (
                    RootCauseCategory.CTR,
                    f"High search impressions and strong ranking coexist with unusually low CTR due to on-page snippet defects: {hit_list}."
                )
            return (
                RootCauseCategory.ON_PAGE_SEO,
                f"On-page HTML title/meta tag defects ({hit_list}) impair search snippet presentation and topical relevance."
            )

        # 5. Search Intent / Page 2 Keyword
        if opportunity_type in ["QUERY_PAGE_OPPORTUNITY", "PAGE_TWO_KEYWORD", OpportunityType.QUERY_PAGE_OPPORTUNITY]:
            return (
                RootCauseCategory.SEARCH_INTENT,
                f"The landing page ranks on Page 2 for query '{target_query or 'target query'}', indicating topical relevance baseline but insufficient depth to satisfy primary search intent."
            )

        # 6. Content depth / quality
        if opportunity_type == "CONTENT_OPPORTUNITY" or any("thin_content" in it or "word_count" in it for it in issue_types):
            return (
                RootCauseCategory.CONTENT,
                "Content depth, keyword integration, and topical coverage fall below top-ranking competitor benchmarks."
            )

        # 7. Fallback if GSC data shows low CTR without specific audit tags
        if gsc_metrics and gsc_metrics.get("impressions", 0) >= 50 and gsc_metrics.get("ctr", 1.0) < 0.02:
            return (
                RootCauseCategory.CTR,
                "High impressions with below-average CTR indicate that the SERP snippet fails to compel searchers compared to competing results."
            )

        # 8. Default fallback
        if not gsc_metrics and not audit_issues:
            return (
                RootCauseCategory.UNKNOWN,
                "Insufficient empirical evidence from Search Console and Site Audit to confirm a specific root cause."
            )

        return (
            RootCauseCategory.ON_PAGE_SEO,
            "General on-page search optimization and metadata refinement required."
        )

    def _calculate_confidence(
        self,
        gsc_connected: bool,
        gsc_metrics: Dict[str, Any],
        audit_available: bool,
        audit_issues: List[Dict[str, Any]],
        target_url: Optional[str],
        target_query: Optional[str]
    ) -> Tuple[float, InvestigationConfidence]:
        """
        Calculate deterministic confidence score (0.0 - 1.0) based on signal verification.
        """
        score = 0.10  # baseline for valid request

        # Signal 1: Empirical GSC metrics confirmed (+0.30)
        if gsc_connected and gsc_metrics:
            score += 0.30
            if gsc_metrics.get("impressions", 0) >= 50 or gsc_metrics.get("clicks", 0) >= 5:
                score += 0.05

        # Signal 2: Empirical SiteAudit diagnostics available (+0.25)
        if audit_available:
            score += 0.10
            if audit_issues:
                score += 0.15

        # Signal 3: URL match confirmed (+0.10)
        if target_url and (gsc_metrics or audit_issues):
            score += 0.10

        # Signal 4: Query relationship confirmed (+0.10)
        if target_query and gsc_metrics and gsc_metrics.get("query"):
            score += 0.10

        # Bound score between 0.0 and 1.0
        score = min(1.0, max(0.0, score))

        if score >= 0.75:
            level = InvestigationConfidence.HIGH
        elif score >= 0.45:
            level = InvestigationConfidence.MEDIUM
        else:
            level = InvestigationConfidence.LOW

        return score, level

    def _classify_impact_effort_risk(
        self,
        opportunity_type: str,
        gsc_metrics: Dict[str, Any],
        audit_issues: List[Dict[str, Any]],
        root_cause_cat: RootCauseCategory
    ) -> Tuple[ImpactEstimate, EffortEstimate, RiskLevel, str]:
        """
        Determine deterministic heuristics for Impact, Effort, Risk, and Severity.
        """
        imp_count = gsc_metrics.get("impressions", 0) if gsc_metrics else 0
        clicks = gsc_metrics.get("clicks", 0) if gsc_metrics else 0
        pos = gsc_metrics.get("position", 50.0) if gsc_metrics else 50.0
        has_critical_issue = any(i.get("severity") == "critical" for i in audit_issues)

        # Impact Estimation
        if (imp_count >= 500 and pos <= 10.0) or clicks >= 20 or has_critical_issue or opportunity_type in ["HIGH_VALUE_PAGE_MAINTENANCE", OpportunityType.HIGH_VALUE_PAGE_MAINTENANCE]:
            impact = ImpactEstimate.HIGH
            severity = "critical" if has_critical_issue else "high"
        elif imp_count >= 50 or (pos <= 20.0 and imp_count >= 20) or audit_issues:
            impact = ImpactEstimate.MEDIUM
            severity = "warning"
        else:
            impact = ImpactEstimate.LOW
            severity = "info"

        # Effort Estimation
        if root_cause_cat in [RootCauseCategory.CTR, RootCauseCategory.ON_PAGE_SEO]:
            effort = EffortEstimate.LOW
        elif root_cause_cat in [RootCauseCategory.CONTENT, RootCauseCategory.SEARCH_INTENT, RootCauseCategory.INTERNAL_LINKING]:
            effort = EffortEstimate.MEDIUM
        elif root_cause_cat in [RootCauseCategory.TECHNICAL_SEO, RootCauseCategory.CANONICAL, RootCauseCategory.PERFORMANCE, RootCauseCategory.INDEXING]:
            effort = EffortEstimate.HIGH
        else:
            effort = EffortEstimate.LOW

        # Risk Estimation
        if root_cause_cat in [RootCauseCategory.CANONICAL, RootCauseCategory.INDEXING, RootCauseCategory.TECHNICAL_SEO]:
            risk = RiskLevel.HIGH
        elif root_cause_cat in [RootCauseCategory.CONTENT, RootCauseCategory.SEARCH_INTENT]:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        return impact, effort, risk, severity

    def _generate_recommendations(
        self,
        root_cause_cat: RootCauseCategory,
        clean_opp_type: str,
        target_url: Optional[str],
        target_query: Optional[str],
        audit_issues: List[Dict[str, Any]],
        gsc_metrics: Dict[str, Any],
        risk_level: RiskLevel,
        confidence_level: InvestigationConfidence
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Generate structured recommended action adhering to human-in-the-loop governance.
        """
        url_str = target_url or "target page"
        query_str = target_query or "primary keyword"

        issue_types = {i.get("issue_type") for i in audit_issues}

        if confidence_level == InvestigationConfidence.LOW and not audit_issues and not gsc_metrics:
            rec = {
                "action_type": InvestigationActionType.MONITOR.value,
                "description": f"Insufficient empirical signals available. Continue monitoring {url_str} across upcoming crawl and search analytics cycles.",
                "target_url": target_url or "",
                "target_query": target_query or "",
                "expected_benefit": "Establishes baseline traffic data before performing modifications.",
                "risk": RiskLevel.LOW.value,
                "requires_human_approval": False
            }
            return rec, [rec]

        # Determine primary action type
        if "missing_meta_description" in issue_types or "short_meta_description" in issue_types or root_cause_cat == RootCauseCategory.CTR:
            action_type = InvestigationActionType.OPTIMIZE_META_DESCRIPTION
            desc = f"Rewrite meta description on {url_str} to feature a clear value proposition and call-to-action targeting '{query_str}'."
            benefit = "Increases organic click-through rate (CTR) without requiring higher ranking positions."
            req_approval = True
        elif "missing_title" in issue_types or "short_title" in issue_types or "long_title" in issue_types:
            action_type = InvestigationActionType.OPTIMIZE_TITLE
            desc = f"Update HTML title tag on {url_str} to front-load primary search query '{query_str}' within 50-60 characters."
            benefit = "Strengthens search relevance and click appeal in SERP listings."
            req_approval = True
        elif "missing_h1" in issue_types:
            action_type = InvestigationActionType.FIX_MISSING_H1
            desc = f"Add a single, semantic <h1> heading to {url_str} clearly stating the page topic and targeting '{query_str}'."
            benefit = "Clarifies topical hierarchy for search bots and improves accessibility."
            req_approval = True
        elif "missing_canonical" in issue_types or "canonical_mismatch" in issue_types or root_cause_cat == RootCauseCategory.CANONICAL:
            action_type = InvestigationActionType.FIX_CANONICAL
            desc = f"Configure a self-referential canonical tag on {url_str} to consolidate link equity and prevent duplicate content."
            benefit = "Prevents keyword cannibalization and ensures clean indexing."
            req_approval = True
        elif "missing_image_alt" in issue_types:
            action_type = InvestigationActionType.FIX_IMAGE_ALT
            desc = f"Add descriptive, keyword-relevant alt attributes to images on {url_str}."
            benefit = "Improves image search rankings and WCAG accessibility compliance."
            req_approval = True
        elif "broken_internal_link" in issue_types or "broken_link" in issue_types:
            action_type = InvestigationActionType.FIX_BROKEN_LINK
            desc = f"Repair broken links pointing to or from {url_str} to restore crawl flow and page equity."
            benefit = "Eliminates 404 crawl errors and preserves search equity."
            req_approval = True
        elif root_cause_cat in [RootCauseCategory.CONTENT, RootCauseCategory.SEARCH_INTENT]:
            action_type = InvestigationActionType.IMPROVE_CONTENT
            desc = f"Enrich content depth, add an FAQ section, and align headings on {url_str} to satisfy search intent for '{query_str}'."
            benefit = "Pushes Page 2 rankings into Top 3 positions by satisfying search intent."
            req_approval = True
        elif root_cause_cat == RootCauseCategory.PERFORMANCE:
            action_type = InvestigationActionType.INVESTIGATE_PERFORMANCE
            desc = f"Investigate server response time and optimize Core Web Vitals on {url_str}."
            benefit = "Reduces bounce rate and improves mobile search rankings."
            req_approval = True
        elif root_cause_cat == RootCauseCategory.INDEXING:
            action_type = InvestigationActionType.INVESTIGATE_INDEXING
            desc = f"Inspect indexability, robots.txt, and sitemap inclusion for {url_str} in Search Console."
            benefit = "Ensures clean URL discovery and prompt re-indexing."
            req_approval = True
        else:
            action_type = InvestigationActionType.OPTIMIZE_TITLE
            desc = f"Review and optimize SERP presentation tags for {url_str}."
            benefit = "Enhances search visibility and click attraction."
            req_approval = True

        primary_rec = {
            "action_type": action_type.value,
            "description": desc,
            "target_url": target_url or "",
            "target_query": target_query or "",
            "expected_benefit": benefit,
            "risk": risk_level.value,
            "requires_human_approval": req_approval
        }

        all_recs = [primary_rec]

        # Add secondary recommendation if multiple issues present
        if len(audit_issues) > 1 and action_type != InvestigationActionType.OPTIMIZE_META_DESCRIPTION:
            all_recs.append({
                "action_type": InvestigationActionType.OPTIMIZE_META_DESCRIPTION.value,
                "description": f"Refine meta description copy on {url_str} alongside primary technical remediations.",
                "target_url": target_url or "",
                "target_query": target_query or "",
                "expected_benefit": "Maximizes SERP click conversion.",
                "risk": RiskLevel.LOW.value,
                "requires_human_approval": True
            })

        return primary_rec, all_recs
