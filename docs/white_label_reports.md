# DoxaRank White-Label PDF Reports Architecture

## 1. Overview
The White-Label PDF Reports module implements the original DoxaRank SRS requirement:

> **Agency Plan:**
> - ETB 6,000/month
> - 20 sites
> - 500 keywords
> - unlimited usage
> - competitor snapshots
> - **white-label PDF reports**

This feature allows Agency-tier subscribers to compile and export professional, unbranded SEO performance and technical audit PDF reports for any of their tracked projects. The report is tailored to client presentations, board reviews, or internal stakeholder deliverables.

### White-Label Guarantee
When a report is generated under the white-label pipeline:
- **ZERO DoxaRank Branding**: No DoxaRank logos, no DoxaRank marketing slogans, no promotional footers, and no vendor sales links.
- **Client & Project Identity**: Supports custom Client/Company branding (`client_name`), the target Project Name, and the website URL.
- **Confidentiality Disclaimer**: Employs an executive, neutral disclaimer ("Confidential SEO Audit & Performance Report prepared for {Client Name}").

---

## 2. Architecture & Data Flow

```
                     +-------------------------------+
                     |     React Client / Dashboard  |
                     +-------------------------------+
                                     |
                        POST /api/seo/reports/generate/
                                     v
                     +-------------------------------+
                     |      Django REST Framework    |
                     |  - IsAuthenticated            |
                     |  - CanAccessWhiteLabelReports |
                     |  - Project Ownership Guard    |
                     +-------------------------------+
                                     |
                        creates SEOReport (PENDING)
                                     v
                     +-------------------------------+
                     |      Celery Worker / Queue    |
                     |  generate_seo_report_task()   |
                     +-------------------------------+
                                     |
                                     v
                     +-------------------------------+
                     |       SEOReportService        |
                     +-------------------------------+
                       /      |              |      \
                      v       v              v       v
           [CrawlJob]   [KeywordRanking] [Competitor] [SEORecommendation]
          Technical SEO  Rank Tracker    Snapshots     Recommendations
                      \       |              |       /
                       v      v              v      v
                     +-------------------------------+
                     |    collect_report_context()   |
                     |   (Factual, Multi-Source)     |
                     +-------------------------------+
                                     |
                                     v
                     +-------------------------------+
                     |    ReportLab PDF Generator    |
                     |   - NumberedCanvas (Page X/Y) |
                     |   - Client-Branded Headers    |
                     |   - Flowable Tables & Layout  |
                     +-------------------------------+
                                     |
                                     v
                     +-------------------------------+
                     |  Secure Media File Storage    |
                     |  media/reports/project_<id>/  |
                     |  report_<id>_<slug>.pdf       |
                     +-------------------------------+
                                     |
                                     v
                     +-------------------------------+
                     | SEOReport (COMPLETED / FAILED)|
                     +-------------------------------+
```

---

## 3. Report Sections & Content Specification

Each white-label PDF report contains seven standardized, professional sections:

### 1. Cover Page
- **Document Title**: User-configurable heading (defaults to *"SEO Performance & Technical Audit Report"*).
- **Target Project**: Project display name and canonical website URL.
- **Client / Company**: Client identity specified at generation time (e.g. *"Acme Corporation"*).
- **Metadata Card**: Report generation date, reporting scope, and coverage period.
- **Confidentiality Notice**: Formal, unbranded client notice.

### 2. Executive Summary
- **Overall Audit Status**: Deterministic assessment badge (*Performing Well*, *Attention Required*, or *Baseline Established*) based on live critical findings.
- **Key Findings**: Fact-based bullet points derived directly from actual crawler, rank tracking, competitor, and recommendation data. No hallucinated values.

### 3. Technical SEO Audit
- **Aggregated Health Metrics**: Pages crawled, pages discovered, broken links (HTTP 4xx/5xx), missing titles, duplicate titles, missing meta descriptions, missing H1 headings, redirect chains, and slow pages (>3s).
- **Notable Crawl Findings (Sample URLs)**: Tabular breakdown of problematic URLs, status codes, response times in milliseconds, and detected issues.
- *Graceful fallback*: Explicitly notes when no crawl data is available yet.

### 4. Search Engine Rank Tracking (google.com.et)
- **SERP Summary Metrics**: Tracked keywords count, top 3 positions, top 10 positions, top 50 positions, found count, and not-found (>100) count.
- **Keyword Detail Table**: Target keyword, target market/device (e.g. `ET/EN · Desktop`), current ranking position (`#1`, `#4`, etc.), ranking landing URL, and position movement (`+3`, `-1`, `=`, `New`).
- *Graceful fallback*: Explains when no keywords are currently tracked.

### 5. Competitor SERP Visibility Benchmarks
- **Monitored Competitors**: List of active competitor domains configured for the project.
- **Visibility Matrix**: Cross-comparison table displaying the project's ranking position against top competitors across shared target queries on Google Ethiopia.
- *Graceful fallback*: Indicates when no competitor domains are configured.

### 6. Prioritized SEO Recommendations
- **Actionable Optimization Feed**: High, Medium, and Low priority recommendations.
- **Contextual Attribution**: Category, originating issue, affected URL or keyword target, and actionable developer guidance.
- *Graceful fallback*: Notes when no pending recommendations exist.

### 7. Phased Implementation Roadmap
- **Phase 1: Immediate Critical Fixes (Week 1–2)**: Urgent technical blockers (broken pages, missing title tags, server errors).
- **Phase 2: On-Page & Technical Optimization (Week 3–4)**: Meta descriptions, H1 tags, page speed enhancements.
- **Phase 3: Search Visibility & Content Expansion (Month 2+)**: Keyword gap closure and competitive ranking expansion.
- **Deterministic**: Derived deterministically via rule-based categorization. **No LLM is used**.

### Running Headers & Footers
- **Dynamic Two-Pass Pagination**: Implemented via `NumberedCanvas` to calculate total pages dynamically and render `"Page X of Y"`.
- **Client Running Header**: Renders the client/project name and report title on pages 2+.
- **Running Footer**: Includes report date, confidentiality label, and exact page numbers.

---

## 4. Subscription Gating & Quotas

Access to white-label reports is controlled via DoxaRank's unified subscription infrastructure:

| Plan | Monthly Price | `FeatureCode.WHITE_LABEL_REPORTS` | Generation Allowed? |
|---|---|---|---|
| **Free** | ETB 0 | ❌ Denied | 403 Forbidden (`FEATURE_NOT_ENTITLED`) |
| **Starter** | ETB 1,500 | ❌ Denied | 403 Forbidden (`FEATURE_NOT_ENTITLED`) |
| **Agency** | ETB 6,000 | ✅ Entitled | 200 OK / 201 Created |

Enforcement points:
1. **DRF Permission Class**: `CanAccessWhiteLabelReports` is applied to `SEOReportViewSet`.
2. **Service Entitlement**: `PlanEntitlementService.check_can_use_feature(user, FeatureCode.WHITE_LABEL_REPORTS)` raises `FeatureNotEntitledException`.
3. **Frontend Paywall**: Dashboard renders an Agency upgrade banner for Free and Starter subscribers.

---

## 5. API Endpoints

All endpoints require JWT Bearer authentication (`IsAuthenticated`) and Agency subscription (`CanAccessWhiteLabelReports`).

### 1. Generate Report
- **URL**: `POST /api/seo/reports/generate/`
- **Request Body**:
  ```json
  {
    "project_id": 1,
    "client_name": "Acme Corp",
    "title": "Quarterly Technical Audit & Rank Report",
    "async": true
  }
  ```
- **Response** (`201 Created`):
  ```json
  {
    "id": 14,
    "project": 1,
    "project_name": "Addis Tech Solutions",
    "project_website_url": "https://addistech.et",
    "title": "Quarterly Technical Audit & Rank Report",
    "client_name": "Acme Corp",
    "status": "COMPLETED",
    "file_size_bytes": 48210,
    "download_url": "/api/seo/reports/14/download/",
    "summary_data": {
      "crawler_available": true,
      "total_keywords": 12,
      "top_10_count": 5,
      "competitors_count": 2,
      "recommendations_count": 4,
      "overall_status": "Performing Well"
    },
    "error_message": "",
    "created_at": "2026-09-29T14:15:00Z",
    "completed_at": "2026-09-29T14:15:02Z"
  }
  ```

### 2. List Reports
- **URL**: `GET /api/seo/reports/?project_id=<id>`
- **Response** (`200 OK`): Array of `SEOReport` objects for the authenticated user's projects.

### 3. Retrieve Report
- **URL**: `GET /api/seo/reports/<id>/`
- **Response** (`200 OK`): Single `SEOReport` object.

### 4. Download Report
- **URL**: `GET /api/seo/reports/<id>/download/`
- **Response** (`200 OK`): Binary stream with `Content-Type: application/pdf` and `Content-Disposition: attachment; filename="seo_report_<slug>_<id>.pdf"`.

---

## 6. PDF Generation & Storage

- **Library**: `reportlab==5.0.1` (pure Python server-side compilation, no headless browser required).
- **Storage Location**: Stored securely on the local filesystem at `MEDIA_ROOT/reports/project_<id>/report_<id>_<slug>.pdf`.
- **API Isolation**: Internal filesystem paths (`file_path`) are never exposed to the client. The client receives a signed/relative `download_url`.

---

## 7. Security & Tenant Isolation Review

1. **Multi-Tenant Scoping**: All queries filter through `project__owner=request.user`. Users cannot generate or inspect reports for projects owned by other users.
2. **Download Authorization**: The download endpoint strictly verifies that `report.project.owner == request.user` before streaming file content.
3. **Path Traversal Defense**: The resolved file path is verified using `os.path.commonpath([MEDIA_ROOT, full_path])`. Any path escaping `MEDIA_ROOT` triggers a security rejection (`403 Forbidden`).
4. **Input Sanitization**: User-supplied client names and report titles are sanitized via `html.escape()` prior to insertion into ReportLab Paragraph flowables, preventing XML/HTML injection.
5. **No Credential Leakage**: Generated PDFs and metadata dictionaries never include API keys, database credentials, Google OAuth tokens, or payment secrets.

---

## 8. Asynchronous Execution & Celery Integration

- **Task Name**: `apps.seo.tasks.generate_seo_report_task`
- **Behavior**:
  - Bound Celery task with automatic retry on transient exceptions (`max_retries=2`).
  - Sets `celery_task_id` on the `SEOReport` record for full traceability.
  - Transitions state: `PENDING` -> `RUNNING` -> `COMPLETED`.
  - In case of unrecoverable compilation failure, transitions to `FAILED` and captures the error message without crashing Celery workers.
  - When `CELERY_TASK_ALWAYS_EAGER=True` (e.g. in test suites), executes synchronously inline.

---

## 9. Dashboard Integration

- **Component**: `dashboard/src/components/WhiteLabelReportsPanel.tsx`
- **Page**: Embedded in `dashboard/src/pages/Dashboard.tsx` under Section 3.8.
- **Capabilities**:
  - Agency subscribers: View existing reports, trigger generation via modal, monitor real-time background status, and download completed PDFs.
  - Free & Starter subscribers: Informative upgrade card explaining Agency white-label capabilities with direct action to upgrade.
  - Polling: Auto-polls report status every 3 seconds while reports are `PENDING` or `RUNNING`.

---

## 10. Limitations

1. **Competitor Crawling**: As defined in the SRS, competitor analysis in the report reflects SERP observations on Google Ethiopia and does not crawl competitor web properties.
2. **Historical Depth**: Rank tracking movements require at least two historical snapshots for a keyword to calculate position deltas. If only one observation exists, it is marked as `New`.
3. **Storage Retention**: Reports are persisted locally in `MEDIA_ROOT`. A future cloud storage migration (e.g., S3) can wrap `SEOReport.file_path` without requiring changes to the public API surface.
