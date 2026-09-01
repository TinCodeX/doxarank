import logging
from typing import Optional, Dict, Any, Union
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from apps.projects.models import Project
from apps.seo.models import SEOAction, ActionStatus
from .agent_events import AgentEventPublisher, AgentEventType, AgentEvent, get_event_publisher

logger = logging.getLogger(__name__)


class ActionApprovalService:
    """
    Centralized Backend Mutation Approval Gate for DoxaRank.
    Enforces that no autonomous agent or unauthorized user can execute website mutations.
    Enforces project ownership, valid transition states, atomicity with row-level locking,
    auditable timestamps/approver tracking, and event broadcasting.
    """

    VALID_APPROVAL_STATUSES = {
        ActionStatus.PENDING_APPROVAL,
        ActionStatus.PROPOSED,
        ActionStatus.REVIEWED,
    }

    def __init__(self, publisher: Optional[AgentEventPublisher] = None):
        self.publisher = publisher or get_event_publisher()

    def _emit_event(
        self,
        event_type: Union[AgentEventType, str],
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
            logger.debug(f"[ActionApprovalService] Event emission skipped/failed: {exc}")

    def approve_action(
        self,
        action_id: int,
        user: Any,
        run_id: Optional[int] = None
    ) -> SEOAction:
        """
        Approve an SEOAction, making it eligible for controlled execution.
        Strictly requires project owner authorization and atomic state transition.
        """
        if not user or not getattr(user, 'is_authenticated', False):
            raise PermissionDenied("Authentication required to approve SEO actions.")

        with transaction.atomic():
            try:
                action = SEOAction.objects.select_for_update().select_related('project').get(id=action_id)
            except SEOAction.DoesNotExist:
                raise ValueError(f"SEOAction #{action_id} does not exist.")

            # Strict Tenant Isolation: Only project owner can approve
            if action.project.owner_id != user.id:
                raise PermissionDenied(f"User '{getattr(user, 'email', user)}' is not the owner of project #{action.project_id}.")

            if action.status not in self.VALID_APPROVAL_STATUSES:
                raise ValueError(
                    f"Cannot approve action #{action.id}. Current status is '{action.status}'. "
                    f"Only actions in {list(self.VALID_APPROVAL_STATUSES)} can be approved."
                )

            action.status = ActionStatus.APPROVED
            action.approved_by = user
            action.approved_at = timezone.now()
            action.rejected_by = None
            action.rejected_at = None
            action.rejection_reason = ""
            action.save(update_fields=[
                'status', 'approved_by', 'approved_at',
                'rejected_by', 'rejected_at', 'rejection_reason',
                'updated_at'
            ])

            logger.info(f"[ActionApprovalService] SEOAction #{action.id} APPROVED by User #{user.id} ({user.email}).")

            self._emit_event(
                AgentEventType.SEO_ACTION_APPROVED,
                project_id=action.project_id,
                payload={
                    "action_id": action.id,
                    "action_type": action.action_type,
                    "title": action.title,
                    "target_url": action.target_url,
                    "approved_by_id": user.id,
                    "approved_by_email": getattr(user, 'email', str(user)),
                    "approved_at": action.approved_at.isoformat() if action.approved_at else None,
                    "requires_human_approval": action.requires_human_approval,
                    "risk_level": action.risk_level
                },
                run_id=run_id
            )

            return action

    def reject_action(
        self,
        action_id: int,
        user: Any,
        reason: str,
        run_id: Optional[int] = None
    ) -> SEOAction:
        """
        Reject an SEOAction with an explicit, auditable reason.
        Strictly requires project owner authorization and atomic state transition.
        """
        if not user or not getattr(user, 'is_authenticated', False):
            raise PermissionDenied("Authentication required to reject SEO actions.")

        if not reason or not str(reason).strip():
            raise ValueError("A meaningful rejection reason is required to reject an SEO action.")

        clean_reason = str(reason).strip()

        with transaction.atomic():
            try:
                action = SEOAction.objects.select_for_update().select_related('project').get(id=action_id)
            except SEOAction.DoesNotExist:
                raise ValueError(f"SEOAction #{action_id} does not exist.")

            # Strict Tenant Isolation: Only project owner can reject
            if action.project.owner_id != user.id:
                raise PermissionDenied(f"User '{getattr(user, 'email', user)}' is not the owner of project #{action.project_id}.")

            if action.status not in self.VALID_APPROVAL_STATUSES:
                raise ValueError(
                    f"Cannot reject action #{action.id}. Current status is '{action.status}'. "
                    f"Only actions in {list(self.VALID_APPROVAL_STATUSES)} can be rejected."
                )

            action.status = ActionStatus.REJECTED
            action.rejected_by = user
            action.rejected_at = timezone.now()
            action.rejection_reason = clean_reason
            action.save(update_fields=[
                'status', 'rejected_by', 'rejected_at', 'rejection_reason',
                'updated_at'
            ])

            logger.info(f"[ActionApprovalService] SEOAction #{action.id} REJECTED by User #{user.id}. Reason: {clean_reason}")

            self._emit_event(
                AgentEventType.SEO_ACTION_REJECTED,
                project_id=action.project_id,
                payload={
                    "action_id": action.id,
                    "action_type": action.action_type,
                    "title": action.title,
                    "target_url": action.target_url,
                    "rejected_by_id": user.id,
                    "rejected_by_email": getattr(user, 'email', str(user)),
                    "rejected_at": action.rejected_at.isoformat() if action.rejected_at else None,
                    "rejection_reason": clean_reason
                },
                run_id=run_id
            )

            return action
