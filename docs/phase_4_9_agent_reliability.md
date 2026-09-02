# Phase 4.9 — Agent Reliability, Failure Recovery & Production Security Hardening

## 1. Reliability Architecture & Circuit Breakers

DoxaRank agent execution is protected by multi-layered boundaries designed to prevent runaway loops, resource exhaustion, and destructive mutations.

### Bounded ReAct Iterations
- `AgentOrchestrator` enforces a strict `max_steps` cap (default: 15, configurable per session).
- Runs exceeding `max_steps` transition to `AgentRunStatus.FAILED` with explicit telemetry (`reason: "max_steps_exceeded"`).
- Infinite recursion is mathematically impossible.

### Repetitive Tool Failure Detection
- `_detect_repeated_tool_loop()` monitors consecutive steps.
- If the agent invokes the identical tool with identical parameters immediately following a failed step, the session is halted immediately with `AgentEventType.STEP_FAILED` and `error: "repetitive_tool_loop"`.

### Tool Exception Isolation
- `ToolRegistry.execute()` wraps all registered tool handlers in isolated `try-except` blocks.
- Tool errors return structured, standardized error objects (`{"success": False, "error": {"code": "EXECUTION_ERROR", "message": ...}}`).
- No tool failure can crash the main Django execution process or agent supervisor.

### MCP Degradation & Circuit Breaker
- External MCP tools communicate via `MCPClient` with strict timeouts (`timeout_seconds=5.0`).
- If an MCP server is unreachable, times out, or throws a protocol exception, the invoking specialized agent catches the exception and falls back to internal repository data.

---

## 2. Production Security Controls

### Multi-Tenant Isolation
- Every database query in tool handlers, agent runs, and actions is scoped strictly to `Project` and verified against `project.owner`.
- The `AgentEvaluationView` requires authentication and enforces project ownership (`run.project.owner == request.user`), rejecting unauthorized cross-tenant requests with `404 Not Found`.

### Secret Scrubbing & Redaction
- `sanitize_event_payload()` scans all event payloads, error strings, and agent telemetry before publication.
- Sensitive keys (`api_key`, `secret`, `token`, `password`, `bearer_token`, `auth`, `authorization`) are permanently replaced with `***REDACTED***`.
- Direct API credentials never appear in telemetry streams or WebSocket feeds.

### Mutation Immutability
- MCP tools are strictly read-only (`is_mutating=False`, `requires_approval=False`). Any MCP tool declaring mutation capabilities is rejected at registry mount time.
- Internal mutation tools are gated behind human approval. Direct mutation execution via raw LLM prompts without explicit user confirmation is prohibited by architecture.
