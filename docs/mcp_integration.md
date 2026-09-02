# DoxaRank — Model Context Protocol (MCP) Integration & External Tool Interoperability (Phase 4.8)

## 1. Executive Summary & Core Conceptual Distinctions

Phase 4.8 introduces an **External Tool Interoperability Layer** via the **Model Context Protocol (MCP)** alongside DoxaRank's existing internal tools, without replacing `ToolRegistry`, rewriting the ReAct loop, or bypassing existing governance and multi-tenant security boundaries:

```text
                DoxaRank System Architecture
                            │
                      SEO Supervisor
                            │
                   Specialized Agent
                            │
          ┌─────────────────┴─────────────────┐
          │                                   │
   Internal Tools                      MCP Tool Adapter
          │                                   │
     ToolRegistry                         MCP Client
   (Central Source                     (JSON-RPC 2.0)
     of Truth)                                │
          │                               MCP Server
          ▼                       ("seo-local-diagnostics")
   Executed within                            │
  DoxaRank Services                     External Tools
                                 - check_url_status
                                 - get_page_metadata
                                 - get_external_page_signals
```

### Critical Conceptual Distinctions:
- **Tool**: *"What can the system do?"* (Deterministic diagnostic, analysis, or internal execution).
- **Agent**: *"How does the system reason about what to do?"* (Specialized domain cognition and multi-source evidence synthesis).
- **MCP**: *"How can tools and capabilities be exposed and consumed across system boundaries?"* (Provider-neutral, standard interoperability protocol).
- **Supervisor**: *"Which agent/workflow should handle the task?"* (Deterministic pipeline routing and shared context coordination).
- **Human Approval**: *"Who is allowed to authorize risky actions?"* (Unyielding governance gate protecting production systems).

---

## 2. Protocol Specification & Architecture

DoxaRank implements standard **JSON-RPC 2.0** Model Context Protocol semantics:

### 2.1 Tool Discovery (`tools/list`)
The MCP Client queries registered servers to discover declared capabilities and JSON-Schema parameters:
```json
{
  "jsonrpc": "2.0",
  "id": "e837f692-...",
  "method": "tools/list",
  "params": {}
}
```
Response:
```json
{
  "jsonrpc": "2.0",
  "id": "e837f692-...",
  "result": {
    "tools": [
      {
        "name": "check_url_status",
        "description": "Inspects live HTTP response code, response latency, redirects, and SSL certificate validity for a target URL.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "url": { "type": "string" },
            "timeout_seconds": { "type": "integer" }
          },
          "required": ["url"]
        },
        "category": "read_only",
        "is_mutating": false
      }
    ]
  }
}
```

### 2.2 Tool Invocation (`tools/call`)
```json
{
  "jsonrpc": "2.0",
  "id": "9934a1b0-...",
  "method": "tools/call",
  "params": {
    "name": "check_url_status",
    "arguments": {
      "url": "https://example.com/pricing",
      "timeout_seconds": 5
    }
  }
}
```
Response:
```json
{
  "jsonrpc": "2.0",
  "id": "9934a1b0-...",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"url\": \"https://example.com/pricing\", \"status_code\": 200, \"latency_ms\": 112, \"ssl_valid\": true, \"reachable\": true}"
      }
    ],
    "isError": false
  }
}
```

---

## 3. Discovered Tools & Adapter Integration

The `MCPToolAdapter` adapts discovered MCP tools into native `AgentToolDefinition` objects, namespace-prefixed with `mcp__{server_id}__{tool_name}`:

| Tool Identifier | Source Server | Category | Mutating | Purpose |
|---|---|---|---|---|
| `mcp__seo_local__check_url_status` | `seo_local` | `READ_ONLY` | No | Inspects live HTTP response status, redirect chains, socket latency, and SSL certificate validity. |
| `mcp__seo_local__get_page_metadata` | `seo_local` | `READ_ONLY` | No | Fetches live HTML `<head>` tags, meta title, meta description, canonical link, OpenGraph tags, and robots directives. |
| `mcp__seo_local__get_external_page_signals` | `seo_local` | `READ_ONLY` | No | Analyzes external DOM metrics including word count, text-to-HTML ratio, total images, and images lacking alt text. |

Discovered tools are automatically mounted into DoxaRank's global `ToolRegistry`, making them available to specialized agents and the ReAct reasoning engine without altering existing tool execution patterns.

---

## 4. Security Boundaries & Permission Policy

1. **Server Allowlist**:
   Only explicitly authorized servers (`APPROVED_MCP_SERVERS = {"seo_local"}`) can be registered or queried. Arbitrary server URLs cannot be introduced by end users.
2. **Strict Read-Only Constraint**:
   In Phase 4.8, any MCP tool declaring `is_mutating: True` or a non-read-only category is **strictly rejected during discovery** (`MCPPermissionPolicy.validate_tool_for_registration`).
3. **Agent Permission Allowlist**:
   External MCP tools may only be invoked by authorized specialized agents (`MCP_AUTHORIZED_AGENTS = {"seo_researcher", "seo_investigator", "seo_supervisor"}`). Non-authorized agents (e.g. `SEOActionPlanningAgent`) calling an MCP tool are blocked with `PermissionError`.
4. **Input Sanitization**:
   All arguments pass through `MCPPermissionPolicy.sanitize_arguments` to strip path traversal (`../`) and script injection payloads.
5. **Human Approval Boundary**:
   MCP tools cannot create, approve, or execute website modifications. Action planning remains strictly within `SEOActionPlanner` behind the human review gate.

---

## 5. Failure Handling & Graceful Degradation

If an MCP server experiences network latency, connection timeout, or returns a protocol error:
- The `MCPClient` normalizes the error without raising an unhandled exception.
- The `MCPToolAdapter` emits `mcp.tool.invocation.failed` with sanitized telemetry.
- The calling agent (e.g. `SEOResearchAgent`) logs the failure, records the warning in its findings, and **continues reasoning using internal Google Search Console and SiteAudit evidence**.
- The agent **never invents or hallucinates external data**.

---

## 6. End-to-End Workflow Trace

### Example: "Investigate why https://example.com/pricing is losing rankings"

1. **Supervisor Routing**:
   - `SEOSupervisorAgent` routes task to `investigate` workflow (`seo_researcher` ➔ `seo_investigator` ➔ `seo_strategist`).
2. **Research Agent**:
   - Gathers GSC clicks, impressions, and CTR.
   - Fetches site audit diagnostic issues.
   - Invokes `mcp__seo_local__check_url_status` on target URL: confirms HTTP 200, 115ms latency, valid SSL.
   - Invokes `mcp__seo_local__get_page_metadata`: detects missing OpenGraph tags and noindex warning.
   - Populates `context.evidence["mcp_url_status"]`.
3. **Investigation Agent**:
   - Correlates GSC impression drop with live MCP metadata.
   - Diagnoses root cause: `search_intent_mismatch` and missing meta tags.
4. **Strategy Agent**:
   - Evaluates domain historical win rates for metadata updates (+0.08 priority adjustment).
5. **Action Planning Agent**:
   - Formulates `SEOActionPlan` with `OPTIMIZE_TITLE` and `OPTIMIZE_META_DESCRIPTION`.
   - Halts at human approval gate with `requires_human_approval = True`.
