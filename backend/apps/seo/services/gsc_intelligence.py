"""
Google Search Console Intelligence & Reasoning Service for DoxaRank.

Transforms raw GSC analytics into structured, actionable SEO intelligence.
Provides deterministic heuristic analysis for:
1. Page Two Ranking Opportunities (Positions 10.1 - 20.0 with notable search volume).
2. SERP Snippet Underperformance (High impressions, low CTR relative to position benchmarks).
3. Keyword Cannibalization (Multiple URLs competing and splitting traffic for the same search query).
4. Period-over-Period Performance Comparison (Detecting traffic drops, gainers, decliners, and new/lost queries).
5. Emerging Long-Tail Opportunities (High CTR, early traction queries).
6. Idempotent persistence to SEOInsight models for downstream recommendation and action workflows.
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple, Union

from django.utils import timezone
from apps.projects.models import Project
from apps.seo.models import (
    SEOInsight, InsightSeverity, InsightStatus, InsightSource, InsightType
)

logger = logging.getLogger(__name__)


# Position-based expected CTR benchmarks (Industry averages for Google SERP)
CTR_BENCHMARKS = {
    "top_3": 0.15,     # Average CTR ~15-30% for positions 1-3
    "page_1": 0.03,    # Average CTR ~3-8% for positions 4-10
    "page_2": 0.01,    # Average CTR ~1-2% for positions 11-20
}


class GSCFindingType:
    """Strongly typed finding categories produced by GSC intelligence analysis."""
    PAGE_TWO_OPPORTUNITY = 'gsc_page_two_opportunity'
    HIGH_IMPRESSIONS_LOW_CTR = 'gsc_high_impressions_low_ctr'
    KEYWORD_CANNIBALIZATION = 'gsc_keyword_cannibalization'
    PERIOD_COMPARISON_DECLINE = 'gsc_period_comparison_decline'
    PERIOD_COMPARISON_GAIN = 'gsc_period_comparison_gain'
    EMERGING_QUERY = 'gsc_emerging_query'
    GENERAL_GSC_OPPORTUNITY = 'gsc_general_opportunity'


@dataclass
class GSCFinding:
    """
    Structured finding representation produced by the GSC intelligence analyzer.
    Grounded in verifiable GSC metrics and consumable by agent reasoning loops.
    """
    finding_type: str
    severity: str  # 'critical', 'warning', 'opportunity', 'info'
    confidence: float  # 0.0 to 1.0
    title: str
    insight: str
    recommendation: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    suggested_action_type: Optional[str] = None
    target_query: Optional[str] = None
    target_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize finding to clean JSON-compatible dictionary."""
        return {
            "finding_type": self.finding_type,
            "severity": self.severity,
            "confidence": round(self.confidence, 2),
            "title": self.title,
            "insight": self.insight,
            "recommendation": self.recommendation,
            "evidence": self.evidence,
            "metrics": self.metrics,
            "requires_approval": self.requires_approval,
            "suggested_action_type": self.suggested_action_type,
            "target_query": self.target_query,
            "target_url": self.target_url
        }


class GSCIntelligenceService:
    """
    Service for analyzing Google Search Console analytics data and producing
    grounded, explainable SEO intelligence for agent decision-making.
    """

    def __init__(self, project: Project):
        if not project or not project.id:
            raise ValueError("Valid Project context is required for GSCIntelligenceService.")
        self.project = project

    # =========================================================================
    # CORE OPPORTUNITY ANALYSIS
    # =========================================================================

    def analyze_opportunities(
        self,
        query_rows: Optional[List[Dict[str, Any]]] = None,
        page_rows: Optional[List[Dict[str, Any]]] = None,
        combined_rows: Optional[List[Dict[str, Any]]] = None,
        min_impressions: int = 10,
        gsc_service: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Evaluate GSC analytics rows to identify actionable SEO opportunities.
        Can process supplied row datasets directly or query live GSC API if needed.
        """
        # If no rows provided, query default last 28 days from GoogleSearchConsoleService
        if query_rows is None and combined_rows is None:
            query_rows, combined_rows = self._fetch_default_analytics(gsc_service)

        queries = query_rows or []
        combined = combined_rows or []
        pages = page_rows or []

        findings: List[GSCFinding] = []

        # 1. Evaluate Page Two Opportunities
        p2_findings = self._detect_page_two_opportunities(queries, min_impressions)
        findings.extend(p2_findings)

        # 2. Evaluate High Impressions Low CTR (SERP Snippet Opportunities)
        ctr_findings = self._detect_high_impressions_low_ctr(queries, min_impressions)
        findings.extend(ctr_findings)

        # 3. Evaluate Keyword Cannibalization
        cannibalization_findings = self._detect_keyword_cannibalization(combined, min_impressions)
        findings.extend(cannibalization_findings)

        # 4. Evaluate Emerging Queries
        emerging_findings = self._detect_emerging_queries(queries, min_impressions)
        findings.extend(emerging_findings)

        # Sort findings by severity and confidence descending
        severity_order = {'critical': 4, 'warning': 3, 'opportunity': 2, 'info': 1}
        sorted_findings = sorted(
            findings,
            key=lambda f: (severity_order.get(f.severity, 0), f.confidence),
            reverse=True
        )

        return {
            "project_id": self.project.id,
            "analyzed_at": timezone.now().isoformat(),
            "total_queries_analyzed": len(queries),
            "total_findings": len(sorted_findings),
            "findings_by_type": {
                "page_two": len(p2_findings),
                "low_ctr": len(ctr_findings),
                "cannibalization": len(cannibalization_findings),
                "emerging": len(emerging_findings),
            },
            "findings": [f.to_dict() for f in sorted_findings]
        }

    # =========================================================================
    # PERIOD-OVER-PERIOD PERFORMANCE COMPARISON
    # =========================================================================

    def compare_periods(
        self,
        base_start: str,
        base_end: str,
        comp_start: str,
        comp_end: str,
        row_limit: int = 100,
        gsc_service: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Compare search performance between two date ranges (e.g. Recent 28 days vs Prior 28 days).
        Computes aggregate metric deltas, top gaining/declining queries, and generates structured findings.
        """
        from apps.seo.services.google_search_console import GoogleSearchConsoleService

        service = gsc_service or GoogleSearchConsoleService(project=self.project)

        # Query both periods with dimensions=['query']
        base_data = service.query_search_analytics(
            start_date=base_start,
            end_date=base_end,
            dimensions=["query"],
            row_limit=row_limit
        )
        comp_data = service.query_search_analytics(
            start_date=comp_start,
            end_date=comp_end,
            dimensions=["query"],
            row_limit=row_limit
        )

        base_summary = base_data.get("summary", {})
        comp_summary = comp_data.get("summary", {})

        base_clicks = base_summary.get("total_clicks", 0)
        comp_clicks = comp_summary.get("total_clicks", 0)
        clicks_delta = base_clicks - comp_clicks
        clicks_change_pct = round(((clicks_delta / comp_clicks) * 100), 2) if comp_clicks > 0 else (100.0 if base_clicks > 0 else 0.0)

        base_impressions = base_summary.get("total_impressions", 0)
        comp_impressions = comp_summary.get("total_impressions", 0)
        impressions_delta = base_impressions - comp_impressions
        impressions_change_pct = round(((impressions_delta / comp_impressions) * 100), 2) if comp_impressions > 0 else (100.0 if base_impressions > 0 else 0.0)

        base_ctr = base_summary.get("average_ctr_percent", 0.0)
        comp_ctr = comp_summary.get("average_ctr_percent", 0.0)
        ctr_delta = round(base_ctr - comp_ctr, 2)

        base_pos = base_summary.get("average_position", 0.0)
        comp_pos = comp_summary.get("average_position", 0.0)
        pos_delta = round(base_pos - comp_pos, 1)  # Negative position delta means improvement (e.g. 5.0 -> 3.0 = -2.0)

        # Map queries across periods
        base_query_map = {r.get("query"): r for r in base_data.get("rows", []) if r.get("query")}
        comp_query_map = {r.get("query"): r for r in comp_data.get("rows", []) if r.get("query")}

        all_queries = set(base_query_map.keys()) | set(comp_query_map.keys())
        query_comparisons = []

        for q in all_queries:
            b_row = base_query_map.get(q)
            c_row = comp_query_map.get(q)

            b_c = b_row.get("clicks", 0) if b_row else 0
            c_c = c_row.get("clicks", 0) if c_row else 0
            b_i = b_row.get("impressions", 0) if b_row else 0
            c_i = c_row.get("impressions", 0) if c_row else 0
            b_p = b_row.get("position", 0.0) if b_row else None
            c_p = c_row.get("position", 0.0) if c_row else None

            c_diff = b_c - c_c
            i_diff = b_i - c_i
            p_diff = round(b_p - c_p, 1) if (b_p is not None and c_p is not None) else None

            query_comparisons.append({
                "query": q,
                "base_clicks": b_c,
                "comp_clicks": c_c,
                "clicks_delta": c_diff,
                "base_impressions": b_i,
                "comp_impressions": c_i,
                "impressions_delta": i_diff,
                "base_position": b_p,
                "comp_position": c_p,
                "position_delta": p_diff,
                "status": "retained" if (b_row and c_row) else ("new" if b_row else "lost")
            })

        # Top gainers and decliners by click delta
        top_gainers = sorted([q for q in query_comparisons if q["clicks_delta"] > 0], key=lambda x: x["clicks_delta"], reverse=True)[:10]
        top_decliners = sorted([q for q in query_comparisons if q["clicks_delta"] < 0], key=lambda x: x["clicks_delta"])[:10]
        lost_queries = [q for q in query_comparisons if q["status"] == "lost" and q["comp_clicks"] > 0][:10]
        new_queries = [q for q in query_comparisons if q["status"] == "new" and q["base_clicks"] > 0][:10]

        findings: List[GSCFinding] = []

        # Generate structured finding if overall clicks declined significantly (>15%)
        if clicks_change_pct <= -15.0 and comp_clicks >= 20:
            sev = 'critical' if clicks_change_pct <= -30.0 else 'warning'
            top_declining_names = [d["query"] for d in top_decliners[:3]]
            findings.append(GSCFinding(
                finding_type=GSCFindingType.PERIOD_COMPARISON_DECLINE,
                severity=sev,
                confidence=0.92,
                title=f"Organic Search Traffic Declined by {abs(clicks_change_pct)}% Period-over-Period",
                insight=(
                    f"Overall search clicks dropped from {comp_clicks} to {base_clicks} ({clicks_delta} clicks, {clicks_change_pct}%). "
                    f"Top declining queries: {', '.join(top_declining_names) if top_declining_names else 'multiple queries'}."
                ),
                recommendation=(
                    "1. Review landing pages associated with top declining queries for recent content changes or technical indexing issues.\n"
                    "2. Inspect competitor SERP positions to determine if rank was lost to new entrant content.\n"
                    "3. Conduct content freshness updates on affected high-impact landing pages."
                ),
                evidence=top_decliners[:5],
                metrics={
                    "base_clicks": base_clicks,
                    "comp_clicks": comp_clicks,
                    "clicks_change_pct": clicks_change_pct,
                    "impressions_change_pct": impressions_change_pct,
                    "ctr_delta": ctr_delta,
                    "position_delta": pos_delta
                },
                suggested_action_type="content_refresh"
            ))
        elif clicks_change_pct >= 20.0 and base_clicks >= 20:
            findings.append(GSCFinding(
                finding_type=GSCFindingType.PERIOD_COMPARISON_GAIN,
                severity='opportunity',
                confidence=0.88,
                title=f"Organic Search Traffic Grew by +{clicks_change_pct}% Period-over-Period",
                insight=f"Search clicks increased from {comp_clicks} to {base_clicks} (+{clicks_delta} clicks).",
                recommendation="Capitalize on search momentum by expanding internal links and topical depth to top gaining pages.",
                evidence=top_gainers[:5],
                metrics={
                    "base_clicks": base_clicks,
                    "comp_clicks": comp_clicks,
                    "clicks_change_pct": clicks_change_pct,
                    "impressions_change_pct": impressions_change_pct
                }
            ))

        return {
            "project_id": self.project.id,
            "base_period": {"start_date": base_start, "end_date": base_end},
            "comparison_period": {"start_date": comp_start, "end_date": comp_end},
            "summary_deltas": {
                "base_clicks": base_clicks,
                "comp_clicks": comp_clicks,
                "clicks_delta": clicks_delta,
                "clicks_change_percent": clicks_change_pct,
                "base_impressions": base_impressions,
                "comp_impressions": comp_impressions,
                "impressions_delta": impressions_delta,
                "impressions_change_percent": impressions_change_pct,
                "base_ctr_percent": base_ctr,
                "comp_ctr_percent": comp_ctr,
                "ctr_delta_percent": ctr_delta,
                "base_avg_position": base_pos,
                "comp_avg_position": comp_pos,
                "position_delta": pos_delta,
            },
            "top_gainers": top_gainers,
            "top_decliners": top_decliners,
            "lost_queries": lost_queries,
            "new_queries": new_queries,
            "total_queries_compared": len(query_comparisons),
            "findings": [f.to_dict() for f in findings]
        }

    # =========================================================================
    # PERSISTENCE & INTEGRATION WITH SEO INSIGHTS
    # =========================================================================

    def sync_findings_to_insights(self, findings: List[Dict[str, Any]]) -> List[SEOInsight]:
        """
        Idempotently create or update SEOInsight records in PostgreSQL from GSC findings.
        Enforces deduplication fingerprints to prevent redundant records across agent runs.
        """
        persisted = []

        type_mapping = {
            GSCFindingType.PAGE_TWO_OPPORTUNITY: InsightType.PAGE_TWO_KEYWORD,
            GSCFindingType.HIGH_IMPRESSIONS_LOW_CTR: InsightType.HIGH_IMPRESSIONS_LOW_CTR,
            GSCFindingType.KEYWORD_CANNIBALIZATION: InsightType.KEYWORD_CANNIBALIZATION,
            GSCFindingType.PERIOD_COMPARISON_DECLINE: InsightType.DECLINING_CLICKS,
            GSCFindingType.PERIOD_COMPARISON_GAIN: InsightType.RANKING_IMPROVEMENT,
            GSCFindingType.EMERGING_QUERY: InsightType.CONTENT_OPPORTUNITY,
        }

        severity_mapping = {
            'critical': InsightSeverity.CRITICAL,
            'warning': InsightSeverity.WARNING,
            'opportunity': InsightSeverity.OPPORTUNITY,
            'info': InsightSeverity.INFO,
        }

        for f in findings:
            f_type = f.get("finding_type", GSCFindingType.GENERAL_GSC_OPPORTUNITY)
            query = f.get("target_query") or ""
            url = f.get("target_url") or ""

            # Deterministic fingerprint for GSC findings
            fingerprint = f"gsc_{f_type}_{self.project.id}_{query[:50]}_{url[:50]}"

            insight_type = type_mapping.get(f_type, InsightType.CONTENT_OPPORTUNITY)
            severity = severity_mapping.get(f.get("severity", "info"), InsightSeverity.INFO)

            insight, _ = SEOInsight.objects.update_or_create(
                project=self.project,
                fingerprint=fingerprint,
                defaults={
                    "insight_type": insight_type,
                    "severity": severity,
                    "title": f.get("title", "GSC SEO Opportunity"),
                    "description": f.get("insight", ""),
                    "recommendation": f.get("recommendation", ""),
                    "source": InsightSource.SEARCH_CONSOLE,
                    "related_url": url,
                    "metadata": {
                        "confidence": f.get("confidence", 0.8),
                        "metrics": f.get("metrics", {}),
                        "evidence": f.get("evidence", []),
                        "suggested_action_type": f.get("suggested_action_type")
                    },
                    "status": InsightStatus.OPEN
                }
            )
            persisted.append(insight)

        return persisted

    # =========================================================================
    # HEURISTIC DETECTOR METHODS
    # =========================================================================

    def _safe_float(self, val: Any, default: float = 0.0) -> float:
        """Safely convert value to float without raising ValueError or TypeError."""
        try:
            return float(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    def _safe_int(self, val: Any, default: int = 0) -> int:
        """Safely convert value to int without raising ValueError or TypeError."""
        try:
            return int(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    def _detect_page_two_opportunities(
        self,
        query_rows: List[Dict[str, Any]],
        min_impressions: int
    ) -> List[GSCFinding]:
        """Identify queries ranking on Page 2 (Positions 10.1 - 20.0) with notable search impressions."""
        findings = []
        for r in query_rows:
            if not isinstance(r, dict):
                continue
            pos = self._safe_float(r.get("position"))
            imp = self._safe_int(r.get("impressions"))
            clicks = self._safe_int(r.get("clicks"))
            ctr_pct = self._safe_float(r.get("ctr_percent"))
            query = r.get("query")

            if not query or not (10.1 <= pos <= 20.0) or imp < min_impressions:
                continue

            # Confidence scales with impression volume
            confidence = min(0.95, 0.70 + (min(imp, 500) / 2000.0))

            findings.append(GSCFinding(
                finding_type=GSCFindingType.PAGE_TWO_OPPORTUNITY,
                severity='opportunity',
                confidence=confidence,
                title=f"Page 2 Opportunity: \"{query}\" (Rank #{round(pos, 1)}, {imp} Impressions)",
                insight=(
                    f"Query \"{query}\" is ranking on page 2 at position #{round(pos, 1)} with {imp} search impressions. "
                    f"Moving this query into the top 10 yields the highest ROI for organic click growth."
                ),
                recommendation=(
                    f"1. Update the primary landing page H1 and H2 headings to include \"{query}\" naturally.\n"
                    f"2. Add dedicated FAQ or body copy answering specific search questions for \"{query}\".\n"
                    f"3. Create internal links from 2-3 high-authority blog posts with relevant anchor text."
                ),
                evidence=[r],
                metrics={
                    "query": query,
                    "position": pos,
                    "impressions": imp,
                    "clicks": clicks,
                    "ctr_percent": ctr_pct
                },
                suggested_action_type="optimize_existing_content",
                target_query=query
            ))
        return findings

    def _detect_high_impressions_low_ctr(
        self,
        query_rows: List[Dict[str, Any]],
        min_impressions: int
    ) -> List[GSCFinding]:
        """Identify high-impression queries underperforming in SERP CTR against position benchmarks."""
        findings = []
        for r in query_rows:
            if not isinstance(r, dict):
                continue
            pos = self._safe_float(r.get("position"))
            imp = self._safe_int(r.get("impressions"))
            clicks = self._safe_int(r.get("clicks"))
            ctr = self._safe_float(r.get("ctr"))
            ctr_pct = self._safe_float(r.get("ctr_percent"))
            query = r.get("query")

            if not query or imp < max(min_impressions, 20):
                continue

            benchmark = None
            if 1.0 <= pos <= 3.0:
                benchmark = CTR_BENCHMARKS["top_3"]
            elif 3.1 <= pos <= 10.0:
                benchmark = CTR_BENCHMARKS["page_1"]

            if benchmark and ctr < (benchmark * 0.6):  # Underperforming by >40% vs benchmark
                confidence = min(0.92, 0.75 + (min(imp, 1000) / 4000.0))
                findings.append(GSCFinding(
                    finding_type=GSCFindingType.HIGH_IMPRESSIONS_LOW_CTR,
                    severity='warning',
                    confidence=confidence,
                    title=f"SERP Snippet Underperformance for \"{query}\" ({imp} Imp, {ctr_pct}% CTR)",
                    insight=(
                        f"Query \"{query}\" ranks in the top 10 at #{round(pos, 1)} with {imp} impressions, but only achieves {ctr_pct}% CTR "
                        f"(expected benchmark: >={round(benchmark * 100, 1)}%). Searchers are choosing competing snippets."
                    ),
                    recommendation=(
                        f"1. Rewrite meta title to feature \"{query}\" with a compelling value proposition in the first 40 characters.\n"
                        f"2. Craft an actionable meta description (140-155 characters) with a clear call-to-action.\n"
                        f"3. Add structured data schema markup (FAQPage / Article) for rich snippet SERP real-estate."
                    ),
                    evidence=[r],
                    metrics={
                        "query": query,
                        "position": pos,
                        "impressions": imp,
                        "clicks": clicks,
                        "ctr_percent": ctr_pct,
                        "expected_ctr_percent": round(benchmark * 100, 1)
                    },
                    suggested_action_type="update_meta_description",
                    target_query=query
                ))
        return findings

    def _detect_keyword_cannibalization(
        self,
        combined_rows: List[Dict[str, Any]],
        min_impressions: int
    ) -> List[GSCFinding]:
        """Detect queries where multiple landing pages rank simultaneously, diluting topical authority."""
        findings = []
        if not combined_rows:
            return findings

        # Group pages by query
        query_pages: Dict[str, List[Dict[str, Any]]] = {}
        for r in combined_rows:
            if not isinstance(r, dict):
                continue
            q = r.get("query")
            p = r.get("page")
            if q and p:
                if q not in query_pages:
                    query_pages[q] = []
                query_pages[q].append(r)

        for q, rows in query_pages.items():
            if len(rows) < 2:
                continue

            total_imp = sum(self._safe_int(r.get("impressions")) for r in rows)
            if total_imp < max(min_impressions, 15):
                continue

            unique_pages = list(set(r.get("page") for r in rows if r.get("page")))
            if len(unique_pages) >= 2:
                sorted_pages = sorted(rows, key=lambda x: self._safe_int(x.get("clicks")), reverse=True)
                primary_page = sorted_pages[0].get("page")
                secondary_pages = [r.get("page") for r in sorted_pages[1:3]]

                findings.append(GSCFinding(
                    finding_type=GSCFindingType.KEYWORD_CANNIBALIZATION,
                    severity='warning',
                    confidence=0.85,
                    title=f"Keyword Cannibalization Detected for \"{q}\" ({len(unique_pages)} competing pages)",
                    insight=(
                        f"Multiple landing pages are competing for query \"{q}\": primary page {primary_page} "
                        f"and competing pages ({', '.join(secondary_pages)}). This splits domain link equity and search signals."
                    ),
                    recommendation=(
                        f"1. Choose the definitive canonical URL for \"{q}\".\n"
                        f"2. Add canonical tag from secondary pages to the primary asset, or add internal link pointing to primary.\n"
                        f"3. Differentiate secondary pages to target distinct sub-topics."
                    ),
                    evidence=rows[:4],
                    metrics={
                        "query": q,
                        "competing_pages_count": len(unique_pages),
                        "total_impressions": total_imp,
                        "primary_page": primary_page
                    },
                    suggested_action_type="technical_seo_fix",
                    target_query=q,
                    target_url=primary_page
                ))
        return findings

    def _detect_emerging_queries(
        self,
        query_rows: List[Dict[str, Any]],
        min_impressions: int
    ) -> List[GSCFinding]:
        """Identify emerging long-tail queries demonstrating early high CTR engagement."""
        findings = []
        for r in query_rows:
            if not isinstance(r, dict):
                continue
            pos = self._safe_float(r.get("position"))
            imp = self._safe_int(r.get("impressions"))
            clicks = self._safe_int(r.get("clicks"))
            ctr_pct = self._safe_float(r.get("ctr_percent"))
            query = r.get("query")

            if not query or imp < min_impressions or clicks < 2:
                continue

            # High CTR (>= 10%) on position 4-15 indicates strong user interest for long-tail
            if pos >= 4.0 and ctr_pct >= 10.0:
                findings.append(GSCFinding(
                    finding_type=GSCFindingType.EMERGING_QUERY,
                    severity='opportunity',
                    confidence=0.80,
                    title=f"High-Intent Emerging Query: \"{query}\" ({ctr_pct}% CTR at Pos #{round(pos, 1)})",
                    insight=(
                        f"Query \"{query}\" is achieving outstanding engagement ({ctr_pct}% CTR) despite ranking at position #{round(pos, 1)}. "
                        f"Expanding dedicated content for this topic will capture untapped search demand."
                    ),
                    recommendation=(
                        f"1. Synthesize a focused content brief targeting \"{query}\".\n"
                        f"2. Publish or expand a dedicated section answering user questions for this query."
                    ),
                    evidence=[r],
                    metrics={
                        "query": query,
                        "position": pos,
                        "impressions": imp,
                        "clicks": clicks,
                        "ctr_percent": ctr_pct
                    },
                    suggested_action_type="publish_new_content",
                    target_query=query
                ))
        return findings

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _fetch_default_analytics(self, gsc_service: Optional[Any] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Fetch default 28-day analytics for automated opportunity detection."""
        from apps.seo.services.google_search_console import GoogleSearchConsoleService

        service = gsc_service or GoogleSearchConsoleService(project=self.project)
        today = timezone.now().date()
        end_date = (today - timedelta(days=2)).strftime('%Y-%m-%d')
        start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')

        try:
            query_data = service.get_top_queries(start_date=start_date, end_date=end_date, limit=50)
            query_rows = query_data.get("top_queries", [])
        except Exception as exc:
            logger.warning(f"[GSCIntelligenceService] Could not fetch top queries for project #{self.project.id}: {exc}")
            query_rows = []

        try:
            combined_data = service.query_search_analytics(
                start_date=start_date,
                end_date=end_date,
                dimensions=["query", "page"],
                row_limit=50
            )
            combined_rows = combined_data.get("rows", [])
        except Exception as exc:
            logger.warning(f"[GSCIntelligenceService] Could not fetch combined query-page data for project #{self.project.id}: {exc}")
            combined_rows = []

        return query_rows, combined_rows
