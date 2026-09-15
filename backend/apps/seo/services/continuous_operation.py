"""
Continuous Agent Operations Service (Milestone 6.1).

Coordinates persistent, scheduled agent operations for SEO projects.
Reuses the existing specialized supervisor and multi-agent execution stack (5.1-5.7),
enforces strict single active run invariants, tenant isolation, concurrency protection,
failure isolation, and safe Human-In-The-Loop (HITL) approval gating.
"""

import logging
from datetime import timedelta
from typing import Optional, Dict, Any, List
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.projects.models import Project
from apps.seo.models import (
    ContinuousOperation,
    ContinuousOperationStatus,
    ContinuousOperationScheduleType,
    AgentRun,
    AgentRunStatus,
)
from apps.seo.services.agent_events import (
    AgentEvent,
    AgentEventType,
    AgentEventPublisher,
    get_event_publisher,
)

logger = logging.getLogger(__name__)


class ContinuousOperationService:
    """
    Lifecycle and scheduling service for continuous autonomous SEO operations.
    """

    def __init__(self, publisher: Optional[AgentEventPublisher] = None):
        self.publisher = publisher or get_event_publisher()

    def _emit_event(
        self,
        event_type: AgentEventType,
        operation: ContinuousOperation,
        run_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Helper to emit sanitized operational events."""
        data = {
            "operation_id": operation.id,
            "project_id": operation.project_id,
            "goal": operation.goal,
            "status": operation.status,
            "schedule_type": operation.schedule_type,
            "interval_value": operation.interval_value,
            **(payload or {})
        }
        if run_id:
            data["run_id"] = run_id

        event = AgentEvent(
            event_type=event_type,
            run_id=run_id,
            project_id=operation.project_id,
            sequence_number=operation.total_runs + 1,
            payload=data,
        )
        try:
            self.publisher.publish(event)
        except Exception as exc:
            logger.warning(f"[ContinuousOperationService] Telemetry publish failed ({event_type}): {exc}")

    def calculate_next_run(
        self,
        operation: ContinuousOperation,
        from_time: Optional[timezone.datetime] = None
    ) -> timezone.datetime:
        """
        Calculate next run timestamp based on recurrence schedule configuration.
        Supported:
        - interval_minutes: from_time + N minutes
        - interval_hours: from_time + N hours
        - daily: from_time + N days
        """
        base_time = from_time or timezone.now()
        interval = max(1, operation.interval_value)

        if operation.schedule_type == ContinuousOperationScheduleType.INTERVAL_MINUTES:
            return base_time + timedelta(minutes=interval)
        elif operation.schedule_type == ContinuousOperationScheduleType.INTERVAL_HOURS:
            return base_time + timedelta(hours=interval)
        elif operation.schedule_type == ContinuousOperationScheduleType.DAILY:
            return base_time + timedelta(days=interval)
        else:
            # Fallback default 30 minutes
            return base_time + timedelta(minutes=30)

    def create_operation(
        self,
        project: Project,
        user: Any,
        goal: str,
        schedule_type: str = ContinuousOperationScheduleType.INTERVAL_MINUTES,
        interval_value: int = 30,
        schedule_config: Optional[Dict[str, Any]] = None,
        auto_activate: bool = True,
    ) -> ContinuousOperation:
        """
        Create a new ContinuousOperation session for a project.
        Enforces tenant isolation (project.owner must match user if authenticated).
        """
        if not goal or not str(goal).strip():
            raise ValueError("Operational goal cannot be empty.")

        initial_status = ContinuousOperationStatus.ACTIVE if auto_activate else ContinuousOperationStatus.INACTIVE
        now = timezone.now()

        with transaction.atomic():
            operation = ContinuousOperation.objects.create(
                project=project,
                user=user,
                goal=str(goal).strip(),
                status=initial_status,
                schedule_type=schedule_type,
                interval_value=max(1, int(interval_value)),
                schedule_config=schedule_config or {},
                next_run_at=now if auto_activate else None,
                metrics={
                    "duplicate_prevention_count": 0,
                    "approval_wait_count": 0,
                    "total_duration_ms": 0,
                    "average_run_duration_ms": 0,
                }
            )

        self._emit_event(AgentEventType.SEO_OPERATION_CREATED, operation)
        if auto_activate:
            self._emit_event(AgentEventType.SEO_OPERATION_STARTED, operation)

        logger.info(f"[ContinuousOperationService] Created ContinuousOperation #{operation.id} for project #{project.id}.")
        return operation

    def pause_operation(self, operation_id: int, user: Optional[Any] = None) -> ContinuousOperation:
        """
        Pause an active continuous operation.
        The current run (if executing) completes gracefully, but the scheduler will
        NOT schedule any subsequent AgentRun while paused.
        """
        with transaction.atomic():
            op = ContinuousOperation.objects.select_for_update().get(id=operation_id)
            if user and hasattr(user, 'id') and op.project.owner_id != user.id:
                raise PermissionError("User does not own the project for this continuous operation.")

            if op.status == ContinuousOperationStatus.PAUSED:
                return op

            op.status = ContinuousOperationStatus.PAUSED
            op.paused_at = timezone.now()
            op.save(update_fields=['status', 'paused_at', 'updated_at'])

        self._emit_event(AgentEventType.SEO_OPERATION_PAUSED, op)
        logger.info(f"[ContinuousOperationService] Paused ContinuousOperation #{op.id}.")
        return op

    def resume_operation(self, operation_id: int, user: Optional[Any] = None) -> ContinuousOperation:
        """
        Resume a paused continuous operation.
        Re-enables scheduler eligibility and schedules next run immediately.
        """
        with transaction.atomic():
            op = ContinuousOperation.objects.select_for_update().get(id=operation_id)
            if user and hasattr(user, 'id') and op.project.owner_id != user.id:
                raise PermissionError("User does not own the project for this continuous operation.")

            if op.status == ContinuousOperationStatus.ACTIVE:
                return op

            now = timezone.now()
            op.status = ContinuousOperationStatus.ACTIVE
            op.resumed_at = now
            # If no active run is currently executing, schedule immediate next run
            if op.current_run_id is None:
                op.next_run_at = now
            else:
                op.status = ContinuousOperationStatus.RUNNING
            op.save(update_fields=['status', 'resumed_at', 'next_run_at', 'updated_at'])

        self._emit_event(AgentEventType.SEO_OPERATION_RESUMED, op)
        logger.info(f"[ContinuousOperationService] Resumed ContinuousOperation #{op.id}.")
        return op

    def trigger_operation_manually(
        self,
        operation_id: int,
        user: Optional[Any] = None
    ) -> Optional[AgentRun]:
        """
        Manually trigger a run for an active/paused operation immediately,
        strictly enforcing the single active run invariant.
        """
        from apps.seo.tasks import execute_continuous_agent_run_task

        with transaction.atomic():
            op = ContinuousOperation.objects.select_for_update().get(id=operation_id)
            if user and hasattr(user, 'id') and op.project.owner_id != user.id:
                raise PermissionError("User does not own the project for this continuous operation.")

            # Concurrency & Invariant Check: At most one active run
            if op.current_run_id is not None or op.status == ContinuousOperationStatus.RUNNING:
                logger.warning(
                    f"[ContinuousOperationService] Manual trigger rejected for Op #{op.id}: "
                    f"Already has active run #{op.current_run_id}."
                )
                metrics = op.metrics or {}
                metrics["duplicate_prevention_count"] = metrics.get("duplicate_prevention_count", 0) + 1
                op.metrics = metrics
                op.save(update_fields=['metrics', 'updated_at'])
                return None

            # Create AgentRun
            now = timezone.now()
            run = AgentRun.objects.create(
                project=op.project,
                user=op.user,
                continuous_operation=op,
                goal=op.goal,
                status=AgentRunStatus.PENDING,
                plan=[],
                context_snapshot={
                    "operation_id": op.id,
                    "schedule_type": op.schedule_type,
                    "trigger": "manual",
                    "triggered_at": now.isoformat(),
                },
                max_steps=op.schedule_config.get("max_steps", 15),
                total_steps=0,
            )

            op.current_run = run
            op.last_run = run
            op.last_run_at = now
            op.total_runs += 1
            op.status = ContinuousOperationStatus.RUNNING
            op.save(update_fields=['current_run', 'last_run', 'last_run_at', 'total_runs', 'status', 'updated_at'])

        self._emit_event(
            AgentEventType.SEO_OPERATION_RUN_SCHEDULED,
            op,
            run_id=run.id,
            payload={"trigger": "manual"}
        )

        try:
            execute_continuous_agent_run_task.delay(operation_id=op.id, run_id=run.id)
        except Exception as exc:
            logger.error(f"[ContinuousOperationService] Failed to enqueue continuous run #{run.id}: {exc}")

        return run

    def evaluate_and_trigger_due_operations(self) -> List[int]:
        """
        Scheduler entrypoint: Identifies due active operations and initiates AgentRuns.
        
        Guarantees:
        1. Multi-tenant row locking: select_for_update(skip_locked=True) ensures parallel
           schedulers never pick the same operation.
        2. Single active run invariant: operation.current_run MUST be None.
        3. Idempotent state transition to RUNNING before Celery task enqueuing.
        4. Increments duplicate prevention telemetry if duplicate evaluation is blocked.
        """
        from apps.seo.tasks import execute_continuous_agent_run_task

        now = timezone.now()
        started_run_ids: List[int] = []

        with transaction.atomic():
            due_ops = list(
                ContinuousOperation.objects.select_for_update(skip_locked=True)
                .filter(
                    status=ContinuousOperationStatus.ACTIVE,
                    next_run_at__lte=now,
                    current_run__isnull=True,
                )
                .select_related('project', 'user')[:50]
            )

            for op in due_ops:
                # Precondition check inside transaction lock
                if op.current_run_id is not None or op.status != ContinuousOperationStatus.ACTIVE:
                    metrics = op.metrics or {}
                    metrics["duplicate_prevention_count"] = metrics.get("duplicate_prevention_count", 0) + 1
                    op.metrics = metrics
                    op.save(update_fields=['metrics', 'updated_at'])
                    continue

                # Create new AgentRun session
                run = AgentRun.objects.create(
                    project=op.project,
                    user=op.user,
                    continuous_operation=op,
                    goal=op.goal,
                    status=AgentRunStatus.PENDING,
                    plan=[],
                    context_snapshot={
                        "operation_id": op.id,
                        "schedule_type": op.schedule_type,
                        "trigger": "scheduled",
                        "scheduled_for": op.next_run_at.isoformat() if op.next_run_at else None,
                    },
                    max_steps=op.schedule_config.get("max_steps", 15),
                    total_steps=0,
                )

                op.current_run = run
                op.last_run = run
                op.last_run_at = now
                op.total_runs += 1
                op.status = ContinuousOperationStatus.RUNNING
                op.save(update_fields=['current_run', 'last_run', 'last_run_at', 'total_runs', 'status', 'updated_at'])

                started_run_ids.append(run.id)

                self._emit_event(
                    AgentEventType.SEO_OPERATION_RUN_SCHEDULED,
                    op,
                    run_id=run.id,
                    payload={"trigger": "scheduled", "scheduled_for": str(op.next_run_at)}
                )

                try:
                    execute_continuous_agent_run_task.delay(operation_id=op.id, run_id=run.id)
                except Exception as exc:
                    logger.error(f"[ContinuousOperationService] Failed to dispatch task for Op #{op.id}: {exc}")

        return started_run_ids

    def handle_run_completion(
        self,
        operation_id: int,
        run_id: int,
        run_status: str,
        duration_ms: int = 0,
        error_summary: str = "",
        failure_category: str = "",
    ) -> ContinuousOperation:
        """
        Post-execution hook called atomically when an AgentRun terminates or enters WAITING_FOR_APPROVAL.
        Handles:
        - Success: resets consecutive failures, calculates next run, transitions to ACTIVE.
        - Human approval needed: transitions operation to WAITING, preserves safety boundary.
        - Failure: records failure details, applies bounded exponential backoff, circuit breaks if limit hit.
        """
        now = timezone.now()

        with transaction.atomic():
            op = ContinuousOperation.objects.select_for_update().get(id=operation_id)
            metrics = op.metrics or {}
            metrics["total_duration_ms"] = metrics.get("total_duration_ms", 0) + max(0, duration_ms)
            finished_runs = op.successful_runs + op.failed_runs + 1
            metrics["average_run_duration_ms"] = round(metrics["total_duration_ms"] / max(1, finished_runs))

            if run_status == AgentRunStatus.WAITING_FOR_APPROVAL:
                # HITL Boundary: Do NOT schedule next run while waiting for human approval
                op.status = ContinuousOperationStatus.WAITING
                metrics["approval_wait_count"] = metrics.get("approval_wait_count", 0) + 1
                op.metrics = metrics
                op.save(update_fields=['status', 'metrics', 'updated_at'])
                logger.info(f"[ContinuousOperationService] Op #{op.id} transitioned to WAITING for human approval.")
                return op

            elif run_status == AgentRunStatus.COMPLETED:
                op.successful_runs += 1
                op.consecutive_failures = 0
                op.last_successful_run_id = run_id
                op.failure_category = ""
                op.failure_reason = ""
                op.current_run = None
                op.metrics = metrics

                # If paused during execution, respect paused status
                if op.status != ContinuousOperationStatus.PAUSED:
                    op.status = ContinuousOperationStatus.ACTIVE
                    op.next_run_at = self.calculate_next_run(op, from_time=now)
                else:
                    op.next_run_at = None

                op.save(update_fields=[
                    'successful_runs', 'consecutive_failures', 'last_successful_run',
                    'failure_category', 'failure_reason', 'current_run', 'metrics',
                    'status', 'next_run_at', 'updated_at'
                ])

                self._emit_event(
                    AgentEventType.SEO_OPERATION_RUN_COMPLETED,
                    op,
                    run_id=run_id,
                    payload={"duration_ms": duration_ms, "next_run_at": str(op.next_run_at)}
                )
                logger.info(f"[ContinuousOperationService] Op #{op.id} run #{run_id} COMPLETED. Next run: {op.next_run_at}")
                return op

            else:
                # Run failed or cancelled
                op.failed_runs += 1
                op.consecutive_failures += 1
                op.failed_run_id = run_id
                op.failure_category = failure_category or "execution_failure"
                op.failure_reason = (error_summary or "Unknown execution failure")[:500]
                op.current_run = None
                op.metrics = metrics

                # Circuit breaker check: consecutive failures >= max_consecutive_failures
                if op.consecutive_failures >= op.max_consecutive_failures:
                    op.status = ContinuousOperationStatus.FAILED
                    op.next_run_at = None
                    op.save(update_fields=[
                        'failed_runs', 'consecutive_failures', 'failed_run_id',
                        'failure_category', 'failure_reason', 'current_run', 'metrics',
                        'status', 'next_run_at', 'updated_at'
                    ])
                    self._emit_event(
                        AgentEventType.SEO_OPERATION_RUN_FAILED,
                        op,
                        run_id=run_id,
                        payload={"circuit_breaker": True, "consecutive_failures": op.consecutive_failures}
                    )
                    logger.error(
                        f"[ContinuousOperationService] Op #{op.id} circuit-breaker tripped "
                        f"after {op.consecutive_failures} consecutive failures. Status set to FAILED."
                    )
                else:
                    # Bounded exponential backoff: min(60, 5 * 2^(failures-1)) minutes
                    backoff_minutes = min(60, 5 * (2 ** (op.consecutive_failures - 1)))
                    if op.status != ContinuousOperationStatus.PAUSED:
                        op.status = ContinuousOperationStatus.ACTIVE
                        op.next_run_at = now + timedelta(minutes=backoff_minutes)
                    else:
                        op.next_run_at = None

                    op.save(update_fields=[
                        'failed_runs', 'consecutive_failures', 'failed_run_id',
                        'failure_category', 'failure_reason', 'current_run', 'metrics',
                        'status', 'next_run_at', 'updated_at'
                    ])
                    self._emit_event(
                        AgentEventType.SEO_OPERATION_RUN_FAILED,
                        op,
                        run_id=run_id,
                        payload={
                            "consecutive_failures": op.consecutive_failures,
                            "backoff_minutes": backoff_minutes,
                            "next_run_at": str(op.next_run_at)
                        }
                    )
                    logger.warning(
                        f"[ContinuousOperationService] Op #{op.id} run #{run_id} FAILED "
                        f"(failures: {op.consecutive_failures}). Next attempt in {backoff_minutes}m."
                    )

                return op
