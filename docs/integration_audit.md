# DoxaRank — Technical Integration & Agentic AI Audit

**Date:** March 2025  
**Version:** 1.0  
**Scope:** Agentic AI Architecture, Model Context Protocol (MCP), Background Tasks (Celery & Redis), Crawler Engine, External Dependencies, and Security Architecture.

---

## Executive Summary

This document details the complete, ground-truth technical audit of the DoxaRank backend architecture, external integrations, and AI orchestration layer. All statements are verified directly against the running codebase (`backend/apps/seo`, `backend/apps/integrations`, `backend/apps/subscriptions`, and `backend/config`).

### Key Audit Conclusions

1. **Agentic AI:** A functional ReAct (Reasoning + Acting) loop operates via `AgentOrchestrator` with state tracking (`AgentRun`, `AgentStep`, `AgentToolCall`). Tool execution is strictly governed by a 3-tier capability system (`READ_ONLY`, `SAFE_INTERNAL`, `HIGH_IMPACT`). High-impact tools enforce Human-in-the-Loop (HITL) approval gates.
2. **Model Context Protocol (MCP):** DoxaRank implements a **JSON-RPC 2.0 internal server/client specification** in `backend/apps/seo/services/mcp/` (`LocalSEOExternalServer`, `MCPClient`, `MCPToolAdapter`), but **external network transport (stdio, SSE, remote HTTP) is not yet wired to third parties**. Third-party interactions currently run through native Django services rather than remote MCP endpoints.
3. **Crawler Engine:** The crawler (`LiveSiteCrawler`, `TechnicalCrawler`) is implemented using **`httpx` + `urllib.robotparser` + `BeautifulSoup4`** with concurrency throttling and polite per-request delays. **Playwright is not currently used or installed**.
4. **External Services:**
   - **Google Search Console & GA4:** Real OAuth2 integration with Fernet encryption-at-rest for tokens.
   - **Microsoft Clarity:** Real OAuth2 integration with API sync.
   - **Google Ethiopia SERP:** Direct localized scraping engine (`google.com.et`) with user-agent rotation and rate limiting.
   - **DataForSEO:** Implemented via REST API client with heuristic mock fallback.
   - **Doxa Payments:** Implemented with HMAC-SHA256 webhook signature verification.
   - **CMS / Git Connectors:** Currently operate as safe staging simulations (`DryRunMutationConnector`).
   - **Sentry:** Not configured; the dashboard tab was previously mislabeled and has been corrected to **Platform Observability**.

---

## 1. Agentic AI Architecture Audit

### 1.1 Orchestrator & ReAct Execution Loop
- **File:** `backend/apps/seo/services/agent_orchestrator.py`
- **Loop Flow:**
  1. `AgentRun` initialized with project, goal, agent role, and empty context.
  2. Orchestrator calls `step()` up to `max_steps` (default: 15).
  3. Formulates structured prompt containing goal, history, and available tool schemas from `ToolRegistry`.
  4. Calls `ai_provider.get_agent_decision(system_prompt, user_prompt)`.
  5. Provider returns structured JSON: `thought`, `action`, `action_input`.
  6. Saves `AgentStep` with `thought` and selected tool.
  7. Invokes tool via `ToolRegistry.execute_tool(action, action_input, context)`.
  8. If tool tier is `HIGH_IMPACT`, the orchestrator suspends the run with status `WAITING_FOR_APPROVAL` and emits an approval request event.
  9. Loops until `action == "finish"`, error threshold reached, or human approval is needed.

### 1.2 Tool Registry & Permission Tiers
- **File:** `backend/apps/seo/services/tool_registry.py`
- **Total Tools:** 36 registered tools.
- **Tiers:**
  - `READ_ONLY`: URL status, page metadata, search console metrics, competitor signals, rank history, audit logs.
  - `SAFE_INTERNAL`: Generating outlines, drafting meta tags, calculating visibility scores, clustering keywords, scheduling re-crawls.
  - `HIGH_IMPACT` (Enforces HITL Approval): `propose_seo_action`, `execute_seo_remediation`, `execute_external_operation`, `propose_strategy_adjustment`.

### 1.3 LLM Provider Layer
- **File:** `backend/apps/seo/services/ai_providers.py`
- **Factory:** `get_ai_provider()` selects based on `AI_PROVIDER` and `OPENAI_API_KEY`:
  - `OpenAIProvider`: Issues real HTTP POST requests to `https://api.openai.com/v1/chat/completions` using `gpt-4o-mini` (configurable via `OPENAI_MODEL`). Formats responses using strict JSON schema extraction.
  - `MockAIProvider`: Zero-credential fallback that generates context-aware, realistic heuristic responses grounded in active project database models.

---

## 2. Model Context Protocol (MCP) Audit

### 2.1 Current Implementation State
- **Explicit Statement:** **MCP is partially implemented as an internal protocol specification.** DoxaRank contains an in-memory JSON-RPC 2.0 client/server adapter (`backend/apps/seo/services/mcp/`), but it is **not yet connected to external MCP servers via stdio or SSE transports**.

```
[Agent Orchestrator] 
        │
        ▼
[ToolRegistry] ──(Internal Dispatch)──► Native Tools (33 tools)
        │
        ▼
[MCPToolAdapter] ──(JSON-RPC 2.0 In-Process)──► LocalSEOExternalServer (3 tools)
```

### 2.2 Implemented MCP Components
| Component | File Path | Functionality |
|---|---|---|
| `LocalSEOExternalServer` | `mcp/server.py` | Implements JSON-RPC 2.0 `tools/list` and `tools/call`. Exposes: `check_url_status`, `get_page_metadata`, `get_external_page_signals`. |
| `MCPClient` | `mcp/client.py` | Handles JSON-RPC dispatch, request serialization, error parsing. |
| `MCPToolAdapter` | `mcp/adapter.py` | Wraps MCP tool definitions into DoxaRank `ToolDefinition` instances. |
| `MCPRegistryService` | `mcp/registry.py` | Manages server registrations (`seo_local`). |
| `MCPPermissionPolicy` | `mcp/permissions.py` | Validates allowed tool namespaces and invocation permissions. |

### 2.3 Recommended MCP Evolution Roadmap
To expand from in-process JSON-RPC to standard external MCP:
1. **Stdio Transport Worker:** Add a subprocess runner (`asyncio.subprocess` / `subprocess.Popen`) to launch and communicate with standard stdio MCP servers (e.g., `@modelcontextprotocol/server-github`, `@modelcontextprotocol/server-postgres`).
2. **Server-Sent Events (SSE) Transport:** Implement an HTTP/SSE client for remote enterprise MCP endpoints.
3. **Target Candidate MCP Servers:**
   - **Google Search Console MCP:** Wrap official Google APIs into an isolated MCP server process.
   - **GitHub MCP:** Enable automated PR creation for technical SEO fixes (robots.txt, schema markup, sitemaps).
   - **WordPress MCP:** Provide structured CMS content publishing and draft updates via REST API / MCP bridge.
   - **Playwright MCP:** Provide headless browser rendering for JavaScript-heavy SPA sites.

---

## 3. Background Architecture: Redis, Celery & Crawler

### 3.1 Broker & Message Routing
- **Broker & Results:** Redis (`redis://127.0.0.1:6379/0`).
- **Django Channels Layer:** Also backed by Redis (`channels_redis.core.RedisChannelLayer`) for real-time WebSocket events.
- **Synchronous Fallback:** `CELERY_TASK_ALWAYS_EAGER=True` can be toggled in development to run tasks synchronously without running Celery worker daemons.

### 3.2 Celery Beat Schedule
Defined in `backend/config/settings.py`:
| Task Name | Schedule | Purpose |
|---|---|---|
| `evaluate_continuous_operations` | Every 5 minutes | Scans active continuous ops configurations and triggers maintenance. |
| `autonomous_seo_monitoring` | Every 15 minutes | Runs autonomous health audits and checks SERP position volatility. |
| `sweep_stale_agent_runs` | Every 30 minutes | Marks abandoned or timed-out agent runs as failed. |
| `daily_rank_tracker_job` | Daily at 02:00 UTC | Queries Google Ethiopia for all tracked keyword rankings. |
| `weekly_competitor_snapshot_job` | Weekly (Sunday midnight) | Updates competitor visibility and SERP share metrics. |
| `check_subscription_expirations` | Daily at 01:00 UTC | Validates tier statuses and billing grace periods. |

### 3.3 Crawler Implementation: `httpx` vs Playwright
- **Audit Findings:** DoxaRank's crawler (`backend/apps/seo/services/live_site_crawler.py` and `technical_crawler.py`) is implemented using **`httpx.Client` + `BeautifulSoup4`**.
- **Features:**
  - `urllib.robotparser` compliance checks.
  - Per-domain concurrency semaphore (`max_concurrent=5`).
  - Polite per-request delay (`0.25s`).
  - Maximum depth (default: 3) and page count limits.
  - Canonical URL extraction, title, meta description, heading structure (`h1`-`h6`), OpenGraph tags, schema JSON-LD extraction, broken link detection.
- **Playwright Status:** **Not installed.** For rendering JavaScript-heavy client-side SPAs, integrating Playwright as a headless rendering microservice or Playwright MCP server is recommended for Phase 7.

---

## 4. Production Integration Matrix

| Integration | Category | Real / Mocked | Transport / Protocol | Auth Mechanism | Primary Files | Fallback Behavior |
|---|---|---|---|---|---|---|
| **Google Search Console** | Search Data | Real | REST / HTTPS | OAuth 2.0 (Encrypted Fernet token) | `integrations/services/search_console.py`, `google_oauth.py` | Returns empty dataset if token expired; alerts user to reconnect |
| **Google Analytics (GA4)** | Web Analytics | Real | REST / HTTPS | OAuth 2.0 (Encrypted Fernet token) | `integrations/services/analytics.py` | Graceful empty response if unlinked |
| **Google Tag Manager** | Tag Management | Real | REST / HTTPS | OAuth 2.0 (Encrypted Fernet token) | `integrations/services/gtm.py` | Graceful empty response if unlinked |
| **Microsoft Clarity** | UX & Heatmaps | Real | REST / HTTPS | OAuth 2.0 (Encrypted Fernet token) | `integrations/services/clarity.py` | Returns empty metrics if unconfigured |
| **DataForSEO** | Keyword Metrics | Real / Hybrid | REST / HTTPS | Basic Auth (API Login + Password) | `seo/services/seo_intelligence.py` | Deterministic heuristic calculation grounded in historical project data |
| **Google Ethiopia SERP** | Rank Tracking | Real | HTTPS Scraping | User-Agent + Rate Limit Backoff | `seo/services/rank_tracker.py` | Mock rank distribution generator if IP blocked or offline |
| **Doxa Payments** | Billing Gateway | Real | HTTPS Webhook | HMAC-SHA256 Signature Verification | `subscriptions/providers/doxa.py` | Sandbox test transaction flow |
| **CMS Connectors** | Automation | Staging Simulation | In-Memory Dry Run | Configured Webhook / API Key | `seo/services/mutation_connectors.py` | Staging log records what would be published |
| **Git / Repo Connectors** | Code PRs | Staging Simulation | In-Memory Dry Run | GitHub Token | `seo/services/mutation_connectors.py` | Diff generated and stored in run artifacts |
| **Local MCP Server** | Context Protocol | Real In-Process | JSON-RPC 2.0 | Memory Bus | `seo/services/mcp/` | Direct fallback to native tool registry |
| **Sentry** | Observability | Unconfigured | N/A | N/A | Corrected to Platform Diagnostics | Built-in database circuit breaker and logging engine |

---

## 5. Security & Credential Protection

1. **Token Encryption at Rest:** All third-party OAuth access and refresh tokens stored in `IntegrationConnection` are encrypted using `cryptography.fernet.Fernet` (AES-128 in CBC mode with HMAC SHA-256 authentication) via `backend/apps/integrations/encryption.py`. The encryption key is sourced from `DOXARANK_ENCRYPTION_KEY`.
2. **Webhook Verification:** Doxa Payments webhooks verify the `X-Doxa-Signature` header by computing an HMAC-SHA256 signature using `DOXA_PAYMENTS_WEBHOOK_SECRET` before processing any payment state transitions.
3. **CORS & CSRF:** Strict origin whitelisting configured via `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`.
4. **Human-in-the-Loop Gating:** No AI agent can execute destructive operations (direct external API calls, modifying live CMS content, or running database migrations) without an explicit approval token signed by an authenticated administrator.
