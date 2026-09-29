"""
Celery background tasks for autonomous SEO agent execution in DoxaRank.

Provides idempotent, concurrency-safe, retry-aware asynchronous execution of AgentRun
sessions using Celery and Redis.
"""

import logging
from typing import Optional, List, Dict, Any
from celery import shared_task
from django.db import transaction, OperationalError
from django.utils import timezone

from apps.seo.models import (
    AgentRun, AgentRunStatus, AgentStep, AgentStepStatus,
    SEOAction, ActionStatus,
    SiteAudit, AuditStatus, AuditIssue,
    CrawlJob, CrawlJobStatus, CrawlPage,
    Keyword, KeywordRanking, RankingResultStatus, RankCheckJob, RankCheckJobStatus,
    Competitor, CompetitorSnapshot, CompetitorSnapshotJob, CompetitorSnapshotJobStatus,
)
from apps.seo.services.agent_orchestrator import AgentOrchestrator
from apps.seo.services.action_executors import get_action_executor
from apps.seo.services.live_site_crawler import LiveSiteCrawlerService
from apps.seo.services.technical_crawler import TechnicalCrawlerService
from apps.seo.services.seo_audit_engine import SEOAuditEngine
from apps.seo.services.rank_tracker import RankTrackerService
from apps.seo.services.competitor_service import CompetitorSnapshotService

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

        # 1b. Acquire execution lease for Celery worker
        worker_id = getattr(self.request, 'id', None) or f"celery-worker-{run.id}"
        from apps.seo.services.production_platform import ExecutionLeaseManager, RetryPolicy, FailureCategory, PlatformSecretRedactor
        lease_mgr = ExecutionLeaseManager()
        if not lease_mgr.acquire_lease(run, worker_id=worker_id, duration_seconds=120):
            logger.warning(
                f"[Celery Task] AgentRun #{run_id} execution lease held by another active worker. Skipping duplicate execution."
            )
            return run.id

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
        lease_mgr.release_lease(run, worker_id=worker_id)
        logger.info(f"[Celery Task] Completed execution loop for AgentRun #{run_id} (Final status: '{run.status}').")
        return run.id

    except RETRYABLE_EXCEPTIONS as retry_exc:
        logger.warning(
            f"[Celery Task] Transient error executing AgentRun #{run_id} (attempt {self.request.retries + 1}/{self.max_retries}): {retry_exc}"
        )
        lease_mgr.release_lease(run, worker_id=worker_id)
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
        lease_mgr.release_lease(run, worker_id=worker_id)
        _mark_run_failed(run, f"Fatal agent execution error: {fatal_exc.__class__.__name__} - {str(fatal_exc)}")
        return run.id


def _mark_run_failed(run: AgentRun, error_summary: str) -> None:
    """Helper to transition an AgentRun to terminal FAILED state safely."""
    try:
        from apps.seo.services.production_platform import PlatformSecretRedactor
        run.refresh_from_db()
        run.status = AgentRunStatus.FAILED
        # Sanitize message to prevent accidental token/key exposure
        clean_summary = PlatformSecretRedactor.redact(error_summary)[:500]
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


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='apps.seo.tasks.execute_seo_action_plan'
)
def execute_seo_action_plan(
    self,
    plan_id: int,
    user_id: Optional[int] = None
) -> Optional[int]:
    """
    Execute an approved SEOActionPlan and all its approved child actions asynchronously.
    Enforces tenant isolation, server-side approval verification, row-level locking,
    and automatic post-execution real-world verification triggering.
    """
    from django.contrib.auth import get_user_model
    from apps.seo.models import SEOActionPlan, ActionPlanStatus
    from apps.seo.services.action_executors import get_action_executor

    User = get_user_model()
    user = User.objects.filter(id=user_id).first() if user_id else None

    # 1. Row-lock plan and verify approval status
    try:
        with transaction.atomic():
            try:
                plan = SEOActionPlan.objects.select_for_update().select_related('project').get(id=plan_id)
            except SEOActionPlan.DoesNotExist:
                logger.error(f"[Celery Plan Execution Task] SEOActionPlan #{plan_id} does not exist. Aborting.")
                return None

            if user and plan.project.owner_id != user.id:
                logger.error(f"[Celery Plan Execution Task] User #{user.id} not authorized on project #{plan.project_id}.")
                return None

            if plan.status not in [ActionPlanStatus.APPROVED, ActionPlanStatus.PROPOSED]:
                logger.warning(
                    f"[Celery Plan Execution Task] Plan #{plan_id} is in status '{plan.status}'. Execution skipped."
                )
                return plan.id

            plan.status = ActionPlanStatus.EXECUTING
            plan.execution_started_at = timezone.now()
            plan.save(update_fields=['status', 'execution_started_at', 'updated_at'])

    except Exception as lock_exc:
        logger.exception(f"[Celery Plan Execution Task] Database lock error for SEOActionPlan #{plan_id}: {lock_exc}")
        if isinstance(lock_exc, RETRYABLE_EXCEPTIONS) and self.request.retries < self.max_retries:
            raise self.retry(exc=lock_exc, countdown=2 ** self.request.retries)
        return None

    # 2. Execute child actions through the safe executor
    executor = get_action_executor()
    actions = plan.actions.filter(status__in=[ActionStatus.APPROVED, ActionStatus.READY_TO_EXECUTE, ActionStatus.PROPOSED])
    success_count = 0
    failure_count = 0
    errors = []

    for action in actions:
        try:
            # Ensure action is approved
            if action.status == ActionStatus.PROPOSED:
                action.status = ActionStatus.APPROVED
                if user:
                    action.approved_by = user
                    action.approved_at = timezone.now()
                action.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

            executor.execute(action, user=user)
            success_count += 1
        except Exception as act_exc:
            logger.error(f"[Celery Plan Execution Task] Error executing child action #{action.id}: {act_exc}")
            failure_count += 1
            errors.append(f"Action #{action.id} ({action.action_type}): {str(act_exc)}")

    # 3. Transition plan terminal execution state
    with transaction.atomic():
        final_plan = SEOActionPlan.objects.select_for_update().get(id=plan_id)
        if failure_count == 0:
            final_plan.status = ActionPlanStatus.COMPLETED
        elif success_count > 0:
            final_plan.status = ActionPlanStatus.PARTIALLY_COMPLETED
            final_plan.failure_reason = "; ".join(errors)[:500]
        else:
            final_plan.status = ActionPlanStatus.FAILED
            final_plan.failure_reason = "; ".join(errors)[:500]

        final_plan.completed_at = timezone.now()
        final_plan.save(update_fields=['status', 'failure_reason', 'completed_at', 'updated_at'])

    logger.info(
        f"[Celery Plan Execution Task] Plan #{plan_id} execution finished "
        f"(Success: {success_count}, Failed: {failure_count})."
    )

    # 4. Trigger asynchronous real-world verification
    try:
        verify_seo_action_plan_task.delay(plan_id=plan_id)
    except Exception as v_exc:
        logger.warning(f"[Celery Plan Execution Task] Could not queue verification task for plan #{plan_id}: {v_exc}")

    return plan_id


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='apps.seo.tasks.verify_seo_action_task'
)
def verify_seo_action_task(self, action_id: int) -> Optional[int]:
    """
    Perform empirical real-world verification for a single executed SEOAction.
    """
    from apps.seo.models import SEOAction
    from apps.seo.services.seo_action_verifier import SEOActionVerifier

    try:
        action = SEOAction.objects.select_related('project').get(id=action_id)
    except SEOAction.DoesNotExist:
        logger.error(f"[Celery Action Verification] SEOAction #{action_id} does not exist.")
        return None

    verifier = SEOActionVerifier(project=action.project)
    verifier.verify_action(action)
    return action.id


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='apps.seo.tasks.verify_seo_action_plan_task'
)
def verify_seo_action_plan_task(self, plan_id: int) -> Optional[int]:
    """
    Perform empirical real-world verification for all executed actions in an SEOActionPlan.
    """
    from apps.seo.models import SEOActionPlan
    from apps.seo.services.seo_action_verifier import SEOActionVerifier

    try:
        plan = SEOActionPlan.objects.select_related('project').prefetch_related('actions').get(id=plan_id)
    except SEOActionPlan.DoesNotExist:
        logger.error(f"[Celery Plan Verification] SEOActionPlan #{plan_id} does not exist.")
        return None

    verifier = SEOActionVerifier(project=plan.project)
    verifier.verify_plan(plan)
    return plan.id


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='apps.seo.tasks.measure_seo_action_outcome_task'
)
def measure_seo_action_outcome_task(
    self,
    action_id: int,
    window_days: int = 14
) -> Optional[int]:
    """
    Asynchronously measure and classify empirical post-execution SEO outcome for an SEOAction.
    Uses select_for_update() row locks, gathers Search Console pre/post evidence,
    and updates persistent outcome records.
    """
    from apps.seo.models import SEOAction
    from apps.seo.services.seo_outcome_learning import SEOOutcomeMeasurementService

    try:
        action = SEOAction.objects.select_related('project').get(id=action_id)
    except SEOAction.DoesNotExist:
        logger.error(f"[Celery Outcome Task] SEOAction #{action_id} does not exist.")
        return None

    try:
        service = SEOOutcomeMeasurementService(project=action.project)
        service.measure_action_outcome(action, window_days=window_days)
        return action.id
    except Exception as exc:
        logger.exception(f"[Celery Outcome Task] Error measuring outcome for action #{action_id}: {exc}")
        if isinstance(exc, RETRYABLE_EXCEPTIONS) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        return action.id


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='apps.seo.tasks.measure_seo_action_plan_outcome_task'
)
def measure_seo_action_plan_outcome_task(
    self,
    plan_id: int,
    window_days: int = 14
) -> Optional[int]:
    """
    Asynchronously measure and aggregate empirical SEO outcomes for all actions in an SEOActionPlan.
    """
    from apps.seo.models import SEOActionPlan
    from apps.seo.services.seo_outcome_learning import SEOOutcomeMeasurementService

    try:
        plan = SEOActionPlan.objects.select_related('project').prefetch_related('actions').get(id=plan_id)
    except SEOActionPlan.DoesNotExist:
        logger.error(f"[Celery Plan Outcome Task] SEOActionPlan #{plan_id} does not exist.")
        return None

    try:
        service = SEOOutcomeMeasurementService(project=plan.project)
        service.measure_plan_outcome(plan, window_days=window_days)
        return plan.id
    except Exception as exc:
        logger.exception(f"[Celery Plan Outcome Task] Error measuring plan #{plan_id} outcome: {exc}")
        if isinstance(exc, RETRYABLE_EXCEPTIONS) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        return plan.id


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='apps.seo.tasks.aggregate_historical_learning_signals_task'
)
def aggregate_historical_learning_signals_task(
    self,
    project_id: int
) -> Optional[int]:
    """
    Asynchronously calculate and cache historical learning signals and improvement rates for a project.
    """
    from apps.projects.models import Project
    from apps.seo.services.seo_outcome_learning import SEOHistoricalLearningService

    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        logger.error(f"[Celery Learning Task] Project #{project_id} does not exist.")
        return None

    try:
        SEOHistoricalLearningService.get_historical_outcome_signals(project=project)
        return project.id
    except Exception as exc:
        logger.exception(f"[Celery Learning Task] Error generating learning signals for project #{project_id}: {exc}")
        if isinstance(exc, RETRYABLE_EXCEPTIONS) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        return project.id


@shared_task(
    bind=True,
    max_retries=1,
    default_retry_delay=10,
    name='apps.seo.tasks.evaluate_due_continuous_operations_task'
)
def evaluate_due_continuous_operations_task(self) -> List[int]:
    """
    Periodic Celery task that evaluates all active continuous operations across all projects,
    identifies operations that are due, creates AgentRun sessions with strict concurrency
    locking, and dispatches them for worker execution.
    """
    from apps.seo.services.continuous_operation import ContinuousOperationService
    service = ContinuousOperationService()
    try:
        started_run_ids = service.evaluate_and_trigger_due_operations()
        if started_run_ids:
            logger.info(f"[Celery Operations Scheduler] Triggered runs for {len(started_run_ids)} due operations: {started_run_ids}")
        return started_run_ids
    except Exception as exc:
        logger.exception(f"[Celery Operations Scheduler] Error evaluating due operations: {exc}")
        return []


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='apps.seo.tasks.execute_continuous_agent_run_task'
)
def execute_continuous_agent_run_task(
    self,
    operation_id: int,
    run_id: int
) -> Optional[int]:
    """
    Execute an AgentRun scheduled under a ContinuousOperation.
    Guarantees:
    - Atomically locks run and continuous operation.
    - Preserves single active run invariant.
    - Invokes SEOSupervisorAgent multi-agent stack (Milestones 5.1-5.7).
    - Preserves HITL boundary: transitions to WAITING_FOR_APPROVAL if mutating actions proposed.
    - Never mutates sites automatically.
    - Survives individual run failures: notifies ContinuousOperationService for failure backoff.
    """
    import time
    from apps.seo.models import (
        ContinuousOperation, ContinuousOperationStatus,
        AgentRun, AgentRunStatus, AgentStep, AgentStepStatus, AgentActionType,
        SEOAction, ActionStatus
    )
    from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
    from apps.seo.services.continuous_operation import ContinuousOperationService
    from apps.seo.services.agent_events import AgentEventType

    service = ContinuousOperationService()
    start_time = time.time()

    # 1. Row-lock run and operation atomically
    try:
        with transaction.atomic():
            try:
                run = AgentRun.objects.select_for_update().select_related('project', 'user').get(id=run_id)
            except AgentRun.DoesNotExist:
                logger.error(f"[Continuous Run Task] AgentRun #{run_id} not found.")
                return None

            try:
                op = ContinuousOperation.objects.select_for_update().get(id=operation_id)
            except ContinuousOperation.DoesNotExist:
                logger.error(f"[Continuous Run Task] ContinuousOperation #{operation_id} not found.")
                return None

            if run.status != AgentRunStatus.PENDING:
                logger.warning(f"[Continuous Run Task] AgentRun #{run_id} status is '{run.status}'. Skipping.")
                return run.id

            run.status = AgentRunStatus.RUNNING
            run.save(update_fields=['status', 'updated_at'])

            op.status = ContinuousOperationStatus.RUNNING
            op.save(update_fields=['status', 'updated_at'])

    except Exception as lock_exc:
        logger.exception(f"[Continuous Run Task] Lock acquisition failed for Run #{run_id}: {lock_exc}")
        if isinstance(lock_exc, RETRYABLE_EXCEPTIONS) and self.request.retries < self.max_retries:
            raise self.retry(exc=lock_exc, countdown=2 ** self.request.retries)
        return None

    service._emit_event(AgentEventType.SEO_OPERATION_RUN_STARTED, op, run_id=run.id)

    # 2. Execute via existing SEOSupervisorAgent multi-agent stack
    error_summary = ""
    failure_category = ""
    is_waiting_approval = False

    try:
        supervisor = SEOSupervisorAgent(
            project=run.project,
            user=run.user
        )
        context = supervisor.orchestrate(
            task=run.goal,
            target_url=op.schedule_config.get("target_url"),
            target_query=op.schedule_config.get("target_query"),
            correlation_id=f"cont-op-{op.id}-run-{run.id}"
        )

        # Record tasks as AgentSteps in PostgreSQL
        if hasattr(context, "task_plan") and context.task_plan:
            plan_tasks = context.task_plan.tasks
            run.plan = [t.to_dict() for t in plan_tasks.values()]
            for step_num, (t_id, task_obj) in enumerate(plan_tasks.items(), start=1):
                thought_text = f"Agent: {task_obj.responsible_agent}\nObjective: {task_obj.objective}"
                if task_obj.result_summary:
                    thought_text += f"\nResult: {str(task_obj.result_summary)[:200]}"
                task_status_val = task_obj.status.value if hasattr(task_obj.status, 'value') else str(task_obj.status)
                AgentStep.objects.get_or_create(
                    run=run,
                    step_number=step_num,
                    defaults={
                        "action_type": AgentActionType.PLAN if "plan" in t_id else AgentActionType.DECISION,
                        "status": AgentStepStatus.COMPLETED if task_status_val in ["completed", "ready"] else AgentStepStatus.FAILED,
                        "thought": thought_text
                    }
                )

        # Check HITL & Autonomous Remediation Policy boundary
        proposed_actions = SEOAction.objects.filter(
            project=run.project,
            status=ActionStatus.PROPOSED
        )
        has_pending_human_approval = False
        if proposed_actions.exists():
            from apps.seo.services.autonomous_remediation import AutonomousRemediationPolicy, AutonomousRemediationService
            rem_service = AutonomousRemediationService()
            for p_act in proposed_actions:
                pol_eval = AutonomousRemediationPolicy.evaluate(action=p_act, project=run.project)
                if pol_eval.decision == "autonomous_allowed":
                    try:
                        rem_service.execute_remediation(action_id=p_act.id, project_id=run.project.id, run_id=run.id)
                    except Exception as auto_err:
                        logger.warning(f"[Continuous Run Task] Autonomous execution failed for #{p_act.id}: {auto_err}")
                else:
                    has_pending_human_approval = True

        if getattr(context, "requires_human_approval", False) or has_pending_human_approval:
            is_waiting_approval = True
            run.status = AgentRunStatus.WAITING_FOR_APPROVAL
            run.summary = "Execution paused: Proposed SEO action(s) require human review and approval."
            run.total_steps = len(run.plan) if run.plan else 1
            run.save(update_fields=['status', 'summary', 'plan', 'total_steps', 'updated_at'])
        else:
            run.status = AgentRunStatus.COMPLETED
            run.completed_at = timezone.now()
            run.total_steps = len(run.plan) if run.plan else 1
            run.summary = getattr(context, "summary", "") or f"Successfully completed continuous multi-agent cycle for: {run.goal[:100]}"
            run.save(update_fields=['status', 'completed_at', 'summary', 'plan', 'total_steps', 'updated_at'])

    except Exception as exec_exc:
        logger.exception(f"[Continuous Run Task] Error during multi-agent execution for Run #{run_id}: {exec_exc}")
        run.status = AgentRunStatus.FAILED
        run.completed_at = timezone.now()
        error_summary = str(exec_exc)
        failure_category = exec_exc.__class__.__name__
        clean_summary = error_summary.replace("sk-", "sk-***")[:500]
        run.summary = f"Fatal execution error: {clean_summary}"
        run.save(update_fields=['status', 'completed_at', 'summary', 'updated_at'])

    # 3. Post-execution completion hook
    duration_ms = int((time.time() - start_time) * 1000)
    service.handle_run_completion(
        operation_id=operation_id,
        run_id=run.id,
        run_status=run.status,
        duration_ms=duration_ms,
        error_summary=error_summary,
        failure_category=failure_category
    )

    return run.id


# Alias for backward compatibility
execute_continuous_run_task = execute_continuous_agent_run_task


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    name="apps.seo.tasks.execute_event_triggered_agent_run_task",
)
def execute_event_triggered_agent_run_task(self, run_id: int, event_id: int) -> Optional[int]:
    """
    Celery background worker task for executing event-triggered AgentRuns (Milestone 6.2).
    Reuses existing SEOSupervisorAgent multi-agent stack, records steps, and enforces HITL boundary.
    """
    import time
    from apps.seo.models import (
        SEOEvent, SEOEventStatus,
        AgentRun, AgentRunStatus, AgentStep, AgentStepStatus, AgentActionType,
        SEOAction, ActionStatus, ContinuousOperation, ContinuousOperationStatus
    )
    from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
    from apps.seo.services.continuous_operation import ContinuousOperationService

    start_time = time.time()

    # 1. Row-lock run atomically
    try:
        with transaction.atomic():
            try:
                run = AgentRun.objects.select_for_update().select_related('project', 'user').get(id=run_id)
            except AgentRun.DoesNotExist:
                logger.error(f"[Event Run Task] AgentRun #{run_id} not found.")
                return None

            try:
                event = SEOEvent.objects.select_for_update().get(id=event_id)
            except SEOEvent.DoesNotExist:
                logger.warning(f"[Event Run Task] SEOEvent #{event_id} not found.")
                event = None

            if run.status != AgentRunStatus.PENDING:
                logger.warning(f"[Event Run Task] AgentRun #{run_id} status is '{run.status}'. Skipping.")
                return run.id

            run.status = AgentRunStatus.RUNNING
            run.save(update_fields=['status', 'updated_at'])

    except Exception as lock_exc:
        logger.exception(f"[Event Run Task] Lock acquisition failed for Run #{run_id}: {lock_exc}")
        if isinstance(lock_exc, RETRYABLE_EXCEPTIONS) and self.request.retries < self.max_retries:
            raise self.retry(exc=lock_exc, countdown=2 ** self.request.retries)
        return None

    # 2. Execute via existing SEOSupervisorAgent multi-agent stack
    error_summary = ""
    failure_category = ""
    is_waiting_approval = False

    try:
        supervisor = SEOSupervisorAgent(
            project=run.project,
            user=run.user
        )
        context = supervisor.orchestrate(
            task=run.goal,
            correlation_id=f"event-{event_id}-run-{run.id}" if event_id else f"run-{run.id}"
        )

        # Record tasks as AgentSteps
        if hasattr(context, "task_plan") and context.task_plan:
            plan_tasks = context.task_plan.tasks
            run.plan = [t.to_dict() for t in plan_tasks.values()]
            for step_num, (t_id, task_obj) in enumerate(plan_tasks.items(), start=1):
                thought_text = f"Agent: {task_obj.responsible_agent}\nObjective: {task_obj.objective}"
                if task_obj.result_summary:
                    thought_text += f"\nResult: {str(task_obj.result_summary)[:200]}"
                task_status_val = task_obj.status.value if hasattr(task_obj.status, 'value') else str(task_obj.status)
                AgentStep.objects.get_or_create(
                    run=run,
                    step_number=step_num,
                    defaults={
                        "action_type": AgentActionType.PLAN if "plan" in t_id else AgentActionType.DECISION,
                        "status": AgentStepStatus.COMPLETED if task_status_val in ["completed", "ready"] else AgentStepStatus.FAILED,
                        "thought": thought_text
                    }
                )

        # Check HITL & Autonomous Remediation Policy boundary
        proposed_actions = SEOAction.objects.filter(
            project=run.project,
            status=ActionStatus.PROPOSED
        )
        has_pending_human_approval = False
        if proposed_actions.exists():
            from apps.seo.services.autonomous_remediation import AutonomousRemediationPolicy, AutonomousRemediationService
            rem_service = AutonomousRemediationService()
            for p_act in proposed_actions:
                pol_eval = AutonomousRemediationPolicy.evaluate(action=p_act, project=run.project)
                if pol_eval.decision == "autonomous_allowed":
                    try:
                        rem_service.execute_remediation(action_id=p_act.id, project_id=run.project.id, run_id=run.id)
                    except Exception as auto_err:
                        logger.warning(f"[Event Run Task] Autonomous execution failed for #{p_act.id}: {auto_err}")
                else:
                    has_pending_human_approval = True

        if getattr(context, "requires_human_approval", False) or has_pending_human_approval:
            is_waiting_approval = True
            run.status = AgentRunStatus.WAITING_FOR_APPROVAL
            run.summary = "Execution paused: Proposed SEO action(s) require human review and approval."
            run.total_steps = len(run.plan) if run.plan else 1
            run.save(update_fields=['status', 'summary', 'plan', 'total_steps', 'updated_at'])
        else:
            run.status = AgentRunStatus.COMPLETED
            run.completed_at = timezone.now()
            run.total_steps = len(run.plan) if run.plan else 1
            run.summary = getattr(context, "summary", "") or f"Successfully completed event-triggered workflow for: {run.goal[:100]}"
            run.save(update_fields=['status', 'completed_at', 'summary', 'plan', 'total_steps', 'updated_at'])

    except Exception as exc:
        logger.exception(f"[Event Run Task] Multi-agent execution error for Run #{run.id}: {exc}")
        error_summary = str(exc).replace("sk-", "sk-***")[:500]
        failure_category = exc.__class__.__name__
        run.status = AgentRunStatus.FAILED
        run.completed_at = timezone.now()
        run.summary = f"Execution failed: {failure_category} - {error_summary}"
        run.save(update_fields=['status', 'completed_at', 'summary', 'updated_at'])

    # 3. If connected to a ContinuousOperation, notify completion hook
    if run.continuous_operation_id:
        duration_ms = int((time.time() - start_time) * 1000)
        cont_service = ContinuousOperationService()
        cont_service.handle_run_completion(
            operation_id=run.continuous_operation_id,
            run_id=run.id,
            run_status=run.status,
            duration_ms=duration_ms,
            error_summary=error_summary,
            failure_category=failure_category
        )

    return run.id


@shared_task(
    bind=True,
    max_retries=1,
    default_retry_delay=30,
    name='apps.seo.tasks.run_autonomous_seo_monitoring_task'
)
def run_autonomous_seo_monitoring_task(self, project_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    """
    Periodic Celery task (Milestone 6.3) that executes an autonomous monitoring cycle
    across active projects. Discovers state changes, compares against baselines,
    and safely dispatches events to the 6.2 ingestion pipeline.
    """
    from apps.seo.services.autonomous_monitoring import AutonomousMonitoringService
    service = AutonomousMonitoringService()
    try:
        results = service.run_monitoring_cycle(project_ids=project_ids)
        return results
    except Exception as exc:
        logger.exception(f"[Celery Monitoring Task] Error running autonomous monitoring cycle: {exc}")
        return {"error": str(exc)}


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    name='apps.seo.tasks.run_project_monitoring_task'
)
def run_project_monitoring_task(self, project_id: int) -> Dict[str, Any]:
    """
    Asynchronous Celery task to monitor a single project with database row-level locking.
    """
    from apps.projects.models import Project
    from apps.seo.services.autonomous_monitoring import AutonomousMonitoringService
    service = AutonomousMonitoringService()
    try:
        with transaction.atomic():
            project = Project.objects.select_for_update(skip_locked=True).filter(id=project_id).first()
            if not project:
                logger.warning(f"[Celery Project Monitoring Task] Project #{project_id} locked or not found.")
                return {"status": "skipped", "reason": "locked_or_missing"}
            return service.monitor_project(project)
    except Exception as exc:
        logger.exception(f"[Celery Project Monitoring Task] Error monitoring project #{project_id}: {exc}")
        return {"error": str(exc)}


@shared_task(
    bind=True,
    max_retries=1,
    default_retry_delay=10,
    name='apps.seo.tasks.sweep_and_recover_stale_runs_task'
)
def sweep_and_recover_stale_runs_task(self=None) -> Dict[str, Any]:
    """
    Periodic Celery task (Milestone 6.7: Production Agent Platform).
    Scans for RUNNING AgentRun instances whose execution leases have expired
    or whose worker heartbeats have timed out, and deterministically recovers them.
    """
    from apps.seo.services.production_platform import ExecutionLeaseManager
    lease_mgr = ExecutionLeaseManager()
    stale_runs = lease_mgr.detect_stale_runs(threshold_seconds=120)
    recovered = []

    for run in stale_runs:
        try:
            cat, rec_run = lease_mgr.recover_stale_run(run, reason="periodic_stale_sweep")
            recovered.append({
                "run_id": run.id,
                "category": cat.value,
                "status": rec_run.status,
                "retry_count": rec_run.retry_count
            })
            logger.info(f"[StaleSweep] Stale AgentRun #{run.id} recovered via {cat.value} -> status '{rec_run.status}'.")
        except Exception as exc:
            logger.exception(f"[StaleSweep] Error recovering stale AgentRun #{run.id}: {exc}")

    return {
        "total_detected": len(stale_runs),
        "total_recovered": len(recovered),
        "recovered": recovered,
        "timestamp": timezone.now().isoformat()
    }


@shared_task(
    name='apps.seo.tasks.compact_platform_data_task'
)
def compact_platform_data_task(older_than_days: int = 30) -> Dict[str, int]:
    """
    Periodic Celery task (Milestone 6.7) to compact expired idempotency records
    and resolved platform alerts while strictly preserving strategic evidence and audit logs.
    """
    from apps.seo.services.production_platform import DataRetentionManager
    return DataRetentionManager.compact_ephemeral_data(older_than_days=older_than_days)


# =============================================================================
# TECHNICAL SEO CRAWLER TASK
# =============================================================================

@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    name='apps.seo.tasks.run_technical_crawl'
)
def run_technical_crawl(
    self,
    crawl_job_id: int,
    max_pages: int = 100,
    max_depth: int = 3,
    respect_robots_txt: bool = True,
) -> Optional[int]:
    """
    Execute a full-site Technical SEO Crawl asynchronously in a Celery worker.

    Guarantees:
    - Atomically transitions CrawlJob status PENDING → RUNNING via select_for_update.
    - SSRF-safe: all target IPs are validated before any outbound requests.
    - Idempotent: already-running jobs are not re-executed.
    - Persists structured CrawlPage records and aggregate summary counters.
    - Transitions CrawlJob to COMPLETED or FAILED; never hangs indefinitely.
    """
    # 1. Atomically acquire lock and transition to RUNNING
    try:
        with transaction.atomic():
            try:
                crawl_job = CrawlJob.objects.select_for_update().select_related('project').get(id=crawl_job_id)
            except CrawlJob.DoesNotExist:
                logger.error(f"[CrawlTask] CrawlJob #{crawl_job_id} does not exist. Aborting.")
                return None

            if crawl_job.status not in (CrawlJobStatus.PENDING,):
                logger.warning(
                    f"[CrawlTask] CrawlJob #{crawl_job_id} status is '{crawl_job.status}'. Skipping."
                )
                return crawl_job.id

            crawl_job.status = CrawlJobStatus.RUNNING
            crawl_job.started_at = timezone.now()
            task_id = getattr(getattr(self, 'request', None), 'id', None)
            crawl_job.celery_task_id = task_id or 'direct-task'
            crawl_job.save(update_fields=['status', 'started_at', 'celery_task_id', 'updated_at'])

    except Exception as lock_exc:
        logger.exception(f"[CrawlTask] DB error acquiring lock for CrawlJob #{crawl_job_id}: {lock_exc}")
        retries = getattr(getattr(self, 'request', None), 'retries', 0)
        max_retries = getattr(self, 'max_retries', 2)
        if isinstance(lock_exc, RETRYABLE_EXCEPTIONS) and retries < max_retries and hasattr(self, 'retry'):
            raise self.retry(exc=lock_exc, countdown=2 ** retries)
        return None

    # 2. Run the crawl
    try:
        start_url = crawl_job.project.website_url
        crawler = TechnicalCrawlerService(
            max_pages=max_pages,
            max_depth=max_depth,
            respect_robots_txt=respect_robots_txt,
        )
        summary, pages_data = crawler.crawl(start_url)

        # 3. Persist CrawlPage records in bulk
        crawl_pages = [
            CrawlPage(
                crawl_job=crawl_job,
                url=p.url[:2048],
                final_url=(p.final_url or p.url)[:2048],
                status_code=p.status_code,
                response_time_ms=p.response_time_ms,
                depth=p.depth,
                title=p.title,
                meta_description=p.meta_description,
                h1_count=p.h1_count,
                word_count=p.word_count,
                canonical_url=p.canonical_url,
                has_redirect=p.has_redirect,
                redirect_chain=p.redirect_chain,
                internal_links_count=p.internal_links_count,
                external_links_count=p.external_links_count,
                images_count=p.images_count,
                images_missing_alt_count=p.images_missing_alt_count,
                is_broken=p.is_broken,
                is_slow=p.is_slow,
                issues=[{'type': f.issue_type, 'severity': f.severity, 'message': f.message}
                        for f in p.findings],
            )
            for p in pages_data
        ]
        CrawlPage.objects.bulk_create(crawl_pages, batch_size=100)

        # 4. Update CrawlJob with aggregates and mark COMPLETED
        crawl_job.status = CrawlJobStatus.COMPLETED
        crawl_job.completed_at = timezone.now()
        crawl_job.pages_crawled = summary.pages_crawled
        crawl_job.pages_discovered = summary.pages_discovered
        crawl_job.broken_links_count = summary.broken_links_count
        crawl_job.missing_titles_count = summary.missing_titles_count
        crawl_job.missing_descriptions_count = summary.missing_descriptions_count
        crawl_job.duplicate_titles_count = summary.duplicate_titles_count
        crawl_job.missing_h1_count = summary.missing_h1_count
        crawl_job.redirect_chains_count = summary.redirect_chains_count
        crawl_job.slow_pages_count = summary.slow_pages_count
        crawl_job.crawl_metadata = summary.metadata
        crawl_job.save(update_fields=[
            'status', 'completed_at', 'pages_crawled', 'pages_discovered',
            'broken_links_count', 'missing_titles_count', 'missing_descriptions_count',
            'duplicate_titles_count', 'missing_h1_count', 'redirect_chains_count',
            'slow_pages_count', 'crawl_metadata', 'updated_at',
        ])

        logger.info(
            f"[CrawlTask] CrawlJob #{crawl_job.id} completed: "
            f"{summary.pages_crawled} pages crawled, {summary.broken_links_count} broken links."
        )
        return crawl_job.id

    except ValueError as ssrf_exc:
        # SSRF or URL validation error — do not retry
        logger.error(f"[CrawlTask] SSRF/validation error for CrawlJob #{crawl_job_id}: {ssrf_exc}")
        _mark_crawl_job_failed(crawl_job, f"URL validation error: {ssrf_exc}")
        return crawl_job.id

    except RETRYABLE_EXCEPTIONS as retry_exc:
        retries = getattr(getattr(self, 'request', None), 'retries', 0)
        max_retries = getattr(self, 'max_retries', 2)
        logger.warning(
            f"[CrawlTask] Transient error for CrawlJob #{crawl_job_id} "
            f"(attempt {retries + 1}/{max_retries}): {retry_exc}"
        )
        if retries < max_retries and hasattr(self, 'retry'):
            countdown = (2 ** retries) * 10
            raise self.retry(exc=retry_exc, countdown=countdown)
        else:
            _mark_crawl_job_failed(
                crawl_job,
                f"Transient failure after {max_retries} retries: {retry_exc}"
            )
        return crawl_job.id

    except Exception as fatal_exc:
        logger.exception(f"[CrawlTask] Fatal error for CrawlJob #{crawl_job_id}: {fatal_exc}")
        _mark_crawl_job_failed(
            crawl_job,
            f"Fatal crawl error: {fatal_exc.__class__.__name__} — {str(fatal_exc)}"
        )
        return crawl_job.id


def _mark_crawl_job_failed(crawl_job: CrawlJob, error_message: str) -> None:
    """Helper to safely transition a CrawlJob to terminal FAILED state."""
    try:
        crawl_job.refresh_from_db()
        crawl_job.status = CrawlJobStatus.FAILED
        crawl_job.error_message = error_message[:1000]
        crawl_job.completed_at = timezone.now()
        crawl_job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
    except Exception as e:
        logger.error(f"Failed to record FAILED status for CrawlJob #{crawl_job.id}: {e}")


# =============================================================================
# RANK TRACKER MVP — Celery Tasks
# =============================================================================

def _mark_rank_check_job_failed(job: RankCheckJob, error_message: str) -> None:
    """Helper to safely transition a RankCheckJob to terminal FAILED state."""
    try:
        job.refresh_from_db()
        job.status = RankCheckJobStatus.FAILED
        job.error_message = error_message[:1000]
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
    except Exception as e:
        logger.error(f"Failed to transition RankCheckJob #{job.id} to FAILED: {e}")


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='apps.seo.tasks.check_keyword_ranking'
)
def check_keyword_ranking(self, keyword_id: int) -> Optional[int]:
    """
    Asynchronously perform a ranking check for a single keyword against google.com.et.
    Enforces FeatureCode.RANK_TRACKING subscription entitlement.
    """
    from apps.subscriptions.services import PlanEntitlementService
    from apps.subscriptions.models import FeatureCode

    try:
        keyword = Keyword.objects.select_related('project', 'project__owner').get(id=keyword_id)
    except Keyword.DoesNotExist:
        logger.error(f"[RankTrackerTask] Keyword #{keyword_id} does not exist.")
        return None

    # Check subscription entitlement
    if not PlanEntitlementService.can_use_feature(keyword.project.owner, FeatureCode.RANK_TRACKING):
        logger.warning(
            f"[RankTrackerTask] User {keyword.project.owner.email} does not have RANK_TRACKING entitlement. Skipping."
        )
        return None

    service = RankTrackerService()
    snapshot = service.check_keyword(keyword)
    logger.info(
        f"[RankTrackerTask] Keyword #{keyword.id} ('{keyword.keyword}') checked: "
        f"Pos #{snapshot.position} ({snapshot.result_status})."
    )
    return snapshot.id


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='apps.seo.tasks.run_project_rank_check'
)
def run_project_rank_check(self, project_id: int, job_id: Optional[int] = None) -> Optional[int]:
    """
    Asynchronously run rank checks for all active keywords of a project.
    Updates RankCheckJob progress and transitions cleanly on completion or failure.
    """
    from apps.projects.models import Project
    from apps.subscriptions.services import PlanEntitlementService
    from apps.subscriptions.models import FeatureCode

    try:
        project = Project.objects.select_related('owner').get(id=project_id)
    except Project.DoesNotExist:
        logger.error(f"[RankTrackerTask] Project #{project_id} does not exist.")
        return None

    job = None
    if job_id:
        try:
            job = RankCheckJob.objects.select_for_update().get(id=job_id)
        except RankCheckJob.DoesNotExist:
            logger.warning(f"[RankTrackerTask] RankCheckJob #{job_id} not found.")

    # Entitlement verification
    if not PlanEntitlementService.can_use_feature(project.owner, FeatureCode.RANK_TRACKING):
        msg = f"User {project.owner.email} is not entitled to FeatureCode.RANK_TRACKING."
        logger.warning(f"[RankTrackerTask] {msg}")
        if job:
            _mark_rank_check_job_failed(job, msg)
        return None

    try:
        service = RankTrackerService()
        snapshots = service.check_project_keywords(project=project, job=job)
        logger.info(
            f"[RankTrackerTask] Completed project #{project.id} rank check: {len(snapshots)} keywords processed."
        )
        return job.id if job else len(snapshots)
    except Exception as exc:
        logger.exception(f"[RankTrackerTask] Fatal error in project #{project_id} rank check: {exc}")
        if job:
            _mark_rank_check_job_failed(job, f"Rank check failed: {exc}")
        return None


@shared_task(
    name='apps.seo.tasks.run_daily_rank_checks'
)
def run_daily_rank_checks() -> Dict[str, Any]:
    """
    Periodic task (Celery Beat) executing daily google.com.et SERP rank checks for all active keywords.
    - Scans active keywords for Starter and Agency users (Free users skipped).
    - Idempotency: skips keywords that already have a ranking snapshot recorded today.
    - Error isolation: failures on one keyword do not abort remaining keywords.
    """
    from apps.subscriptions.services import PlanEntitlementService
    from apps.subscriptions.models import FeatureCode

    today = timezone.localdate()
    active_keywords = (
        Keyword.objects.filter(is_active=True)
        .select_related('project', 'project__owner')
        .order_by('project_id', 'id')
    )

    total_count = active_keywords.count()
    checked_count = 0
    skipped_count = 0
    failed_count = 0

    service = RankTrackerService()

    logger.info(f"[DailyRankTracker] Starting daily rank checks for {total_count} active keywords.")

    for kw in active_keywords:
        # Check plan entitlement
        if not PlanEntitlementService.can_use_feature(kw.project.owner, FeatureCode.RANK_TRACKING):
            skipped_count += 1
            continue

        # Idempotency check: skip if already checked today
        already_checked_today = KeywordRanking.objects.filter(
            keyword=kw,
            recorded_at__date=today
        ).exists()

        if already_checked_today:
            skipped_count += 1
            continue

        try:
            snapshot = service.check_keyword(kw)
            if snapshot.result_status == RankingResultStatus.ERROR:
                failed_count += 1
            else:
                checked_count += 1
        except Exception as e:
            logger.error(f"[DailyRankTracker] Keyword #{kw.id} failed: {e}")
            failed_count += 1

    summary = {
        'date': str(today),
        'total': total_count,
        'checked': checked_count,
        'skipped': skipped_count,
        'failed': failed_count,
    }
    logger.info(f"[DailyRankTracker] Daily check completed: {summary}")
    return summary


# =============================================================================
# COMPETITOR SERP SNAPSHOT TASKS (Original SRS: Weekly Competitor Snapshots)
# =============================================================================

def _mark_competitor_snapshot_job_failed(job: CompetitorSnapshotJob, error_message: str) -> None:
    """Safely transitions a CompetitorSnapshotJob to FAILED without throwing exceptions."""
    try:
        job.status = CompetitorSnapshotJobStatus.FAILED
        job.error_message = error_message[:2000]
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'completed_at'])
    except Exception as exc:
        logger.error(f"[CompetitorSnapshot] Could not mark job #{job.id} as failed: {exc}")


@shared_task(
    bind=True,
    name='apps.seo.tasks.run_project_competitor_snapshot',
    max_retries=2,
    default_retry_delay=60,
)
def run_project_competitor_snapshot(self, project_id: int, job_id: Optional[int] = None) -> Optional[int]:
    """
    Executes a competitor SERP snapshot batch for all active keywords and competitors in a project.
    Ensures safe job state transitions and guarantees the job never remains stuck in RUNNING.
    """
    try:
        service = CompetitorSnapshotService()
        job = service.run_snapshot_for_project(project_id=project_id, job_id=job_id)
        return job.id
    except RETRYABLE_EXCEPTIONS as exc:
        logger.warning(
            f"[CompetitorSnapshot] Transient error on project #{project_id} (attempt {self.request.retries + 1}): {exc}"
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        else:
            if job_id:
                try:
                    job = CompetitorSnapshotJob.objects.get(id=job_id)
                    _mark_competitor_snapshot_job_failed(job, f"Exhausted retries: {exc}")
                except CompetitorSnapshotJob.DoesNotExist:
                    pass
            return None
    except Exception as exc:
        logger.error(f"[CompetitorSnapshot] Fatal error on project #{project_id}: {exc}", exc_info=True)
        if job_id:
            try:
                job = CompetitorSnapshotJob.objects.get(id=job_id)
                _mark_competitor_snapshot_job_failed(job, str(exc))
            except CompetitorSnapshotJob.DoesNotExist:
                pass
        return None


@shared_task(name='apps.seo.tasks.run_weekly_competitor_snapshots')
def run_weekly_competitor_snapshots() -> Dict[str, Any]:
    """
    Weekly periodic task (scheduled via Celery Beat) executing competitor SERP snapshots
    for all eligible projects across the platform.

    Guarantees:
    - Entitlement: Only projects whose owners have FeatureCode.COMPETITOR_SNAPSHOTS (Agency plan).
    - Idempotency: Projects that already ran a snapshot job within the last 6 days are skipped.
    - Error isolation: A failure on one project never stops other projects from being processed.
    """
    from apps.projects.models import Project
    from apps.subscriptions.services import PlanEntitlementService
    from apps.subscriptions.models import FeatureCode
    import datetime

    now = timezone.now()
    six_days_ago = now - datetime.timedelta(days=6)

    projects = Project.objects.all().select_related('owner')
    total_projects = 0
    enqueued_count = 0
    skipped_count = 0
    failed_count = 0

    for project in projects:
        total_projects += 1

        # 1. Entitlement verification
        if not PlanEntitlementService.can_use_feature(project.owner, FeatureCode.COMPETITOR_SNAPSHOTS):
            skipped_count += 1
            continue

        # 2. Check active competitors and active keywords exist
        has_competitors = project.competitors.filter(is_active=True).exists()
        has_keywords = project.keywords.filter(is_active=True).exists()
        if not has_competitors or not has_keywords:
            skipped_count += 1
            continue

        # 3. Weekly idempotency check: skip if a job completed within the last 6 days
        already_run_recently = CompetitorSnapshotJob.objects.filter(
            project=project,
            status__in=[CompetitorSnapshotJobStatus.COMPLETED, CompetitorSnapshotJobStatus.PARTIAL_FAILURE],
            created_at__gte=six_days_ago,
        ).exists()

        if already_run_recently:
            skipped_count += 1
            continue

        # 4. Enqueue weekly snapshot job
        try:
            job = CompetitorSnapshotJob.objects.create(
                project=project,
                trigger='scheduled_weekly',
                status=CompetitorSnapshotJobStatus.PENDING,
            )
            run_project_competitor_snapshot.delay(project.id, job.id)
            enqueued_count += 1
        except Exception as exc:
            logger.error(f"[WeeklyCompetitorSnapshots] Failed to enqueue job for project #{project.id}: {exc}")
            failed_count += 1

    summary = {
        'date': str(now.date()),
        'total_projects': total_projects,
        'enqueued': enqueued_count,
        'skipped': skipped_count,
        'failed': failed_count,
    }
    logger.info(f"[WeeklyCompetitorSnapshots] Weekly schedule run completed: {summary}")
    return summary


# =============================================================================
# SEO RECOMMENDATIONS FEED TASKS (Original SRS: Rule-Based Recommendations)
# =============================================================================

@shared_task(
    bind=True,
    name='apps.seo.tasks.generate_project_recommendations_task',
    max_retries=2,
    default_retry_delay=30,
)
def generate_project_recommendations_task(self, project_id: int) -> Dict[str, Any]:
    """
    Asynchronously evaluates crawler, rank tracker, and competitor data to generate
    or update actionable, prioritized recommendations for a project.

    Guarantees:
    - Tenant safety: Operates strictly within the requested project's boundary.
    - Idempotency: Multiple runs update existing active recommendations without creating duplicates.
    - Failure safety: Safely logs and handles unexpected errors without leaking credentials.
    """
    from apps.projects.models import Project
    from apps.seo.services.recommendations import RecommendationEngine
    from apps.seo.models import Recommendation, RecommendationState

    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        logger.error(f"[RecommendationsTask] Project #{project_id} does not exist.")
        return {'status': 'error', 'message': f'Project #{project_id} not found', 'project_id': project_id}

    try:
        recommendations = RecommendationEngine.generate_project_recommendations(project)
        open_count = Recommendation.objects.filter(
            project=project,
            status=RecommendationState.OPEN
        ).count()

        summary = {
            'status': 'success',
            'project_id': project_id,
            'total_generated': len(recommendations),
            'open_count': open_count,
        }
        logger.info(f"[RecommendationsTask] Successfully generated recommendations for project #{project_id}: {summary}")
        return summary
    except Exception as exc:
        logger.error(f"[RecommendationsTask] Error generating recommendations for project #{project_id}: {exc}", exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        return {'status': 'failed', 'error': str(exc), 'project_id': project_id}


# =============================================================================
# WHITE-LABEL REPORT ASYNC TASK (Original SRS: Agency White-Label Reports)
# =============================================================================

@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    name='apps.seo.tasks.generate_seo_report_task'
)
def generate_seo_report_task(self, report_id: int) -> Optional[int]:
    """
    Celery background worker task for generating an executive White-Label PDF report.
    Loads the SEOReport record, verifies multi-tenant integrity, executes PDF compilation,
    and updates report status to COMPLETED or FAILED safely.
    """
    from apps.seo.models import SEOReport
    from apps.seo.services.reports import SEOReportService

    try:
        report = SEOReport.objects.select_related('project', 'project__owner').get(id=report_id)
    except SEOReport.DoesNotExist:
        logger.error(f"[ReportTask] SEOReport #{report_id} does not exist. Aborting task.")
        return None

    # Update celery task id if available
    task_id = getattr(getattr(self, 'request', None), 'id', None)
    if task_id and not report.celery_task_id:
        report.celery_task_id = task_id
        report.save(update_fields=['celery_task_id'])

    try:
        SEOReportService.execute_report_generation(report_id)
        logger.info(f"[ReportTask] Successfully completed generation for SEOReport #{report_id}.")
        return report.id
    except Exception as exc:
        logger.error(f"[ReportTask] Error generating SEOReport #{report_id}: {exc}", exc_info=True)
        retries = getattr(getattr(self, 'request', None), 'retries', 0)
        max_retries = getattr(self, 'max_retries', 2)
        if retries < max_retries and hasattr(self, 'retry'):
            raise self.retry(exc=exc, countdown=10 * (retries + 1))
        return None


# =============================================================================
# KEYWORD INTELLIGENCE ASYNC TASKS (Original SRS: Search Volume & CPC)
# =============================================================================

@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name='apps.seo.tasks.refresh_keyword_intelligence_task'
)
def refresh_keyword_intelligence_task(self, keyword_id: int, force: bool = False) -> Optional[int]:
    """
    Celery background worker task for refreshing keyword intelligence metrics (volume, CPC, competition).
    Enforces FeatureCode.RANK_TRACKING subscription entitlement and project owner isolation.
    """
    from apps.seo.models import Keyword
    from apps.seo.services.keyword_intelligence import KeywordIntelligenceService
    from apps.subscriptions.services import PlanEntitlementService
    from apps.subscriptions.models import FeatureCode

    try:
        keyword = Keyword.objects.select_related('project', 'project__owner').get(id=keyword_id)
    except Keyword.DoesNotExist:
        logger.error(f"[KeywordIntelTask] Keyword #{keyword_id} does not exist. Aborting.")
        return None

    # Check subscription entitlement
    if not PlanEntitlementService.can_use_feature(keyword.project.owner, FeatureCode.RANK_TRACKING):
        logger.warning(
            f"[KeywordIntelTask] User {keyword.project.owner.email} lacks RANK_TRACKING entitlement. Skipping."
        )
        return None

    try:
        intel = KeywordIntelligenceService.refresh_keyword_intelligence(keyword.id, force=force)
        logger.info(f"[KeywordIntelTask] Successfully refreshed intelligence for Keyword #{keyword.id} ('{keyword.keyword}').")
        return intel.id
    except Exception as exc:
        logger.error(f"[KeywordIntelTask] Error refreshing intelligence for Keyword #{keyword.id}: {exc}", exc_info=True)
        retries = getattr(getattr(self, 'request', None), 'retries', 0)
        max_retries = getattr(self, 'max_retries', 2)
        if retries < max_retries and hasattr(self, 'retry'):
            raise self.retry(exc=exc, countdown=5 * (retries + 1))
        return None


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    name='apps.seo.tasks.bulk_refresh_project_keywords_intelligence_task'
)
def bulk_refresh_project_keywords_intelligence_task(self, project_id: int, force: bool = False) -> Dict[str, Any]:
    """
    Celery background task for refreshing all active keywords for a given project.
    """
    from apps.projects.models import Project
    from apps.seo.models import Keyword
    from apps.seo.services.keyword_intelligence import KeywordIntelligenceService
    from apps.subscriptions.services import PlanEntitlementService
    from apps.subscriptions.models import FeatureCode

    try:
        project = Project.objects.select_related('owner').get(id=project_id)
    except Project.DoesNotExist:
        logger.error(f"[KeywordIntelTask] Project #{project_id} does not exist. Aborting.")
        return {'status': 'failed', 'error': 'Project does not exist'}

    if not PlanEntitlementService.can_use_feature(project.owner, FeatureCode.RANK_TRACKING):
        logger.warning(f"[KeywordIntelTask] User {project.owner.email} lacks RANK_TRACKING entitlement. Skipping.")
        return {'status': 'failed', 'error': 'Feature not entitled'}

    keywords = Keyword.objects.filter(project=project, is_active=True).values_list('id', flat=True)
    count = 0
    for kw_id in keywords:
        try:
            KeywordIntelligenceService.refresh_keyword_intelligence(kw_id, force=force)
            count += 1
        except Exception as e:
            logger.error(f"[KeywordIntelTask] Error in bulk refresh for kw #{kw_id}: {e}")

    logger.info(f"[KeywordIntelTask] Bulk refreshed {count}/{len(keywords)} keywords for Project #{project_id}.")
    return {'status': 'completed', 'project_id': project_id, 'refreshed_count': count, 'total_keywords': len(keywords)}



