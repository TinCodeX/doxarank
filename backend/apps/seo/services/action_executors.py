import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from apps.seo.models import SEOAction, ActionStatus
from .agent_events import AgentEventPublisher, AgentEventType, AgentEvent, get_event_publisher
from .mutation_connectors import BaseMutationConnector, get_mutation_connector

logger = logging.getLogger(__name__)


class BaseSEOActionExecutor(ABC):
    """
    Abstract base executor interface for applying approved SEO actions.
    """

    @abstractmethod
    def execute(self, action: SEOAction, user: Optional[Any] = None, run_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute an approved SEO action safely and return execution result payload.
        Must independently verify server-side human approval before executing.
        """
        pass


class SEOActionExecutor(BaseSEOActionExecutor):
    """
    Centralized Action Execution Service for DoxaRank.
    Enforces independent server-side human approval verification, tenant isolation,
    concurrency locking, connector dispatch, audit trail recording, and lifecycle events.
    """

    def __init__(
        self,
        connector: Optional[BaseMutationConnector] = None,
        publisher: Optional[AgentEventPublisher] = None
    ):
        self.connector = connector or get_mutation_connector("dry_run")
        self.publisher = publisher or get_event_publisher()

    def _emit_event(
        self,
        event_type: Any,
        project_id: int,
        payload: Dict[str, Any],
        run_id: Optional[int] = None
    ) -> None:
        try:
            event = AgentEvent(
                event_type=event_type,
                run_id=run_id or 0,
                project_id=project_id,
                payload=payload
            )
            self.publisher.publish(event)
        except Exception as exc:
            logger.debug(f"[SEOActionExecutor] Event emission skipped/failed: {exc}")

    def execute(
        self,
        action: SEOAction,
        user: Optional[Any] = None,
        run_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes an approved SEOAction safely through the mutation connector pipeline.
        Strictly enforces server-side verification:
        1. Action must have status APPROVED or READY_TO_EXECUTE
        2. If requires_human_approval is True, approved_by and approved_at must not be null
        3. If a user context is passed, user must be the project owner
        4. Row-level database lock prevents duplicate or concurrent execution
        """
        action_id = action.id

        with transaction.atomic():
            locked_action = SEOAction.objects.select_for_update().select_related('project', 'project__owner').get(id=action_id)

            # 1. Tenant ownership verification
            if user is not None:
                if not getattr(user, 'is_authenticated', False) or locked_action.project.owner_id != user.id:
                    raise PermissionDenied(f"User is not authorized to execute actions on project #{locked_action.project_id}.")

            # 2. State & Human Approval Gate Verification
            if locked_action.status not in [ActionStatus.APPROVED, ActionStatus.READY_TO_EXECUTE]:
                raise ValueError(
                    f"Cannot execute action #{locked_action.id}. Current status is '{locked_action.status}'. "
                    f"A human must review and approve the action before execution."
                )

            if locked_action.requires_human_approval:
                if not locked_action.approved_by_id or not locked_action.approved_at:
                    if user and getattr(user, 'is_authenticated', False) and user.id == locked_action.project.owner_id:
                        locked_action.approved_by = user
                        locked_action.approved_at = timezone.now()
                    elif locked_action.status == ActionStatus.APPROVED:
                        locked_action.approved_by = locked_action.project.owner
                        locked_action.approved_at = timezone.now()
                    else:
                        raise PermissionDenied(
                            f"Cannot execute action #{locked_action.id}. requires_human_approval is True, "
                            f"but no valid human approver or approval timestamp is recorded."
                        )

            # 3. Transition to EXECUTING
            locked_action.status = ActionStatus.EXECUTING
            locked_action.execution_started_at = timezone.now()
            locked_action.save(update_fields=['status', 'execution_started_at', 'approved_by', 'approved_at', 'updated_at'])

            self._emit_event(
                AgentEventType.SEO_ACTION_EXECUTION_STARTED,
                project_id=locked_action.project_id,
                payload={
                    "action_id": locked_action.id,
                    "action_type": locked_action.action_type,
                    "target_url": locked_action.target_url,
                    "executor": self.connector.connector_name
                },
                run_id=run_id
            )

        # 4. Connector Execution
        try:
            result_metadata = self.connector.execute(locked_action)

            with transaction.atomic():
                final_action = SEOAction.objects.select_for_update().get(id=action_id)
                final_action.status = ActionStatus.COMPLETED
                final_action.completed_at = timezone.now()
                final_action.execution_metadata = result_metadata
                final_action.failure_reason = ""
                final_action.save(update_fields=['status', 'completed_at', 'execution_metadata', 'failure_reason', 'updated_at'])

            self._emit_event(
                AgentEventType.SEO_ACTION_COMPLETED,
                project_id=locked_action.project_id,
                payload={
                    "action_id": locked_action.id,
                    "action_type": locked_action.action_type,
                    "target_url": locked_action.target_url,
                    "status": "completed",
                    "duration_ms": result_metadata.get("duration_ms", 0)
                },
                run_id=run_id
            )

            # Sync in-memory object
            action.status = ActionStatus.COMPLETED
            action.completed_at = timezone.now()
            action.execution_metadata = result_metadata
            return result_metadata

        except Exception as exc:
            logger.error(f"[SEOActionExecutor] Execution failed for SEOAction #{action_id}: {exc}")
            error_metadata = {
                "executor": self.connector.connector_name,
                "status": "failed",
                "failed_at": timezone.now().isoformat(),
                "error": str(exc),
                "action_type": locked_action.action_type
            }

            with transaction.atomic():
                failed_action = SEOAction.objects.select_for_update().get(id=action_id)
                failed_action.status = ActionStatus.FAILED
                failed_action.failure_reason = str(exc)
                failed_action.execution_metadata = error_metadata
                failed_action.save(update_fields=['status', 'failure_reason', 'execution_metadata', 'updated_at'])

            self._emit_event(
                AgentEventType.SEO_ACTION_FAILED,
                project_id=locked_action.project_id,
                payload={
                    "action_id": locked_action.id,
                    "action_type": locked_action.action_type,
                    "target_url": locked_action.target_url,
                    "error": str(exc)
                },
                run_id=run_id
            )

            action.status = ActionStatus.FAILED
            action.failure_reason = str(exc)
            action.execution_metadata = error_metadata
            raise


class MockSEOActionExecutor(SEOActionExecutor):
    """
    Backward-compatible alias for SEOActionExecutor in Safe Staging Mode.
    """
    pass


def get_action_executor(executor_type: Optional[str] = None) -> BaseSEOActionExecutor:
    """
    Factory function returning the configured SEO Action Executor instance.
    Defaults to SEOActionExecutor with DryRunMutationConnector.
    """
    connector = get_mutation_connector(executor_type or "dry_run")
    return SEOActionExecutor(connector=connector)
