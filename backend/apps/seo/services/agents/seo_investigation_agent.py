"""
DoxaRank Specialized SEO Agents — Investigation Agent (Phase 4.7)

Responsible for diagnosing root causes, determining search performance anomalies,
assessing diagnostic certainty, and identifying affected pages and queries.
Reuses the proven deterministic SEOInvestigationService.
"""

import logging
from typing import Dict, Any, List
from .base_agent import BaseSpecializedAgent, AgentResult, SharedContext
from apps.seo.services.seo_investigation import SEOInvestigationService

logger = logging.getLogger(__name__)


class SEOInvestigationAgent(BaseSpecializedAgent):
    """
    SEO Investigation Agent.
    Executes cross-source correlation and deterministic root-cause diagnosis.
    Allowed Tools: Diagnostic, correlation, and opportunity investigation tools.
    """

    name: str = "seo_investigator"
    purpose: str = "Diagnose root causes, identify ranking/traffic drivers, and evaluate diagnostic certainty."

    allowed_tools: List[str] = [
        "get_gsc_performance",
        "get_gsc_queries",
        "get_gsc_pages",
        "analyze_gsc_performance",
        "get_site_audit_summary",
        "get_audit_issues",
        "analyze_seo_opportunities",
        "investigate_seo_opportunity",
        "get_action_outcomes",
        "get_adaptive_seo_strategy",
        "mcp__seo_local__check_url_status",
        "mcp__seo_local__get_page_metadata",
        "mcp__seo_local__get_external_page_signals"
    ]

    def _execute(self, context: SharedContext) -> AgentResult:
        findings: List[str] = []
        investigation_records: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []

        service = SEOInvestigationService(project=self.project, publisher=self.publisher)

        # 1. If target URL or opportunity type provided in context, investigate directly
        if context.target_url or context.target_query:
            inv = service.investigate(
                opportunity_type="ranking_anomaly" if not context.task_type else context.task_type,
                target_url=context.target_url or self.project.website_url,
                target_query=context.target_query,
                run_id=None
            )
            inv_dict = inv.to_dict()
            investigation_records.append(inv_dict)
            cause_label = inv.root_cause_category or (inv.inferred_root_causes[0] if inv.inferred_root_causes else "UNKNOWN")
            findings.append(
                f"Investigated {inv.target_url}: Root cause classified as '{cause_label}' "
                f"({inv.confidence_level.upper()} certainty, confidence {round(inv.confidence_score*100)}%)."
            )
            if inv.recommendations:
                recommendations.extend(inv.recommendations)

        # 2. Correlate cross-source opportunities across GSC and site audit
        try:
            opp_res = self.execute_tool("analyze_seo_opportunities", {"limit": 5})
            if opp_res.get("success") and opp_res.get("data"):
                opps = opp_res["data"].get("opportunities", [])
                for opp in opps[:3]:
                    inv = service.investigate(
                        opportunity_type=opp.get("opportunity_type", "underperforming_serp_snippet"),
                        target_url=opp.get("page", self.project.website_url),
                        target_query=opp.get("query", ""),
                        run_id=None
                    )
                    inv_dict = inv.to_dict()
                    investigation_records.append(inv_dict)
                    cause_label = inv.root_cause_category or (inv.inferred_root_causes[0] if inv.inferred_root_causes else "UNKNOWN")
                    findings.append(
                        f"Opportunity '{opp.get('opportunity_type')}': Page {inv.target_url} — "
                        f"Root Cause: '{cause_label}'."
                    )
                    if inv.recommendations:
                        recommendations.extend(inv.recommendations)
        except Exception as exc:
            logger.warning(f"[{self.name}] Cross-source opportunity analysis failed: {exc}")

        # Update shared context
        context.investigation_findings.extend(investigation_records)

        # Compute average confidence across investigations
        if investigation_records:
            avg_conf = sum(inv.get("confidence_score", 0.70) for inv in investigation_records) / len(investigation_records)
        else:
            avg_conf = 0.50
            findings.append("No definitive anomalies or opportunities detected during investigation.")

        return AgentResult(
            agent=self.name,
            status="completed",
            confidence=round(avg_conf, 4),
            evidence={"investigations": investigation_records},
            findings=findings,
            recommendations=recommendations,
            next_step="strategy",
            metadata={"investigations_count": len(investigation_records)}
        )
