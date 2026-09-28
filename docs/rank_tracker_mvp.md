# DoxaRank Rank Tracker MVP Architecture

## 1. Overview
The Rank Tracker MVP provides automated, historical search engine ranking tracking for English and Amharic keywords against Google Ethiopia (**`google.com.et`**). It fulfills the original DoxaRank SRS specification:

> *"Rank tracker: Amharic + English keywords tracked against google.com.et"*
> *"Rank tracker MVP — daily google.com.et SERP scrape for a handful of keywords"*

The feature allows Starter and Agency subscribers to configure keywords, launch manual on-demand ranking checks, run daily automated checks via Celery Beat, track historical position changes (+/-), and view visual trend indicators directly in the DoxaRank dashboard.

---

## 2. Architecture & System Flow

```
                      +-----------------------------+
                      |   Dashboard / React Client  |
                      +-----------------------------+
                                     |
                        POST /api/seo/rankings/check/
                                     v
                      +-----------------------------+
                      |     Django REST ViewSet     |
                      |  - IsAuthenticated         |
                      |  - Project Ownership        |
                      |  - PlanEntitlementService   |
                      |    (FeatureCode.RANK_TRACKING)|
                      +-----------------------------+
                                     |
                                  enqueue
                                     v
                      +-----------------------------+
                      |    Celery Worker (Redis)    |
                      |  - check_keyword_ranking    |
                      |  - run_project_rank_check   |
                      |  - run_daily_rank_checks    |
                      +-----------------------------+
                                     |
                         RankTrackerService
                                     v
                      +-----------------------------+
                      |   GoogleEtSerpClient        |
                      |  - Fixed host: google.com.et|
                      |  - SSRF-protected           |
                      |  - Bounded retries          |
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
                      |          SerpParser         |
                      |  - Filters ads & widgets    |
                      |  - Extracts organic results |
                      |  - Normalizes target domain |
                      |  - Detects position (1-100) |
                      +-----------------------------+
                                     |
                                  persist
                                     v
                      +-----------------------------+
                      |  RankingSnapshot            |
                      |  (KeywordRanking model)     |
                      |  - position (nullable)      |
                      |  - result_status            |
                      |  - ranking_url & title      |
                      |  - delta metrics            |
                      +-----------------------------+
```

---

## 3. Data Model

### `Keyword` (Alias: `TrackedKeyword`)
Represents a search query tracked for a specific project.
- `project`: Foreign key to `Project` (cascade delete).
- `keyword`: Search query string (Charfield, max 255). Amharic UTF-8 keywords are stored verbatim without transliteration.
- `search_engine`: Default `'google'`.
- `search_domain`: Default `'google.com.et'`.
- `country`: Default `'ET'` (Ethiopia).
- `language`: `'en'` (English) or `'am'` (Amharic).
- `device`: `'desktop'` or `'mobile'`.
- `is_active`: Boolean flag indicating active tracking.
- `created_at` / `updated_at`: Audit timestamps.
- **Constraint**: `unique_keyword_configuration_per_project` (`project`, `keyword`, `search_engine`, `country`, `language`, `device`).

### `KeywordRanking` (Alias: `RankingSnapshot`)
Stores an individual ranking observation point.
- `keyword`: Foreign key to `Keyword`.
- `position`: Positive integer (1-100) or `null` when outside the top 100 organic SERP results.
- `result_status`: `found` (in top 100), `not_found` (outside top 100), or `error` (network/parsing error).
- `ranking_url`: Exact URL of the landing page found in the organic SERP snippet.
- `title`: Extracted SERP title snippet.
- `search_engine`: `'google'`.
- `search_domain`: `'google.com.et'`.
- `country`: `'ET'`.
- `language`: `'en'` or `'am'`.
- `device`: `'desktop'` or `'mobile'`.
- `error_message`: Error details if check failed.
- `recorded_at`: Timestamp of the ranking check.
- **Indexes**: `seo_kw_rk_kw_rec_idx` (`keyword`, `-recorded_at`), `seo_kw_rk_stat_rec_idx` (`result_status`, `-recorded_at`).
- **Constraint**: `unique_ranking_observation_per_time`.

### `RankCheckJob`
Represents an asynchronous rank check batch or single-keyword job execution.
- `project`: Foreign key to `Project`.
- `status`: `pending`, `running`, `completed`, `failed`, `partial_failure`.
- `total_keywords`: Total keywords queued.
- `completed_keywords`: Number successfully checked.
- `failed_keywords`: Number failed.
- `trigger`: `'manual'`, `'single_keyword'`, or `'scheduled_daily'`.
- `started_at` / `completed_at`: Execution timing.
- `error_message`: Diagnostic failure message.

---

## 4. SERP Fetching & Parsing Engine

### `GoogleEtSerpClient`
- **Target**: `google.com.et` (with fallback to `www.google.com.et`).
- **Query Construction**:
  `https://www.google.com.et/search?q={urllib.parse.quote(keyword)}&hl={hl}&gl=et&num=100&pws=0`
  - `hl='am'` for Amharic keywords, `hl='en'` for English.
  - `gl='et'` fixes geographic ranking context to Ethiopia.
  - `pws='0'` disables personalization biases.
- **Network Politeness & Concurrency**:
  - Configurable politeness delay between requests (default: 0.5s - 1.5s, 0s in tests).
  - Bounded retries: 2 retries with exponential backoff on HTTP 429/503 or transient network timeouts.
  - Timeout: 15.0 seconds per request.
- **Security / SSRF Boundaries**:
  - Hardcoded `APPROVED_GOOGLE_HOSTS` allowlist (`google.com.et`, `www.google.com.et`, `google.com`, `www.google.com`).
  - Rejects arbitrary user-supplied target domains.

### `SerpParser`
- **Ad & Widget Filtering**:
  Decomposes `#tads`, `#bottomads`, `div[data-text-ad]`, `.kp-wholepage`, `.knowledge-panel`, `.related-question-pair` (People Also Ask), and navigation elements before parsing.
  Recognizes ad indicators in English ("Sponsored", "Ad") and Amharic ("ማስታወቂያ").
- **Two-Tier Extraction Strategy**:
  1. *Primary*: Queries standard organic result containers (`div.g`, `div.MjjYud`, `div[data-sokoban-container]`).
  2. *Fallback*: Locates all `a[href]` elements wrapping `h3` heading tags.
- **Redirect Unwrapping**:
  Unwraps `/url?q=...` Google redirect wrappers to canonical target URLs.
- **Domain Normalization & Matching**:
  Canonicalizes project website URLs and SERP candidate URLs (lowercasing, stripping `www.`, matching root domain and subdomains).
- **Position Output**:
  1-based index (1-100) or `null` if not found in top 100 results.

---

## 5. Subscription Gating & Quotas

Rank tracking is gated strictly through the existing `PlanEntitlementService` and `FeatureCode.RANK_TRACKING`:
- **Free Tier**:
  - `FeatureCode.RANK_TRACKING` is **not entitled**.
  - Rank tracking checks (`/api/seo/rankings/check/`) return **403 Forbidden**.
  - Keyword creation capped at 3 keywords.
- **Starter Tier**:
  - `FeatureCode.RANK_TRACKING` is **entitled**.
  - Tracked keywords allowed: up to **50 keywords**.
- **Agency Tier**:
  - `FeatureCode.RANK_TRACKING` is **entitled**.
  - Tracked keywords allowed: up to **500 keywords**.

---

## 6. Celery Background Tasks & Daily Scheduling

- `check_keyword_ranking(keyword_id)`:
  Asynchronous single-keyword check.
- `run_project_rank_check(project_id, job_id)`:
  Asynchronous batch check for all active keywords of a project. Transitions `RankCheckJob` through `PENDING -> RUNNING -> COMPLETED / PARTIAL_FAILURE / FAILED`.
- `run_daily_rank_checks()`:
  Scheduled daily via `CELERY_BEAT_SCHEDULE['daily-rank-tracker-checks']` (every 24h / 86400s).
  - Evaluates active keywords belonging to users with `FeatureCode.RANK_TRACKING`.
  - **Idempotency**: Skips keywords that already have a ranking snapshot recorded today (`recorded_at__date == today`).
  - **Error Isolation**: Individual keyword network or parsing errors do not halt remaining keywords.

---

## 7. Position Change & Metrics Calculation

Given the two most recent snapshots for a keyword:
- `current_position`: latest observation position (e.g. 5, or null)
- `previous_position`: prior observation position (e.g. 8, or null)
- `change`: `previous_position - current_position`
  - E.g. Previous 8, Current 5 -> `change = +3` (improved by 3 positions)
  - E.g. Previous 5, Current 8 -> `change = -3` (dropped by 3 positions)
- `change_status`:
  - `improved`: `change > 0`
  - `declined`: `change < 0`
  - `unchanged`: `change == 0`
  - `entered`: Current position found, previous was not found
  - `dropped`: Current position not found, previous was found
  - `new`: Only 1 observation recorded
  - `not_found`: Both current and previous are outside top 100

---

## 8. REST API Reference

| Method | Endpoint | Description | Gating |
|---|---|---|---|
| `GET` | `/api/seo/keywords/?project_id=<id>` | List tracked keywords | Authentication + Project Owner |
| `POST` | `/api/seo/keywords/` | Create new keyword | Authentication + Keyword Limit |
| `POST` | `/api/seo/keywords/<id>/check/` | Check ranking for specific keyword | Authentication + `RANK_TRACKING` |
| `POST` | `/api/seo/rankings/check/` | Launch check (keyword or project batch) | Authentication + `RANK_TRACKING` |
| `GET` | `/api/seo/rankings/summary/?project_id=<id>` | Aggregate ranking summary with delta metrics | Authentication + Project Owner |
| `GET` | `/api/seo/rankings/history/?keyword_id=<id>` | Historical snapshots for a keyword | Authentication + Keyword Owner |
| `GET` | `/api/seo/rankings/jobs/?project_id=<id>` | List async rank check jobs | Authentication + Project Owner |
| `GET` | `/api/seo/rankings/jobs/<job_id>/` | Get job status & counts | Authentication + Project Owner |

---

## 9. Fragility & Known Limitations of Google SERP Scraping

1. **SERP Markup Volatility**:
   Google frequently alters DOM class names, obfuscates CSS tags, and tests new SERP layouts. The parser employs multi-strategy fallbacks (`div.g`, `div.MjjYud`, and `a > h3`), but severe Google layout revamps may necessitate parser updates.
2. **Automated Query Detection (CAPTCHA / 429)**:
   Google monitors rapid, unauthenticated scraping. If CAPTCHA is detected, the engine flags `result_status='error'` with `"Google CAPTCHA / automated query block detected"` rather than fabricating false rankings.
3. **DataForSEO / Proxy Architecture Boundary**:
   In accordance with the SRS milestone boundaries, this MVP is configured for `google.com.et` SERP scraping. Commercial SERP proxy providers or DataForSEO APIs can be plugged in behind `GoogleEtSerpClient` in future milestones without changing the domain models or dashboard interfaces.

---

## 10. Local Development & Verification

### Run dedicated rank tracker tests:
```bash
python manage.py test apps.seo.tests_rank_tracker
```

### Run crawler regression tests:
```bash
python manage.py test apps.seo.tests_crawler
```

### Run cross-app regression test suite:
```bash
python manage.py test apps.integrations apps.users apps.projects apps.subscriptions apps.seo.tools
```

### Build dashboard frontend:
```bash
cd dashboard
npm run build
```
