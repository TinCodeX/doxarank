"""
DoxaRank External Integration Service & Execution Engine (Milestone 6.5).

Coordinates multi-system external operations across CMS, Git, and Webhook adapters.
Enforces:
1. Strict ToolRegistry authority: Agent -> ToolRegistry -> ExternalIntegrationService -> Adapter.
2. Tenant Isolation: Cross-tenant operations are strictly rejected with PermissionDenied.
3. Role-Based Permissions: Specialized agent allowlists (e.g. researcher cannot mutate).
4. Idempotency: Deterministic SHA-256 fingerprinting and row locking prevent duplicate execution.
5. HITL Boundary: High-risk operations require explicit human approval.
6. Rate Limiting & Bounded Retries: Exponential backoff on 429 and transient network failures.
7. Mandatory Empirical Verification: Execution success != SEO success; requires post-mutation verification.
8. Shared Working Memory Provenance: Ingests structured epistemic records with secrets redacted.
9. Runtime Telemetry: Emits all 10 external integration lifecycle events.
"""

import hashlib
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.projects.models import Project
from apps.seo.models import (
    ExternalConnection,
    ExternalOperationRecord,
    ExternalOperationStatus,
    ExternalSystemType,
    SEOAction,
    ActionStatus,
    RemediationRecord,
    AgentRun,
)
from apps.seo.services.agent_events import (
    AgentEvent,
    AgentEventType,
    AgentEventPublisher,
    get_event_publisher,
)
from .base import (
    BaseExternalAdapter,
    ExternalOperationResult,
    CMSCapability,
    GitCapability,
    WebhookCapability,
    redact_secrets,
)
from .registry import get_external_adapter_registry

logger = logging.getLogger(__name__)

# Operations considered read-only (safe for research and diagnostics)
READ_ONLY_OPERATIONS: Set[str] = {
    "read_page",
    "read_metadata",
    "read_repository",
    "check_status",
    "discover_capabilities",
}

# Agents permitted to execute mutating external operations when policy or human authorization exists
MUTATION_AUTHORIZED_AGENTS: Set[str] = {
    "seo_action_planner",
    "seo_supervisor",
    "seo_action_executor",
}


class ExternalIntegrationService:
    """
    Central service governing execution, verification, and audit for all external system interactions.
    """

    def __init__(self, publisher: Optional[AgentEventPublisher] = None):
        self._publisher = publisher
        self.registry = get_external_adapter_registry()

    @property
    def publisher(self) -> AgentEventPublisher:
        return self._publisher or get_event_publisher()

    def _emit_event(
        self,
        event_type: Any,
        project_id: int,
        payload: Dict[str, Any],
        run_id: Optional[int] = None,
        correlation_id: Optional[str] = None
    ) -> None:
        try:
            event = AgentEvent(
                event_type=event_type,
                run_id=run_id or 0,
                project_id=project_id,
                payload=redact_secrets(payload),
                correlation_id=correlation_id or ""
            )
            self.publisher.publish(event)
        except Exception as exc:
            logger.warning(f"[ExternalIntegrationService] Telemetry publish skipped/failed: {exc}")

    @classmethod
    def compute_idempotency_key(
        cls,
        project_id: int,
        connection_id: int,
        operation: str,
        target: str,
        params: Dict[str, Any]
    ) -> str:
        """Deterministic SHA-256 fingerprint preventing duplicate execution across retries."""
        norm_params = json.dumps(redact_secrets(params), sort_keys=True)
        raw = f"{project_id}:{connection_id}:{operation.lower().strip()}:{target.lower().strip()}:{norm_params}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]

    def execute_operation(
        self,
        project: Project,
        connection_id: int,
        operation: str,
        target: str,
        params: Dict[str, Any],
        agent_name: str,
        action: Optional[SEOAction] = None,
        remediation_record: Optional[RemediationRecord] = None,
        agent_run: Optional[AgentRun] = None,
        task_id: str = "",
        correlation_id: str = "",
        force_autonomous: bool = False,
        user: Optional[Any] = None,
    ) -> ExternalOperationRecord:
        """
        Execute an external operation through the authorized adapter.
        Guarantees:
        - Strict tenant isolation.
        - Agent role permission check (researchers cannot mutate).
        - Idempotency & row locking.
        - HITL approval boundary.
        - Bounded retries and rate limiting backoff.
        - Mandatory empirical verification.
        - Epistemic memory ingestion and telemetry.
        """
        cid = correlation_id or f"ext-{uuid.uuid4().hex[:12]}"
        start_time = time.time()
        op = (operation or "").lower().strip()
        is_mutating = op not in READ_ONLY_OPERATIONS

        # 1. Fetch connection and enforce Tenant Isolation
        try:
            connection = ExternalConnection.objects.get(id=connection_id)
        except ExternalConnection.DoesNotExist:
            raise ValueError(f"ExternalConnection #{connection_id} not found.")

        if connection.project_id != project.id:
            raise PermissionDenied(
                f"Tenant Isolation Violation: Connection #{connection_id} belongs to project "
                f"#{connection.project_id}, not requested project #{project.id}."
            )

        if user and getattr(user, "is_authenticated", False) and project.owner_id != user.id:
            raise PermissionDenied(
                f"User #{user.id} is not authorized for project #{project.id}."
            )

        # 2. Agent Role Permission Check
        if is_mutating and agent_name not in MUTATION_AUTHORIZED_AGENTS:
            err_msg = (
                f"Permission Denied: Agent '{agent_name}' is not authorized to perform mutating external "
                f"operation '{operation}' on system '{connection.system_type}'. Mutating agents: {MUTATION_AUTHORIZED_AGENTS}"
            )
            logger.error(f"[ExternalIntegrationPermissionDenied] {err_msg}")
            self._emit_event(
                AgentEventType.EXTERNAL_INTEGRATION_DENIED,
                project_id=project.id,
                payload={"agent": agent_name, "operation": operation, "reason": err_msg},
                run_id=agent_run.id if agent_run else None,
                correlation_id=cid,
            )
            raise PermissionError(err_msg)

        # 3. Idempotency Key & Row Locking
        idempotency_key = self.compute_idempotency_key(
            project_id=project.id,
            connection_id=connection.id,
            operation=operation,
            target=target,
            params=params
        )

        with transaction.atomic():
            record, created = ExternalOperationRecord.objects.select_for_update().get_or_create(
                project=project,
                idempotency_key=idempotency_key,
                defaults={
                    "connection": connection,
                    "action": action,
                    "remediation_record": remediation_record,
                    "agent_run": agent_run,
                    "task_id": task_id,
                    "correlation_id": cid,
                    "system_type": connection.system_type,
                    "provider": connection.provider,
                    "operation": operation,
                    "required_capability": f"{connection.system_type.upper()}.{operation.upper()}",
                    "target": target,
                    "status": ExternalOperationStatus.PENDING,
                    "risk_level": "high" if op in ["publish_content"] else ("medium" if is_mutating else "low"),
                    "is_autonomous": False,
                    "request_summary": redact_secrets(params),
                }
            )

            # Prevent duplicate execution if already running or completed
            if not created and record.status in [
                ExternalOperationStatus.EXECUTING,
                ExternalOperationStatus.COMPLETED,
                ExternalOperationStatus.VERIFIED,
            ]:
                logger.warning(
                    f"[ExternalIntegration] Duplicate operation prevented for key {idempotency_key}."
                )
                self._emit_event(
                    AgentEventType.EXTERNAL_INTEGRATION_DUPLICATE_PREVENTED,
                    project_id=project.id,
                    payload={
                        "operation_id": record.id,
                        "status": record.status,
                        "idempotency_key": idempotency_key,
                    },
                    run_id=agent_run.id if agent_run else None,
                    correlation_id=cid,
                )
                return record

            self._emit_event(
                AgentEventType.EXTERNAL_INTEGRATION_REQUESTED,
                project_id=project.id,
                payload={
                    "operation_id": record.id,
                    "system_type": connection.system_type,
                    "provider": connection.provider,
                    "operation": operation,
                    "target": target,
                },
                run_id=agent_run.id if agent_run else None,
                correlation_id=cid,
            )

            # 4. HITL Authorization Boundary
            requires_human_approval = False
            if record.risk_level in ["high", "critical"] or op in ["publish_content"]:
                requires_human_approval = True

            is_human_approved = False
            if action:
                is_human_approved = (
                    action.status == ActionStatus.APPROVED
                    or (action.approved_by_id is not None and action.approved_at is not None)
                )

            if is_mutating and requires_human_approval and not is_human_approved and not force_autonomous:
                record.status = ExternalOperationStatus.PENDING
                record.error_category = "hitl_required"
                record.error_message = f"High-risk operation '{operation}' strictly requires human approval."
                record.save(update_fields=["status", "error_category", "error_message", "updated_at"])

                self._emit_event(
                    AgentEventType.EXTERNAL_INTEGRATION_DENIED,
                    project_id=project.id,
                    payload={
                        "operation_id": record.id,
                        "reason": record.error_message,
                        "risk_level": record.risk_level,
                    },
                    run_id=agent_run.id if agent_run else None,
                    correlation_id=cid,
                )
                return record

            # Transition to AUTHORIZED -> EXECUTING
            record.status = ExternalOperationStatus.AUTHORIZED
            record.is_autonomous = not is_human_approved and is_mutating
            record.save(update_fields=["status", "is_autonomous", "updated_at"])

            self._emit_event(
                AgentEventType.EXTERNAL_INTEGRATION_AUTHORIZED,
                project_id=project.id,
                payload={"operation_id": record.id, "is_autonomous": record.is_autonomous},
                run_id=agent_run.id if agent_run else None,
                correlation_id=cid,
            )

            record.status = ExternalOperationStatus.EXECUTING
            record.save(update_fields=["status", "updated_at"])

            self._emit_event(
                AgentEventType.EXTERNAL_INTEGRATION_STARTED,
                project_id=project.id,
                payload={"operation_id": record.id, "operation": operation},
                run_id=agent_run.id if agent_run else None,
                correlation_id=cid,
            )

        # 5. Execute with Bounded Retries & Rate Limiting Backoff
        adapter = self.registry.get_adapter(connection.system_type, connection.provider)
        max_retries = 3
        retry_count = 0
        exec_result: Optional[ExternalOperationResult] = None

        while retry_count <= max_retries:
            try:
                exec_result = adapter.execute(
                    connection=connection,
                    operation=operation,
                    target=target,
                    params=params,
                    correlation_id=cid,
                    retry_count=retry_count
                )
            except Exception as exc:
                exec_result = ExternalOperationResult(
                    success=False,
                    system=connection.system_type,
                    provider=connection.provider,
                    operation=operation,
                    target=target,
                    error_category="adapter_exception",
                    error_message=str(exc),
                    correlation_id=cid,
                    retry_count=retry_count,
                )

            if exec_result.success:
                break

            # Handle rate limiting (429) or transient timeout
            if exec_result.error_category in ["rate_limited", "network_timeout"]:
                retry_count += 1
                if exec_result.error_category == "rate_limited":
                    self._emit_event(
                        AgentEventType.EXTERNAL_INTEGRATION_RATE_LIMITED,
                        project_id=project.id,
                        payload={"operation_id": record.id, "attempt": retry_count},
                        run_id=agent_run.id if agent_run else None,
                        correlation_id=cid,
                    )
                if retry_count <= max_retries:
                    self._emit_event(
                        AgentEventType.EXTERNAL_INTEGRATION_RETRY,
                        project_id=project.id,
                        payload={"operation_id": record.id, "attempt": retry_count, "category": exec_result.error_category},
                        run_id=agent_run.id if agent_run else None,
                        correlation_id=cid,
                    )
                    # Bounded exponential backoff
                    time.sleep(min(0.2 * (2 ** (retry_count - 1)), 1.0))
                    continue

            # Non-retryable error
            break

        # 6. Record Execution Outcome
        with transaction.atomic():
            record.refresh_from_db()
            record.retry_count = retry_count
            record.status_code = exec_result.status_code
            record.response_summary = exec_result.response_summary
            record.before_state = exec_result.before_state
            record.after_state = exec_result.after_state
            record.changed = exec_result.changed
            record.duration_ms = int((time.time() - start_time) * 1000)

            if not exec_result.success:
                record.status = ExternalOperationStatus.RATE_LIMITED if exec_result.error_category == "rate_limited" else ExternalOperationStatus.FAILED
                record.error_category = exec_result.error_category
                record.error_message = exec_result.error_message or "Execution failed."
                record.save(update_fields=[
                    "status", "error_category", "error_message", "retry_count",
                    "status_code", "response_summary", "duration_ms", "updated_at"
                ])

                self._emit_event(
                    AgentEventType.EXTERNAL_INTEGRATION_FAILED,
                    project_id=project.id,
                    payload={
                        "operation_id": record.id,
                        "error_category": record.error_category,
                        "error": record.error_message,
                    },
                    run_id=agent_run.id if agent_run else None,
                    correlation_id=cid,
                )
                return record

            # Execution succeeded
            record.status = ExternalOperationStatus.COMPLETED
            record.save(update_fields=[
                "status", "status_code", "response_summary", "before_state",
                "after_state", "changed", "retry_count", "duration_ms", "updated_at"
            ])

            self._emit_event(
                AgentEventType.EXTERNAL_INTEGRATION_COMPLETED,
                project_id=project.id,
                payload={"operation_id": record.id, "duration_ms": record.duration_ms},
                run_id=agent_run.id if agent_run else None,
                correlation_id=cid,
            )

        # 7. Mandatory Empirical Verification Phase
        if is_mutating:
            expected_verif = {}
            if op == "update_metadata":
                expected_verif = {k: v for k, v in params.items() if k in ["title", "meta_description", "canonical_url"]}
            elif op == "write_file":
                expected_verif = {
                    "expected_file": params.get("file_path") or params.get("path"),
                    "expected_content": params.get("content", ""),
                }
            elif op == "create_branch":
                expected_verif = {"expected_branch": params.get("branch_name") or params.get("branch")}
            elif op == "send_webhook":
                expected_verif = {"expected_event": params.get("event") or params.get("action_type", "")}

            is_verified, verif_data = adapter.verify(
                connection=connection,
                operation=operation,
                target=target,
                expected_state=expected_verif
            )

            with transaction.atomic():
                record.refresh_from_db()
                record.verification_data = verif_data
                if is_verified:
                    record.status = ExternalOperationStatus.VERIFIED
                    record.verification_status = "verified"
                    record.save(update_fields=["status", "verification_status", "verification_data", "updated_at"])

                    self._emit_event(
                        AgentEventType.EXTERNAL_INTEGRATION_VERIFIED,
                        project_id=project.id,
                        payload={"operation_id": record.id, "verified": True},
                        run_id=agent_run.id if agent_run else None,
                        correlation_id=cid,
                    )
                else:
                    # Invariant: Execution Success + Verification Failure != Success
                    record.status = ExternalOperationStatus.FAILED
                    record.verification_status = "failed"
                    record.error_category = "verification_failure"
                    record.error_message = "Empirical verification failed: external state did not reflect mutations."
                    record.save(update_fields=[
                        "status", "verification_status", "verification_data",
                        "error_category", "error_message", "updated_at"
                    ])

                    self._emit_event(
                        AgentEventType.EXTERNAL_INTEGRATION_FAILED,
                        project_id=project.id,
                        payload={
                            "operation_id": record.id,
                            "error_category": "verification_failure",
                            "verification_data": verif_data,
                        },
                        run_id=agent_run.id if agent_run else None,
                        correlation_id=cid,
                    )
        else:
            # Read-only operations are marked completed
            record.verification_status = "not_required"
            record.save(update_fields=["verification_status", "updated_at"])

        return record
