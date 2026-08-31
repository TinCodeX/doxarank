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
