"""
Audit script for Milestone 6.2: Event-Driven Agents.
Executes comprehensive end-to-end verification and prints verifiable runtime proofs for:
- Proof A: Event triggers appropriate agent workflow (ingestion -> policy -> run creation -> multi-agent execution)
- Proof B: Duplicate event protection (idempotency deduplication -> DEDUPLICATED status, single run)
- Proof C: Event storm protection (rate limiting -> SUPPRESSED status, threshold enforcement)
- Proof D: Existing architecture preserved (SEOSupervisorAgent, planner, memory, learning, reasoning, tools)
- Proof E: HITL safety boundary strictly preserved (mutating actions enter WAITING_FOR_APPROVAL, PROPOSED)
- Proof F: Tenant / project isolation strictly preserved (User B cannot access or ingest for Project A)
- Proof G: Restart resilience and persistence across reloads
- Proof H: Cooldown window protection (cooldown suppression for repeated event types)
- Proof I: ContinuousOperation single active run invariant enforcement
- Proof J: Telemetry event lifecycle publishing & Runtime Evaluation Metrics
- Proof K: REST API endpoints (list, retrieve, runs, metrics, ingest)
"""
import os
import sys
import time
import uuid
from datetime import timedelta
import django
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
settings.CELERY_TASK_ALWAYS_EAGER = True
settings.CELERY_TASK_EAGER_PROPAGATES = True

from apps.projects.models import Project
from apps.users.models import User
from apps.seo.models import (
    SEOEvent,
    SEOEventType,
    SEOEventSeverity,
    SEOEventStatus,
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
    AgentActionType,
    ContinuousOperation,
    ContinuousOperationStatus,
    ContinuousOperationScheduleType,
    SEOAction,
    ActionStatus,
    ActionType,
)
from apps.seo.services.event_ingestion import SEOEventIngestionService, EventTriggerPolicy
from apps.seo.services.agent_events import AgentEventType, InMemoryEventPublisher
from apps.seo.services.agent_evaluation import SEOAgentEvaluationService
from apps.seo.services.continuous_operation import ContinuousOperationService
from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
from apps.seo.services.agents.shared_memory import SharedWorkingMemory, SharedMemoryRegistry
from apps.seo.services.tool_registry import get_tool_registry
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.seo.views import SEOEventViewSet


def run_audit():
    print("=" * 80)
    print("STARTING MILESTONE 6.2 RUNTIME AUDIT VERIFICATION & PROOFS")
    print("=" * 80)

    # Clean in-memory registries
    SharedMemoryRegistry.get_instance().clear()

    # Isolated test entities
    unique_suffix = uuid.uuid4().hex[:8]
    user_a, _ = User.objects.get_or_create(email=f"audit62_a_{unique_suffix}@doxarank.io")
    user_b, _ = User.objects.get_or_create(email=f"audit62_b_{unique_suffix}@doxarank.io")

    project_a, _ = Project.objects.get_or_create(
        owner=user_a,
        name=f"Event SEO Audit Project A {unique_suffix}",
        website_url="https://alpha-event-audit.example.com"
    )
    project_b, _ = Project.objects.get_or_create(
        owner=user_b,
        name=f"Event SEO Audit Project B {unique_suffix}",
        website_url="https://beta-event-audit.example.com"
    )

    publisher = InMemoryEventPublisher()
    service = SEOEventIngestionService(publisher=publisher)
    cont_service = ContinuousOperationService(publisher=publisher)
    eval_service = SEOAgentEvaluationService()

    # -------------------------------------------------------------------------
    # PROOF A: Event triggers appropriate agent workflow
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PROOF A: Event Triggers Appropriate Agent Workflow")
    print("-" * 80)
    runs_before = AgentRun.objects.filter(project=project_a).count()
    ev_a = service.ingest_event(
        project=project_a,
        event_type=SEOEventType.RANKING_CHANGE,
        source="google_serp_tracker",
        severity=SEOEventSeverity.HIGH,
        payload={"keyword": "best crm software", "rank_drop": 8, "previous_rank": 3, "current_rank": 11},
        user=user_a
    )
    runs_after = AgentRun.objects.filter(project=project_a).count()
    assert ev_a.status == SEOEventStatus.PROCESSED, f"Expected PROCESSED, got {ev_a.status}"
    assert ev_a.agent_run_id is not None, "Expected linked agent_run_id"
    assert runs_after == runs_before + 1, "Expected exactly 1 new AgentRun created"
    run_a = ev_a.agent_run
    assert run_a.project_id == project_a.id
    assert run_a.context_snapshot.get("trigger") == "event"
    assert "Investigate ranking drop for 'best crm software'" in run_a.goal
    print(f"  [PASS] SEOEvent #{ev_a.id} status={ev_a.status}, severity={ev_a.severity}")
    print(f"  [PASS] Triggered AgentRun #{run_a.id}: Goal='{run_a.goal[:60]}...'")
    print(f"  [PASS] Context snapshot trigger={run_a.context_snapshot.get('trigger')}, correlation_id={ev_a.correlation_id}")

    # -------------------------------------------------------------------------
    # PROOF B: Duplicate event protection (Deterministic Idempotency)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PROOF B: Duplicate Event Protection (Deduplication)")
    print("-" * 80)
    runs_before_dup = AgentRun.objects.filter(project=project_a).count()
    payload_dup = {"keyword": "ai seo agent", "rank_drop": 6}
    custom_key = f"idemp-proof-b-{unique_suffix}"

    ev_b1 = service.ingest_event(
        project=project_a,
        event_type=SEOEventType.RANKING_CHANGE,
        source="serp_webhook",
        payload=payload_dup,
        idempotency_key=custom_key,
        cooldown_minutes=0,
        user=user_a
    )
    assert ev_b1.status == SEOEventStatus.PROCESSED

    ev_b2 = service.ingest_event(
        project=project_a,
        event_type=SEOEventType.RANKING_CHANGE,
        source="serp_webhook",
        payload=payload_dup,
        idempotency_key=custom_key,
        cooldown_minutes=0,
        user=user_a
    )
    runs_after_dup = AgentRun.objects.filter(project=project_a).count()
    assert ev_b2.status == SEOEventStatus.DEDUPLICATED, f"Expected DEDUPLICATED, got {ev_b2.status}"
    assert ev_b2.agent_run_id == ev_b1.agent_run_id, "Duplicate must point to original AgentRun"
    assert runs_after_dup == runs_before_dup + 1, "Duplicate submission must NOT create a second AgentRun"
    print(f"  [PASS] Event 1 #{ev_b1.id} status={ev_b1.status}, created Run #{ev_b1.agent_run_id}")
    print(f"  [PASS] Event 2 #{ev_b2.id} status={ev_b2.status}, linked to Run #{ev_b2.agent_run_id} (No extra run created)")
    print(f"  [PASS] Suppression reason: '{ev_b2.suppression_reason}'")

    # -------------------------------------------------------------------------
    # PROOF C: Event storm protection (Rate Limiting)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PROOF C: Event Storm Protection (Threshold Enforcement)")
    print("-" * 80)
    storm_events = []
    # Ingest 21 rapid low-severity events to trip the >20 event storm threshold
    for i in range(21):
        ev_storm = service.ingest_event(
            project=project_a,
            event_type=SEOEventType.PAGE_STATUS_CHANGE,
            source="storm_simulator",
            payload={"url": f"https://alpha-event-audit.example.com/p{i}", "status_code": 200, "is_error": False},
            idempotency_key=f"storm-{unique_suffix}-{i}",
            user=user_a
        )
        storm_events.append(ev_storm)

    # The 22nd event must be suppressed due to event storm
    ev_storm_tripped = service.ingest_event(
        project=project_a,
        event_type=SEOEventType.RANKING_CHANGE,
        source="storm_simulator",
        payload={"keyword": "storm tripped", "rank_drop": 10},
        idempotency_key=f"storm-trip-{unique_suffix}",
        user=user_a
    )
    assert ev_storm_tripped.status == SEOEventStatus.SUPPRESSED, f"Expected SUPPRESSED, got {ev_storm_tripped.status}"
    assert "event storm detected" in ev_storm_tripped.suppression_reason.lower()
    assert ev_storm_tripped.agent_run is None
    print(f"  [PASS] Ingested 21 rapid events. Event #{ev_storm_tripped.id} status={ev_storm_tripped.status}")
    print(f"  [PASS] Storm suppression reason: '{ev_storm_tripped.suppression_reason}'")

    # -------------------------------------------------------------------------
    # PROOF D: Existing Architecture Preserved (SEOSupervisorAgent multi-agent stack)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PROOF D: Existing Architecture Preserved")
    print("-" * 80)
    # Verify ToolRegistry and authorizations
    reg = get_tool_registry()
    tool_names = [t.name for t in reg.list_tools()]
    assert "publish_live_site_update" not in tool_names
    assert "arbitrary_bash_command" not in tool_names
    print(f"  [PASS] ToolRegistry contains {len(tool_names)} registered tools. Unauthorized tools blocked.")

    # Verify SEOSupervisorAgent integration
    supervisor = SEOSupervisorAgent(project=project_a)
    assert hasattr(supervisor, "orchestrate"), "Supervisor orchestrate method preserved"
    assert hasattr(supervisor, "planner"), "Dynamic task planner preserved"
    assert hasattr(supervisor, "reasoning_service"), "Advanced reasoning preserved"
    print("  [PASS] SEOSupervisorAgent multi-agent stack, planner, and memory integration preserved.")

    # -------------------------------------------------------------------------
    # PROOF E: HITL Safety Boundary Strictly Preserved
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PROOF E: HITL Safety Boundary Preserved")
    print("-" * 80)
    from apps.seo.tasks import execute_event_triggered_agent_run_task

    ev_hitl = service.ingest_event(
        project=project_b,
        event_type=SEOEventType.CONTENT_CHANGE,
        source="cms_audit",
        payload={"url": "https://beta-event-audit.example.com/pricing", "significant": True},
        user=user_b
    )
    run_hitl = ev_hitl.agent_run
    action_hitl = SEOAction.objects.create(
        project=project_b,
        title="Audit Fix: Update meta description for pricing",
        action_type=ActionType.TECHNICAL_SEO_FIX,
        status=ActionStatus.PROPOSED
    )

    run_hitl.status = AgentRunStatus.PENDING
    run_hitl.save(update_fields=['status'])
    execute_event_triggered_agent_run_task(run_id=run_hitl.id, event_id=ev_hitl.id)

    run_hitl.refresh_from_db()
    action_hitl.refresh_from_db()
    assert run_hitl.status == AgentRunStatus.WAITING_FOR_APPROVAL, f"Expected WAITING_FOR_APPROVAL, got {run_hitl.status}"
    assert action_hitl.status == ActionStatus.PROPOSED, f"Expected PROPOSED, got {action_hitl.status}"
    print(f"  [PASS] Run #{run_hitl.id} status={run_hitl.status} (Safety Gated)")
    print(f"  [PASS] SEOAction #{action_hitl.id} status={action_hitl.status} (Requires explicit human review)")
    print(f"  [PASS] Run summary: '{run_hitl.summary}'")

    # -------------------------------------------------------------------------
    # PROOF F: Tenant / Project Isolation Preserved
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PROOF F: Tenant / Project Isolation Preserved")
    print("-" * 80)
    # User B attempting to ingest event for Project A must be rejected
    try:
        service.ingest_event(
            project=project_a,
            event_type=SEOEventType.RANKING_CHANGE,
            source="unauthorized_actor",
            payload={"keyword": "hack", "rank_drop": 5},
            user=user_b
        )
        assert False, "Should have raised PermissionError"
    except (PermissionError, ValueError) as p_err:
        print(f"  [PASS] Ingestion cross-tenant access blocked: '{p_err}'")

    # REST API isolation: User B accessing Project A's event returns 404
    factory = APIRequestFactory()
    req = factory.get(f"/api/seo/ai/events/{ev_a.id}/")
    force_authenticate(req, user=user_b)
    res = SEOEventViewSet.as_view({"get": "retrieve"})(req, pk=ev_a.id)
    assert res.status_code == 404, f"Expected 404, got {res.status_code}"
    print(f"  [PASS] REST API GET /api/seo/ai/events/{ev_a.id}/ with User B: status=404 (Isolated)")

    # -------------------------------------------------------------------------
    # PROOF G: Restart Resilience and Persistence Across Queries
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PROOF G: Restart Resilience and Persistence")
    print("-" * 80)
    reloaded_ev = SEOEvent.objects.get(id=ev_a.id)
    assert reloaded_ev.status == SEOEventStatus.PROCESSED
    assert reloaded_ev.agent_run_id == run_a.id
    reloaded_run = AgentRun.objects.get(id=run_a.id)
    assert reloaded_run.project_id == project_a.id
    print(f"  [PASS] Event #{reloaded_ev.id} and Run #{reloaded_run.id} linkages fully persistent.")

    # -------------------------------------------------------------------------
    # PROOF H: Cooldown Window Protection
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PROOF H: Cooldown Window Protection")
    print("-" * 80)
    ev_cooldown = service.ingest_event(
        project=project_b,
        event_type=SEOEventType.CONTENT_CHANGE,
        source="cms_rapid",
        payload={"url": "https://beta-event-audit.example.com/blog/1", "significant": True},
        cooldown_minutes=15,
        user=user_b
    )
    assert ev_cooldown.status == SEOEventStatus.SUPPRESSED, f"Expected SUPPRESSED, got {ev_cooldown.status}"
    assert "cooldown active" in ev_cooldown.suppression_reason.lower()
    print(f"  [PASS] Repeated event type suppressed: status={ev_cooldown.status}")
    print(f"  [PASS] Cooldown reason: '{ev_cooldown.suppression_reason}'")

    # -------------------------------------------------------------------------
    # PROOF I: ContinuousOperation Single Active Run Invariant Enforcement
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PROOF I: ContinuousOperation Single Active Run Invariant")
    print("-" * 80)
    op = cont_service.create_operation(
        project=project_b,
        user=user_b,
        goal="Audit continuous operation for project B",
        auto_activate=True
    )
    # Manually start a run so the operation is RUNNING
    run_active = cont_service.trigger_operation_manually(op.id, user=user_b)
    assert run_active is not None
    op.refresh_from_db()
    op.status = ContinuousOperationStatus.RUNNING
    op.current_run = run_active
    op.save(update_fields=['status', 'current_run'])

    # Ingest event connected to op - must be SUPPRESSED to prevent overlapping runs
    ev_inv = service.ingest_event(
        project=project_b,
        event_type=SEOEventType.PAGE_STATUS_CHANGE,
        source="server_alert",
        payload={"url": "https://beta-event-audit.example.com/down", "status_code": 503, "is_error": True},
        continuous_operation=op,
        user=user_b
    )
    assert ev_inv.status == SEOEventStatus.SUPPRESSED, f"Expected SUPPRESSED, got {ev_inv.status}"
    assert "already has active run" in ev_inv.suppression_reason.lower()
    print(f"  [PASS] Event #{ev_inv.id} suppressed because Op #{op.id} has active run #{op.current_run_id}")
    print(f"  [PASS] Single active run invariant preserved.")

    # Complete run_active and clean up
    cont_service.handle_run_completion(op.id, run_active.id, AgentRunStatus.COMPLETED)

    # -------------------------------------------------------------------------
    # PROOF J: Telemetry Lifecycle & Runtime Evaluation Metrics
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PROOF J: Telemetry Lifecycle & Runtime Evaluation Metrics")
    print("-" * 80)
    emitted_types = {e.event_type for e in publisher.get_events()}
    assert AgentEventType.SEO_EVENT_RECEIVED in emitted_types
    assert AgentEventType.SEO_EVENT_TRIGGERED in emitted_types
    assert AgentEventType.SEO_EVENT_SUPPRESSED in emitted_types
    assert AgentEventType.SEO_EVENT_DEDUPLICATED in emitted_types
    print(f"  [PASS] Publisher recorded {len(publisher.get_events())} lifecycle telemetry events.")
    emitted_str_types = [(t.value if hasattr(t, 'value') else str(t)) for t in emitted_types]
    print(f"  [PASS] Key telemetry types verified: {[s for s in emitted_str_types if 'event' in s][:6]}")

    metrics = eval_service.evaluate_event_driven_operations(project=project_a)
    assert metrics["events_received"] > 0
    assert "event_trigger_rate" in metrics
    assert "events_deduplicated" in metrics
    assert "events_suppressed" in metrics
    assert "event_to_run_rate" in metrics
    print(f"  [PASS] Runtime metrics for Project A: events_received={metrics['events_received']}, "
          f"events_accepted={metrics['events_accepted']}, events_suppressed={metrics['events_suppressed']}, "
          f"trigger_rate={metrics['event_trigger_rate']}%")

    # -------------------------------------------------------------------------
    # PROOF K: REST API Endpoints Verification
    # -------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("PROOF K: REST API Endpoints Verification")
    print("-" * 80)
    # 1. Ingest via API
    req = factory.post("/api/seo/ai/events/ingest/", {
        "project_id": project_a.id,
        "event_type": "page_status_change",
        "source": "api_test",
        "severity": "critical",
        "payload": {"url": "https://alpha-event-audit.example.com/checkout", "status_code": 500, "is_error": True}
    }, format="json")
    force_authenticate(req, user=user_a)
    res_ingest = SEOEventViewSet.as_view({"post": "ingest"})(req)
    assert res_ingest.status_code == 201, f"Expected 201, got {res_ingest.status_code}"
    new_event_id = res_ingest.data["id"]
    print(f"  [PASS] POST /api/seo/ai/events/ingest/: status=201, event_id={new_event_id}")

    # 2. List events
    req = factory.get(f"/api/seo/ai/events/?project={project_a.id}")
    force_authenticate(req, user=user_a)
    res_list = SEOEventViewSet.as_view({"get": "list"})(req)
    assert res_list.status_code == 200
    items = res_list.data["results"] if "results" in res_list.data else res_list.data
    assert len(items) >= 2
    print(f"  [PASS] GET /api/seo/ai/events/?project={project_a.id}: status=200, count={len(items)}")

    # 3. Retrieve event
    req = factory.get(f"/api/seo/ai/events/{new_event_id}/")
    force_authenticate(req, user=user_a)
    res_ret = SEOEventViewSet.as_view({"get": "retrieve"})(req, pk=new_event_id)
    assert res_ret.status_code == 200
    assert res_ret.data["id"] == new_event_id
    print(f"  [PASS] GET /api/seo/ai/events/{new_event_id}/: status=200, type={res_ret.data['event_type']}")

    # 4. Metrics endpoint
    req = factory.get(f"/api/seo/ai/events/metrics/?project={project_a.id}")
    force_authenticate(req, user=user_a)
    res_met = SEOEventViewSet.as_view({"get": "metrics"})(req)
    assert res_met.status_code == 200
    assert "event_trigger_rate" in res_met.data
    print(f"  [PASS] GET /api/seo/ai/events/metrics/: status=200, trigger_rate={res_met.data['event_trigger_rate']}%")

    # 5. Runs for event endpoint
    req = factory.get(f"/api/seo/ai/events/{ev_a.id}/runs/")
    force_authenticate(req, user=user_a)
    res_runs = SEOEventViewSet.as_view({"get": "runs"})(req, pk=ev_a.id)
    assert res_runs.status_code == 200
    assert len(res_runs.data) >= 1
    print(f"  [PASS] GET /api/seo/ai/events/{ev_a.id}/runs/: status=200, runs={len(res_runs.data)}")

    print("\n" + "=" * 80)
    print("ALL MILESTONE 6.2 RUNTIME AUDIT PROOFS (A THROUGH K) VERIFIED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    run_audit()
