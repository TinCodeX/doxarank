"""
DoxaRank Milestone 6.2 — Event-Driven Agents Ingestion & Trigger Policy Service.

Handles event ingestion, validation, deterministic idempotency, cooldown & storm suppression,
policy evaluation, and automated agent workflow triggering via existing SEOSupervisorAgent.
"""
import hashlib
import json
import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.projects.models import Project
from apps.seo.models import (
    SEOEvent,
    SEOEventType,
    SEOEventSeverity,
    SEOEventStatus,
    AgentRun,
    AgentRunStatus,
    ContinuousOperation,
    ContinuousOperationStatus,
)
from apps.seo.services.agent_events import AgentEventType, AgentEvent, InMemoryEventPublisher

logger = logging.getLogger(__name__)

# Forbidden keys in event payloads to prevent arbitrary agent or tool injection
FORBIDDEN_PAYLOAD_KEYS = {
    "tools",
    "agents",
    "allowed_tools",
    "skip_hitl",
    "auto_approve",
    "bypass_permissions",
    "override_roles",
}

DEFAULT_COOLDOWN_MINUTES = 15
DEFAULT_EVENT_STORM_THRESHOLD = 20  # Max events per project in 5 minutes
DEFAULT_EVENT_STORM_WINDOW_MINUTES = 5


class PolicyDecision:
    """Encapsulates the explainable decision of an EventTriggerPolicy."""

    def __init__(
        self,
        should_trigger: bool,
        goal: str = "",
        reason: str = "",
        suggested_priority: str = "medium",
        workflow_type: str = "investigation"
    ):
        self.should_trigger = should_trigger
        self.goal = goal
        self.reason = reason
        self.suggested_priority = suggested_priority
        self.workflow_type = workflow_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_trigger": self.should_trigger,
            "goal": self.goal,
            "reason": self.reason,
            "suggested_priority": self.suggested_priority,
            "workflow_type": self.workflow_type,
        }


class EventTriggerPolicy:
    """
    Deterministic rule-based trigger policy engine for Milestone 6.2.
    Evaluates an SEOEvent against domain thresholds and synthesizes explainable goals.
    """

    @classmethod
    def evaluate(cls, event: SEOEvent) -> PolicyDecision:
        payload = event.payload or {}
        event_type = event.event_type
        severity = event.severity

        # 1. RANKING_CHANGE
        if event_type == SEOEventType.RANKING_CHANGE:
            rank_drop = payload.get("rank_drop", 0)
            keyword = payload.get("keyword", "primary target keyword")
            prev_rank = payload.get("previous_rank", None)
            new_rank = payload.get("new_rank", None)

            if prev_rank is not None and new_rank is not None and not rank_drop:
                try:
                    rank_drop = max(0, int(new_rank) - int(prev_rank))
                except (ValueError, TypeError):
                    rank_drop = 0

            # Threshold: rank decline >= 3 positions OR High/Critical severity
            if rank_drop >= 3 or severity in [SEOEventSeverity.HIGH, SEOEventSeverity.CRITICAL]:
                goal = f"Investigate ranking drop for '{keyword}' (declined {rank_drop} positions to #{new_rank or 'unranked'})"
                reason = f"Rank drop of {rank_drop} positions met trigger threshold (>=3 positions or severity={severity})"
                return PolicyDecision(
                    should_trigger=True,
                    goal=goal,
                    reason=reason,
                    suggested_priority="high" if rank_drop >= 5 else "medium",
                    workflow_type="investigation"
                )
            return PolicyDecision(
                should_trigger=False,
                reason=f"Minor ranking fluctuation ({rank_drop} positions) below threshold (<3 positions)"
            )

        # 2. PAGE_STATUS_CHANGE
        elif event_type == SEOEventType.PAGE_STATUS_CHANGE:
            status_code = payload.get("status_code", 200)
            target_url = payload.get("url", "homepage")
            is_error = payload.get("is_error", False) or status_code >= 400

            if is_error or severity in [SEOEventSeverity.HIGH, SEOEventSeverity.CRITICAL]:
                goal = f"Investigate HTTP {status_code} error on critical page: {target_url}"
                reason = f"Page status code {status_code} indicates HTTP client/server fault"
                return PolicyDecision(
                    should_trigger=True,
                    goal=goal,
                    reason=reason,
                    suggested_priority="critical" if status_code >= 500 else "high",
                    workflow_type="audit"
                )
            return PolicyDecision(
                should_trigger=False,
                reason=f"HTTP status code {status_code} is healthy; no trigger required"
            )

        # 3. SEO_AUDIT_CHANGE
        elif event_type == SEOEventType.SEO_AUDIT_CHANGE:
            critical_issues = payload.get("critical_issues_count", 0)
            score_drop = payload.get("score_drop", 0)
            url = payload.get("url", "website")

            if critical_issues > 0 or score_drop >= 5 or severity in [SEOEventSeverity.HIGH, SEOEventSeverity.CRITICAL]:
                goal = f"Diagnose new critical SEO audit findings ({critical_issues} critical issues) for {url}"
                reason = f"Audit detected {critical_issues} critical issues or score drop of {score_drop} points"
                return PolicyDecision(
                    should_trigger=True,
                    goal=goal,
                    reason=reason,
                    suggested_priority="high",
                    workflow_type="audit"
                )
            return PolicyDecision(
                should_trigger=False,
                reason=f"Audit changes ({critical_issues} critical issues, score drop {score_drop}) below threshold"
            )

        # 4. GSC_CHANGE
        elif event_type == SEOEventType.GSC_CHANGE:
            clicks_drop = payload.get("clicks_drop_percent", 0)
            impressions_drop = payload.get("impressions_drop_percent", 0)

            if clicks_drop >= 15 or impressions_drop >= 20 or severity in [SEOEventSeverity.HIGH, SEOEventSeverity.CRITICAL]:
                goal = f"Analyze Google Search Console traffic drop (-{clicks_drop}% clicks, -{impressions_drop}% impressions)"
                reason = f"GSC metrics drop exceeded threshold (-{clicks_drop}% clicks, -{impressions_drop}% impressions)"
                return PolicyDecision(
                    should_trigger=True,
                    goal=goal,
                    reason=reason,
                    suggested_priority="high",
                    workflow_type="investigation"
                )
            return PolicyDecision(
                should_trigger=False,
                reason=f"GSC fluctuation (-{clicks_drop}% clicks) below investigation threshold"
            )

        # 5. CRAWL_ISSUE
        elif event_type == SEOEventType.CRAWL_ISSUE:
            issue_type = payload.get("issue_type", "crawl_block")
            url = payload.get("url", "target site")
            goal = f"Investigate crawl impediment ({issue_type}) detected on {url}"
            reason = f"Crawl issue '{issue_type}' reported with severity {severity}"
            return PolicyDecision(
                should_trigger=True,
                goal=goal,
                reason=reason,
                suggested_priority="high",
                workflow_type="audit"
            )

        # 6. KEYWORD_VISIBILITY_CHANGE
        elif event_type == SEOEventType.KEYWORD_VISIBILITY_CHANGE:
            drop_pts = payload.get("visibility_drop_points", 0)
            if drop_pts >= 5 or severity in [SEOEventSeverity.HIGH, SEOEventSeverity.CRITICAL]:
                goal = f"Investigate keyword visibility decline (-{drop_pts} points) across tracked queries"
                reason = f"Visibility drop of {drop_pts} points exceeded monitoring threshold"
                return PolicyDecision(
                    should_trigger=True,
                    goal=goal,
                    reason=reason,
                    suggested_priority="medium",
                    workflow_type="investigation"
                )
            return PolicyDecision(
                should_trigger=False,
                reason=f"Keyword visibility fluctuation ({drop_pts} pts) below threshold"
            )

        # 7. CONTENT_CHANGE
        elif event_type == SEOEventType.CONTENT_CHANGE:
            url = payload.get("url", "page")
            significant = payload.get("significant", True)
            if significant or severity in [SEOEventSeverity.HIGH, SEOEventSeverity.CRITICAL]:
                goal = f"Evaluate search index and keyword impact of recent content update on {url}"
                reason = f"Significant content change reported on {url}"
                return PolicyDecision(
                    should_trigger=True,
                    goal=goal,
                    reason=reason,
                    suggested_priority="medium",
                    workflow_type="content"
                )
            return PolicyDecision(
                should_trigger=False,
                reason="Insignificant content change; no agent action required"
            )

        # Fallback default
        return PolicyDecision(
            should_trigger=False,
            reason=f"No active trigger rule matched event type '{event_type}'"
        )


class SEOEventIngestionService:
    """
    Controlled Event Ingestion Service for Milestone 6.2.
    Ensures validation, deterministic idempotency, storm suppression, and safe dispatch.
    """

    def __init__(self, publisher: Optional[Any] = None):
        self.publisher = publisher or InMemoryEventPublisher()

    def _emit_event(self, event_type: AgentEventType, event_obj: SEOEvent, run_id: Optional[int] = None, extra: Optional[Dict[str, Any]] = None):
        """Helper to publish event lifecycle telemetry events."""
        payload = {
            "event_id": event_obj.id,
            "project_id": event_obj.project_id,
            "event_type": event_obj.event_type,
            "source": event_obj.source,
            "severity": event_obj.severity,
            "status": event_obj.status,
            "correlation_id": event_obj.correlation_id,
            "idempotency_key": event_obj.idempotency_key,
            **(extra or {})
        }
        if run_id:
            payload["agent_run_id"] = run_id

        event = AgentEvent(
            event_type=event_type,
            run_id=run_id,
            project_id=event_obj.project_id,
            sequence_number=1,
            payload=payload,
        )
        try:
            self.publisher.publish(event)
        except Exception as exc:
            logger.warning(f"[SEOEventIngestionService] Telemetry publish failed ({event_type}): {exc}")

    @classmethod
    def compute_deterministic_idempotency_key(
        cls,
        project_id: int,
        event_type: str,
        source: str,
        payload: Dict[str, Any],
        custom_key: Optional[str] = None
    ) -> str:
        """
        Generate a deterministic idempotency key for deduplication.
        Ensures identical event submissions within the deduplication window map to the exact same key.
        """
        if custom_key and str(custom_key).strip():
            return str(custom_key).strip()

        # Sort payload keys to guarantee deterministic string representation
        serialized_payload = json.dumps(payload, sort_keys=True, default=str)
        raw_token = f"{project_id}:{event_type}:{source}:{serialized_payload}"
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def validate_event_input(
        self,
        project: Project,
        event_type: str,
        source: str,
        payload: Any,
        user: Optional[Any] = None
    ) -> Tuple[bool, str]:
        """
        Validate incoming event parameters against strict security and schema boundaries.
        Rejects missing/unauthorized projects, invalid event types, and forbidden payload injections.
        """
        # Tenant isolation
        if user and hasattr(user, "id") and project.owner_id != user.id:
            return False, "Project does not belong to the authenticated user."

        # Controlled taxonomy validation
        valid_types = [choice[0] for choice in SEOEventType.choices]
        if event_type not in valid_types:
            return False, f"Invalid event_type '{event_type}'. Must be one of: {valid_types}."

        if not source or not str(source).strip():
            return False, "Event 'source' identifier is required and cannot be empty."

        if not isinstance(payload, dict):
            return False, "Event 'payload' must be a valid JSON object."

        # Security check: Prohibit injection of tools or agent overrides in event payloads
        injected_forbidden = FORBIDDEN_PAYLOAD_KEYS.intersection(payload.keys())
        if injected_forbidden:
            return False, f"Payload contains forbidden keys: {list(injected_forbidden)}. Event payloads cannot configure tools or agents."

        return True, ""

    def ingest_event(
        self,
        project: Project,
        event_type: str,
        source: str,
        payload: Dict[str, Any],
        severity: str = SEOEventSeverity.MEDIUM,
        occurred_at: Optional[timezone.datetime] = None,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
        continuous_operation: Optional[ContinuousOperation] = None,
        user: Optional[Any] = None,
        cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    ) -> SEOEvent:
        """
        Ingest, validate, deduplicate, and evaluate an SEO event.
        Dispatches an AgentRun if trigger policy criteria are met.
        """
        now = timezone.now()
        occurred_time = occurred_at or now
        corr_id = correlation_id or str(uuid.uuid4())

        # 1. Validation
        is_valid, error_msg = self.validate_event_input(
            project=project,
            event_type=event_type,
            source=source,
            payload=payload,
            user=user
        )
        if not is_valid:
            # Persist rejected event record if project is known
            rejected_key = idempotency_key or str(uuid.uuid4())
            event_obj = SEOEvent.objects.create(
                project=project,
                event_type=event_type if event_type in [c[0] for c in SEOEventType.choices] else SEOEventType.RANKING_CHANGE,
                source=source or "unknown",
                severity=severity if severity in [c[0] for c in SEOEventSeverity.choices] else SEOEventSeverity.MEDIUM,
                status=SEOEventStatus.REJECTED,
                payload={"validation_error": error_msg, "original_payload": str(payload)[:500]},
                correlation_id=corr_id,
                idempotency_key=rejected_key,
                occurred_at=occurred_time,
                suppression_reason=error_msg,
            )
            self._emit_event(AgentEventType.SEO_EVENT_REJECTED, event_obj, extra={"error": error_msg})
            raise ValueError(f"Event rejected: {error_msg}")

        # Compute deterministic idempotency key
        final_idempotency_key = self.compute_deterministic_idempotency_key(
            project_id=project.id,
            event_type=event_type,
            source=source,
            payload=payload,
            custom_key=idempotency_key
        )

        with transaction.atomic():
            # 2. Idempotency & Deduplication Check (Window: 1 hour)
            dedup_window = now - timedelta(hours=1)
            existing_event = (
                SEOEvent.objects.select_for_update()
                .filter(
                    project=project,
                    idempotency_key=final_idempotency_key,
                    created_at__gte=dedup_window,
                )
                .first()
            )

            if existing_event:
                # Same event submitted twice -> mark deduplicated without creating second run
                logger.info(
                    f"[SEOEventIngestionService] Deduplicated event for project #{project.id}: "
                    f"idempotency_key={final_idempotency_key} matches existing #{existing_event.id}."
                )
                dedup_event = SEOEvent.objects.create(
                    project=project,
                    event_type=event_type,
                    source=source,
                    severity=severity,
                    status=SEOEventStatus.DEDUPLICATED,
                    payload=payload,
                    correlation_id=corr_id,
                    idempotency_key=f"{final_idempotency_key}:dup:{uuid.uuid4().hex[:6]}",
                    occurred_at=occurred_time,
                    suppression_reason=f"Duplicate of event #{existing_event.id}",
                    agent_run=existing_event.agent_run,
                    continuous_operation=continuous_operation or existing_event.continuous_operation,
                )
                self._emit_event(
                    AgentEventType.SEO_EVENT_DEDUPLICATED,
                    dedup_event,
                    extra={"original_event_id": existing_event.id}
                )
                return dedup_event

            # Create initial accepted event record
            event_obj = SEOEvent.objects.create(
                project=project,
                event_type=event_type,
                source=source,
                severity=severity,
                status=SEOEventStatus.RECEIVED,
                payload=payload,
                correlation_id=corr_id,
                idempotency_key=final_idempotency_key,
                occurred_at=occurred_time,
                continuous_operation=continuous_operation,
            )

        self._emit_event(AgentEventType.SEO_EVENT_RECEIVED, event_obj)

        # 3. Cooldown & Storm Suppression Checks
        # A. Event Storm Protection: Max N events per project in window
        storm_window = now - timedelta(minutes=DEFAULT_EVENT_STORM_WINDOW_MINUTES)
        recent_count = SEOEvent.objects.filter(project=project, created_at__gte=storm_window).count()
        if recent_count > DEFAULT_EVENT_STORM_THRESHOLD:
            event_obj.status = SEOEventStatus.SUPPRESSED
            event_obj.suppression_reason = f"Event storm detected: {recent_count} events in {DEFAULT_EVENT_STORM_WINDOW_MINUTES}m exceeded threshold ({DEFAULT_EVENT_STORM_THRESHOLD})"
            event_obj.save(update_fields=["status", "suppression_reason", "updated_at"])
            self._emit_event(AgentEventType.SEO_EVENT_SUPPRESSED, event_obj, extra={"reason": event_obj.suppression_reason})
            logger.warning(f"[SEOEventIngestionService] {event_obj.suppression_reason}")
            return event_obj

        # B. Cooldown Protection: Max 1 triggered run per (project, event_type) within cooldown window
        cooldown_window = now - timedelta(minutes=cooldown_minutes)
        last_triggered = (
            SEOEvent.objects.filter(
                project=project,
                event_type=event_type,
                agent_run__isnull=False,
                processed_at__gte=cooldown_window
            )
            .exclude(id=event_obj.id)
            .first()
        )
        if last_triggered:
            event_obj.status = SEOEventStatus.SUPPRESSED
            event_obj.suppression_reason = f"Cooldown active: Event type '{event_type}' was already triggered {int((now - last_triggered.processed_at).total_seconds() / 60)}m ago (cooldown: {cooldown_minutes}m)"
            event_obj.save(update_fields=["status", "suppression_reason", "updated_at"])
            self._emit_event(AgentEventType.SEO_EVENT_COOLDOWN, event_obj, extra={"reason": event_obj.suppression_reason})
            self._emit_event(AgentEventType.SEO_EVENT_SUPPRESSED, event_obj, extra={"reason": event_obj.suppression_reason})
            logger.info(f"[SEOEventIngestionService] {event_obj.suppression_reason}")
            return event_obj

        # 4. Trigger Policy Evaluation
        policy_decision = EventTriggerPolicy.evaluate(event_obj)
        if not policy_decision.should_trigger:
            event_obj.status = SEOEventStatus.ACCEPTED
            event_obj.suppression_reason = policy_decision.reason
            event_obj.processed_at = timezone.now()
            event_obj.save(update_fields=["status", "suppression_reason", "processed_at", "updated_at"])
            self._emit_event(AgentEventType.SEO_EVENT_ACCEPTED, event_obj, extra={"policy_reason": policy_decision.reason})
            logger.info(f"[SEOEventIngestionService] Event #{event_obj.id} accepted without trigger: {policy_decision.reason}")
            return event_obj

        # 5. ContinuousOperation Single Active Run Invariant Check (if connected to an operation)
        target_op = continuous_operation
        if target_op is not None:
            target_op = ContinuousOperation.objects.filter(id=target_op.id).first()
        else:
            # Check if project has an active continuous operation matching this domain
            target_op = (
                ContinuousOperation.objects.filter(
                    project=project,
                    status=ContinuousOperationStatus.ACTIVE
                )
                .first()
            )

        if target_op:
            if target_op.current_run_id is not None or target_op.status == ContinuousOperationStatus.RUNNING:
                # Single active run invariant: Do not start overlapping run on the continuous operation
                event_obj.status = SEOEventStatus.SUPPRESSED
                event_obj.suppression_reason = f"Operation #{target_op.id} already has active run #{target_op.current_run_id}"
                event_obj.continuous_operation = target_op
                event_obj.save(update_fields=["status", "suppression_reason", "continuous_operation", "updated_at"])
                
                # Increment metrics
                metrics = target_op.metrics or {}
                metrics["duplicate_prevention_count"] = metrics.get("duplicate_prevention_count", 0) + 1
                target_op.metrics = metrics
                target_op.save(update_fields=["metrics", "updated_at"])

                self._emit_event(AgentEventType.SEO_EVENT_SUPPRESSED, event_obj, extra={"reason": event_obj.suppression_reason})
                logger.warning(f"[SEOEventIngestionService] Suppressed event #{event_obj.id}: {event_obj.suppression_reason}")
                return event_obj

        # 6. Dispatch AgentRun
        from apps.seo.tasks import execute_event_triggered_agent_run_task

        with transaction.atomic():
            if target_op:
                target_op = ContinuousOperation.objects.select_for_update().get(id=target_op.id)

            run = AgentRun.objects.create(
                project=project,
                user=project.owner,
                continuous_operation=target_op,
                goal=policy_decision.goal,
                status=AgentRunStatus.PENDING,
                plan=[],
                context_snapshot={
                    "event_id": event_obj.id,
                    "event_type": event_obj.event_type,
                    "source": event_obj.source,
                    "severity": event_obj.severity,
                    "correlation_id": corr_id,
                    "trigger": "event",
                    "policy_reason": policy_decision.reason,
                    "workflow_type": policy_decision.workflow_type,
                    "triggered_at": now.isoformat(),
                },
                max_steps=15,
                total_steps=0,
            )

            if target_op:
                target_op.current_run = run
                target_op.last_run = run
                target_op.last_run_at = now
                target_op.total_runs += 1
                target_op.status = ContinuousOperationStatus.RUNNING
                target_op.save(update_fields=["current_run", "last_run", "last_run_at", "total_runs", "status", "updated_at"])

            event_obj.agent_run = run
            event_obj.continuous_operation = target_op
            event_obj.status = SEOEventStatus.PROCESSED
            event_obj.processed_at = now
            event_obj.save(update_fields=["agent_run", "continuous_operation", "status", "processed_at", "updated_at"])

        self._emit_event(AgentEventType.SEO_EVENT_TRIGGERED, event_obj, run_id=run.id, extra={"goal": run.goal})
        self._emit_event(AgentEventType.SEO_EVENT_RUN_CREATED, event_obj, run_id=run.id)

        # Enqueue execution in Celery worker (or synchronous in tests)
        try:
            execute_event_triggered_agent_run_task.delay(run_id=run.id, event_id=event_obj.id)
        except Exception as exc:
            logger.error(f"[SEOEventIngestionService] Failed to enqueue execution task for run #{run.id}: {exc}")

        logger.info(f"[SEOEventIngestionService] Event #{event_obj.id} triggered AgentRun #{run.id}: '{run.goal}'")
        return event_obj
