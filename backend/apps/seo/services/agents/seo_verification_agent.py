"""
DoxaRank Specialized SEO Agents — Verification & Outcome Agent (Phase 4.7)

Responsible for verifying live website state post-deployment and measuring
deterministic search performance lift via Google Search Console.
Reuses SEOActionVerifier and SEOOutcomeMeasurementService.
"""

import logging
from typing import Dict, Any, List
from .base_agent import BaseSpecializedAgent, AgentResult, SharedContext
from apps.seo.services.seo_action_verifier import SEOActionVerifier
from apps.seo.services.seo_outcome_learning import SEOOutcomeMeasurementService
from apps.seo.models import SEOAction, SEOActionPlan, ActionStatus, VerificationStatus

logger = logging.getLogger(__name__)


class SEOVerificationAgent(BaseSpecializedAgent):
    """
    SEO Verification & Outcome Agent.
    Empirically verifies live changes and deterministically measures search outcome lift.
    Allowed Tools: Verification and outcome tools.
    """

    name: str = "seo_verifier"
    purpose: str = "Verify live website modifications and measure empirical GSC outcome lift."

    allowed_tools: List[str] = [
        "verify_seo_action",
        "verify_action_plan",
        "get_action_outcomes"
    ]

    def _execute(self, context: SharedContext) -> AgentResult:
        findings: List[str] = []
        verifications: Dict[str, Any] = {}
        outcome_results: Dict[str, Any] = {}

        verifier = SEOActionVerifier(project=self.project, publisher=self.publisher)
        outcome_service = SEOOutcomeMeasurementService(project=self.project, publisher=self.publisher)

        # 1. Verify specific plan if created in context
        target_plan = None
        if context.created_plan_id:
            target_plan = SEOActionPlan.objects.filter(id=context.created_plan_id, project=self.project).first()

        if not target_plan:
            # Check for latest approved/completed plan
            target_plan = SEOActionPlan.objects.filter(
                project=self.project
            ).exclude(status=ActionStatus.CANCELLED).order_by('-updated_at').first()

        if target_plan:
            plan_verif = verifier.verify_plan(target_plan)
            verifications["plan_verification"] = plan_verif
            verified_count = plan_verif.get("verified_actions_count", 0)
            failed_count = plan_verif.get("failed_actions_count", 0)
            findings.append(
                f"Verified ActionPlan #{target_plan.id}: {verified_count} verified, "
                f"{failed_count} unverified out of {plan_verif.get('total_actions_count', 0)} actions."
            )

            # Measure plan outcome if actions are completed
            try:
                outcome_summary = outcome_service.measure_plan_outcome(target_plan, window_days=14)
                outcome_results["plan_outcome"] = outcome_summary
                findings.append(
                    f"Plan Outcome Measurement: {outcome_summary.get('improved', 0)} improved, "
                    f"{outcome_summary.get('no_change', 0)} neutral, {outcome_summary.get('declined', 0)} declined "
                    f"({outcome_summary.get('plan_outcome', 'UNKNOWN').upper()})."
                )
            except Exception as exc:
                logger.warning(f"[{self.name}] Plan outcome measurement skipped: {exc}")

        # 2. Check for individual completed actions awaiting measurement
        completed_actions = SEOAction.objects.filter(
            project=self.project,
            status=ActionStatus.COMPLETED
        ).order_by('-completed_at')[:5]

        for act in completed_actions:
            if act.verification_status == VerificationStatus.PENDING:
                act_verif = verifier.verify_action(act)
                verifications[f"action_{act.id}"] = act_verif.to_dict()

            if not act.outcome_measured_at:
                try:
                    act_outcome = outcome_service.measure_action_outcome(act, window_days=14)
                    outcome_results[f"action_{act.id}"] = act_outcome.to_dict()
                    findings.append(
                        f"Action #{act.id} ({act.action_type}): Classified as {act_outcome.outcome.value.upper()} "
                        f"(confidence {round(act_outcome.confidence_score*100)}%)."
                    )
                except Exception as exc:
                    logger.warning(f"[{self.name}] Action outcome measurement skipped for #{act.id}: {exc}")

        context.verification_results.update(verifications)
        context.outcome_measurements.update(outcome_results)

        if not findings:
            findings.append("No active or completed actions required verification or measurement.")

        return AgentResult(
            agent=self.name,
            status="completed",
            confidence=0.90 if verifications or outcome_results else 0.50,
            evidence={
                "verifications": verifications,
                "outcomes": outcome_results
            },
            findings=findings,
            recommendations=[],
            next_step="completed",
            metadata={
                "verified_items": len(verifications),
                "measured_outcomes": len(outcome_results)
            }
        )
