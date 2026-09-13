# DoxaRank Phase 5.5 — Adaptive Agent Coordination & Dynamic Agent Selection

## 1. Why Adaptive Agent Coordination Exists

Prior to Phase 5.5, DoxaRank coordinated specialized agents across Milestones 5.1–5.4 through static task-to-agent assignments defined during initial task decomposition or static pipeline templates. While Milestone 5.4 introduced bounded parallel execution of independent DAG tasks, static agent binding suffered from key operational limits:

1. **Rigid Worker Assignment**: If a task required nuanced empirical evidence collection or diagnostic inspection, the system relied on the planner's initial hardcoded agent assignment rather than assessing the optimal worker based on real-time candidate capabilities, scope boundaries, and workloads.
2. **Workload Blindness**: Multiple parallel tasks could saturate a single specialized agent while other capable agents remained idle, with no mechanism to dynamically balance or penalize overloaded candidates.
3. **Brittle Worker Failures**: If an assigned agent experienced a transient failure or external rate limit, the task failed immediately without attempting safe, explainable reassignment to next-eligible specialized agents.
4. **Opaque Routing Logic**: Routing decisions lacked structured, auditable scoring breakdowns explaining *why* a given agent was chosen and *why* alternative candidates were rejected.

Milestone 5.5 introduces **Adaptive Agent Coordination & Dynamic Agent Selection**. The orchestration layer now evaluates every `READY` AgentTask against all registered specialized agents, applies non-negotiable hard safety constraints, computes a deterministic multi-factor fit score, breaks ties with zero randomness, and emits auditable lifecycle telemetry. If execution encounters an unexpected failure, bounded fallback reassigns the task to the next-ranked eligible candidate while strictly enforcing safety boundaries.

---

## 2. Adaptive Selection Architecture

```
TaskPlan (DAG)
      │
      ▼
READY AgentTask
      │
      ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   AdaptiveAgentSelector Engine                         │
│                                                                        │
│ 1. HARD CONSTRAINT FILTERING                                          │
│    ├── Tenant Isolation Boundary (Project A ≠ Project B)              │
│    ├── Mandatory Capability Verification                              │
│    ├── ToolRegistry Allowlist & MCP Permission Policy                  │
│    ├── Forbidden Tool Exclusions                                       │
│    ├── Task Risk Level vs Agent Max Permitted Risk                     │
│    └── HITL Governance Invariant (Mutations require requires_hitl)    │
│                                                                        │
│ 2. MULTI-FACTOR SOFT SCORING                                          │
│    ├── Capability Match Score      (Weight: 0.35)                     │
│    ├── Task Type / Domain Match    (Weight: 0.20)                     │
│    ├── Role Suitability / Baseline (Weight: 0.15)                     │
│    ├── Tool Permission Coverage    (Weight: 0.15)                     │
│    ├── Active Workload Penalty     (Weight: 0.10)                     │
│    └── Historical Performance Lift (Bounded Bonus: ≤0.05)             │
│                                                                        │
│ 3. DETERMINISTIC TIE-BREAKING                                          │
│    1. Total Score (descending)                                         │
│    2. Active Workload (ascending: lower workload preferred)           │
│    3. Capability Match Score (descending)                             │
│    4. Agent Name (lexicographical ascending: zero-randomness)          │
│                                                                        │
│ 4. CONFIDENCE ESTIMATION & EXPLAINABILITY                              │
│    └── Score margin between 1st & 2nd candidate + baseline profile     │
└────────────────────────────────────────────────────────────────────────┘
      │
      ├───► RoutingDecision (selected_agent, score, confidence, reasons)
      │
      ▼
SEOSupervisorAgent Batch Formation
      │
      ├── Active Workload Tracker Increment
      ├── ParallelExecutionBatch (Bounded by max_parallel_tasks)
      │
      ▼
Execution & Verification
      │
      ├── Success ──► Workload Decrement ──► Task COMPLETED
      │
      └── Failure ──► select_fallback() (Bounded max_attempts = 2)
                        ├── Next-ranked eligible candidate
                        ├── Re-verify all hard constraints
                        └── Emit SEO_AGENT_FALLBACK
```

---

## 3. Canonical Specialized Agent Capability Profiles

All specialized agents are registered in `CANONICAL_CAPABILITY_PROFILES` with explicit capability tags, supported scopes, tool allowlists, forbidden tools, risk tolerance, and Human-In-The-Loop requirements:

| Agent Name | Role | Primary Capabilities | Allowed Tools | Max Risk | Requires HITL |
|---|---|---|---|---|---|
| `seo_researcher` | Evidence & Research Specialist | `keyword_research`, `serp_research`, `competitor_research`, `ranking_analysis`, `search_intent_analysis`, `empirical_data_collection`, `performance_analysis`, `audit_data_collection` | GSC queries/pages/performance, keyword rankings, site audit summary, audit issues, MCP local signals | `low` | `False` |
| `seo_investigator` | Root-Cause & Diagnostic Specialist | `root_cause_analysis`, `technical_diagnosis`, `evidence_correlation`, `opportunity_investigation`, `anomaly_detection`, `diagnostic_correlation`, `technical_audit`, `cannibalization_diagnosis` | Diagnostic tools, GSC analysis, audit issues, MCP signals | `medium` | `False` |
| `seo_strategist` | Strategy & Prioritization Architect | `seo_strategy`, `prioritization`, `recommendation_generation`, `historical_learning`, `opportunity_scoring`, `strategic_planning`, `portfolio_prioritization` | GSC queries, adaptive SEO strategy, audit summary | `medium` | `False` |
| `seo_action_planner` | Action & Remediation Planner | `action_planning`, `approved_mutation_execution`, `action_synthesis`, `remediation_design`, `proposal_generation`, `code_fix_design` | `plan_seo_actions`, `propose_seo_action`, GSC performance, audit issues | `high` | `True` |
| `seo_verifier` | Verification & Outcome Lift Agent | `outcome_verification`, `post_action_validation`, `outcome_measurement`, `verification_testing` | `verify_seo_action`, `verify_action_plan`, GSC performance, MCP URL status | `medium` | `False` |

---

## 4. Multi-Factor Scoring Formula & Weights

Candidates that satisfy all hard constraints are evaluated using the following deterministic formula:

$$\text{Total Score} = w_{\text{cap}} S_{\text{cap}} + w_{\text{type}} S_{\text{type}} + w_{\text{role}} S_{\text{role}} + w_{\text{tool}} S_{\text{tool}} + w_{\text{workload}} S_{\text{workload}} + S_{\text{hist}}$$

Where:
- $w_{\text{cap}} = 0.35$: Match between candidate capabilities and task requirements.
- $w_{\text{type}} = 0.20$: Match between candidate supported task types and task objective.
- $w_{\text{role}} = 0.15$: Alignment with planned role baseline (1.0 if pre-assigned, 0.5 otherwise).
- $w_{\text{tool}} = 0.15$: Ratio of required tools permitted by candidate allowlist.
- $w_{\text{workload}} = 0.10$: $1.0 - (\text{active\_tasks} / \text{max\_concurrency})$, penalizing saturated workers.
- $S_{\text{hist}} \le 0.05$: Historical success rate bounded bonus.

### Tie-Breaking Guarantee
When multiple candidates achieve identical total scores, ties are broken deterministically with zero randomness:
1. **Total score** (descending)
2. **Current active workload** (ascending: least loaded agent preferred)
3. **Capability match score** (descending)
4. **Agent name** (ascending lexicographical)

---

## 5. Non-Negotiable Safety Boundaries

1. **Human-in-the-Loop (HITL) Invariant**: Dynamic agent selection **cannot authorize mutations**. If a task attempts or plans mutations (`is_mutating=True`), candidates without `requires_hitl=True` are eliminated immediately with `hitl_governance_required`. All synthesized proposals remain strictly in `PROPOSED` or `PENDING_APPROVAL` status until a verified human explicitly approves them.
2. **ToolRegistry & MCP Boundaries**: No agent can be selected for a task requiring tools outside its explicit allowlist. Agent selection cannot grant runtime permissions or bypass MCP policies.
3. **Tenant Isolation**: Tasks are strictly isolated by `project_id`. An agent evaluating a task for Project A cannot access, query, or project memory from Project B. Cross-tenant mismatch immediately triggers rejection (`tenant_isolation`).
4. **Bounded Safe Fallback**: If an assigned worker reports a failure, fallback reassignment is strictly bounded by `max_fallback_attempts = 2`. The failing agent is marked exhausted for that task. If no alternative eligible candidate exists, the task fails cleanly, cascading `BLOCKED` status to downstream dependents.

---

## 6. Telemetry & Observability Events

Milestone 5.5 introduces six structured, sanitized agent coordination events:

| Event Type | Purpose | Emitted Payload Fields |
|---|---|---|
| `seo.agent.selection.started` | Initiates agent candidate evaluation | `task_id`, `objective`, `candidates_count`, `candidates`, `project_id`, `correlation_id` |
| `seo.agent.candidate.evaluated` | Evaluates single candidate score | `task_id`, `agent`, `score`, `breakdown`, `project_id`, `correlation_id` |
| `seo.agent.candidate.rejected` | Records candidate elimination | `task_id`, `agent`, `reason`, `hard_constraint`, `project_id`, `correlation_id` |
| `seo.agent.selected` | Records final selection decision | `task_id`, `selected_agent`, `score`, `confidence`, `reasons`, `is_low_confidence` |
| `seo.agent.fallback` | Records failure fallback reassignment | `task_id`, `failed_agent`, `fallback_agent`, `attempt`, `max_attempts`, `failure_reason` |
| `seo.agent.selection.failed` | Records unresolvable selection failure | `task_id`, `reason`, `rejected_candidates`, `project_id`, `correlation_id` |

*Security Invariant*: All telemetry payloads pass through `sanitize_event_payload` to ensure API keys, bearer tokens, and credentials are scrubbed prior to publication.

---

## 7. Runtime Evaluation Metrics

The `SEOAgentEvaluationService` computes runtime-derived metrics reflecting adaptive selection health:
- `routing_decisions`: Total dynamic selection decisions made.
- `successful_selections`: Decisions resolving to an eligible candidate.
- `selection_confidence`: Mean confidence across all routing decisions.
- `average_candidate_count`: Mean evaluated candidates per task.
- `capability_match_rate`: Percentage of decisions with direct capability overlap.
- `fallback_rate`: Proportion of tasks requiring fallback reassignment.
- `task_completion_by_selected_agent`: Breakdown of completed tasks per selected agent.

---

## 8. Test Suite & Verification Summary

The Milestone 5.5 test suite (`apps.seo.tests.SEOAdaptiveAgentCoordinationTests`) covers 18 focused test cases:

1. `test_01_best_capability_match_selected`: Best capability profile match selected.
2. `test_02_hard_constraint_rejects_ineligible_candidate`: Ineligible candidate eliminated by hard constraint.
3. `test_03_tool_permission_mismatch_eliminates_candidate`: Missing tool authorization eliminates candidate.
4. `test_04_hitl_requirement_cannot_be_bypassed`: Selection $\neq$ mutation authorization; strict HITL gate enforced.
5. `test_05_workload_affects_ranking_when_capabilities_otherwise_comparable`: Workload factor shifts ranking when capability scores tie.
6. `test_06_deterministic_tie_breaking`: Deterministic ranking with zero randomness across 20 iterations.
7. `test_07_routing_decision_contains_explainable_reasons`: Explainable reasons and rejected candidate breakdowns.
8. `test_08_low_confidence_routing_triggers_safe_behavior`: Low-confidence routing flags review requirements.
9. `test_09_failed_selected_agent_safely_falls_back_to_next_eligible`: Safe fallback reassignment on worker failure.
10. `test_10_fallback_is_bounded_and_cannot_loop_indefinitely`: Bounded fallback halts at `max_attempts`.
11. `test_11_same_agent_can_execute_multiple_independent_parallel_tasks`: Parallel execution of same agent across tasks.
12. `test_12_adaptive_routing_preserves_dag_dependencies`: Dependency satisfaction preserved across dynamic routing.
13. `test_13_parallel_execution_works_after_dynamic_agent_assignment`: Dynamically selected agents execute in parallel batches.
14. `test_14_shared_memory_context_remains_tenant_isolated`: Cross-tenant tasks rejected by hard constraint.
15. `test_15_routing_telemetry_emitted_correctly`: Structured telemetry events emitted and validated.
16. `test_16_routing_evaluation_metrics_derived_from_runtime_state`: Runtime-derived routing metrics validated.
17. `test_17_no_secrets_appear_in_routing_telemetry`: Tokens and passwords scrubbed from routing events.
18. `test_18_full_realistic_doxarank_scenario`: End-to-end 7-stage workflow dynamically routed across specialized agents.

**Regression Results Across Milestones 5.1–5.5:**
- `SEOAdaptiveAgentCoordinationTests` (Milestone 5.5): 18 / 18 passed (100%)
- `SEOParallelAgentExecutionTests` (Milestone 5.4): 11 / 11 passed (100%)
- `SEODynamicTaskPlanningTests` (Milestone 5.3): 23 / 23 passed (100%)
- `SEOSharedWorkingMemoryTests` (Milestone 5.2): 16 / 16 passed (100%)
- `SEOAgentOrchestrationTests` (Milestone 5.1): 7 / 7 passed (100%)
- **Total:** 75 / 75 multi-agent orchestrator tests passing 100%.
