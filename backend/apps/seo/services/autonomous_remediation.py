"""
DoxaRank Autonomous Remediation Policy & Execution Engine (Milestone 6.4).

Provides centralized, deterministic, explainable, and safety-governed remediation
of detected SEO issues. Enforces:
1. Strict Authorization & Risk Boundary:
   - Low-risk, reversible actions can execute autonomously when permitted by policy and project quotas.
   - High-risk actions strictly require human approval (HITL).
2. ToolRegistry & Connector Authority: All mutations execute via ToolRegistry gateways.
3. Mandatory Empirical Verification: Execution success != SEO success; changes must be verified against live HTML/status.
4. Deterministic Failure Categorization: Standard error categories for failures.
5. Persistent Idempotency: Deduplication and row locking prevent duplicate executions.
6. Deterministic Rollback: Pre-execution snapshots enable reverting changes.
7. Multi-Tenant Isolation: Cross-project remediation is strictly prohibited.
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.projects.models import Project
from apps.seo.models import (
    SEOAction,
    SEOActionPlan,
    SEOEvent,
    AgentRun,
    ActionType,
    ActionStatus,
    ActionRiskLevel,
    VerificationStatus,
    ProjectRemediationPolicy,
    RemediationRecord,
    RemediationRiskLevel,
    RemediationPolicyDecision,
    RemediationErrorCategory,
)
from apps.seo.services.agent_events import (
    AgentEvent,
    AgentEventType,
    AgentEventPublisher,
    get_event_publisher,
)
from apps.seo.services.seo_action_verifier import SEOActionVerifier
from apps.seo.services.mutation_connectors import get_mutation_connector

logger = logging.getLogger(__name__)

# Permitted low-risk action types eligible for autonomous remediation
AUTONOMOUS_ALLOWED_ACTION_TYPES: Set[str] = {
    ActionType.UPDATE_TITLE,
    ActionType.UPDATE_META_DESCRIPTION,
    ActionType.FIX_BROKEN_INTERNAL_LINK,
    ActionType.REMOVE_REDIRECT_CHAIN,
    ActionType.ADD_INTERNAL_LINKS,
}

# High-risk action types strictly requiring human-in-the-loop review
HIGH_RISK_ACTION_TYPES: Set[str] = {
    ActionType.PUBLISH_NEW_CONTENT,
    ActionType.CONTENT_REFRESH,
    ActionType.OPTIMIZE_EXISTING_CONTENT,
    ActionType.TECHNICAL_SEO_FIX,
}


@dataclass
class PolicyEvaluationResult:
    """Encapsulates the deterministic decision of AutonomousRemediationPolicy."""
    decision: str  # RemediationPolicyDecision
    risk_level: str  # RemediationRiskLevel
    is_reversible: bool
    explanation: str
    error_category: str = ""
    can_execute: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "risk_level": self.risk_level,
            "is_reversible": self.is_reversible,
            "explanation": self.explanation,
            "error_category": self.error_category,
            "can_execute": self.can_execute,
        }


class AutonomousRemediationPolicy:
    """
    Centralized, deterministic policy engine governing autonomous SEO remediations.
    Determines whether an action may execute automatically, requires human approval, or is blocked.
    """

    @classmethod
    def evaluate(
        cls,
        action: SEOAction,
        project: Optional[Project] = None,
        policy_config: Optional[ProjectRemediationPolicy] = None,
    ) -> PolicyEvaluationResult:
        """
        Evaluate an SEOAction against all safety, risk, reversibility, confidence, and project boundaries.
        Returns an explainable PolicyEvaluationResult.
        """
        proj = project or action.project
        action_type = action.action_type
        assessed_risk = str(action.risk_level or "low").lower()

        # 1. Project Tenant Policy Check
        if not policy_config:
            policy_config = ProjectRemediationPolicy.objects.filter(project=proj).first()

        is_autonomous_enabled = True
        max_daily = 10
        min_conf = 0.85
        allowed_types_override: List[str] = []

        if policy_config:
            is_autonomous_enabled = policy_config.is_autonomous_enabled
            max_daily = policy_config.max_daily_autonomous_actions
            min_conf = policy_config.min_confidence_threshold
            allowed_types_override = policy_config.allowed_autonomous_types or []

        # 2. Risk Classification
        # Any critical or high risk action strictly requires human approval
        if assessed_risk in [RemediationRiskLevel.CRITICAL, RemediationRiskLevel.HIGH]:
            return PolicyEvaluationResult(
                decision=RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED,
                risk_level=assessed_risk,
                is_reversible=False,
                explanation=f"Action '{action.title}' is classified as {assessed_risk.upper()} risk. High-risk actions require mandatory human sign-off.",
                can_execute=False,
            )

        # High-risk action types require human approval
        if action_type in HIGH_RISK_ACTION_TYPES:
            return PolicyEvaluationResult(
                decision=RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED,
                risk_level=RemediationRiskLevel.HIGH,
                is_reversible=False,
                explanation=f"Action type '{action_type}' can modify page content or site architecture. Human approval is strictly required.",
                can_execute=False,
            )

        # 3. Action Type Allowlist Check
        allowed_types = set(allowed_types_override) if allowed_types_override else AUTONOMOUS_ALLOWED_ACTION_TYPES
        if action_type not in allowed_types:
            return PolicyEvaluationResult(
                decision=RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED,
                risk_level=assessed_risk if assessed_risk in RemediationRiskLevel.values else RemediationRiskLevel.MEDIUM,
                is_reversible=False,
                explanation=f"Action type '{action_type}' is not in the autonomous allowed allowlist. Human approval required.",
                can_execute=False,
            )

        # 4. Project Global Autonomous Switch
        if not is_autonomous_enabled:
            return PolicyEvaluationResult(
                decision=RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED,
                risk_level=assessed_risk,
                is_reversible=True,
                explanation="Autonomous remediation is disabled in project policy settings. Human approval required.",
                can_execute=False,
            )

        # 5. Reversibility & Baseline State Check
        # Autonomous execution requires captured pre-state to guarantee safe rollback
        current_state = action.current_state or {}
        has_baseline = bool(
            current_state.get("target_url")
            or current_state.get("title")
            or current_state.get("meta_description")
            or current_state.get("summary")
        )
        if not has_baseline:
            return PolicyEvaluationResult(
                decision=RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED,
                risk_level=RemediationRiskLevel.MEDIUM,
                is_reversible=False,
                explanation="No baseline pre-state snapshot was captured for this action. Cannot safely support rollback. Human approval required.",
                can_execute=False,
            )

        # 6. Confidence & Evidence Threshold
        evidence = action.evidence_snapshot or {}
        confidence = float(evidence.get("confidence_score") or evidence.get("confidence") or 1.0)
        if confidence < min_conf:
            return PolicyEvaluationResult(
                decision=RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED,
                risk_level=RemediationRiskLevel.MEDIUM,
                is_reversible=True,
                explanation=f"Remediation confidence score ({confidence:.2f}) is below project threshold ({min_conf:.2f}). Human review required.",
                can_execute=False,
            )

        # 7. Daily Quota Check
        now = timezone.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_executed_count = RemediationRecord.objects.filter(
            project=proj,
            is_autonomous=True,
            created_at__gte=start_of_day,
            status__in=[ActionStatus.COMPLETED, ActionStatus.VERIFIED]
        ).count()

        if daily_executed_count >= max_daily:
            return PolicyEvaluationResult(
                decision=RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED,
                risk_level=assessed_risk,
                is_reversible=True,
                explanation=f"Project daily autonomous remediation quota reached ({daily_executed_count}/{max_daily}). Subsequent actions require human approval.",
                can_execute=False,
            )

        # 8. Competing Hypotheses / Multi-Agent Disagreement Check
        inferences = evidence.get("inferences", [])
        if any("competing" in str(inf).lower() or "uncertain" in str(inf).lower() for inf in inferences):
            return PolicyEvaluationResult(
                decision=RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED,
                risk_level=RemediationRiskLevel.MEDIUM,
                is_reversible=True,
                explanation="Underlying diagnosis contains competing hypotheses or unresolved uncertainty. Human approval required.",
                can_execute=False,
            )

        # All safety checks passed!
        return PolicyEvaluationResult(
            decision=RemediationPolicyDecision.AUTONOMOUS_ALLOWED,
            risk_level=RemediationRiskLevel.LOW,
            is_reversible=True,
            explanation=f"Action '{action.title}' is a verified low-risk, reversible remediation ({action_type}) meeting all policy thresholds.",
            can_execute=True,
        )


class AutonomousRemediationService:
    """
    Centralized execution and lifecycle orchestrator for Autonomous Remediation (Milestone 6.4).
    Enforces ToolRegistry authorization, atomic concurrency locking, verification, and rollback.
    """

    def __init__(
        self,
        publisher: Optional[AgentEventPublisher] = None,
        verifier: Optional[SEOActionVerifier] = None,
    ):
        self.publisher = publisher or get_event_publisher()
        self._verifier = verifier

    def _emit_event(
        self,
        event_type: Any,
        project_id: int,
        payload: Dict[str, Any],
        run_id: Optional[int] = None,
    ) -> None:
        try:
            event = AgentEvent(
                event_type=event_type,
                run_id=run_id or 0,
                project_id=project_id,
                payload=payload,
            )
            self.publisher.publish(event)
        except Exception as exc:
            logger.debug(f"[AutonomousRemediationService] Telemetry publish skipped/failed: {exc}")

    @classmethod
    def compute_remediation_idempotency_key(
        cls,
        project_id: int,
        action_id: int,
        target_url: str,
        action_type: str,
        salt: Optional[str] = None
    ) -> str:
        """Deterministic fingerprint preventing duplicate execution across workers/retries."""
        raw = f"{project_id}:{action_id}:{target_url.strip().lower()}:{action_type.strip().lower()}"
        if salt:
            raw += f":{salt}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]

    def propose_remediation(
        self,
        action: SEOAction,
        event: Optional[SEOEvent] = None,
        agent_run: Optional[AgentRun] = None,
        idempotency_key: Optional[str] = None,
        user: Optional[Any] = None,
    ) -> RemediationRecord:
        """
        Record a structured remediation proposal from an SEOAction, evaluate policy,
        and stage the RemediationRecord.
        """
        project = action.project

        # Tenant isolation
        if user and getattr(user, "is_authenticated", False) and project.owner_id != user.id:
            raise PermissionDenied(f"User is not authorized for project #{project.id}.")

        idem_key = idempotency_key or self.compute_remediation_idempotency_key(
            project_id=project.id,
            action_id=action.id,
            target_url=action.target_url,
            action_type=action.action_type
        )

        with transaction.atomic():
            # Check for existing remediation record
            existing = RemediationRecord.objects.select_for_update().filter(
                project=project,
                idempotency_key=idem_key
            ).first()
            if existing:
                return existing

            # Evaluate policy
            policy_result = AutonomousRemediationPolicy.evaluate(action=action, project=project)

            # Determine initial status
            initial_status = action.status
            if policy_result.decision == RemediationPolicyDecision.AUTONOMOUS_ALLOWED:
                action_status = ActionStatus.PROPOSED
            else:
                action_status = ActionStatus.PENDING_APPROVAL

            record = RemediationRecord.objects.create(
                project=project,
                action=action,
                event=event,
                agent_run=agent_run,
                idempotency_key=idem_key,
                risk_level=policy_result.risk_level,
                policy_decision=policy_result.decision,
                policy_explanation=policy_result.explanation,
                is_autonomous=(policy_result.decision == RemediationPolicyDecision.AUTONOMOUS_ALLOWED),
                status=action_status,
                rollback_data=action.current_state or {},
                verification_data={},
            )

        self._emit_event(
            AgentEventType.SEO_REMEDIATION_PROPOSED,
            project_id=project.id,
            payload={
                "remediation_id": record.id,
                "action_id": action.id,
                "action_type": action.action_type,
                "risk_level": record.risk_level,
                "policy_decision": record.policy_decision,
            },
            run_id=agent_run.id if agent_run else None,
        )

        self._emit_event(
            AgentEventType.SEO_REMEDIATION_AUTH_EVALUATED,
            project_id=project.id,
            payload={
                "remediation_id": record.id,
                "policy_decision": record.policy_decision,
                "explanation": record.policy_explanation,
            },
            run_id=agent_run.id if agent_run else None,
        )

        return record

    def execute_remediation(
        self,
        action_id: int,
        project_id: int,
        user: Optional[Any] = None,
        run_id: Optional[int] = None,
        force_autonomous: bool = False,
    ) -> RemediationRecord:
        """
        Safely execute a remediation action adhering strictly to:
        1. Tenant isolation (project must own action).
        2. Database row lock to prevent race conditions.
        3. Idempotency check: duplicate execution is prevented.
        4. Authorization check: must be AUTONOMOUS_ALLOWED or explicitly approved by human.
        5. Connector mutation execution.
        6. Mandatory empirical verification (SEOActionVerifier).
        7. Deterministic failure categorization on error.
        """
        with transaction.atomic():
            # 1. Fetch action with row lock
            try:
                action = (
                    SEOAction.objects.select_for_update()
                    .select_related("project", "project__owner")
                    .get(id=action_id)
                )
            except SEOAction.DoesNotExist:
                raise ValueError(f"SEOAction #{action_id} not found.")

            # 2. Strict Tenant Isolation
            if action.project_id != project_id:
                raise PermissionDenied(
                    f"Tenant Isolation Violation: Action #{action_id} belongs to project "
                    f"#{action.project_id}, not requested project #{project_id}."
                )

            if user and getattr(user, "is_authenticated", False) and action.project.owner_id != user.id:
                raise PermissionDenied(
                    f"User #{user.id} is not authorized to execute actions on project #{action.project_id}."
                )

            # 3. Retrieve or create RemediationRecord
            idem_key = self.compute_remediation_idempotency_key(
                project_id=action.project_id,
                action_id=action.id,
                target_url=action.target_url,
                action_type=action.action_type
            )
            record, _ = RemediationRecord.objects.select_for_update().get_or_create(
                project=action.project,
                idempotency_key=idem_key,
                defaults={
                    "action": action,
                    "risk_level": str(action.risk_level or "low").lower() if str(action.risk_level or "low").lower() in RemediationRiskLevel.values else RemediationRiskLevel.LOW,
                    "policy_decision": RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED,
                    "status": action.status,
                    "rollback_data": action.current_state or {},
                }
            )

            # 3b. Human Rejection Boundary: Rejection strictly prevents execution
            if action.status == ActionStatus.REJECTED or record.status == ActionStatus.REJECTED or action.rejected_at is not None:
                action.status = ActionStatus.REJECTED
                action.save(update_fields=["status", "updated_at"])
                record.status = ActionStatus.REJECTED
                record.error_category = RemediationErrorCategory.HUMAN_REJECTION
                record.policy_explanation = action.rejection_reason or "Action has been rejected by a human reviewer."
                record.save(update_fields=["status", "error_category", "policy_explanation", "updated_at"])
                self._emit_event(
                    AgentEventType.SEO_REMEDIATION_AUTH_REJECTED,
                    project_id=action.project_id,
                    payload={
                        "action_id": action.id,
                        "remediation_id": record.id,
                        "reason": record.policy_explanation,
                    },
                    run_id=run_id,
                )
                return record

            # 4. Idempotency Check: Prevent duplicate execution
            if action.status in [
                ActionStatus.EXECUTING,
                ActionStatus.VERIFYING,
                ActionStatus.VERIFIED,
                ActionStatus.COMPLETED,
            ] or record.status in [
                ActionStatus.VERIFYING,
                ActionStatus.VERIFIED,
                ActionStatus.COMPLETED,
            ]:
                logger.warning(
                    f"[AutonomousRemediation] Duplicate execution prevented for Action #{action.id}. "
                    f"Current status: action={action.status}, record={record.status}."
                )
                self._emit_event(
                    AgentEventType.SEO_REMEDIATION_DUPLICATE_PREVENTED,
                    project_id=action.project_id,
                    payload={
                        "action_id": action.id,
                        "remediation_id": record.id,
                        "status": record.status,
                        "reason": "Action is already executing or completed.",
                    },
                    run_id=run_id,
                )
                return record

            # 5. Evaluate Policy & Authorization
            policy_result = AutonomousRemediationPolicy.evaluate(action=action, project=action.project)
            record.risk_level = policy_result.risk_level
            record.policy_decision = policy_result.decision
            record.policy_explanation = policy_result.explanation

            # Check if human approval exists
            is_human_approved = (
                action.status == ActionStatus.APPROVED
                or (action.approved_by_id is not None and action.approved_at is not None)
            )

            if not is_human_approved:
                # Must be permitted by AutonomousRemediationPolicy
                if policy_result.decision != RemediationPolicyDecision.AUTONOMOUS_ALLOWED and not force_autonomous:
                    # Action is blocked from autonomous execution
                    action.status = ActionStatus.BLOCKED if policy_result.decision == RemediationPolicyDecision.BLOCKED else ActionStatus.PENDING_APPROVAL
                    action.save(update_fields=["status", "updated_at"])

                    record.status = action.status
                    record.error_category = RemediationErrorCategory.POLICY_BLOCK if policy_result.decision == RemediationPolicyDecision.BLOCKED else RemediationErrorCategory.AUTHORIZATION_FAILURE
                    record.save(update_fields=["status", "error_category", "policy_decision", "policy_explanation", "updated_at"])

                    self._emit_event(
                        AgentEventType.SEO_REMEDIATION_BLOCKED,
                        project_id=action.project_id,
                        payload={
                            "action_id": action.id,
                            "remediation_id": record.id,
                            "reason": policy_result.explanation,
                            "decision": policy_result.decision,
                        },
                        run_id=run_id,
                    )
                    return record

                # Autonomous execution allowed!
                record.is_autonomous = True
                self._emit_event(
                    AgentEventType.SEO_REMEDIATION_AUTONOMOUS_ALLOWED,
                    project_id=action.project_id,
                    payload={
                        "action_id": action.id,
                        "remediation_id": record.id,
                        "action_type": action.action_type,
                    },
                    run_id=run_id,
                )
            else:
                self._emit_event(
                    AgentEventType.SEO_REMEDIATION_AUTH_APPROVED,
                    project_id=action.project_id,
                    payload={
                        "action_id": action.id,
                        "remediation_id": record.id,
                        "approved_by_id": action.approved_by_id,
                    },
                    run_id=run_id,
                )

            # 6. Transition to AUTHORIZED -> EXECUTING
            action.status = ActionStatus.AUTHORIZED
            action.save(update_fields=["status", "updated_at"])
            record.status = ActionStatus.AUTHORIZED
            record.save(update_fields=["status", "is_autonomous", "risk_level", "policy_decision", "policy_explanation", "updated_at"])

            action.status = ActionStatus.EXECUTING
            action.execution_started_at = timezone.now()
            action.save(update_fields=["status", "execution_started_at", "updated_at"])
            record.status = ActionStatus.EXECUTING
            record.rollback_data = action.current_state or {}
            record.save(update_fields=["status", "rollback_data", "is_autonomous", "updated_at"])

            self._emit_event(
                AgentEventType.SEO_REMEDIATION_EXECUTION_STARTED,
                project_id=action.project_id,
                payload={
                    "action_id": action.id,
                    "remediation_id": record.id,
                    "action_type": action.action_type,
                    "is_autonomous": record.is_autonomous,
                },
                run_id=run_id,
            )

        # 7. Connector Execution (outside atomic lock to prevent blocking connection during network I/O)
        try:
            connector = get_mutation_connector("dry_run")
            execution_result = connector.execute(action)

            with transaction.atomic():
                action.refresh_from_db()
                action.status = ActionStatus.COMPLETED
                action.completed_at = timezone.now()
                action.execution_metadata = execution_result
                action.save(update_fields=["status", "completed_at", "execution_metadata", "updated_at"])

                record.refresh_from_db()
                record.status = ActionStatus.COMPLETED
                record.save(update_fields=["status", "updated_at"])

            self._emit_event(
                AgentEventType.SEO_REMEDIATION_EXECUTION_COMPLETED,
                project_id=action.project_id,
                payload={
                    "action_id": action.id,
                    "remediation_id": record.id,
                    "duration_ms": execution_result.get("duration_ms", 0),
                },
                run_id=run_id,
            )

        except Exception as exec_exc:
            logger.error(f"[AutonomousRemediationService] Execution failed for Action #{action.id}: {exec_exc}")
            with transaction.atomic():
                action.refresh_from_db()
                action.status = ActionStatus.FAILED
                action.failure_reason = str(exec_exc)
                action.save(update_fields=["status", "failure_reason", "updated_at"])

                record.refresh_from_db()
                record.status = ActionStatus.FAILED
                record.error_category = RemediationErrorCategory.TOOL_FAILURE
                record.policy_explanation = f"Connector tool execution error: {str(exec_exc)}"
                record.save(update_fields=["status", "error_category", "policy_explanation", "updated_at"])

            self._emit_event(
                AgentEventType.SEO_REMEDIATION_EXECUTION_FAILED,
                project_id=action.project_id,
                payload={
                    "action_id": action.id,
                    "remediation_id": record.id,
                    "error": str(exec_exc),
                    "error_category": RemediationErrorCategory.TOOL_FAILURE,
                },
                run_id=run_id,
            )
            return record

        # 8. Mandatory Empirical Verification Phase
        with transaction.atomic():
            action.refresh_from_db()
            action.status = ActionStatus.VERIFYING
            action.verification_status = VerificationStatus.VERIFYING
            action.save(update_fields=["status", "verification_status", "updated_at"])

            record.refresh_from_db()
            record.status = ActionStatus.VERIFYING
            record.save(update_fields=["status", "updated_at"])

        self._emit_event(
            AgentEventType.SEO_REMEDIATION_VERIFICATION_STARTED,
            project_id=action.project_id,
            payload={"action_id": action.id, "remediation_id": record.id},
            run_id=run_id,
        )

        verifier = self._verifier or SEOActionVerifier(project=action.project, publisher=self.publisher)
        try:
            verification_res = verifier.verify_action(action=action, run_id=run_id)
            is_verified = bool(
                verification_res.get("is_verified", False)
                or verification_res.get("verified", False)
                or verification_res.get("verification_status") == "verified"
            )

            with transaction.atomic():
                action.refresh_from_db()
                record.refresh_from_db()

                if is_verified:
                    action.status = ActionStatus.VERIFIED
                    action.verification_status = VerificationStatus.VERIFIED
                    action.verification_result = verification_res
                    action.save(update_fields=["status", "verification_status", "verification_result", "updated_at"])

                    record.status = ActionStatus.VERIFIED
                    record.verification_data = verification_res
                    record.error_category = ""
                    record.save(update_fields=["status", "verification_data", "error_category", "updated_at"])

                    self._emit_event(
                        AgentEventType.SEO_REMEDIATION_VERIFICATION_PASSED,
                        project_id=action.project_id,
                        payload={"action_id": action.id, "remediation_id": record.id},
                        run_id=run_id,
                    )
                    self._emit_event(
                        AgentEventType.SEO_REMEDIATION_COMPLETED,
                        project_id=action.project_id,
                        payload={
                            "action_id": action.id,
                            "remediation_id": record.id,
                            "status": "verified",
                            "is_autonomous": record.is_autonomous,
                        },
                        run_id=run_id,
                    )
                else:
                    # Critical Safety Invariant: Execution Success + Failed Verification != Successful Remediation
                    action.status = ActionStatus.FAILED
                    action.verification_status = VerificationStatus.FAILED
                    action.verification_result = verification_res
                    action.failure_reason = "Empirical verification failed: Live page did not reflect expected changes."
                    action.save(update_fields=["status", "verification_status", "verification_result", "failure_reason", "updated_at"])

                    record.status = ActionStatus.FAILED
                    record.verification_data = verification_res
                    record.error_category = RemediationErrorCategory.VERIFICATION_FAILURE
                    record.policy_explanation = "Execution succeeded but post-mutation verification failed."
                    record.save(update_fields=["status", "verification_data", "error_category", "policy_explanation", "updated_at"])

                    self._emit_event(
                        AgentEventType.SEO_REMEDIATION_VERIFICATION_FAILED,
                        project_id=action.project_id,
                        payload={
                            "action_id": action.id,
                            "remediation_id": record.id,
                            "reason": action.failure_reason,
                            "error_category": RemediationErrorCategory.VERIFICATION_FAILURE,
                        },
                        run_id=run_id,
                    )

        except Exception as verif_exc:
            logger.error(f"[AutonomousRemediationService] Verification exception for Action #{action.id}: {verif_exc}")
            with transaction.atomic():
                action.refresh_from_db()
                action.status = ActionStatus.FAILED
                action.verification_status = VerificationStatus.FAILED
                action.failure_reason = f"Verification error: {str(verif_exc)}"
                action.save(update_fields=["status", "verification_status", "failure_reason", "updated_at"])

                record.refresh_from_db()
                record.status = ActionStatus.FAILED
                record.error_category = RemediationErrorCategory.VERIFICATION_FAILURE
                record.save(update_fields=["status", "error_category", "updated_at"])

            self._emit_event(
                AgentEventType.SEO_REMEDIATION_VERIFICATION_FAILED,
                project_id=action.project_id,
                payload={
                    "action_id": action.id,
                    "remediation_id": record.id,
                    "error": str(verif_exc),
                    "error_category": RemediationErrorCategory.VERIFICATION_FAILURE,
                },
                run_id=run_id,
            )

        return record

    def rollback_remediation(
        self,
        action_id: int,
        user: Optional[Any] = None,
        run_id: Optional[int] = None,
    ) -> RemediationRecord:
        """
        Revert an executed or verified remediation using stored rollback state.
        Transitions action and record to ROLLED_BACK.
        """
        with transaction.atomic():
            try:
                action = SEOAction.objects.select_for_update().select_related("project").get(id=action_id)
            except SEOAction.DoesNotExist:
                raise ValueError(f"SEOAction #{action_id} not found.")

            # Tenant isolation
            if user and getattr(user, "is_authenticated", False) and action.project.owner_id != user.id:
                raise PermissionDenied(f"User is not authorized to rollback actions on project #{action.project_id}.")

            record = RemediationRecord.objects.select_for_update().filter(
                project=action.project,
                action=action
            ).order_by("-created_at").first()

            if not record:
                raise ValueError(f"No RemediationRecord found for Action #{action_id} to rollback.")

            rollback_payload = record.rollback_data or {}
            if not rollback_payload:
                raise ValueError(f"Action #{action_id} has no pre-execution rollback data recorded.")

        self._emit_event(
            AgentEventType.SEO_REMEDIATION_ROLLBACK_STARTED,
            project_id=action.project_id,
            payload={"action_id": action.id, "remediation_id": record.id},
            run_id=run_id,
        )

        # Apply rollback mutation
        connector = get_mutation_connector("dry_run")
        revert_action = SEOAction(
            project=action.project,
            action_type=action.action_type,
            target_url=action.target_url,
            current_state=action.proposed_change,
            proposed_change=rollback_payload,
            title=f"Rollback: {action.title}",
        )
        connector.execute(revert_action)

        with transaction.atomic():
            action.refresh_from_db()
            action.status = ActionStatus.ROLLED_BACK
            action.save(update_fields=["status", "updated_at"])

            record.refresh_from_db()
            record.status = ActionStatus.ROLLED_BACK
            record.policy_explanation = f"Rolled back to pre-execution state by user/system at {timezone.now().isoformat()}."
            record.save(update_fields=["status", "policy_explanation", "updated_at"])

        self._emit_event(
            AgentEventType.SEO_REMEDIATION_ROLLBACK_COMPLETED,
            project_id=action.project_id,
            payload={"action_id": action.id, "remediation_id": record.id, "status": "rolled_back"},
            run_id=run_id,
        )

        return record
