# DoxaRank — Asynchronous Agent Architecture & Celery Infrastructure

This document outlines the asynchronous job execution engine and Celery/Redis infrastructure for DoxaRank's autonomous SEO agent.

---

## 1. System Architecture Overview

```text
HTTP Client (React Dashboard / API Client)
    │
    │  POST /api/seo/ai/agent/runs/
    ▼
Django REST API (`AgentRunViewSet.create`)
    │
    │  1. Validates user access & project boundary
    │  2. Creates AgentRun(status='pending')
    │  3. Enqueues execute_agent_run.delay(run_id)
    ▼
Redis Message Broker (`redis://127.0.0.1:6379/0`)
    │
    ▼
Celery Worker Process (`celery -A config worker --loglevel=info`)
    │
    │  1. Selects & locks AgentRun (select_for_update)
    │  2. Atomically transitions PENDING -> RUNNING
    │  3. Instantiates AgentOrchestrator
    │  4. Runs iterative ReAct reasoning loop
    │  5. Safely calls governed ToolRegistry tools
    │  6. Records step thoughts & tool telemetry
    ▼
State Transitions:
    ├── Pauses on `propose_seo_action` (status='waiting_for_approval')
    ├── Terminal success (status='completed')
    └── Terminal failure (status='failed') / timeout / loop exit
```

---

## 2. Human-in-the-Loop Approval Workflow

```text
Celery Worker
    ↓
Agent proposes SEOAction
    ↓
AgentRun status = WAITING_FOR_APPROVAL
Celery task exits safely
    ↓
Human User reviews proposal in Dashboard UI
    ├── Option A: User approves
    │      ↓
    │   POST /api/seo/ai/agent/runs/{id}/resume/ (decision='approved')
    │      ↓
    │   Celery task re-queued asynchronously
    │      ↓
    │   SafeActionExecutor executes approved action
    │      ↓
    │   Agent loop continues to completion
    │
    └── Option B: User rejects
           ↓
        POST /api/seo/ai/agent/runs/{id}/resume/ (decision='rejected')
           ↓
        Proposed SEOAction marked REJECTED
        AgentRun transitioned to CANCELLED
        No action executed
```

---

## 3. Concurrency Guarantees & Idempotency

- **Row-Level Locking**: `select_for_update()` in atomic database transactions prevents duplicate workers from processing the same `AgentRun`.
- **Precondition Verification**:
  - Initial execution only allows `status == 'pending'`.
  - Resumption only allows `status == 'waiting_for_approval'`.
- **Terminal State Protection**: Already completed, failed, or cancelled runs reject execution attempts gracefully without modifying state.

---

## 4. Bounded Retry Strategy

- **Retryable Exceptions**:
  - `ConnectionError`, `TimeoutError`, `OperationalError`
  - Transient Redis connection drops (`redis.exceptions.ConnectionError`)
  - Provider network hiccups (`requests.exceptions.ConnectionError`)
  - Retried up to **3 times** with exponential backoff: `(2 ^ retry_count) * 5s`.
- **Non-Retryable Exceptions**:
  - Validation errors (`ValidationError`, schema mismatches)
  - Security / permission violations
  - Bounded step limits reached (`max_steps=15`)
  - Repetitive tool loop detections
  - Fatal provider errors
  - Instantly transitioned to `FAILED` with sanitized error summaries.

---

## 5. Local Development Setup

### 1. Start Redis
```bash
# Using local Redis or Docker
docker run -d -p 6379:6379 --name doxarank-redis redis:alpine
```

### 2. Start Celery Worker
From `backend/`:
```bash
celery -A config worker --loglevel=info
```

### 3. Start Django Server
From `backend/`:
```bash
python manage.py runserver
```

### 4. Start React Frontend
From `dashboard/`:
```bash
npm run dev
```

### 5. Automated Tests
Tests execute with `CELERY_TASK_ALWAYS_EAGER=True` automatically, running all background tasks synchronously in-process without requiring a live external Redis daemon:
```bash
python manage.py test
```
