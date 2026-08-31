# DoxaRank — Google Search Console API Integration & Agent Tool Architecture

This document describes the design, security boundaries, and data access layer for integrating live Google Search Console (GSC) search analytics into DoxaRank's agent system.

---

## 1. System Architecture Overview

```text
Agent / ReAct Execution Loop
      │
      ▼
Tool Registry (`apps.seo.services.tool_registry.ToolRegistry`)
      │
      ├── `gsc_search_analytics` (custom dimensions, filters, rows)
      ├── `gsc_top_queries`      (top queries by impressions & clicks)
      └── `gsc_top_pages`        (top landing pages by clicks & traffic)
      │
      ▼
GoogleSearchConsoleService (`apps.seo.services.google_search_console.GoogleSearchConsoleService`)
      │
      ├── 1. Verifies Project context & tenant ownership
      ├── 2. Loads `SearchConsoleConnection` from PostgreSQL
      ├── 3. In-memory Fernet decryption of refresh token
      ├── 4. Builds auto-refreshing `google.oauth2.credentials.Credentials`
      └── 5. Instantiates Google Search Console API Client (`v1`)
      │
      ▼
Google Search Console API (`https://searchconsole.googleapis.com/v1/`)
      │
      ▼
Normalized Internal Data Structures (Returned safely to Agent)
```

---

## 2. Core Security & Architectural Guarantees

### 1. PostgreSQL Authoritative State
PostgreSQL remains the single source of truth for project configurations, user associations, and `SearchConsoleConnection` state records.

### 2. Encrypted Tokens at Rest
OAuth refresh tokens are encrypted using symmetric Fernet AES encryption at rest in `SearchConsoleConnection.encrypted_refresh_token`. Plaintext tokens only exist transiently in memory during API client initialization.

### 3. Agent Access Exclusively via Governed Tools
The ReAct agent and LLM providers never manipulate OAuth credentials, client secrets, or raw HTTP headers. All GSC access is mediated through registered, validated tools in the `ToolRegistry`.

### 4. Strict Tenant Isolation
Every tool invocation requires an authenticated `Project` context. The `GoogleSearchConsoleService` verifies that the requested project owns the connection before initiating any API request. Cross-project data access is strictly rejected.

### 5. Zero Credential Leakage
All error messages, tool results, and telemetry outputs pass through sanitization filters that redact refresh tokens, access tokens, client secrets, and authorization headers before returning to the LLM or client.

---

## 3. Registered GSC Agent Tools

| Tool Name | Category | Mutating | Approval Required | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `gsc_search_analytics` | `READ_ONLY` | No | No | Query live Search Console metrics (clicks, impressions, CTR, position) across custom dimensions (`query`, `page`, `country`, `device`, `date`) and date ranges. |
| `gsc_top_queries` | `READ_ONLY` | No | No | Retrieve top performing organic search queries for a date range with optional landing page filter. |
| `gsc_top_pages` | `READ_ONLY` | No | No | Retrieve highest-traffic landing pages for a date range with optional query filter. |

---

## 4. Parameter Validation & Normalization

### Input Validations
- **Date Format**: Validated against `YYYY-MM-DD`.
- **Date Range**: Validates `start_date <= end_date`, rejects future dates, and bounds historical lookback to ~16 months (Google Search Console API maximum).
- **Dimensions**: Strictly whitelisted to `["query", "page", "country", "device", "date"]`.
- **Row Limits**: Clamped between `1` and `250` rows per request.

### Normalized Output Schema
```json
{
  "project_id": 1,
  "property_url": "sc-domain:example.com",
  "start_date": "2026-08-01",
  "end_date": "2026-08-30",
  "dimensions": ["query"],
  "total_rows": 2,
  "rows": [
    {
      "query": "ethiopia tech news",
      "clicks": 1420,
      "impressions": 28400,
      "ctr": 0.05,
      "ctr_percent": 5.0,
      "position": 3.2
    }
  ],
  "summary": {
    "total_clicks": 1420,
    "total_impressions": 28400,
    "average_ctr_percent": 5.0,
    "average_position": 3.2
  }
}
```

---

## 5. Error Handling & Diagnostics

| Failure Scenario | Internal Exception | Error Returned to Agent |
| :--- | :--- | :--- |
| No GSC connection on project | `SearchConsoleNotConnectedError` | Actionable message indicating Search Console is not connected for the project. |
| Missing or revoked credentials | `SearchConsoleCredentialsError` | Actionable message stating credentials have expired/been revoked. |
| Invalid date / format / range | `SearchConsoleValidationError` | Clear validation error specifying invalid argument. |
| Google API permission denied (403) | `SearchConsoleApiError` | Permission denied message without leaking tokens. |
| Google API quota exceeded (429) | `SearchConsoleApiError` | Rate limit notice advising backoff. |
