# DoxaRank Milestone 6.2 — Event-Driven Agents

## 1. Executive Summary & Core Philosophy

Milestone 6.2 marks the introduction of **event-driven autonomous workflows** to DoxaRank. While Milestone 6.1 introduced continuous, schedule-driven agent execution, Milestone 6.2 establishes real-time responsiveness to meaningful external and internal SEO occurrences.

### Core Question
> **“Can DoxaRank automatically trigger the appropriate agent workflow when a meaningful SEO event occurs, instead of relying only on a schedule or manual user action?”**

### Zero-Bypass Principle
Event-driven agents do **not** create an ad-hoc runner or bypass the core platform architecture. Every event-triggered workflow runs through the complete, battle-tested multi-agent stack established in Milestones 5.1–5.7 and 6.1:
- **`SEOSupervisorAgent`**: Evaluates the event-generated goal and orchestrates the agent team.
- **`DynamicTaskPlanner`**: Creates an initial DAG of tasks with deterministic dependency graphs and replan triggers.
- **`AdaptiveAgentSelector`**: Assigns specialized agents (`seo_researcher`, `seo_investigator`, `seo_strategist`, `seo_action_planner`, `seo_verifier`) using capability profiles, epistemic weighting, and historical competence.
- **`ParallelBatchExecutor`**: Executes independent subagent tasks concurrently with bounded worker concurrency.
- **`SharedWorkingMemory`**: Retains segregated evidence, observations, and structured decision logs.
- **`AdvancedReasoningService`**: Resolves hypotheses, cross-critiques, and dialectical consensus when agent conclusions diverge.
- **`ToolRegistry` & MCP Permissions**: All tool executions remain strictly validated against project tenant constraints and agent authorization lists.

### Scope & Safety Boundaries
1. **Human-In-The-Loop (HITL) Safety Gating**: Events may autonomously trigger investigation, auditing, and strategy formulation. However, **no event or agent may ever autonomously mutate live sites or external systems**. Any mutating recommendation (e.g. `TECHNICAL_SEO_FIX`, `OPTIMIZE_TITLE`, `FIX_CANONICAL`) results in an `SEOAction` created in `PROPOSED` status, and the `AgentRun` immediately transitions to `WAITING_FOR_APPROVAL`.
2. **Payload Sanitization & Tool Safety**: Event payloads are treated as untrusted input. Forbidden keys such as `tools`, `agents`, `bypass_*`, or `execute_*` are blocked and stripped, preventing prompt injections from manipulating tool authorizations.
3. **Deterministic Idempotency & Storm Suppression**: Events are deduplicated by SHA-256 fingerprint over a 1-hour window. Event storms (>20 events per 5 minutes) and rapid repeats (cooldown window of 15 minutes per event type) are suppressed with explicit audit trails.
4. **Single Active Run Invariant**: When an event targets an active `ContinuousOperation`, the single active run invariant is preserved: if the operation is already executing a run, the incoming event is suppressed to prevent race conditions and overlapping tasks.
5. **Strict Scope Control**: No autonomous remediation (6.4), external monitoring scrapers (6.3), or multi-system webhooks (6.5) are implemented in this phase.

---

## 2. Architecture & Data Model

### Data Model: `SEOEvent`
Stored in `apps.seo.models.SEOEvent`:

| Field | Type | Description |
| :--- | :--- | :--- |
| `project` | `ForeignKey(Project)` | Tenant/project boundary with cascade delete. |
| `event_type` | `CharField(SEOEventType)` | Type of event: `ranking_change`, `page_status_change`, `seo_audit_change`, `gsc_change`, `content_change`, `competitor_move`, `index_change`. |
| `source` | `CharField(100)` | Origin identifier (e.g., `google_serp`, `uptime_monitor`, `cms_webhook`). |
| `severity` | `CharField(SEOEventSeverity)` | `low`, `medium`, `high`, `critical`. |
| `status` | `CharField(SEOEventStatus)` | `received`, `accepted`, `rejected`, `deduplicated`, `suppressed`, `processed`, `failed`. |
| `payload` | `JSONField` | Sanitized key-value data describing the event. |
| `correlation_id` | `CharField(64)` | Trace ID connecting telemetry, logs, and downstream runs. |
| `idempotency_key` | `CharField(128)` | Deterministic SHA-256 or caller-supplied uniqueness key. |
| `occurred_at` | `DateTimeField` | When the event actually occurred at the source. |
| `processed_at` | `DateTimeField` | When the ingestion pipeline evaluated/dispatched the event. |
| `suppression_reason` | `TextField` | Detailed explanation if suppressed, deduplicated, or accepted without trigger. |
| `agent_run` | `ForeignKey(AgentRun)` | Linked `AgentRun` created to address this event. |
| `continuous_operation` | `ForeignKey(ContinuousOperation)` | Optional link to project's continuous operation. |

### Indexes & Uniqueness
- B-Tree indexes on `(project, event_type, created_at)` and `(project, status, created_at)`.
- Unique constraint / index on `(project, idempotency_key)`.

---

## 3. Ingestion & Event Processing Pipeline

```
                ┌────────────────────────────────┐
                │      Incoming SEO Event        │
                └───────────────┬────────────────┘
                                │
                                ▼
            [Stage 1: Validation & Sanitization]
              - Tenant permission check
              - Schema & required fields
              - Strip forbidden keys (tools, agents)
                                │
                                ▼
            [Stage 2: Deterministic Idempotency]
              - SHA-256 fingerprint within 1h window
              - Duplicate? ──► [Mark DEDUPLICATED] ──► Return original run
                                │ (New Event)
                                ▼
            [Stage 3: Cooldown & Storm Protection]
              - Event storm (>20 / 5m)? ──► [Mark SUPPRESSED] ──► Return
              - Cooldown active? ──────────► [Mark SUPPRESSED] ──► Return
                                │ (Passed Limits)
                                ▼
            [Stage 4: Trigger Policy Evaluation]
              - Evaluate event threshold (drop >= 3, HTTP >= 400)
              - Below threshold? ──► [Mark ACCEPTED] ──► Return
                                │ (Trigger Required)
                                ▼
            [Stage 5: ContinuousOperation Invariant]
              - Operation already running? ──► [Mark SUPPRESSED] ──► Return
                                │ (Ready to Dispatch)
                                ▼
            [Stage 6: Dispatch AgentRun via Celery]
              - Atomically create AgentRun with context snapshot
              - Mark SEOEvent PROCESSED
              - Enqueue execute_event_triggered_agent_run_task
              - SEOSupervisorAgent.orchestrate()
```

### Stage 1: Validation & Security Sanitization
- Validates that the calling user owns the project (cross-tenant access raises `PermissionError`/`ValueError`).
- Scans payload for forbidden injection keys (`tools`, `agents`, `bypass_*`, `execute_*`, `permissions`, `eval`). If detected, ingestion is rejected.

### Stage 2: Deterministic Idempotency & Deduplication
- Computes SHA-256 over normalized `(project_id, event_type, sorted_payload)` if no custom key is provided.
- Queries for matching events within the last 1 hour.
- If a match exists, creates a `DEDUPLICATED` event linked to the existing `AgentRun` without launching a duplicate workflow.

### Stage 3: Cooldown & Event Storm Suppression
- **Event Storm Protection**: Evaluates total events for the project in the last 5 minutes. If count > 20, event is marked `SUPPRESSED` with reason `"Event storm detected: ... exceeded threshold (20)"`.
- **Cooldown Window Protection**: Enforces a minimum cooldown window (default 15 minutes) between triggered runs for the same `(project, event_type)`.

### Stage 4: Trigger Policy Evaluation (`EventTriggerPolicy`)
Translates domain signals into high-level agent objectives without pre-selecting specific agents:
- `RANKING_CHANGE`: Requires rank drop >= 3 positions or high/critical severity.
- `PAGE_STATUS_CHANGE`: Requires HTTP error status (>= 400) or explicit error flag.
- `SEO_AUDIT_CHANGE`: Requires >= 1 critical issue or >= 3 total issues.
- `GSC_CHANGE`: Requires clicks drop >= 20% or impressions drop >= 25%.
- `CONTENT_CHANGE`: Requires significant modification flag or high severity.

### Stage 5: ContinuousOperation Integration & Single Active Run Invariant
If linked to a `ContinuousOperation`, verifies that `operation.status != RUNNING` and `operation.current_run is None`. If an active run is in flight, the event is marked `SUPPRESSED` and increments `duplicate_prevention_count`.

### Stage 6: Agent Run Dispatch
- Atomically creates an `AgentRun` with `trigger: "event"` and context snapshot.
- Links `SEOEvent.agent_run = run` and sets `status = PROCESSED`.
- Dispatches `execute_event_triggered_agent_run_task.delay(run_id, event_id)` to the Celery worker queue.

---

## 4. Background Execution & Human-In-The-Loop Safety

### `execute_event_triggered_agent_run_task`
1. **Row-Level Locking**: Atomically acquires the `AgentRun` using `select_for_update()`.
2. **Supervisor Orchestration**: Instantiates `SEOSupervisorAgent(project=run.project, user=run.user)` and executes `supervisor.orchestrate(initial_goal=run.goal, run_id=run.id)`.
3. **Step Recording**: Converts dynamic task planner tasks into persisted `AgentStep` records.
4. **HITL Mutating Action Gate**:
   - Queries `SEOAction.objects.filter(project=run.project, status=ActionStatus.PROPOSED)`.
   - If any mutating actions were proposed or if `context.requires_human_approval` is True:
     - Sets `run.status = AgentRunStatus.WAITING_FOR_APPROVAL`.
     - Leaves `SEOAction.status = ActionStatus.PROPOSED`.
     - Logs `"Execution paused: Proposed SEO action(s) require human review and approval."`.
   - If no approval is required:
     - Sets `run.status = AgentRunStatus.COMPLETED`.
5. **Failure Isolation**: Any uncaught exception in the multi-agent stack is isolated; sets `run.status = FAILED`, sanitizes secret keys from error messages, and updates the linked `ContinuousOperation` if present.

---

## 5. Telemetry & Runtime Evaluation Metrics

### Telemetry Events (`AgentEventType`)
Milestone 6.2 introduces 9 dedicated event lifecycle telemetry signals:
- `SEO_EVENT_RECEIVED`: Emitted upon ingestion into the system.
- `SEO_EVENT_ACCEPTED`: Emitted when validated and stored without triggering a run.
- `SEO_EVENT_REJECTED`: Emitted when payload validation fails or forbidden keys are found.
- `SEO_EVENT_DEDUPLICATED`: Emitted when duplicate submission is suppressed.
- `SEO_EVENT_SUPPRESSED`: Emitted when suppressed by storm, cooldown, or active run lock.
- `SEO_EVENT_TRIGGERED`: Emitted when an event passes policy and initiates a run.
- `SEO_EVENT_COOLDOWN`: Emitted when cooldown protection suppresses a duplicate run.
- `SEO_EVENT_RUN_CREATED`: Emitted when the child `AgentRun` is persisted.
- `SEO_EVENT_PROCESSING_FAILED`: Emitted when worker execution encounters an unhandled failure.

### Runtime Metrics (`SEOAgentEvaluationService.evaluate_event_driven_operations`)
Dynamically derived from actual database records (no mock or static numbers):
- `events_received`: Total events received.
- `events_accepted`: Events accepted into the system.
- `events_rejected`: Events rejected during ingestion.
- `events_deduplicated`: Events deduplicated via idempotency keys.
- `events_suppressed`: Events suppressed by rate limits or cooldowns.
- `events_triggered`: Events that successfully initiated an `AgentRun`.
- `event_trigger_rate`: `(events_triggered / events_accepted) * 100`.
- `event_to_run_rate`: `(events_triggered / events_received) * 100`.
- `average_event_trigger_delay`: Average latency in seconds between `occurred_at` and processing.
- `event_storm_suppressions`: Events suppressed due to event storm thresholds.
- `cooldown_suppressions`: Events suppressed due to active cooldown windows.

---

## 6. REST API Endpoints

All endpoints are registered under `/api/seo/ai/events/` and enforce project ownership:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/seo/ai/events/?project={id}` | List project events with filtering by `status`, `event_type`, `severity`. |
| `POST` | `/api/seo/ai/events/ingest/` | Ingest external SEO event with automatic sanitization and triggering. |
| `GET` | `/api/seo/ai/events/{id}/` | Retrieve full event details including suppression reasons and linked run. |
| `GET` | `/api/seo/ai/events/{id}/runs/` | List all `AgentRun` records associated with this event. |
| `GET` | `/api/seo/ai/events/metrics/?project={id}` | Retrieve runtime evaluation metrics for event-driven operations. |

---

## 7. Dashboard UI: Event Activity Panel

Located in `dashboard/src/components/EventActivityPanel.tsx` and integrated into the main `Dashboard.tsx`:
- **Real-Time KPI Cards**: Total Events, Trigger Rate (%), Deduplication Rate (%), and Active Cooldowns.
- **Filtering & Search**: Filter by status (`all`, `processed`, `suppressed`, `deduplicated`), event type, and severity.
- **Event Audit Table**: Displays event type badges, severity indicators, trigger status, linked run navigation, and timestamps.
- **Interactive Detail Drawer**: Inspects full payload JSON, correlation IDs, idempotency keys, and suppression audit trails.
- **"Simulate SEO Event" Modal**: Allows operators to test event ingestion directly from the UI with preset templates (Ranking Drop, 500 Error, GSC Drop, Content Update).

---

## 8. Verification & Audit Results

### Test Verification Summary
- **Milestone 6.2 Dedicated Tests (`EventDrivenAgentsTests`)**: 24/24 passed (100%).
- **Milestone 6.1 Continuous Operations Regression**: 12/12 passed (100%).
- **Milestones 5.1–5.7 Core Multi-Agent Regressions**: 136/136 passed (100%).
- **Total Test Suite**: 172/172 passed.

### Standalone Runtime Audit (`backend/audit_milestone_6_2.py`)
All 11 runtime proofs (Proofs A through K) executed successfully against live database instances:
- `[PASS] Proof A: Event Triggers Appropriate Agent Workflow` (Status: PROCESSED, Run created with event snapshot)
- `[PASS] Proof B: Duplicate Event Protection` (Status: DEDUPLICATED, links to original run, 0 extra runs)
- `[PASS] Proof C: Event Storm Protection` (Threshold >20 events / 5m enforced, Status: SUPPRESSED)
- `[PASS] Proof D: Existing Architecture Preserved` (SEOSupervisorAgent, planner, memory, learning, reasoning, tools intact)
- `[PASS] Proof E: HITL Safety Boundary Preserved` (Mutating actions enter WAITING_FOR_APPROVAL, PROPOSED)
- `[PASS] Proof F: Tenant / Project Isolation Preserved` (Cross-tenant access returns 404 / PermissionError)
- `[PASS] Proof G: Restart Resilience and Persistence` (DB reloads preserve event-to-run linkage)
- `[PASS] Proof H: Cooldown Window Protection` (Repeated event types within 15m suppressed)
- `[PASS] Proof I: ContinuousOperation Invariant` (Overlapping run on active operation suppressed)
- `[PASS] Proof J: Telemetry Lifecycle & Runtime Evaluation Metrics` (64 telemetry events published, runtime metrics verified)
- `[PASS] Proof K: REST API Endpoints Verification` (ingest, list, retrieve, metrics, runs verified with HTTP 200/201)
