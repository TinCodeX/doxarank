# DoxaRank Competitor SERP Snapshots Architecture

## 1. Overview
The Competitor SERP Snapshots module implements the original DoxaRank SRS requirement:

> *"weekly competitor snapshots"*

This capability allows Agency-tier subscribers to monitor competitor search visibility against Google Ethiopia (**`google.com.et`**) for their active tracked keywords. It captures point-in-time SERP rankings for user-defined competitors, compares them against project keywords, preserves an immutable audit trail of weekly snapshots, and visualizes visibility in the DoxaRank dashboard.

> **CRITICAL ARCHITECTURAL BOUNDARY:**  
> This MVP captures **SERP competitor snapshots** and does **NOT** crawl competitor websites. Direct crawling of competitor infrastructure is outside the scope of this feature and is intentionally prevented by design.

---

## 2. Architecture & System Flow

```
                      +-----------------------------+
                      |   Dashboard / React Client  |
                      +-----------------------------+
                                     |
                       POST /api/seo/competitor-snapshots/check/
                                     v
                      +-----------------------------+
                      |     Django REST ViewSets    |
                      |  - IsAuthenticated         |
                      |  - Project Ownership        |
                      |  - PlanEntitlementService   |
                      |    (COMPETITOR_SNAPSHOTS)   |
                      +-----------------------------+
                                     |
                                  enqueue
                                     v
                      +-----------------------------+
                      |    Celery Worker (Redis)    |
                      |  - run_project_competitor_  |
                      |    snapshot                 |
                      |  - run_weekly_competitor_   |
                      |    snapshots (Celery Beat)  |
                      +-----------------------------+
                                     |
                         CompetitorSnapshotService
                                     v
                      +-----------------------------+
                      |     GoogleEtSerpClient      |
                      |  (Reused Rank Tracker infra)|
                      |  - Host: google.com.et      |
                      |  - Country: ET              |
                      |  - Politeness delays        |
                      +-----------------------------+
                                     |
                                 HTTP GET
                                     v
                      +-----------------------------+
                      |        google.com.et        |
                      |      (Google Ethiopia)      |
                      +-----------------------------+
                                     |
                                 SERP HTML
                                     v
                      +-----------------------------+
                      |         SerpParser          |
                      |  (Reused Rank Tracker infra)|
                      |  - parse_organic_results()  |
                      |  - Strips ads & PAA units   |
                      |  - Domain normalization     |
                      +-----------------------------+
                                     |
                               Multi-Match
                                     v
                      +-----------------------------+
                      |   CompetitorSnapshot Model  |
                      |  - Position (1-100 or null) |
                      |  - Status (found/not_found) |
                      |  - Immutable history        |
                      +-----------------------------+
```

---

## 3. Data Model

The data model is minimal, normalized, and integrated with the existing `Project` and `Keyword` models.

### 3.1. `Competitor`
Represents an external competitor entity tracked within the context of a project.
- `project` (ForeignKey -> `Project`, `on_delete=CASCADE`): Project relationship.
- `name` (CharField 255): User-defined label (e.g., "Shega Media", "Addis Fortune").
- `domain` (CharField 255): Normalized canonical domain (e.g., `shega.co`, `addisinsight.net`).
- `website_url` (CharField 500, optional): Base URL (e.g., `https://shega.co`).
- `is_active` (BooleanField, default=True): Active status flag.
- `created_at`, `updated_at`: Timestamps.

**Constraint:** Unique constraint on `['project', 'domain']` prevents duplicate competitors within the same project.

### 3.2. `CompetitorSnapshotJob`
Represents an asynchronous snapshot run tracking progress across keywords.
- `project` (ForeignKey -> `Project`): Target project.
- `status` (CharField): `pending`, `running`, `completed`, `failed`, `cancelled`.
- `trigger` (CharField): `manual` or `scheduled_weekly`.
- `total_keywords`, `completed_keywords`, `failed_keywords`: Execution counters.
- `started_at`, `completed_at`: Execution timestamps.
- `error_message` (TextField): Failure diagnosis if applicable.

### 3.3. `CompetitorSnapshot`
Point-in-time observation of a competitor's organic SERP visibility for a specific tracked keyword.
- `competitor` (ForeignKey -> `Competitor`): The competitor inspected.
- `project` (ForeignKey -> `Project`): The owning project.
- `keyword` (ForeignKey -> `Keyword`): The tracked query.
- `snapshot_job` (ForeignKey -> `CompetitorSnapshotJob`, optional): The job that produced this snapshot.
- `position` (PositiveIntegerField, nullable): Organic SERP rank (`1` to `100`), or `None` if not found.
- `result_status` (CharField): `found`, `not_found`, or `error`.
- `ranking_url` (CharField 1000, optional): The exact destination SERP URL found.
- `snippet_title` (CharField 500, optional): SERP result title.
- `search_engine` (`google`), `search_domain` (`google.com.et`), `country` (`ET`).
- `language` (`en` or `am`): Preserves exact Unicode Amharic queries (e.g., `በአዲስ አበባ ምርጥ ሆቴል`).
- `recorded_at` (DateTimeField): Timestamp of observation.

**Historical Invariance:** Snapshots are strictly append-only. Previous observations are never overwritten or mutated, preserving full longitudinal ranking history.

---

## 4. Reusing Rank Tracker Infrastructure

To avoid duplicate network and parsing logic, the competitor snapshot engine reuses the Rank Tracker architecture:
1. **Single Google Query Optimization:** When checking a keyword for multiple competitors, `CompetitorSnapshotService` queries `GoogleEtSerpClient` **once per keyword**, then iterates over all organic SERP results to detect all active competitors in that single pass. This dramatically reduces network overhead and minimizes rate-limiting risks on Google Ethiopia.
2. **`SerpParser` Reuse:** Organic results are extracted using `SerpParser.parse_organic_results()`, which decomposes sponsored blocks (`#tads`, `#bottomads`, data-text-ad), knowledge panels, related questions / PAA, and resolves Google redirect URLs (`/url?q=...`).
3. **Subdomain and Domain Matching:** Reuses `SerpParser.domains_match()` to match variations such as `subdomain.competitor.com` or `competitor.com` accurately.

---

## 5. Subscription Gating & Permissions

Competitor snapshots are strictly controlled via `PlanEntitlementService` and `FeatureCode.COMPETITOR_SNAPSHOTS`:
- **Free Plan:** Blocked (`HTTP 403 Forbidden`).
- **Starter Plan:** Blocked (`HTTP 403 Forbidden`).
- **Agency Plan:** Allowed (`HTTP 200 / 201 / 202`).

Every ViewSet action checks user plan entitlement during `initial()` and enforces project ownership:
```python
PlanEntitlementService.check_can_use_feature(request.user, FeatureCode.COMPETITOR_SNAPSHOTS)
```

---

## 6. Security Controls & SSRF Protection

Competitor domains are user-provided input. To prevent SSRF (Server-Side Request Forgery) and internal reconnaissance:
1. **Input Normalization & Sanitization:** `validate_and_normalize_competitor_domain()` parses the candidate domain, strips schemes, credentials, ports, and paths, and lowercases the domain.
2. **SSRF Rejections:**
   - Single-word hostnames (e.g., `localhost`, `intranet`, `corp`).
   - Loopback and local IP ranges (`127.0.0.1`, `::1`, `0.0.0.0`).
   - Private IPv4 address blocks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
   - Link-local addresses (`169.254.0.0/16`, `fe80::/10`).
   - Cloud metadata hostnames and endpoints (`metadata.google.internal`, `169.254.169.254`).
   - Dangerous URI schemes (`file://`, `ftp://`, `javascript://`, `gopher://`).
3. **Project Self-Reference Prohibition:** Competitors cannot be assigned the project's own website domain.
4. **No Direct Crawling:** The system never initiates outbound HTTP requests to competitor domains. Outbound requests are strictly limited to `google.com.et` via `GoogleEtSerpClient`.

---

## 7. Tenant Isolation

All queries in `CompetitorViewSet`, `CompetitorSnapshotViewSet`, and `CompetitorSnapshotJobViewSet` enforce project ownership:
```python
queryset = Competitor.objects.filter(project__owner=self.request.user)
```
- User A cannot view, add, modify, or delete User B's competitors.
- User A cannot view or trigger snapshot jobs on User B's projects.
- Any attempt to access resources across tenant boundaries returns `HTTP 404 Not Found` or `HTTP 403 Forbidden`.

---

## 8. Weekly Automation & Idempotency

### 8.1. Celery Beat Schedule
Automated weekly runs are registered in `CELERY_BEAT_SCHEDULE`:
```python
'weekly-competitor-serp-snapshots': {
    'task': 'apps.seo.tasks.run_weekly_competitor_snapshots',
    'schedule': 604800.0,  # 7 days (weekly)
}
```

### 8.2. Weekly Idempotency Protection
To prevent duplicate runs if the scheduled task is retried or manually triggered in quick succession, `run_weekly_competitor_snapshots()` queries existing jobs within the past 6 days:
```python
recent_job = CompetitorSnapshotJob.objects.filter(
    project=project,
    status__in=[CompetitorSnapshotJobStatus.PENDING, CompetitorSnapshotJobStatus.RUNNING, CompetitorSnapshotJobStatus.COMPLETED],
    created_at__gte=cutoff_date  # 6 days ago
).first()
```
If a project has already run or is currently running within that window, it is cleanly skipped.

### 8.3. Failure Isolation
Individual keyword query failures (e.g., temporary network timeouts) do not abort the entire job. The failed keyword is recorded with status `error`, counters are incremented, and remaining keywords and competitors continue to be processed. Jobs transition to `completed` (or `failed` if all keywords fail) and are never left hanging in `running`.

---

## 9. REST API Reference

| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/seo/competitors/?project_id=<id>` | List competitors for a project | `200 OK` |
| `POST` | `/api/seo/competitors/` | Add a new competitor | `201 Created` |
| `GET` | `/api/seo/competitors/<id>/` | Retrieve competitor details | `200 OK` |
| `PATCH` | `/api/seo/competitors/<id>/` | Update competitor details | `200 OK` |
| `DELETE` | `/api/seo/competitors/<id>/` | Delete competitor | `204 No Content` |
| `POST` | `/api/seo/competitor-snapshots/check/` | Trigger manual asynchronous snapshot | `202 Accepted` |
| `POST` | `/api/seo/competitors/snapshots/check/` | Path alias for snapshot trigger | `202 Accepted` |
| `GET` | `/api/seo/competitor-snapshots/?project_id=<id>` | List historical snapshots | `200 OK` |
| `GET` | `/api/seo/competitor-snapshots/latest/?project_id=<id>` | Latest snapshot matrix for dashboard | `200 OK` |
| `GET` | `/api/seo/competitor-snapshot-jobs/?project_id=<id>` | List snapshot job progress | `200 OK` |
| `GET` | `/api/seo/competitors/snapshot-jobs/?project_id=<id>` | Path alias for snapshot jobs | `200 OK` |

---

## 10. Dashboard User Experience

The dashboard integration is provided in `dashboard/src/components/CompetitorSnapshotsPanel.tsx`:
1. **Live Job Polling Banner:** Displays active Celery background execution status and auto-refreshes every 3 seconds until completed.
2. **Competitor Management Modal:** Allows Agency users to register and delete competitors with domain validation.
3. **Manual Trigger Action:** A "Run Snapshot Now" button triggers an immediate background job.
4. **SERP Visibility Matrix:** A table mapping Tracked Keyword, Competitor, Ranking Position (`#1` - `#100`), Result Status (with green `FOUND` badge or grey `NOT FOUND` indicator), SERP Landing URL, and Snapshot Date.

---

## 11. Testing & Validation

A test suite of 28 dedicated unit and integration tests is located at `backend/apps/seo/tests_competitor_snapshots.py`:
- **Domain Validation & SSRF:** Verifies normalization and rejection of localhost, private IPs (10.x, 192.168.x, 172.x), cloud metadata, and dangerous schemes.
- **Data Models:** Verifies competitor creation, snapshot history preservation, job state transitions, and Amharic Unicode fidelity.
- **Subscription Gating:** Verifies Free/Starter rejection (403) and Agency authorization.
- **Tenant Isolation:** Verifies User A cannot read or modify User B's competitors or snapshot jobs.
- **SERP Parsing & Matching:** Tests top-ranked (1), mid-ranked (10), deep-ranked (100), not found (>100), ad-filtering, and Amharic keyword queries.
- **Celery Tasks:** Tests async task execution, error isolation on failure, and weekly schedule idempotency.
- **REST APIs:** Tests complete CRUD workflow, snapshot triggers, latest matrix endpoint, and alias routes.

---

## 12. Known Limitations & Future Considerations

1. **SERP Depth Window:** Google Ethiopia SERPs are inspected up to the standard top-100 window. Competitors ranking past position 100 are recorded as `not_found`.
2. **Rate Limiting:** Google Ethiopia applies anti-scraping countermeasures on high concurrency. The service applies politeness delays (1.0s) between keyword queries.
3. **No Direct Site Crawling:** By design, competitor pages are not crawled; only their visibility in Google Ethiopia search results is recorded.
