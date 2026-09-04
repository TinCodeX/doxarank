# DoxaRank Phase 5.3 — Dynamic Task Decomposition & Collaborative Planning

## 1. Why Dynamic Task Planning Exists

Prior to Phase 5.3, DoxaRank orchestrated specialized multi-agent workflows using predefined, hardcoded linear execution pipelines (e.g., `research -> investigation -> strategy -> action_planning`). While robust for standard exploratory workflows, static pipelines exhibit three critical architectural limitations:

1. **Inflexibility to Specific Intent**: A user requesting a technical verification check or an immediate ranking diagnosis was forced through unnecessary preliminary research stages, or required manual supervisor pipeline overrides.
2. **Fragility in the Face of Failure & Blockers**: If an upstream agent failed (e.g., Google Search Console credentials expired), static pipelines either halted the entire run or blindly executed downstream agents that lacked required dependencies.
3. **Inability to Adapt to Emerging Evidence & Conflicts**: When an agent uncovered contradictory evidence or unexpected diagnostic anomalies, static pipelines had no mechanism to dynamically insert diagnostic branches, reprioritize downstream tasks, or adaptively replan without restarting the entire collaboration from scratch.

Phase 5.3 introduces **Dynamic Task Decomposition & Collaborative Planning**. Instead of rigid pipelines, the supervisor parses user goals into a **Directed Acyclic Graph (DAG)** of typed `AgentTask` nodes with explicit dependency relationships. The system dynamically validates the graph for cycles using Kahn's algorithm, evaluates ready tasks, executes agents, cascades failure to downstream tasks as `BLOCKED`, and dynamically replans when conflicts or new evidence emerge—all while strictly enforcing human approval boundaries, tool permission non-escalation, and deterministic planning budgets.

---

## 2. Dynamic Task Planning Architecture

```
                    ┌────────────────────────────────────────────────────────┐
                    │                      User Goal                         │
                    │ ("Diagnose CTR drop and propose title tag fixes")     │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                                                ▼
                    ┌────────────────────────────────────────────────────────┐
                    │               Dynamic Task Planner                     │
                    │  - Decomposes goal into typed AgentTasks               │
                    │  - Infers dependencies & required evidence             │
                    │  - Assigns responsible specialized agents              │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                                                ▼
                    ┌────────────────────────────────────────────────────────┐
                    │                 TaskPlan DAG Engine                    │
                    │  - Kahn's Algorithm Cycle Validation                   │
                    │  - Topological Sort & Dependency Tracking              │
                    │  - Parallel Group Tier Computation                     │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                 ┌──────────────────────────────┴─────────────────────────────┐
                 │                                                            │
                 ▼                                                            ▼
    [Parallel Tier 0: Ready Tasks]                               [Parallel Tier 1: Dependent Tasks]
    ┌───────────────────────────┐                                ┌───────────────────────────┐
    │ Task 1: Research Agent    │                                │ Task 2: Investigator      │
    │ (GSC Performance Data)    │                                │ (Root Cause Analysis)     │
    └─────────────┬─────────────┘                                └─────────────┬─────────────┘
                  │                                                            │
                  ▼ (Task Completed)                                           ▼ (Task Completed)
    [Resolve Downstream Dependencies] ──────────────────────────► [Transition Dependent to READY]
                  │
                  ▼
    ┌───────────────────────────┐
    │ Task 3: Strategist Agent  │
    │ (Intervention Hypotheses) │
    └─────────────┬─────────────┘
                  │
                  ▼
    ┌───────────────────────────┐
    │ Task 4: Action Planner    │ ───► [Human Approval Boundary: requires_approval=True]
    │ (Draft SEOAction Proposals│
    └───────────────────────────┘
```

---

## 3. AgentTask Lifecycle & Validated State Transitions

Every unit of work in the collaboration is encapsulated in an `AgentTask` dataclass governed by strict state machine transitions:

```
                  ┌───────────────┐
                  │    PENDING    │
                  └───────┬───────┘
                          │ (Dependencies Satisfied)
                          ▼
                  ┌───────────────┐
                  │     READY     │
                  └───────┬───────┘
                          │ (Agent Assigned & Started)
                          ▼
                  ┌───────────────┐
                  │    RUNNING    │
                  └───────┬───────┘
                          │
          ┌───────────────┼───────────────┐
          │ (Success)     │ (Error/Fail)  │ (Cancelled/Skipped)
          ▼               ▼               ▼
   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
   │  COMPLETED  │ │   FAILED    │ │   SKIPPED   │
   └──────┬──────┘ └──────┬──────┘ └─────────────┘
          │               │ (Cascades downstream)
          ▼               ▼
   [Unblocks Ready ┌─────────────┐
     Dependencies] │   BLOCKED   │
                   └─────────────┘
```

### Valid Transition Matrix

| Current Status | Allowed Next Statuses | Enforcing Logic |
| :--- | :--- | :--- |
| `PENDING` | `READY`, `SKIPPED`, `CANCELLED` | Transition to `READY` only when all prerequisite `dependencies` have reached `COMPLETED`. |
| `READY` | `RUNNING`, `SKIPPED`, `CANCELLED`, `BLOCKED` | Supervisor marks `RUNNING` upon launching agent execution. |
| `RUNNING` | `COMPLETED`, `FAILED`, `BLOCKED`, `CANCELLED` | Success updates `result_summary`; failure records `error` and triggers downstream cascading. |
| `BLOCKED` | `READY`, `SKIPPED`, `CANCELLED` | Can only return to `READY` if an adaptive replan substitutes the prerequisite dependency. |
| `FAILED` | `PENDING`, `READY`, `CANCELLED` | Retriable only under explicit supervisor replanning rounds. |
| `COMPLETED` | *(Terminal)* | Immutable once finished; guarantees idempotency of downstream executions. |
| `SKIPPED` | *(Terminal)* | Bypassed task; does not satisfy dependencies of downstream tasks. |
| `CANCELLED`| *(Terminal)* | Aborted execution. |

---

## 4. Intent-Driven Dynamic Goal Decomposition

The `DynamicTaskPlanner` evaluates user goals using keyword, pattern, and intent classification to construct minimal, focused DAGs:

1. **Investigation / Traffic Drop Intent** (`drop`, `decline`, `investigate`, `anomaly`, `traffic`):
   - `Task 1`: Research Agent — Collect 28-day vs previous period GSC queries, impressions, and CTR anomalies.
   - `Task 2` *(Depends on 1)*: Investigator Agent — Diagnostic causal analysis isolating query and page degradation.
   - `Task 3` *(Depends on 2)*: Strategist Agent — Synthesize recovery recommendations.
   - `Task 4` *(Depends on 3)*: Action Planner Agent — Draft actionable `SEOAction` proposals (`requires_approval=True`).

2. **Verification & Audit Intent** (`verify`, `audit`, `inspect`, `check`, `technical`):
   - `Task 1`: Research Agent — Collect site audit diagnostic issues and crawl warnings.
   - `Task 2` *(Depends on 1)*: Investigator Agent — Identify root-cause technical defects (broken links, missing tags).
   - `Task 3` *(Depends on 2)*: Action Planner Agent — Draft technical remediation action items.

3. **Strategy & Keyword Opportunities** (`opportunity`, `page 2`, `keyword`, `content`):
   - `Task 1`: Research Agent — Extract high-impression, low-CTR Page 2 queries.
   - `Task 2` *(Depends on 1)*: Strategist Agent — Formulate content expansion and metadata refresh tactics.
   - `Task 3` *(Depends on 2)*: Action Planner Agent — Propose concrete title and meta description drafts.

4. **Action Planning Direct** (`action`, `plan`, `propose`, `draft`):
   - `Task 1`: Investigator Agent — Validate targeting criteria and page metadata.
   - `Task 2` *(Depends on 1)*: Action Planner Agent — Structure validated action proposals.

5. **General / Full-Cycle Fallback**:
   - Decomposes into complete phased collaboration (`research -> investigate -> strategy -> action_planning`).

---

## 5. DAG Cycle Detection & Parallel Grouping

### Kahn's Algorithm Cycle Detection
Before any task plan is registered or executed, `TaskPlan.validate_graph()` executes Kahn's algorithm for topological sorting:
- Calculates in-degrees (number of prerequisite dependencies) for all tasks.
- If the count of visited nodes does not equal the total number of tasks, a circular dependency exists.
- Any cycle immediately raises `CircularDependencyError`, preventing deadlocks and halting invalid workflows before execution.

### Dependency Depth Limits
To prevent runaway nested dependency chains, `TaskPlan.validate_graph()` calculates the longest directed path in the DAG. If `max_depth > budget.max_dependency_depth` (default: 8), a `PlanLimitExceededError` is raised.

### Parallel Group Tiers
`TaskPlan.get_parallel_groups()` partitions tasks into independent execution tiers:
- **Tier 0**: Tasks with zero prerequisite dependencies (immediately runnable).
- **Tier 1**: Tasks whose dependencies reside entirely in Tier 0.
- **Tier K**: Tasks dependent on Tier K-1.
This enables parallelizable modeling, topological visualization, and clear UI progress indication.

---

## 6. Adaptive Replanning Engine & Failure Cascading

### Adaptive Replanning Triggers
Replanning is triggered deterministically by:
- `ReplanReason.TASK_FAILURE`: An agent execution encounters an unrecoverable tool error or exception.
- `ReplanReason.CONFLICT_DETECTED`: Shared Working Memory detects contradictory claims between agents.
- `ReplanReason.NEW_EVIDENCE`: Newly discovered diagnostic anomalies invalidate current strategy tasks.
- `ReplanReason.VERIFICATION_FAILURE`: Verification measurements fail post-action execution.

### Cascading Failure Propagation
When a task fails, `TaskPlan.handle_task_failure(failed_task_id)` executes a Breadth-First Search (BFS) traversal across all downstream dependent tasks and transitions them to `BLOCKED`. This guarantees:
- No downstream agent executes on missing, corrupted, or invalid prerequisites.
- Blocked tasks emit `SEO_TASK_BLOCKED` telemetry events for dashboard visibility.

### Deterministic Replanning Budgets
To prevent infinite replanning loops, `PlanBudgetConfig` enforces strict invariant boundaries:
- `max_tasks_per_plan = 20`
- `max_planning_rounds = 3`
- `max_replans = 2`
- `max_dependency_depth = 8`

When budget limits are reached, the planner refuses new tasks, logs `SEO_TASK_PLAN_LIMIT_REACHED`, and forces completion with current partial evidence.

---

## 7. Safety Invariants & Hard Boundaries

| Safety Invariant | Mechanism | Enforcement Level |
| :--- | :--- | :--- |
| **Zero Autonomous Mutations** | Action Planner tasks generate `SEOAction` records strictly with `requires_human_approval = True` and status `PROPOSED`. | Absolute hard gate. No autonomous database or live CMS mutations. |
| **Tool Permission Non-Escalation** | The planner cannot dynamically grant or modify tool permissions. `ToolRegistry` and static agent tool allowlists remain authoritative. | Authoritative allowlist verification per agent. |
| **Multi-Tenant Isolation** | All task plans enforce `project_id` matching. API endpoints check `Project.objects.filter(id=plan.project_id, owner=request.user)`. Cross-tenant attempts return `HTTP 403 Forbidden`. | Enforced at DB and API boundary. |
| **Secret Redaction** | Any task objective, description, or metadata ingesting credentials, Bearer tokens, or API keys is scrubbed via regex redaction prior to storage. | Enforced in `AgentTask.__post_init__`. |
| **Cycle & Depth Prevention** | Kahn's algorithm validates DAG before execution; cycles raise `CircularDependencyError`. | Enforced in `TaskPlan.validate_graph()`. |

---

## 8. Telemetry & Event System (Phase 5.3)

Phase 5.3 adds 11 structured lifecycle events to `AgentEventType`:

| Event Type | Description | Key Payload Attributes |
| :--- | :--- | :--- |
| `agent.task.plan.created` | New DAG task plan decomposed from goal. | `project_id`, `correlation_id`, `goal`, `total_tasks`, `planning_rounds` |
| `agent.task.created` | Individual task node registered in plan. | `task_id`, `objective`, `responsible_agent`, `priority`, `dependencies` |
| `agent.task.ready` | Task dependencies satisfied; ready to run. | `task_id`, `responsible_agent`, `dependencies` |
| `agent.task.started` | Agent assigned and execution initiated. | `task_id`, `responsible_agent` |
| `agent.task.completed` | Agent successfully completed task objective. | `task_id`, `responsible_agent`, `result_summary` |
| `agent.task.failed` | Agent failed during task execution. | `task_id`, `responsible_agent`, `error` |
| `agent.task.blocked` | Downstream task blocked due to dependency failure. | `task_id`, `blocked_by`, `reason` |
| `agent.task.replanned` | Adaptive replanning round executed. | `replan_count`, `reason`, `tasks_added`, `tasks_modified` |
| `agent.task.cancelled` | Task cancelled by supervisor or user. | `task_id`, `reason` |
| `agent.task.dependency_resolved` | Prerequisite task finished, unblocking dependency. | `task_id`, `resolved_dependency` |
| `agent.task.limit_reached` | Planning budget limit reached (max replans/tasks). | `correlation_id`, `limit_type`, `current_count`, `max_limit` |

---

## 9. Evaluation Metrics (Phase 5.3)

`SEOAgentEvaluationService.evaluate_shared_context()` computes 12 observable dimensions for task planning:

1. `tasks_created`: Total number of tasks generated in the plan.
2. `tasks_completed`: Total number of tasks successfully finished.
3. `tasks_failed`: Total number of tasks that failed.
4. `tasks_blocked`: Total number of tasks blocked by upstream failures.
5. `tasks_replanned`: Total count of replanning cycles executed.
6. `planning_rounds`: Total planning iterations.
7. `average_tasks_per_plan`: `tasks_created / planning_rounds`.
8. `dependency_resolution_rate`: Percentage of planned tasks whose dependencies completed.
9. `circular_dependencies_detected`: Verified 0 in valid runs.
10. `task_completion_efficiency`: Percentage of planned tasks completed.
11. `replan_efficiency`: Inverse penalty score based on replan counts.
12. `planning_safety_compliance`: 100.0% adherence to human approval and budget boundaries.

---

## 10. Dashboard UI Integration & API Endpoints

### API Endpoints

- `GET /api/seo/ai/orchestrate/<run_id>/tasks/`: Returns complete structured `TaskPlan` dictionary with all tasks, statuses, dependencies, and metadata.
- `GET /api/seo/ai/orchestrate/<run_id>/tasks/summary/`: Returns compact metrics summary (`total_tasks`, `completed_tasks`, `blocked_tasks`, `completion_rate`, `planning_rounds`, `parallel_groups_count`).
- `GET /api/seo/ai/orchestrate/<run_id>/tasks/graph/`: Returns visualization DAG format with `nodes` (id, label, agent, status, priority, parallel_tier) and `edges` (from, to).

### Dashboard Card (`AgentOrchestratorPanel.tsx`)

The dashboard features a dedicated **Dynamic Task Plan & Decomposition (Phase 5.3)** card displaying:
- Real-time planning round and replan counters.
- Completion rate percentage badge.
- 6-metric summary grid (Total, Ready/Running, Completed, Blocked, Failed, Parallel Tiers).
- Topological task execution timeline with agent attribution, priority indicators, dependency lists, and live status badges (`COMPLETED`, `RUNNING`, `BLOCKED`, `FAILED`).
