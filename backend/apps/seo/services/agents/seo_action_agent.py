"""
DoxaRank Specialized SEO Agents — Action Planning Agent (Phase 4.7)

Responsible for translating strategic recommendations into structured, deduplicated
SEOActionPlan and SEOAction records with deterministic risk classification.
Strictly preserves human-in-the-loop approval gating (requires_human_approval = True).
Reuses SEOActionPlanner.
"""

import logging
from typing import Dict, Any, List
from .base_agent import BaseSpecializedAgent, AgentResult, SharedContext
from apps.seo.services.seo_action_planner import SEOActionPlanner
from apps.seo.models import SEOAction, SEOActionPlan, ActionStatus, ActionPlanStatus

logger = logging.getLogger(__name__)


class SEOActionPlanningAgent(BaseSpecializedAgent):
    """
    SEO Action Planning Agent.
    Creates formal action proposals and plan structures.
    Allowed Tools: Planning and proposal tools.
    Safety Invariant: Every proposed action requires human approval.
    """

    name: str = "seo_action_planner"
    purpose: str = "Synthesize structured action plans and proposals with strict human approval governance."

    allowed_tools: List[str] = [
        "plan_seo_actions",
        "get_action_plan",
        "propose_seo_action",
        "get_action",
        "preview_action"
    ]

    def _execute(self, context: SharedContext) -> AgentResult:
        findings: List[str] = []
        proposals_summary: List[Dict[str, Any]] = []

        planner = SEOActionPlanner(project=self.project, publisher=self.publisher)

        # 1. Synthesize plan from investigations in context or site baseline
        investigation_objs = []
        # If there are investigations in context, retrieve or construct them
        if context.investigation_findings:
            try:
                from apps.seo.services.seo_investigation import SEOInvestigationResult
                for inv in context.investigation_findings:
                    if isinstance(inv, SEOInvestigationResult):
                        investigation_objs.append(inv)
            except Exception:
                pass

        plan = planner.create_action_plan(
            title=f"Autonomous Plan: {context.task_goal or 'SEO Strategy Execution'}"[:255],
            summary=f"Formulated by {self.name} based on multi-source research and empirical strategy.",
            investigations=investigation_objs if investigation_objs else None,
            user=self.user,
            max_actions=10,
            run_id=None
        )

        context.created_plan_id = plan.id
        context.action_plan_id = plan.id
        actions = plan.actions.all()

        findings.append(
            f"Created SEOActionPlan #{plan.id} ('{plan.title}') containing {actions.count()} actions. "
            f"Risk Level: {plan.risk_level.upper()}, Confidence: {round(plan.confidence_score*100)}%."
        )

        for act in actions:
            # SAFETY INVARIANT: Verify server-side that approval is required
            assert act.requires_human_approval is True, f"Security Violation: Action #{act.id} missing human approval gate!"

            act_summary = {
                "id": act.id,
                "title": act.title,
                "action_type": act.action_type,
                "target_url": act.target_url,
                "priority": act.priority,
                "risk_level": act.risk_level,
                "requires_human_approval": act.requires_human_approval,
                "status": act.status
            }
            proposals_summary.append(act_summary)
            findings.append(
                f"- [Action #{act.id}] {act.action_type}: '{act.title}' "
                f"({act.priority.upper()} priority, {act.risk_level.upper()} risk) -> PENDING HUMAN APPROVAL."
            )

        context.action_proposals.extend(proposals_summary)

        return AgentResult(
            agent=self.name,
            status="completed",
            confidence=plan.confidence_score,
            evidence={
                "plan_id": plan.id,
                "plan_title": plan.title,
                "actions_count": len(proposals_summary),
                "risk_level": plan.risk_level,
                "requires_human_approval": plan.requires_human_approval
            },
            findings=findings,
            recommendations=proposals_summary,
            next_step="human_approval",
            metadata={
                "plan_id": plan.id,
                "requires_human_approval": True
            }
        )
