"""
Celery background tasks for autonomous SEO agent execution in DoxaRank.

Provides idempotent, concurrency-safe, retry-aware asynchronous execution of AgentRun
sessions using Celery and Redis.
"""

import logging
from typing import Optional
from celery import shared_task
from django.db import transaction, OperationalError
from django.utils import timezone

from apps.seo.models import (
    AgentRun, AgentRunStatus, AgentStep, AgentStepStatus,
    SEOAction, ActionStatus,
    SiteAudit, AuditStatus, AuditIssue
)
from apps.seo.services.agent_orchestrator import AgentOrchestrator
from apps.seo.services.action_executors import get_action_executor
from apps.seo.services.live_site_crawler import LiveSiteCrawlerService
from apps.seo.services.seo_audit_engine import SEOAuditEngine

logger = logging.getLogger(__name__)

# Transient error classes eligible for automatic bounded Celery retries
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OperationalError,
)

try:
    import redis.exceptions
    RETRYABLE_EXCEPTIONS += (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError)
except ImportError:
    pass

try:
    import requests.exceptions
    RETRYABLE_EXCEPTIONS += (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.HTTPError
    )
except ImportError:
    pass


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name='apps.seo.tasks.execute_agent_run'
)
def execute_agent_run(
    self,
    run_id: int,
    is_resume: bool = False,
    approval_decision: str = "approved"
) -> Optional[int]:
    """
    Execute or resume an AgentRun session asynchronously inside a Celery worker.

    Guarantees:
    - Multi-tenant data integrity: runs are bound to their authentic project & user.
    - Idempotency & Concurrency: uses select_for_update() row locks to prevent
      duplicate execution across parallel Celery workers.
    - Safe state transitions: only PENDING runs can start, only WAITING_FOR_APPROVAL
      runs can be resumed.
    - Resilient error handling: bounded exponential retries for transient connection
      failures, safe terminal failure states without sensitive credential leakage.
    """
    # 1. Fetch and lock run atomically to ensure safe state transition
    try:
        with transaction.atomic():
            try:
                run = AgentRun.objects.select_for_update().select_related('project', 'user').get(id=run_id)
            except AgentRun.DoesNotExist:
                logger.error(f"[Celery Task] AgentRun #{run_id} does not exist. Aborting task.")
                return None

            if is_resume:
                # Validate resume precondition
                if run.status != AgentRunStatus.WAITING_FOR_APPROVAL:
                    logger.warning(
                        f"[Celery Task] AgentRun #{run_id} cannot be resumed because current status is '{run.status}'."
                    )
                    return run.id

                decision = (approval_decision or "approved").lower()
                latest_step = run.steps.order_by('-step_number').first()

                if decision == "approved":
                    logger.info(f"[Celery Task] Resuming AgentRun #{run_id} with APPROVAL.")
                    
                    # Execute proposed action safely
                    proposed_action = SEOAction.objects.filter(
                        project=run.project,
                        status=ActionStatus.PROPOSED
                    ).order_by('-created_at').first()

                    if proposed_action:
                        proposed_action.status = ActionStatus.APPROVED
                        proposed_action.save(update_fields=['status', 'updated_at'])
                        executor = get_action_executor()
                        executor.execute(proposed_action)

                    if latest_step:
                        latest_step.status = AgentStepStatus.COMPLETED
                        latest_step.thought += "\n[Human Approval]: SEO Action was reviewed, approved, and executed by safe action executor."
                        latest_step.save(update_fields=['status', 'thought'])

                    run.status = AgentRunStatus.RUNNING
                    run.save(update_fields=['status', 'updated_at'])
                else:
                    logger.info(f"[Celery Task] Terminating AgentRun #{run_id} due to REJECTION.")
                    
                    # Mark proposed action as rejected
                    proposed_action = SEOAction.objects.filter(
                        project=run.project,
                        status=ActionStatus.PROPOSED
                    ).order_by('-created_at').first()

                    if proposed_action:
                        proposed_action.status = ActionStatus.REJECTED
                        proposed_action.save(update_fields=['status', 'updated_at'])

                    if latest_step:
                        latest_step.status = AgentStepStatus.FAILED
                        latest_step.thought += "\n[Human Rejection]: Proposed SEO Action was rejected by user."
                        latest_step.save(update_fields=['status', 'thought'])

                    run.status = AgentRunStatus.CANCELLED
                    run.summary = "Run terminated because human user rejected the proposed SEO Action."
                    run.completed_at = timezone.now()
                    run.save(update_fields=['status', 'summary', 'completed_at', 'updated_at'])
                    return run.id

            else:
                # Validate initial run precondition
                if run.status != AgentRunStatus.PENDING:
                    logger.warning(
                        f"[Celery Task] AgentRun #{run_id} is not PENDING (current status: '{run.status}'). Skipping execution to prevent duplicate processing."
                    )
                    return run.id

                # Transition atomically PENDING -> RUNNING
                run.status = AgentRunStatus.RUNNING
                run.save(update_fields=['status', 'updated_at'])

    except Exception as lock_exc:
        logger.exception(f"[Celery Task] Database error acquiring lock for AgentRun #{run_id}: {lock_exc}")
        if isinstance(lock_exc, RETRYABLE_EXCEPTIONS) and self.request.retries < self.max_retries:
            raise self.retry(exc=lock_exc, countdown=2 ** self.request.retries)
        return None

    # 2. Execute the ReAct Orchestrator loop
    try:
        orchestrator = AgentOrchestrator(
            project=run.project,
            user=run.user
        )
        orchestrator.execute_loop(run)
        logger.info(f"[Celery Task] Completed execution loop for AgentRun #{run_id} (Final status: '{run.status}').")
        return run.id

    except RETRYABLE_EXCEPTIONS as retry_exc:
        logger.warning(
            f"[Celery Task] Transient error executing AgentRun #{run_id} (attempt {self.request.retries + 1}/{self.max_retries}): {retry_exc}"
        )
        if self.request.retries < self.max_retries:
            countdown = (2 ** self.request.retries) * 5
            raise self.retry(exc=retry_exc, countdown=countdown)
        else:
            # Exhausted retries -> mark as FAILED safely
            logger.error(f"[Celery Task] Max retries reached for AgentRun #{run_id}. Marking run as FAILED.")
            _mark_run_failed(run, f"Transient execution failure after {self.max_retries} retries: {str(retry_exc)}")
            return run.id

    except Exception as fatal_exc:
        logger.exception(f"[Celery Task] Non-retryable error executing AgentRun #{run_id}: {fatal_exc}")
        _mark_run_failed(run, f"Fatal agent execution error: {fatal_exc.__class__.__name__} - {str(fatal_exc)}")
        return run.id


def _mark_run_failed(run: AgentRun, error_summary: str) -> None:
    """Helper to transition an AgentRun to terminal FAILED state safely."""
    try:
        run.refresh_from_db()
        run.status = AgentRunStatus.FAILED
        # Sanitize message to prevent accidental token/key exposure
        clean_summary = error_summary.replace("sk-", "sk-***")[:500]
        run.summary = clean_summary
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'summary', 'completed_at', 'updated_at'])
    except Exception as e:
        logger.error(f"Failed to record FAILED status for AgentRun #{run.id}: {e}")


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='apps.seo.tasks.run_site_audit'
)
def run_site_audit(
    self,
    audit_id: int,
    start_url: Optional[str] = None,
    max_pages: int = 50,
    max_depth: int = 3
) -> Optional[int]:
    """
    Execute website crawl and SEO audit evaluation asynchronously in Celery worker.

    Guarantees:
    - Atomically transitions SiteAudit status PENDING -> RUNNING.
    - Bounded live website crawl using LiveSiteCrawlerService.
    - Deterministic SEO audit rule evaluation via SEOAuditEngine.
    - Idempotent persistence of SiteAudit health score and AuditIssue records.
    - Graceful error recovery: transitions SiteAudit to FAILED without hanging on unexpected exceptions.
    """
    try:
        with transaction.atomic():
            try:
                audit = SiteAudit.objects.select_for_update().select_related('project').get(id=audit_id)
            except SiteAudit.DoesNotExist:
                logger.error(f"[Celery Audit Task] SiteAudit #{audit_id} does not exist. Aborting task.")
                return None

            if audit.status not in (AuditStatus.PENDING, AuditStatus.RUNNING):
                logger.warning(
                    f"[Celery Audit Task] SiteAudit #{audit_id} status is '{audit.status}'. Skipping execution."
                )
                return audit.id

            audit.status = AuditStatus.RUNNING
            audit.started_at = audit.started_at or timezone.now()
            audit.save(update_fields=['status', 'started_at', 'updated_at'])

    except Exception as lock_exc:
        logger.exception(f"[Celery Audit Task] Database error acquiring lock for SiteAudit #{audit_id}: {lock_exc}")
        if isinstance(lock_exc, RETRYABLE_EXCEPTIONS) and self.request.retries < self.max_retries:
            raise self.retry(exc=lock_exc, countdown=2 ** self.request.retries)
        return None

    try:
        # 1. Execute live website crawl
        crawler = LiveSiteCrawlerService(
            project=audit.project,
            max_pages=max_pages,
            max_depth=max_depth
        )
        target_start_url = start_url or audit.project.website_url
        crawl_result = crawler.crawl(target_start_url)

        # 2. Evaluate SEO rules & persist SiteAudit + AuditIssue records
        engine = SEOAuditEngine()
        engine.persist_audit(
            project=audit.project,
            crawl_result=crawl_result,
            audit=audit
        )

        logger.info(
            f"[Celery Audit Task] Successfully completed SiteAudit #{audit.id} "
            f"for project #{audit.project.id} (Score: {audit.score})."
        )
        return audit.id

    except RETRYABLE_EXCEPTIONS as retry_exc:
        logger.warning(
            f"[Celery Audit Task] Transient error executing SiteAudit #{audit_id} "
            f"(attempt {self.request.retries + 1}/{self.max_retries}): {retry_exc}"
        )
        if self.request.retries < self.max_retries:
            countdown = (2 ** self.request.retries) * 5
            raise self.retry(exc=retry_exc, countdown=countdown)
        else:
            _mark_audit_failed(audit, f"Transient crawl failure after {self.max_retries} retries: {str(retry_exc)}")
            return audit.id

    except Exception as fatal_exc:
        logger.exception(f"[Celery Audit Task] Non-retryable error executing SiteAudit #{audit_id}: {fatal_exc}")
        _mark_audit_failed(audit, f"Fatal audit execution error: {fatal_exc.__class__.__name__} - {str(fatal_exc)}")
        return audit.id


def _mark_audit_failed(audit: SiteAudit, error_message: str) -> None:
    """Helper to transition a SiteAudit to terminal FAILED state safely."""
    try:
        audit.refresh_from_db()
        audit.status = AuditStatus.FAILED
        audit.error_message = error_message[:500]
        audit.completed_at = timezone.now()
        audit.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
    except Exception as e:
        logger.error(f"Failed to record FAILED status for SiteAudit #{audit.id}: {e}")
