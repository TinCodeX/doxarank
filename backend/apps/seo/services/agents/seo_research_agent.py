"""
DoxaRank Specialized SEO Agents — Research & Evidence Agent (Phase 4.7)

Responsible for gathering multi-source empirical SEO data across Google Search Console,
site audit diagnostics, keyword rankings, and historical outcomes. Strictly read-only.
"""

import logging
from typing import Dict, Any, List
from .base_agent import BaseSpecializedAgent, AgentResult, SharedContext

logger = logging.getLogger(__name__)


class SEOResearchAgent(BaseSpecializedAgent):
    """
    SEO Research & Evidence Agent.
    Gathers multi-source evidence without performing any mutations.
    Allowed Tools: READ_ONLY diagnostic and performance retrieval tools.
    """

    name: str = "seo_researcher"
    purpose: str = "Gather empirical performance, ranking, audit diagnostics, and historical evidence."

    allowed_tools: List[str] = [
        "get_gsc_performance",
        "get_gsc_queries",
        "get_gsc_pages",
        "analyze_gsc_performance",
        "get_keyword_rankings",
        "get_ranking_history",
        "get_tracked_keywords",
        "get_site_audit_summary",
        "get_audit_issues",
        "get_action_outcomes",
        "get_adaptive_seo_strategy",
        "mcp__seo_local__check_url_status",
        "mcp__seo_local__get_page_metadata",
        "mcp__seo_local__get_external_page_signals"
    ]

    def _execute(self, context: SharedContext) -> AgentResult:
        findings: List[str] = []
        evidence_collected: Dict[str, Any] = {}

        # 1. Gather GSC Performance Data
        try:
            gsc_res = self.execute_tool(
                "get_gsc_performance",
                {"days": 28, "page": context.target_url}
            )
            if gsc_res.get("success") and gsc_res.get("data"):
                data = gsc_res["data"]
                evidence_collected["gsc_performance"] = data
                clicks = data.get("total_clicks", 0)
                imps = data.get("total_impressions", 0)
                ctr = data.get("average_ctr", 0.0)
                pos = data.get("average_position", 0.0)
                findings.append(
                    f"Google Search Console: {clicks:,} clicks, {imps:,} impressions, "
                    f"{round(ctr*100, 2)}% CTR, position #{round(pos, 1)} over past 28 days."
                )
        except Exception as exc:
            logger.warning(f"[{self.name}] GSC performance collection failed: {exc}")

        # 2. Gather Top Queries / Pages if specific target provided
        if context.target_url:
            try:
                queries_res = self.execute_tool(
                    "get_gsc_queries",
                    {"page": context.target_url, "limit": 10}
                )
                if queries_res.get("success") and queries_res.get("data"):
                    evidence_collected["top_queries"] = queries_res["data"]
                    findings.append(f"Retrieved {len(queries_res['data'])} active search queries for {context.target_url}.")
            except Exception as exc:
                logger.warning(f"[{self.name}] Top queries collection failed: {exc}")

            # 2b. External MCP Diagnostics (check URL status & metadata)
            try:
                mcp_status = self.execute_tool(
                    "mcp__seo_local__check_url_status",
                    {"url": context.target_url}
                )
                if mcp_status.get("success") and mcp_status.get("data"):
                    st_data = mcp_status["data"]
                    inner = st_data.get("data", st_data)
                    evidence_collected["mcp_url_status"] = inner
                    code = inner.get("status_code", "N/A")
                    findings.append(f"MCP External Diagnostics: URL status HTTP {code} (latency {inner.get('latency_ms', 0)}ms).")
            except Exception as exc:
                logger.warning(f"[{self.name}] MCP status check skipped: {exc}")

        # 3. Gather Site Audit Diagnostics
        try:
            audit_res = self.execute_tool("get_site_audit_summary", {})
            if audit_res.get("success") and audit_res.get("data"):
                audit_data = audit_res["data"]
                evidence_collected["audit_summary"] = audit_data
                crit_issues = audit_data.get("critical_issues_count", 0)
                warn_issues = audit_data.get("warning_issues_count", 0)
                findings.append(
                    f"Site Audit: Health score {audit_data.get('health_score', 'N/A')}/100 "
                    f"with {crit_issues} critical and {warn_issues} warning issues."
                )
        except Exception as exc:
            logger.warning(f"[{self.name}] Audit summary collection failed: {exc}")

        # 4. Gather Historical Action Outcomes & Strategy Baseline
        try:
            strat_res = self.execute_tool("get_adaptive_seo_strategy", {})
            if strat_res.get("success") and strat_res.get("data"):
                strat_data = strat_res["data"]
                evidence_collected["historical_strategy"] = strat_data
                sample_size = strat_data.get("historical_sample_size", 0)
                conf = strat_data.get("strategy_confidence", "none")
                findings.append(
                    f"Historical Outcomes: {sample_size} past actions measured ({conf.upper()} domain confidence)."
                )
        except Exception as exc:
            logger.warning(f"[{self.name}] Historical strategy collection failed: {exc}")

        # Merge evidence into shared context
        context.evidence.update(evidence_collected)

        confidence = 0.90 if len(evidence_collected) >= 2 else 0.60

        return AgentResult(
            agent=self.name,
            status="completed",
            confidence=confidence,
            evidence=evidence_collected,
            findings=findings,
            recommendations=[],
            next_step="investigation",
            metadata={"evidence_sources": list(evidence_collected.keys())}
        )
