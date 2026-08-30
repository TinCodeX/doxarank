# DoxaRank — Real-Time Agent Event Architecture (Milestone 3, Phase 3.1 - 3.3)

This document outlines the transport-independent event contract, lifecycle events, publisher abstraction, sequence ordering, payload security, WebSocket client layer, and architectural relationship between the database source-of-truth and the real-time event stream in DoxaRank.

---

## 1. Architectural Purpose & Separation of Concerns

```text
PostgreSQL AgentRun / AgentStep State  ===>  Authoritative Source of Truth (Persistence & Integrity)
AgentEvents Notification Stream        ===>  Real-Time Ephemeral Streaming & Observability
```

The real-time event layer provides decoupled, transport-independent structured events emitted at deterministic lifecycle boundaries throughout an autonomous agent run.

### Design Principles:
1. **Transport Independence**: The core agent orchestrator and event definitions do not depend directly on Redis, WebSockets, Django Channels, React, or Celery.
2. **Authoritative Persistence**: PostgreSQL `AgentRun`, `AgentStep`, and `AgentToolCall` models remain the authoritative source of truth.
3. **Observability Resilience**: Event publication errors are treated as non-fatal observability warnings; transport failures never abort or corrupt an active SEO agent execution.
4. **Zero Token / Secret Leakage**: Strict sanitization guarantees that OpenAI/Anthropic API keys, Bearer tokens, passwords, and private provider credentials are never placed in event payloads.
5. **No Private Hidden Reasoning**: Event payloads contain concise, user-facing summary information and action rationale, preventing exposure of internal chain-of-thought tokens.
6. **Read-Only Real-Time Transport**: The WebSocket channel is strictly a notification/read stream. All state mutations and human approvals occur via authenticated REST APIs.

---

## 2. End-to-End Real-Time Event Architecture

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

## 5. Sequence Ordering Strategy

1. **Ordering Mechanism**: Ordering is determined **exclusively** by the monotonically increasing integer `sequence_number` per `AgentRun` (1, 2, 3, 4...).
2. **Timestamps as Metadata**: Timestamps provide chronological context for humans and logging, but must not be used for ordering.
3. **Frontend De-duplication & Sorting**: The React client uses `seenEventIds` to reject duplicates and sorts incoming events strictly by `sequence_number` ascending.
4. **Resumption Continuity**:
   - When an `AgentRun` pauses on `approval.required` (e.g. at sequence #6), the last sequence number is tracked in `run.context_snapshot['_event_seq']`.
   - When resumed in a subsequent Celery worker or process, the orchestrator initializes from `_event_seq` and emits `approval.approved` as sequence #7.
   - Resumed runs **never** reset sequence numbers to 1 and **never** re-emit `agent.started`.

```text
Sequence Flow:
Sequence 1 → agent.started
Sequence 2 → step.started
Sequence 3 → tool.started
Sequence 4 → tool.completed
Sequence 5 → step.completed
Sequence 6 → approval.required  ───[ PAUSE FOR REVIEW ]───
Sequence 7 → approval.approved  ───[ RESUME APPROVED ]───
Sequence 8 → step.started
Sequence 9 → step.completed
Sequence 10 → agent.completed
```

---

## 6. Frontend Client & Hook Layer (Phase 3.3)

### WebSocket Client (`dashboard/src/api/agentEvents.ts`)
- Reusable `AgentEventClient` class managing connection state (`connecting`, `connected`, `reconnecting`, `disconnected`, `error`).
- Reuses authenticated JWT access tokens from storage via `?token=<access_token>`.
- Exponential backoff reconnection (`1s, 2s, 4s, 8s, 16s...` capped at `30s`).
- Immediately terminates retry loops on terminal authentication/authorization close codes (`4001`, `4003`, `4004`).

### React Hook (`dashboard/src/hooks/useAgentEvents.ts`)
- Hook `useAgentEvents(runId)` automatically connects and subscribes on mount / run selection.
- Validates event contract and maintains state: `{ events, connectionState, error, lastEvent, connect, disconnect, clearEvents }`.
- Guarantees ascending sequence order and eliminates duplicate `event_id` entries.

### Fallback Polling & Authoritative State
- **Primary Transport**: WebSocket streaming for instantaneous sub-second UI reactivity.
- **Fallback Polling**: If the WebSocket is disconnected, in error, or reconnecting, the dashboard automatically maintains polling at 1.5s intervals.
- When WebSocket is connected, polling is reduced to a relaxed 10s heartbeat.
- **Authoritative Source**: PostgreSQL remains the authoritative source of record. WebSocket events trigger reactive re-fetching or incremental updates without duplicating state.
- **Server-Controlled Approval**: `approval.required` events notify the UI to display the review card, but approvals/rejections are submitted strictly via authenticated POST endpoints (`/api/seo/ai/agent/runs/{id}/resume/`).

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
- **Phase 3.4**: Reconnection resilience, missed event replay buffer, and detailed step telemetry visualization.
