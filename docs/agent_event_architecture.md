# DoxaRank — Real-Time Agent Event Architecture (Milestone 3, Phase 3.1 - 3.4)

This document outlines the transport-independent event contract, lifecycle events, publisher abstraction, sequence ordering, payload security, WebSocket client layer, event resilience and replay recovery mechanisms, and the architectural relationship between the database source-of-truth and the real-time event stream in DoxaRank.

---

## 1. Architectural Purpose & Separation of Concerns

```text
PostgreSQL AgentRun / AgentStep State  ===>  Authoritative Source of Truth (Persistence & Integrity)
AgentEvents Notification Stream        ===>  Real-Time Ephemeral Streaming & Observability
Replay & Recovery REST Layer           ===>  Deterministic Gap Recovery & Reconnection Resilience
```

The real-time event layer provides decoupled, transport-independent structured events emitted at deterministic lifecycle boundaries throughout an autonomous agent run.

### Design Principles:
1. **Transport Independence**: The core agent orchestrator and event definitions do not depend directly on Redis, WebSockets, Django Channels, React, or Celery.
2. **Authoritative Persistence**: PostgreSQL `AgentRun`, `AgentStep`, and `AgentToolCall` models remain the authoritative source of truth.
3. **Observability Resilience**: Event publication errors are treated as non-fatal observability warnings; transport failures never abort or corrupt an active SEO agent execution.
4. **Zero Token / Secret Leakage**: Strict sanitization guarantees that OpenAI/Anthropic API keys, Bearer tokens, passwords, and private provider credentials are never placed in event payloads.
5. **No Private Hidden Reasoning**: Event payloads contain concise, user-facing summary information and action rationale, preventing exposure of internal chain-of-thought tokens.
6. **Read-Only Real-Time Transport**: The WebSocket and Replay channels are strictly notification/read streams. All state mutations and human approvals occur via authenticated REST APIs.

---

## 2. End-to-End Real-Time Event & Replay Flow

### Normal Execution Stream
```text
               React Dashboard (AgentOrchestratorPanel)
                                  │
                                  ▼
                            useAgentEvents
                                  │
                                  ▼
                         AgentEventClient (WS)
                                  │
               (ws://.../ws/seo/ai/agent/runs/{run_id}/?token=...)
                                  ▼
                         AgentEventConsumer
                     (Django Channels ASGI Layer)
                                  │
                                  ▼
                         Redis Pub/Sub Layer
                   (channel `agent:run:{run_id}`)
                                  ▲
                                  │
                         RedisEventPublisher
                                  ▲
                                  │
                          AgentOrchestrator
                                  │
                                  ▼
                   PostgreSQL State (Authoritative)
```

### Disconnection & Gap Recovery Stream (Phase 3.4)
```text
React Dashboard (Disconnect Detected / Seq Gap Detected)
                      │
                      ▼
            useAgentEvents Hook
                      │
             (highestSequence = N)
                      │
                      ▼
GET /api/seo/ai/agent/runs/{run_id}/events/?after_sequence=N
                      │
                      ▼
               AgentRunViewSet
            (Tenant Authorization)
                      │
                      ▼
         get_agent_run_events(run, N)
                      │
            [ Missing Events N+1..M ]
                      │
                      ▼
            useAgentEvents Merge
          (Deduplicate via event_id
           + Sort by sequence_number)
                      │
                      ▼
            Resume Live WS Stream
```

---

## 3. Strongly-Typed Event System

All events use the `AgentEventType` enum defined in `apps.seo.services.agent_events.py` (and mirrored in `dashboard/src/types/agentEvent.ts`):

| Event Type | Category | Emitted When |
|---|---|---|
| `agent.started` | Agent Session | `AgentOrchestrator.start_run()` creates the run session and begins execution. |
| `agent.completed` | Agent Session | The agent reaches a successful terminal state (`finish` action). |
| `agent.failed` | Agent Session | The agent fails due to max step bounding, repetitive loops, or fatal errors. |
| `agent.cancelled` | Agent Session | The agent run is cancelled by the human user during approval review. |
| `step.started` | Reasoning Step | An iterative reasoning or tool step begins execution. |
| `step.completed` | Reasoning Step | A reasoning or tool step concludes successfully. |
| `step.failed` | Reasoning Step | A reasoning or tool step fails or encounters a tool error. |
| `tool.started` | Tool Execution | A registered tool in `ToolRegistry` begins execution. |
| `tool.completed` | Tool Execution | A registered tool completes successfully. |
| `tool.failed` | Tool Execution | A registered tool fails or throws an exception. |
| `approval.required` | Human Approval | Agent proposes a high-impact `SEOAction` and pauses in `waiting_for_approval`. |
| `approval.approved` | Human Approval | Human user approves the proposed action; action is safely executed. |
| `approval.rejected` | Human Approval | Human user rejects the proposed action; run is cancelled. |
| `seo.action.plan.created` | Action Planning | Autonomous planner synthesizes multi-source evidence into a structured `SEOActionPlan`. |
| `seo.action.approval.requested` | Action Planning | Structured `SEOActionPlan` requests human review and approval before mutation execution. |
| `seo.action.verification.started` | Verification | Empirical real-world verifier begins probing target live website URL/HTML state. |
| `seo.action.verification.completed` | Verification | Real-world verification confirms that target HTML/metadata reflects proposed changes. |
| `seo.action.verification.failed` | Verification | Real-world verification detects discrepancies, status errors, or missing metadata. |
| `seo.outcome.measurement.started` | Outcome Learning | Empirical measurement worker begins collecting pre- vs. post-execution GSC performance metrics. |
| `seo.outcome.evidence.collected` | Outcome Learning | Search performance evidence and metric deltas (CTR, impressions, position) collected. |
| `seo.outcome.classified` | Outcome Learning | Deterministic classification engine categorizes outcome (`improved`, `no_change`, `declined`, etc.). |
| `seo.learning.signal.generated` | Outcome Learning | Aggregated historical win/loss signals updated for future agent planning and confidence scoring. |
| `seo.outcome.completed` | Outcome Learning | Full outcome measurement lifecycle completes and updates the database record. |


---

## 4. AgentEvent Contract & Schema

Every event implements the `AgentEvent` data structure:

```json
{
  "event_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "event_type": "tool.completed",
  "run_id": 42,
  "project_id": 7,
  "step_number": 3,
  "sequence_number": 4,
  "timestamp": "2026-08-29T10:00:00.000000+00:00",
  "payload": {
    "tool_name": "get_keyword_rankings",
    "duration_ms": 1240,
    "success": true
  }
}
```

### Field Definitions:
- **`event_id`** (`str`): Server-side generated UUID4 string. Clients cannot supply or override this identifier.
- **`event_type`** (`str`): Stable event name from `AgentEventType`.
- **`run_id`** (`int`): Integer ID of the parent `AgentRun`.
- **`project_id`** (`int`): Integer ID of the scoped `Project` (enforces multi-tenant isolation).
- **`step_number`** (`Optional[int]`): 1-indexed step number within the run session (or `None` for top-level events).
- **`sequence_number`** (`int`): Monotonically increasing sequence number scoped to the `AgentRun`.
- **`timestamp`** (`str`): ISO-8601 UTC timestamp string.
- **`payload`** (`Dict[str, Any]`): Sanitized dictionary containing concise, user-facing summary information.

---

## 5. Sequence Ordering & Deduplication Strategy

1. **Monotonic Sequence Ordering**: Ordering is determined **exclusively** by the integer `sequence_number` per `AgentRun` (1, 2, 3, 4...).
2. **Timestamps as Metadata**: Timestamps provide chronological context for humans and logging, but must not be used for ordering.
3. **Frontend De-duplication (`event_id`)**: The React client uses `seenEventIdsRef` to reject duplicates and sorts incoming events strictly by `sequence_number` ascending.
4. **Race Condition Immunity**: When replay responses arrive while live WebSocket events are in-flight, `seenEventIdsRef` ensures that late-arriving duplicates are dropped seamlessly.
5. **Resumption Continuity**:
   - When an `AgentRun` pauses on `approval.required` (e.g. at sequence #6), the last sequence number is tracked in `run.context_snapshot['_event_seq']`.
   - When resumed in a subsequent process, the orchestrator initializes from `_event_seq` and emits `approval.approved` as sequence #7.
   - Resumed runs **never** reset sequence numbers to 1 and **never** re-emit `agent.started`.

---

## 6. Event Resilience & Replay (Phase 3.4)

### Replay API Endpoint
`GET /api/seo/ai/agent/runs/{run_id}/events/?after_sequence=N`

- **Multi-Tenant Isolation**: Verified strictly via `run.project.owner == request.user`. Cross-user access returns HTTP 404 without leaking run metadata.
- **Cursor Filtering**:
  - `?after_sequence=0`: Returns all events from start of run.
  - `?after_sequence=N`: Returns strictly events where `sequence_number > N`.
  - `?after_sequence=latest`: Returns empty list `[]`.
- **Deterministic Reconstruction**: If `_event_history` is not present in `run.context_snapshot`, events are deterministically reconstructed from PostgreSQL `AgentRun`, `AgentStep`, `AgentToolCall`, and `SEOAction` records.

### Gap Detection & Reconnection
- `useAgentEvents` continuously monitors sequence numbers.
- If an incoming live event has `sequence_number > highestSeenSequence + 1`, a sequence gap is detected and replay recovery is automatically triggered.
- Upon WebSocket reconnection, the client automatically requests `fetchReplayEvents(runId, highestSeenSequence)` and seamlessly merges missing events.

### Fallback Transport Hierarchy
```text
WebSocket (Primary Real-Time Transport)
      ↓
Event Replay (Gap Recovery Mechanism)
      ↓
REST Polling (Fallback when WebSocket Offline)
```

---

## 7. Security & Sanitization Rules

1. **Automatic Credential Masking**:
   - API keys matching `sk-[a-zA-Z0-9_-]{8,}` are masked as `sk-***`.
   - Bearer tokens matching `Bearer\s+[a-zA-Z0-9_\-\.]{8,}` are masked as `Bearer ***`.
   - Password / secret patterns (`password=...`, `api_key=...`, `token=...`) are stripped.
   - Dictionary keys matching `password`, `secret`, `token`, `auth_token`, `api_key` are replaced with `***REDACTED***`.
2. **Hidden Reasoning Protection**:
   - Internal chain-of-thought prompts and intermediate LLM scratchpad states are never included in event payloads.
   - Only user-facing status messages, tool names, durations, and high-level rationales are propagated.
3. **No Credential Exposure**:
   - Client-side WebSocket logging avoids logging raw URLs containing JWT tokens.
   - All authorization checks remain strictly server-side (`run.project.owner_id == user.id`).

---

## 8. Milestone Roadmap

- **Phase 3.1 (Completed)**: Transport-Independent Event Contract & Lifecycle Definitions.
- **Phase 3.2.1 (Completed)**: `RedisEventPublisher` implementing Pub/Sub on `agent:run:{run_id}`.
- **Phase 3.2.2 (Completed)**: Django Channels ASGI setup, channel layers, and `AgentEventConsumer` WebSocket consumer.
- **Phase 3.3 (Completed)**: Frontend Real-Time Agent Event Client (`AgentEventClient`, `useAgentEvents`, `AgentOrchestratorPanel` integration, fallback polling, connection indicator).
- **Phase 3.4 (Completed)**: Real-Time Event Resilience & Replay (Replay API endpoint, cursor filtering, gap detection, reconnect recovery, enhanced telemetry visualization).
- **Phase 4.2.3.1 (Completed)**: Live Website Audit Agent Tools & Intelligence Foundation (`trigger_site_audit`, `get_site_audit_summary`, `get_audit_issues`, ReAct agent integration).

---

## 9. Live Website Audit Agent Tools & Intelligence Foundation (Phase 4.2.3.1)

Phase 4.2.3.1 connects the deterministic `LiveSiteCrawlerService` and `SEOAuditEngine` with the `AgentOrchestrator` ReAct loop via safe, provider-neutral tools in `ToolRegistry`.

### Architecture Flow:
```text
                    ┌───────────────────────────┐
                    │        ReAct Agent        │
                    │   (AgentOrchestrator)     │
                    └─────────────┬─────────────┘
                                  │
                            Tool Registry
                                  │
           ┌──────────────────────┼──────────────────────┐
           ↓                      ↓                      ↓
  trigger_site_audit    get_site_audit_summary    get_audit_issues
  (Async Celery Task)   (Compact Findings)        (Filtered Findings)
           │                      │                      │
           ↓                      └──────────┬───────────┘
      Celery Task                            │
  (run_site_audit.delay)                     │
           │                                 │
           ↓                                 │
  LiveSiteCrawlerService                     │
           │                                 │
           ↓                                 │
     CrawlResult                             │
           │                                 │
           ↓                                 │
     SEOAuditEngine ─────────────────────────┘
           │
           ↓
    SiteAudit / AuditIssue (PostgreSQL)
```

### Agent-Callable Audit Tools:

| Tool Name | Category | Mutating | Requires Approval | Purpose |
|---|---|---|---|---|
| `trigger_site_audit` | `SAFE_INTERNAL` | Yes (creates pending audit) | No | Dispatches asynchronous Celery live website crawl and audit task. Validates `start_url` against project domain and bounds `max_pages` (1..200) and `max_depth` (0..10). |
| `get_site_audit_summary` | `READ_ONLY` | No | No | Retrieves compact summary of latest or specified site audit: health score (0..100), issue counts by severity (`critical`, `warning`, `notice`), and top issue groups. Optimized for LLM observations. |
| `get_audit_issues` | `READ_ONLY` | No | No | Retrieves detailed technical SEO issues with optional filtering by `audit_id`, `severity` (`critical`/`warning`/`notice`), `issue_type`, and `page_url`. |

### Multi-Tenant Security & Isolation:
- Server-side authorization guarantees that the agent can **only** trigger or inspect audits belonging to the authenticated project (`project.owner == request.user`).
- Never trusts client-supplied `user_id` or `owner_id`.
- Zero credentials or tokens exposed in tool outputs.

---

## 10. Live SEO Intelligence: GSC + Website Audit Correlation (Phase 4.2.3.2)

Phase 4.2.3.2 introduces cross-source deterministic correlation between Google Search Console performance data and live technical website audit diagnostics.

```
+-----------------------------------------------------------------------------------+
|                        CROSS-SOURCE CORRELATION PIPELINE                          |
|                                                                                   |
|  Google Search Console Data                 Live Site Audit & Diagnostics         |
|  (impressions, clicks, CTR, pos)            (missing H1, broken links, canonical) |
|               │                                              │                    |
|               └───────────────────────┬──────────────────────┘                    |
|                                       │                                           |
|                                       ↓                                           |
|                     SEOCorrelationIntelligenceService                             |
|                                       │                                           |
|        ┌──────────────────────────────┼──────────────────────────────┐            |
|        ↓                              ↓                              ↓            |
|  Rule 1: LOW_CTR_HIGH_IMP      Rule 2: RANKING_DECAY         Rule 3: HIGH_VAL_PAGE|
|  (High imp, low CTR +          (Pos > 10 + broken links,     (Top traffic page +  |
|   title/meta description gaps)  missing canonical blockers)   technical warnings) |
|        └──────────────────────────────┬──────────────────────────────┘            |
|                                       │                                           |
|                                       ↓                                           |
|                     SEOCorrelationOpportunity / Agent Tool                        |
|                                       │                                           |
|                         analyze_seo_opportunities                                 |
+-----------------------------------------------------------------------------------+
```

### Registered Correlation Tool:

| Tool Name | Category | Mutating | Requires Approval | Purpose |
|---|---|---|---|---|
| `analyze_seo_opportunities` | `READ_ONLY` | No | No | Correlates Google Search Console performance metrics with live website audit diagnostics to discover high-leverage SEO opportunities (low CTR with on-page defects, ranking decay with technical crawl blockers, high-value page vulnerabilities, and query-to-page optimizations). |

### Real-Time SEO Intelligence Lifecycle Events:
- `seo.intelligence.started`: Emitted when correlation analysis begins with filter parameters.
- `seo.evidence.collected`: Emitted after aggregating GSC and SiteAudit evidence metrics.
- `seo.opportunity.detected`: Emitted for each prioritized candidate opportunity.
- `seo.intelligence.completed`: Emitted upon pipeline completion with summary counts.

---

## 11. Autonomous SEO Investigation & Decision Loop (Phase 4.2.3.3)

Phase 4.2.3.3 upgrades DoxaRank from passive opportunity detection to autonomous, evidence-grounded investigation and structured decision formulation without performing destructive website mutations.

```text
                     SEO Opportunity Detected
                                │
                                ▼
                   Create Investigation Context
                                │
                                ▼
                        Collect Evidence
                  (GSC Metrics + SiteAudit Issues)
                                │
                                ▼
                        Correlate Evidence
                                │
                                ▼
                       Evaluate Confidence
                      (Deterministic 0.0 - 1.0)
                                │
                                ▼
                      Determine Root Cause
                 (Deterministic Classification)
                                │
                                ▼
                   Generate Recommended Action
                                │
                                ▼
                       Risk Classification
                     (HIGH / MEDIUM / LOW)
                                │
                                ▼
                   Human Approval Boundary
             (requires_human_approval = True)
```

### Evidence Hierarchy

The investigation engine strictly separates factual observation from reasoned inference:

1. **Observed Facts**: Empirical measurements retrieved directly from Google Search Console (impressions, clicks, CTR, position) and Site Audit diagnostics (HTTP status codes, title/meta length, canonical tags, heading counts, broken links).
2. **Inferences**: Logical deductions reasoned from observed empirical facts (e.g. "High visibility with low CTR indicates snippet conversion failure rather than ranking deficit").
3. **Root Causes**: Classification of primary bottleneck into deterministic categories (`CONTENT`, `ON_PAGE_SEO`, `TECHNICAL_SEO`, `CTR`, `INDEXING`, `CANONICAL`, `PERFORMANCE`, `INTERNAL_LINKING`, `SEARCH_INTENT`, `UNKNOWN`) accompanied by clear explanatory justification.
4. **Recommendations**: Concrete action plans with expected benefits and risk ratings.

### Deterministic Confidence Scoring Methodology

Confidence is computed deterministically based on multi-source evidence verification:

* **Direct GSC metrics matching target URL/query**: +0.30 (high-volume data adds +0.05)
* **Direct SiteAudit issues matching target URL**: +0.25 (audit available +0.10, matching issues +0.15)
* **Direct URL path match verified**: +0.10
* **Query-to-page relationship confirmed in GSC**: +0.10
* **Confidence Levels**:
  * `HIGH`: Score $\ge 0.75$
  * `MEDIUM`: $0.45 \le \text{Score} < 0.75$
  * `LOW`: Score $< 0.45$

### Impact, Effort & Risk Classification

* **Impact**:
  * `HIGH`: Impressions $\ge 500$, position $\le 10$, clicks $\ge 20$, or critical crawl issues.
  * `MEDIUM`: Impressions $\ge 50$, position $\le 20$, or warning audit issues.
  * `LOW`: Impressions $< 50$ or notice/info issues.
* **Effort**:
  * `LOW`: Title, meta description, missing H1, or image alt optimizations.
  * `MEDIUM`: Content depth expansion, search intent rewrite, internal linking.
  * `HIGH`: Canonical structure fixes, redirect loop resolution, Core Web Vitals latency.
* **Risk**:
  * `LOW`: Non-destructive snippet updates (title, meta description, alt text).
  * `MEDIUM`: On-page content layout and heading reorganizations.
  * `HIGH`: Canonical tags, HTTP redirects, and URL slug modifications.

### Human-in-the-Loop Governance Boundary

All recommendations that could modify website assets explicitly declare:
```json
{
  "requires_human_approval": true
}
```
No autonomous website mutation is performed during investigation. Non-mutating recommendations (`MONITOR`, `NO_ACTION`) declare `requires_human_approval = false`.

### Registered Investigation Tool:

| Tool Name | Category | Mutating | Requires Approval | Purpose |
|---|---|---|---|---|
| `investigate_seo_opportunity` | `READ_ONLY` | No | No | Autonomously investigate a specific SEO opportunity by gathering multi-source evidence from Google Search Console and Site Audit diagnostics, classifying root cause, evaluating confidence, and generating structured recommended actions. |

### Real-Time SEO Investigation Lifecycle Events:
- `seo.investigation.started`: Emitted when an opportunity investigation begins.
- `seo.investigation.evidence_collected`: Emitted after aggregating targeted GSC metrics and matching audit issues.
- `seo.investigation.root_cause_identified`: Emitted upon deterministic root-cause classification.
- `seo.investigation.recommendation_generated`: Emitted when recommended action and risk levels are computed.
- `seo.investigation.completed`: Emitted with final investigation status and confidence score.

---

## 12. Human-in-the-Loop Action Execution & Mutation Gating (Phase 4.3)

Phase 4.3 establishes an immutable, server-side security boundary between autonomous agent reasoning and website mutations.

### Governance Principles

1. **Human Approval as a Security Control**: Human approval is not merely a UI convenience; it is a hard server-side security boundary. The backend independently validates `approved_by` and `approved_at` timestamps before executing any mutation.
2. **Untrusted Agent Boundary**: The LLM agent is never trusted to bypass or self-approve mutations. When an action is proposed, it is persisted in `PENDING_APPROVAL` status with `requires_human_approval = True`.
3. **Structured Proposal Payloads**: Mutation connectors receive structured, validated database models (`SEOAction`), not arbitrary LLM strings or code snippets.
4. **Safe Staging Execution**: In this phase, mutations execute through the `DryRunMutationConnector`, producing exact before/after visual diffs and setting up monitoring baselines with zero destructive modifications.

### State Machine Lifecycle

```
[PROPOSED / PENDING_APPROVAL] ──(Human Project Owner Rejects)──> [REJECTED] (Reason recorded)
        │
        └──(Human Project Owner Approves)──> [APPROVED]
                                                 │
                                                 └──(Execution Triggered)──> [EXECUTING]
                                                                                │
                                                                                ├──(Success)──> [COMPLETED]
                                                                                └──(Error)────> [FAILED]
```

### Action Tools & Lifecycle Events

| Tool Name | Category | Mutating | Requires Approval | Purpose |
|---|---|---|---|---|
| `propose_seo_action` | `SAFE_INTERNAL` | Yes (DB) | No | Create structured proposal in `PENDING_APPROVAL` status. |
| `get_pending_actions` | `READ_ONLY` | No | No | List pending actions requiring human review. |
| `get_action` | `READ_ONLY` | No | No | Retrieve single action detail, evidence snapshot, and rationale. |
| `preview_action` | `READ_ONLY` | No | No | Generate non-destructive before/after visual diff. |

#### Real-Time Action Events:
* `seo.action.proposed`: Emitted when a new SEOAction proposal is generated.
* `seo.action.pending_approval`: Emitted when an action enters the human review gate.
* `seo.action.approved`: Emitted when project owner approves an action.
* `seo.action.rejected`: Emitted when project owner rejects an action with explanation.
* `seo.action.execution_started`: Emitted when controlled execution begins.
* `seo.action.completed`: Emitted on successful execution with execution metadata.
* `seo.action.failed`: Emitted on execution error with sanitized failure reason.

---

## 13. SEO Outcome Learning & Deterministic Measurement (Phase 4.5)

Phase 4.5 introduces the closed feedback loop connecting past executed actions to observed search performance lift:

```text
EXECUTE ──> VERIFY ──> MEASURE OUTCOME ──> LEARN
```

### Registered Outcome Learning Tools:

| Tool Name | Category | Mutating | Requires Approval | Purpose |
|---|---|---|---|---|
| `get_action_outcomes` | `READ_ONLY` | No | No | Retrieve historical SEO action outcomes, empirical improvement rates, and before/after search performance evidence for a project. |

### Real-Time Outcome Events:
* `seo.outcome.measured`: Emitted when before/after GSC metrics are deterministically classified (`IMPROVED`, `NO_CHANGE`, `DECLINED`, `INSUFFICIENT_DATA`).
* `seo.outcome.evaluated`: Emitted with aggregate empirical improvement rates and statistical confidence.
* `seo.outcome.insufficient_data`: Emitted when before/after query traffic does not meet the minimum statistical threshold.

---

## 14. Adaptive SEO Strategy & Real-Time Events (Phase 4.6)

Phase 4.6 enables the autonomous SEO agent to utilize historical learning to calibrate and prioritize future action recommendations:

```text
PAST OUTCOMES → LEARNED ACTION-TYPE PERFORMANCE → FUTURE ACTION PRIORITIZATION → NEW EXECUTION → NEW OUTCOME → UPDATED LEARNING
```

### Core Architecture:
1. **Mathematical Grounding**:
   - Deterministic Laplace / Bayesian smoothing prevents small-sample bias:
     $$\hat{p} = \frac{\text{improved} + 1}{\text{evaluatable} + 2}$$
   - Bounded priority calibration strictly clamped to $[-0.15, +0.15]$:
     $$\Delta = (\hat{p} - 0.50) \times 0.30 \times w$$
   - Historical evidence influences priority ordering without overriding safety controls or removing human approval gates.

2. **Registered Adaptive Strategy Tool**:

| Tool Name | Category | Mutating | Requires Approval | Purpose |
|---|---|---|---|---|
| `get_adaptive_seo_strategy` | `READ_ONLY` | No | No | Retrieve project-scoped adaptive SEO strategy, Bayesian-smoothed win rates, confidence tiers, and priority adjustments. |

3. **Real-Time Strategy Lifecycle Events**:
- `seo.strategy.learning.started`: Emitted when historical outcomes are queried for strategy formulation.
- `seo.strategy.evidence.collected`: Emitted after historical sample sizes, evaluatable records, and empirical win rates are aggregated.
- `seo.strategy.generated`: Emitted when Bayesian-smoothed win rates, confidence tiers (`high`, `medium`, `low`, `none`), and action classifications (`preferred`, `deprioritized`, `neutral`) are determined.
- `seo.strategy.applied`: Emitted when adaptive adjustments are applied to action proposals during plan creation.
- `seo.strategy.completed`: Emitted upon finalized plan generation with strategy summary and confidence.

4. **Multi-Tenant Security Boundary**:
Strategy evaluation strictly enforces tenant ownership: `project.owner == request.user`. Cross-project outcome data is never commingled.

---

## 15. Specialized SEO Agent Orchestration & Supervision Lifecycle Events (Phase 4.7)

Phase 4.7 introduces explicit multi-agent coordination telemetry tracking task routing, agent lifecycles, and inter-agent handoffs:

```text
Supervisor ──(routing)──> ResearchAgent ──(handoff)──> InvestigationAgent ──(handoff)──> StrategyAgent ──(handoff)──> ActionPlanningAgent
```

### Real-Time Orchestration Events:
- `seo.agent.routing.started`: Emitted when the supervisor begins evaluating user goal keywords and task intent.
- `seo.agent.routing.completed`: Emitted with the selected workflow pipeline (e.g. `["seo_researcher", "seo_investigator", "seo_strategist"]`) and correlation ID.
- `seo.agent.started`: Emitted when a specialized agent begins its bounded execution step.
- `seo.agent.completed`: Emitted upon successful agent execution with duration, findings count, and confidence score.
- `seo.agent.failed`: Emitted on agent failure with sanitized error reason.
- `seo.agent.handoff`: Emitted at explicit inter-agent transition boundaries, recording `source_agent`, `target_agent`, `step_index`, and `correlation_id`.

### Governance & Privacy:
- All event payloads are sanitized via `sanitize_event_payload` to guarantee that credentials, tokens, and internal chain-of-thought tokens are never leaked into the event stream.

---

## 16. Model Context Protocol (MCP) Interoperability Lifecycle Events (Phase 4.8)

Phase 4.8 establishes observable telemetry for external MCP server registration, capability discovery, and tool invocations:

```text
MCP Server Registered ──> Tools Discovered ──> Tool Authorization Checked ──> Tool Invocation Started ──> Tool Invocation Completed / Failed
```

### Real-Time MCP Events:
- `mcp.server.registered`: Emitted when an approved MCP server is connected and registered into the subsystem.
- `mcp.tools.discovered`: Emitted upon scanning an MCP server's declared tool capabilities (`tools/list`).
- `mcp.tool.authorization.checked`: Emitted when an agent's permission to execute an external MCP tool is validated against the security policy.
- `mcp.tool.invocation.started`: Emitted before dispatching a `tools/call` JSON-RPC message to an external server.
- `mcp.tool.invocation.completed`: Emitted upon receiving a valid, parsed tool response with execution latency.
- `mcp.tool.invocation.failed`: Emitted when an external tool invocation fails, times out, or returns a protocol error.

### Governance & Privacy:
- Invocations preserve multi-tenant project isolation and sanitize external parameters against injection payloads.
