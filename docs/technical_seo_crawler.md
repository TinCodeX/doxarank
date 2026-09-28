# Technical SEO Crawler — Architecture & Development Guide

## Overview
The Technical SEO Crawler is a paid capability for **Starter** and **Agency** tier users in DoxaRank (`FeatureCode.TECHNICAL_CRAWLER`). It crawls a user's verified/owned project website, captures rich on-page SEO signals, identifies technical defects, and presents findings in the dashboard.

## Key Components

### 1. Backend Data Models (`apps/seo/models.py`)
- **`CrawlJob`**: Represents an audit crawl execution session for a Project.
  - Lifecycle: `PENDING` → `RUNNING` → `COMPLETED` / `FAILED` / `CANCELLED`
  - Enforces project ownership, stores crawl configuration, aggregate issue counters, and timing.
- **`CrawlPage`**: Represents individual crawled URLs within a CrawlJob.
  - Stores status code, response time, depth, title, meta description, H1 count, canonical URL, redirect chain, internal/external links, image alt counts, and structured findings.
  - Indexed on `(crawl_job, is_broken)`, `(crawl_job, is_slow)`, and `(crawl_job, status_code)`.

### 2. Async Execution Pipeline (`apps/seo/tasks.py`)
- Task: `apps.seo.tasks.run_technical_crawl`
- Managed via Celery + Redis with atomic row locks (`select_for_update`) to prevent duplicate worker execution.
- Safe retry handling with exponential backoff on transient Redis/network errors.
- Never leaves jobs in `RUNNING` upon errors (guaranteed transition to `FAILED` with sanitized error message).

### 3. SSRF & Network Security (`apps/seo/services/technical_crawler.py`)
The crawler employs defense-in-depth SSRF prevention:
- **Pre-resolution check**: Scheme validation (`http`, `https` only; blocks `file://`, `gopher://`, `dict://`, etc.).
- **DNS validation & IP blocking**: Resolves hostname and validates all target IPs against blocked networks:
  - Loopback (`127.0.0.0/8`, `::1/128`, IPv4-mapped loopback)
  - RFC1918 private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
  - Link-local and APIPA (`169.254.0.0/16`, `fe80::/10`)
  - Cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`, AWS/Azure/GCP metadata)
  - Multicast, broadcast, reserved ranges
- **Post-redirect validation**: Validates every intermediate redirect target before following.
- **Playwright route-level interception**: Intercepts every outgoing browser request via `context.route('**/*', ...)` to enforce SSRF blocks.

### 4. Technical SEO Checks
- Broken pages (HTTP 4xx / 5xx)
- Missing or empty `<title>` tags
- Missing meta descriptions
- Missing H1 tags or multiple H1 tags
- Canonical URL declarations and mismatches
- Redirect chains (>1 redirect)
- Slow response times (>3000ms)
- Images missing `alt` attributes
- Robots.txt compliance check

### 5. REST API Endpoints
- `GET /api/seo/crawler/?project_id=<id>`: List crawl jobs
- `POST /api/seo/crawler/launch/`: Queue new crawl job (Requires Starter/Agency)
- `GET /api/seo/crawler/<id>/`: Retrieve crawl job status & metrics
- `POST /api/seo/crawler/<id>/cancel/`: Cancel in-progress crawl job
- `GET /api/seo/crawler-pages/?crawl_job_id=<id>&is_broken=true`: Filter crawled pages

### 6. Local Development Setup

#### Quick Start with Docker
```bash
# Start Redis and the Playwright Celery worker
docker compose -f docker-compose.crawler.yml up -d
```

#### Running Locally (Without Docker)
1. **Start Redis**:
   ```bash
   redis-server
   ```
2. **Install Playwright & Browser Binaries**:
   ```bash
   pip install playwright
   playwright install chromium
   ```
3. **Run Celery Worker**:
   ```bash
   celery -A config worker -l info -Q default,crawler
   ```
4. **Run Django Dev Server**:
   ```bash
   python manage.py runserver
   ```
5. **Run Dashboard**:
   ```bash
   cd dashboard
   npm run dev
   ```
