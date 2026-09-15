# DoxaRank Milestone 6.1 — Continuous Agent Operations

## 1. Executive Summary & Core Philosophy

Milestone 6.1 marks the transition of DoxaRank from a purely manual, user-triggered orchestration platform to an autonomous, continuous multi-agent system.

### Core Question
> **“Can DoxaRank agents operate continuously on SEO projects instead of only running when a user manually triggers an orchestration?”**

### Fundamental Architectural Tenet
Continuous operations do **not** introduce a duplicate orchestration or reasoning engine. Instead, Milestone 6.1 provides a robust, stateful scheduling and lifecycle harness (`ContinuousOperationService`) directly over the established multi-agent foundation established in Milestones 5.1–5.7:
- **`SEOSupervisorAgent`**: High-level goal orchestration and DAG generation.
- **`DynamicTaskPlanner`**: Plan creation, dependency tracking, replanning triggers.
- **`AdaptiveAgentSelector`**: Multi-factor agent scoring with epistemic and competence weighting.
- **`ParallelBatchExecutor`**: Concurrent agent task dispatch with concurrency limits.
- **`SharedWorkingMemory`**: Epistemic segregation, evidence items, and decision logs.
- **`AdvancedReasoningService`**: Hypothesis testing, peer critiques, and dialectical consensus.

### Strict Scope & Safety Boundaries
To preserve system safety, security, and predictability, Milestone 6.1 adheres to rigid boundaries:
1. **Human-In-The-Loop (HITL) Mutating Action Gate**: Continuous operations can continuously crawl, audit, analyze, and synthesize. However, any mutating action (e.g. modifying meta tags, updating sitemaps, changing content) **must** enter a pending approval state (`WAITING_FOR_APPROVAL`). When an approval is required, the continuous operation transitions to `WAITING` status and suspends further scheduled runs until human sign-off.
2. **Strict Single Active Run Invariant**: At most **one** active `AgentRun` may exist for any `ContinuousOperation` at any given time. Overlapping, parallel runs of the same operation are strictly forbidden.
3. **Pessimistic Concurrency Locking**: Due operation triggers use database row locks (`select_for_update`) to prevent race conditions across distributed Celery workers.
4. **Resilience & Circuit Breaking**: Transient failures trigger exponential backoff. Persistent failures (exceeding `max_consecutive_failures`) trip a circuit breaker, setting the operation status to `FAILED` and halting recurring executions.
5. **Strict Scope Control**: No event-driven triggers (6.2), autonomous monitoring webhooks (6.3), or autonomous self-remediation (6.4) are implemented here.

---

## 2. Continuous Operation Lifecycle & State Machine

```
               ┌───────────────┐
               │    CREATE     │
               └───────┬───────┘
                       │
                       ▼
               ┌───────────────┐
         ┌────►│    ACTIVE     │◄────────────┐
         │     └───────┬───────┘             │
         │             │ (due/triggered)     │
         │             ▼                     │
         │     ┌───────────────┐             │
         │     │    RUNNING    │             │ (resume)
         │     └───────┬───────┘             │
         │             │                     │
(success)│     ┌───────┴───────┬─────────┐   │
         │     │               │         │   │
         │     ▼               ▼         ▼   │
         │  (normal)       (mutating)  (fatal)
         │  [success]        [HITL]    [circuit trip]
         │     │               │         │
         └─────┘               ▼         ▼
                       ┌───────────┐ ┌────────┐
                       │  WAITING  │ │ FAILED │
                       └───────────┘ └────────┘
                             │
                             ▼ (pause / maintenance)
                       ┌───────────┐
                       │  PAUSED   │
                       └───────────┘
```

### State Definitions
| Status | Description | Scheduled Run Behavior |
| :--- | :--- | :--- |
| `ACTIVE` | Normal operating status. | Evaluated by scheduler; runs triggered when `next_run_at <= now()`. |
| `RUNNING` | An `AgentRun` is currently executing. | Locked; duplicate triggers rejected. |
| `WAITING` | An action requires human review (`HITL`). | Scheduling suspended until pending action is resolved. |
| `PAUSED` | User or administrator manually paused operation. | Scheduling suspended; `next_run_at` cleared. |
| `COMPLETED` | One-shot or bounded operation finished. | Terminal state; no further runs scheduled. |
| `FAILED` | Circuit breaker tripped after consecutive failures. | Terminal state; alerts emitted; requires manual intervention. |

---

## 3. Concurrency Protection & Invariant Enforcement

### Single Active Run Invariant
To prevent resource exhaustion and data races within project memory, an operation can never have more than one run active at a time:
```python
if operation.current_run is not None and operation.current_run.status in [
    AgentRunStatus.PENDING,
    AgentRunStatus.RUNNING,
    AgentRunStatus.WAITING_APPROVAL,
]:
    logger.warning(f"Manual trigger rejected for Op #{operation_id}: Already has active run #{operation.current_run_id}.")
    return None
```

### Distributed Worker Protection
Celery beat dispatches `evaluate_due_continuous_operations_task` every 60 seconds. Each candidate operation is locked using `select_for_update(skip_locked=True)` within an atomic transaction:
```python
with transaction.atomic():
    operation = ContinuousOperation.objects.select_for_update().get(id=operation_id)
    if operation.status != ContinuousOperationStatus.ACTIVE:
        return
    # Mark as running and launch execution task
    operation.status = ContinuousOperationStatus.RUNNING
    operation.save(update_fields=["status"])
```

---

## 4. Failure Recovery & Circuit Breaker

Continuous operations feature self-healing with graceful backoff and hard trip boundaries:

1. **Exponential Backoff**:
   On failure, the next attempt is delayed dynamically:
   $$\text{Backoff Minutes} = 5 \times 2^{(\text{consecutive\_failures} - 1)}$$
   - Failure 1: 5 minutes
   - Failure 2: 10–15 minutes
   - Failure 3: 20–30 minutes (capped at 1440 minutes / 24 hours)

2. **Circuit Breaker**:
   If $\text{consecutive\_failures} \ge \text{max\_consecutive\_failures}$ (default 3):
   - Operation status transitions to `ContinuousOperationStatus.FAILED`.
   - `next_run_at` is set to `None`.
   - `SEO_OPERATION_FAILED` telemetry event is published.
   - An operational alert is surfaced on the dashboard.

---

## 5. Human-in-the-Loop (HITL) Safety Gate

Autonomous execution of destructive or public-facing changes without human oversight is prohibited:
- Read-only operations (crawling, ranking checks, GSC analysis, content drafting, technical audit) run automatically.
- Any task producing an `SEOAction` with status `PENDING_APPROVAL` or an `AgentRun` entering `WAITING_APPROVAL` automatically signals the post-run completion handler.
- The continuous operation enters `WAITING` status and clears `next_run_at`, preventing subsequent runs until a user explicitly approves or rejects the action through the dashboard.

---

## 6. Telemetry & Event Architecture

Milestone 6.1 introduces 9 specialized telemetry event types emitted through `InMemoryEventPublisher` / streaming channels:

| Event Type | Description |
| :--- | :--- |
| `SEO_OPERATION_CREATED` | Emitted upon creation of a new continuous operation. |
| `SEO_OPERATION_STARTED` | Emitted when continuous operation is activated/started. |
| `SEO_OPERATION_PAUSED` | Emitted when operation is manually paused. |
| `SEO_OPERATION_RESUMED` | Emitted when paused operation is resumed. |
| `SEO_OPERATION_RUN_SCHEDULED` | Emitted when the next recurrence timestamp is calculated. |
| `SEO_OPERATION_RUN_STARTED` | Emitted when a background `AgentRun` begins execution. |
| `SEO_OPERATION_RUN_COMPLETED` | Emitted upon successful execution of an operation run. |
| `SEO_OPERATION_RUN_FAILED` | Emitted upon failure of an individual run. |
| `SEO_OPERATION_COMPLETED` | Emitted when an operation finishes or trips the circuit breaker. |

---

## 7. Runtime Evaluation & Observability

The `SEOAgentEvaluationService.evaluate_continuous_operations(project_id)` method aggregates 15 runtime metrics across all continuous operations:
- `total_operations`, `active_operations`, `paused_operations`, `waiting_operations`, `failed_operations`, `completed_operations`
- `total_runs`, `successful_runs`, `failed_runs`
- `circuit_breaker_trips`, `consecutive_failures_peak`
- `overall_success_rate`: Percentage of completed runs that succeeded
- `failure_rate`: Percentage of completed runs that failed
- `uptime_percentage`: $\frac{\text{active\_operations}}{\text{total\_operations}} \times 100\%$
- `mean_time_between_runs_minutes`: Average interval between continuous execution cycles

---

## 8. Frontend Dashboard & User Experience

The operational panel (`ContinuousOperationsPanel.tsx`) provides complete operational visibility:
- **Metrics Strip**: Total Operations, Active, Uptime %, Total Executions, and Circuit Breaker Trips.
- **Operations Table**:
  - Name, objective, schedule interval badge (`Daily`, `Hourly`, `Custom Cron`).
  - Next Run countdown (live humanized format).
  - Status badges (`ACTIVE`, `RUNNING`, `WAITING`, `PAUSED`, `FAILED`).
  - Quick action buttons: **Pause**, **Resume**, **Run Now**.
- **Execution Run History**: Real-time drilldown into recent runs, status, duration, and findings.
- **Create Operation Modal**: Guided dialog to configure schedules, target agents, and failure thresholds.

---

## 9. Explicit Deferrals (Out of Scope for Milestone 6.1)

To maintain focus and avoid unbounded complexity, the following areas are strictly deferred:
- **Milestone 6.2 — Event-Driven Agents**: Webhook listeners, real-time GSC API push triggers, Git webhooks.
- **Milestone 6.3 — Autonomous SEO Monitoring**: Anomaly detection engines, continuous metric deviation alarms.
- **Milestone 6.4 — Autonomous Remediation**: Self-healing robots.txt, automated canonical repair without human review.
- **Milestone 6.5 — Multi-System Agent Integration**: CMS write-backs (WordPress/Shopify plugins), CDN edge workers.
- **Milestone 6.6 — Long-Term SEO Strategy**: Quarterly strategic roadmap agents, macro trend forecasting.
- **Milestone 6.7 — Production Agent Platform**: Multi-cluster Kubernetes agent deployment, tenant billing meters.
