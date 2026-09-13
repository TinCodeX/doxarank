# DoxaRank Phase 5.6 — Agent Learning & Optimization

## 1. Executive Summary & Core Philosophy

Milestone 5.6 introduces **Agent Learning & Optimization** for the DoxaRank Agentic AI multi-agent system. Building directly upon Milestones 5.1–5.5, Milestone 5.6 enables the system to systematically learn from historical execution, verification, and routing outcomes to make superior agent selection and coordination decisions over time.

### Core Question
> **“Based on what happened before, how should the system make better decisions next time?”**

### Guiding Principles

1. **Advisory & Bounded Learning**:
   Learning provides soft scoring adjustments bounded within $[-0.08, +0.08]$. Historical performance can refine candidate rankings among eligible agents but **never** overrules hard architectural constraints or core capability matches (where capability differences carry a weight of $0.35$).
2. **Safety & Governance Invariance**:
   Learning signals can never bypass:
   - Tenant isolation boundaries (Project A cannot access Project B's private SEO data).
   - ToolRegistry allowlists and forbidden tool prohibitions.
   - MCP permissions and server boundaries.
   - Task risk gates and Human-In-The-Loop (HITL) mandatory approval requirements for mutating actions.
3. **No Autonomous Code Modification or Weight Fine-Tuning**:
   Learning operates deterministically over structured runtime records, empirical success ratios, and calibration curves. It does not autonomously rewrite source code, alter tool schemas, or invoke non-deterministic self-tuning.
4. **Distinct Classification of Non-Competence Failures**:
   Human rejection (`HUMAN_REJECTION`) and safety blocks (`SAFETY_BLOCK`) are segregated from genuine agent operational failures (`AGENT_FAILURE`, `VERIFICATION_FAILURE`, `TIMEOUT`). An agent is never penalized for upholding safety boundaries or when a human reviewer exercises editorial preference.
5. **Cold-Start Resilience & Statistical Rigor**:
   Under small sample sizes ($N < 3$), historical signals are explicitly ignored. Between 3 and 10 samples, signals scale smoothly using Bayesian shrinkage priors ($\alpha=2, \beta=2$) to prevent wild oscillations on early outcomes.

---

## 2. System Architecture & Feedback Loop

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                 TaskPlan (DAG)                                    │
└────────────────────────────────────────┬──────────────────────────────────────────┘
                                         │
                                         ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           READY AgentTask Execution                               │
└────────────────────────────────────────┬──────────────────────────────────────────┘
                                         │
                                         ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                     AdaptiveAgentSelector (Milestone 5.5 + 5.6)                   │
│                                                                                   │
│ 1. Hard Constraint Validation (Tenant, Tools, Capabilities, Risk, HITL)           │
│ 2. Base Multi-Factor Scoring (Cap: 0.35, Type: 0.20, Role: 0.15, Workload: 0.10)  │
│ 3. Milestone 5.6 Historical Signal Calculation:                                  │
│    ├── Query AgentPerformanceStore for (agent, task_type, project_id)             │
│    ├── Check sample size threshold (N >= 3)                                       │
│    ├── Compute Bayesian smoothed rate: p_hat = (k + 2) / (N + 4)                  │
│    ├── Compute bounded signal: S_hist = clamp((p_hat - p_base) * w_ev * 0.08)     │
│    └── Annotate explainable reasons: "historical_signal_applied: +0.051..."       │
│ 4. Deterministic Tie-Breaking                                                     │
└────────────────────────────────────────┬──────────────────────────────────────────┘
                                         │
                                         ├───► RoutingDecision (includes confidence)
                                         ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           SEOSupervisorAgent Orchestration                        │
│                                                                                   │
│ ├── Execute Task with Selected Worker (or Safe Fallback Worker)                   │
│ ├── Capture Duration, Outcome, Findings, and Verification Lift                    │
│ └── Emit Milestone 5.6 Telemetry Events                                           │
└────────────────────────────────────────┬──────────────────────────────────────────┘
                                         │
                                         ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           AgentLearningService (Record)                           │
│                                                                                   │
│ ├── Classify Outcome (NONE, AGENT_FAILURE, VERIFICATION_FAILURE, SAFETY_BLOCK...) │
│ ├── Construct AgentPerformanceRecord                                              │
│ ├── Append to CollaborationState & SharedContext                                  │
│ └── Persist into AgentPerformanceStore                                            │
└────────────────────────────────────────┬──────────────────────────────────────────┘
                                         │
                                         ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           AgentPerformanceStore (Update)                          │
│                                                                                   │
│ ├── Update Tenant-Isolated Partition: records_by_tenant[project_id]               │
│ ├── Update Global Anonymized Rollup: global_records (Zero PII/Keywords)           │
│ └── Recompute AgentPerformanceStats & Calibration Curves                          │
└───────────────────────────────────────────────────────────────────────────────────┘
                                         │
                     (Feeds next routing decision) ◄────────────────────────────────┘
```

---

## 3. Data Structures & Failure Categorization

### 3.1 FailureCategory

```python
class FailureCategory(str, Enum):
    NONE = "none"                          # Successful execution
    AGENT_FAILURE = "agent_failure"        # Tool exception, unhandled error, invalid response
    VERIFICATION_FAILURE = "verification_failure"  # Failed empirical post-action verification
    SAFETY_BLOCK = "safety_block"          # Hard constraint rejection (not an agent defect)
    HUMAN_REJECTION = "human_rejection"    # Human reviewer declined proposal (not a defect)
    TIMEOUT = "timeout"                    # Execution timed out
    SYSTEM_ERROR = "system_error"          # Infrastructure / network failure
```

**Key Safety Rule**: In `AgentPerformanceStore.get_agent_stats()`, records categorized as `SAFETY_BLOCK` or `HUMAN_REJECTION` are excluded from the denominator when calculating an agent's failure rate and routing quality penalty.

### 3.2 AgentPerformanceRecord

```python
@dataclass
class AgentPerformanceRecord:
    agent_name: str
    task_id: str
    task_type: str
    project_id: int
    success: bool
    execution_duration_ms: float = 0.0
    predicted_confidence: float = 0.85
    verification_status: str = "none"  # "none", "verified", "failed"
    reassignment_count: int = 0
    tool_usage: List[str] = field(default_factory=list)
    failure_category: FailureCategory = FailureCategory.NONE
    failure_reason: str = ""
    was_fallback: bool = False
    routing_metadata: Dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    recorded_at: str = field(default_factory=...)
```

### 3.3 AgentPerformanceStats

Deterministic summary statistics generated on demand:

* `sample_size`: Total evaluated tasks.
* `successful_tasks`: Count of successful tasks.
* `failed_tasks`: Count of operational failures.
* `success_rate`: $k / N$.
* `failure_rate`: $1.0 - \text{success\_rate}$.
* `verification_attempts`: Count of tasks with verification (`"verified"` or `"failed"`).
* `verified_successes`: Count of verified successful tasks.
* `verification_success_rate`: Ratio of verified successes to verification attempts.
* `reassignment_rate`: Ratio of tasks requiring reassignment.
* `avg_duration_ms`: Average execution duration.
* `confidence_calibration_error`: Brier score $|c - y|^2$ assessing confidence accuracy.
* `has_sufficient_evidence`: Boolean flag ($N \ge 3$).
* `routing_quality_score`: Composite quality metric in $[0.0, 1.0]$.

---

## 4. Mathematical Model & Bounded Historical Signal

### 4.1 Sample Size Thresholds

* **Minimum Sample Size ($N_{\text{min}} = 3$)**: If $N < N_{\text{min}}$, the store returns `HistoricalSignal(signal_applied=False, reason="insufficient sample size")`.
* **Full Evidence Sample Size ($N_{\text{full}} = 10$)**: Evidence weighting scales linearly from $0.0$ at $N=0$ to $1.0$ at $N \ge N_{\text{full}}$.

### 4.2 Bayesian Prior Smoothing (Laplace / Beta-Binomial)

To prevent volatility when sample sizes are modest ($3 \le N < 10$), the success rate is smoothed using a neutral prior ($\alpha=2, \beta=2$):

$$\hat{p} = \frac{k + \alpha}{N + \alpha + \beta} = \frac{k + 2}{N + 4}$$

This guarantees that:
- 3 successes out of 3 attempts results in $\hat{p} = \frac{5}{7} \approx 0.714$, rather than $1.0$.
- 0 successes out of 3 attempts results in $\hat{p} = \frac{2}{7} \approx 0.286$, rather than $0.0$.

### 4.3 Historical Signal Formula

The historical signal combines the Bayesian smoothed success component with operational penalties and empirical verification bonuses:

$$\text{success\_component} = (\hat{p} - 0.70) \times 0.15 \times w_{\text{evidence}}$$
$$\text{reassign\_penalty} = \text{reassignment\_rate} \times 0.03$$
$$\text{verif\_bonus} = (\text{verification\_success\_rate} - 0.70) \times 0.03 \quad (\text{if } N_{\text{verif}} > 0)$$

$$\text{raw\_signal} = \text{success\_component} - \text{reassign\_penalty} + \text{verif\_bonus}$$
$$S_{\text{hist}} = \text{clamp}\left(\text{raw\_signal}, -0.08, +0.08\right)$$

Where:
$$w_{\text{evidence}} = \min\left(1.0, \frac{N}{N_{\text{full}}}\right)$$ with $N_{\text{full}} = 10$.

### 4.4 Mathematical Invariance Proof

The total candidate score formula is:
$$\text{Total Score} = w_{\text{cap}} S_{\text{cap}} + w_{\text{type}} S_{\text{type}} + w_{\text{role}} S_{\text{role}} + w_{\text{tool}} S_{\text{tool}} + w_{\text{workload}} S_{\text{workload}} + S_{\text{hist}}$$

Since $|S_{\text{hist}}| \le 0.08$ and capability weight $w_{\text{cap}} = 0.35$:
- A candidate lacking a required capability incurs a penalty $\ge 0.35$.
- The maximum positive historical boost is $+0.08$.
- Therefore, $0.08 < 0.35$, mathematically guaranteeing that historical learning **can never elevate an incapable candidate over a capable one**.

---

## 5. Multi-Tenant Privacy & Data Isolation

DoxaRank enforces strict multi-tenant boundaries across all learning and memory layers:

1. **Partitioned Storage**:
   Records are keyed by `project_id` in `AgentPerformanceStore.records_by_tenant[project_id]`.
2. **Strict SEO Data Sanitization**:
   Learning records store only operational execution metadata:
   - Agent identifier (`"seo_researcher"`)
   - High-level task category (`"research"`)
   - Outcome status (`success=True`)
   - Execution duration and confidence
   - Tool names invoked (`"get_search_console_performance"`)
   - Failure category and operational reason
3. **Global Anonymized Rollups**:
   Global cross-tenant rollups store zero keywords, query terms, target URLs, domain names, or client SEO evidence. This allows cold-start assistance without leaking proprietary client SEO strategies.

---

## 6. Telemetry & Lifecycle Events

Milestone 5.6 introduces 5 distinct lifecycle event types in `agent_events.py`:

| Event Type | Description | Emitted When |
|---|---|---|
| `SEO_LEARNING_RECORD_CREATED` | Emitted when a new execution outcome is recorded | Task completes, fails, or triggers fallback |
| `SEO_AGENT_PERFORMANCE_UPDATED` | Emitted when agent stats are refreshed | Learning store receives a new record |
| `SEO_HISTORICAL_SIGNAL_APPLIED` | Emitted when historical signal modifies candidate score | Candidate evaluated during `select_agent` ($N \ge 3$) |
| `SEO_HISTORICAL_SIGNAL_IGNORED` | Emitted when historical signal is bypassed | Insufficient samples ($N < 3$) or cold-start |
| `SEO_ROUTING_OUTCOME_RECORDED` | Emitted to record routing prediction vs final outcome | Task execution finishes and correlates with routing |

All events are fully integrated with the existing `AgentEventBus` and `AgentEventEmitter` infrastructure.

---

## 7. Runtime Evaluation Metrics & Calibration

In `backend/apps/seo/services/agent_evaluation.py`, `evaluate_shared_context` computes runtime-derived evaluation metrics for Milestone 5.6:

1. **`learning_coverage`**: Ratio of executed tasks that produced structured learning records.
2. **`historical_signal_usage`**: Ratio of routing decisions where historical signals were actively applied.
3. **`routing_improvement`**: Ratio of tasks where top-ranked agent succeeded on the first attempt without reassignment.
4. **`success_rate_by_agent`**: Map of empirical success rates per specialized agent.
5. **`success_rate_by_task_type`**: Map of empirical success rates per SEO task category.
6. **`verification_success_rate`**: Overall ratio of verified action successes.
7. **`reassignment_rate`**: Ratio of tasks that required fallback execution.
8. **`confidence_calibration_error`**: Expected calibration error (Brier score) between routing confidence and observed success.
9. **`cold_start_coverage`**: Ratio of evaluated agents that operated with prior historical evidence.

---

## 8. Read-Only API Endpoints

### 8.1 Agent Performance Query

* **URL**: `GET /api/seo/ai/learning/performance/`
* **Query Parameters**:
  - `agent` (optional): Filter by specialized agent name.
  - `task_type` (optional): Filter by task category (e.g., `"research"`, `"audit"`).
  - `project_id` (optional): Tenant scope.
* **Authentication**: Requires authenticated user with project permission.
* **Response**:
  ```json
  {
    "status": "success",
    "project_id": 12,
    "agent": "seo_researcher",
    "task_type": "research",
    "sample_size": 14,
    "successful_tasks": 13,
    "failed_tasks": 1,
    "success_rate": 0.929,
    "verification_success_rate": 1.0,
    "reassignment_rate": 0.0,
    "avg_duration_ms": 342.5,
    "confidence_calibration_error": 0.012,
    "routing_quality_score": 0.925,
    "has_sufficient_evidence": true
  }
  ```

### 8.2 Collaboration Learning Records Query

* **URL**: `GET /api/seo/ai/orchestrate/<run_id>/learning/`
* **Query Parameters**:
  - `project_id` (required): Tenant project ID.
* **Authentication**: Requires authenticated user with project permission.
* **Response**:
  ```json
  {
    "status": "success",
    "run_id": "corr-uuid-1234",
    "project_id": 12,
    "learning_records_count": 4,
    "learning_records": [
      {
        "agent_name": "seo_researcher",
        "task_id": "task_1",
        "task_type": "research",
        "success": true,
        "execution_duration_ms": 250.0,
        "predicted_confidence": 0.92,
        "verification_status": "none",
        "failure_category": "none"
      }
    ]
  }
  ```

---

## 9. Verification & Test Suite

The implementation is verified by 22 comprehensive deterministic tests in `apps.seo.tests.SEOAgentLearningTests`:

1. `test_01_performance_store_singleton_and_recording`: Basic recording and singleton lifecycle.
2. `test_02_deterministic_metric_calculations`: Deterministic calculation of success rate, verification rate, reassignment rate, and calibration error.
3. `test_03_historical_performance_influences_eligible_ranking`: Soft preference granted to historically high-performing eligible candidate.
4. `test_04_hard_constraints_never_overridden_by_history`: Capable candidate strictly preferred over historically strong but incapable candidate.
5. `test_05_tool_registry_and_mcp_never_bypassed_by_history`: Forbidden tools eliminate candidate despite high historical success.
6. `test_06_hitl_and_risk_boundaries_strictly_preserved`: High-risk mutating task enforces HITL requirements regardless of historical score.
7. `test_07_cold_start_handling_insufficient_samples`: Samples below threshold ($N < 3$) safely ignore historical signal.
8. `test_08_cold_start_handling_bayesian_smoothing`: Modest samples ($3 \le N < 10$) use Bayesian smoothing prior.
9. `test_09_multi_tenant_isolation_partitioned_records`: Project A records never influence Project B routing decisions.
10. `test_10_multi_tenant_anonymized_global_rollups`: Global baselines strip all private keywords, URLs, and tenant data.
11. `test_11_failure_categorization_safety_blocks_not_penalized`: Safety blocks do not reduce agent competence or routing score.
12. `test_12_failure_categorization_human_rejection_not_penalized`: Human editorial rejection is not treated as an agent failure.
13. `test_13_failure_categorization_verification_and_agent_failures`: Genuine tool and verification failures correctly penalize agent.
14. `test_15_bounded_learning_signal_limits`: Signal is strictly clamped within $[-0.08, +0.08]$.
15. `test_16_complete_runtime_learning_feedback_loop`: End-to-end feedback loop from history to selection, execution, and store update.
16. `test_17_fallback_reassignment_updates_learning`: Fallback execution accurately logs failure for initial worker and reassignment count.
17. `test_18_explainable_routing_reasons_contain_historical_signals`: Detailed routing reasons include sample size, Bayesian smoothed rate, and delta.
18. `test_19_telemetry_events_emitted`: Complete event sequence emitted through `AgentEventBus`.
19. `test_20_runtime_evaluation_metrics`: Context evaluation computes all 9 Milestone 5.6 metrics.
20. `test_21_learning_performance_api_view`: Read-only API returns accurate agent performance metrics.
21. `test_22_collaboration_learning_api_view`: Read-only API retrieves orchestration run learning records.
