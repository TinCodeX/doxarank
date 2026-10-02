# Production Google Ethiopia SERP & Rank Tracking Architecture

## 1. Overview & System Target
DoxaRank's Rank Tracker service provides automated, resilient, multi-lingual search engine ranking observation against **Google Ethiopia (`google.com.et`)**. It fulfills the core SRS specification:

> *"Rank tracker: Amharic + English keywords tracked against google.com.et"*
> *"Rank tracker MVP — daily google.com.et SERP scrape for a handful of keywords"*

The production implementation hardens network safety, request throttling, response validation, organic link parsing, multi-tenant data isolation, device emulation, and Celery background task execution.

---

## 2. Google Ethiopia Target & Network Boundaries

### 2.1 Fixed Search Target
- Outbound queries strictly target **`google.com.et`** (or `www.google.com.et`).
- **No silent domain fallback**: The client never falls back to `google.com`, `google.co.uk`, or other geographic Google domains without user instruction.
- **SSRF Protection**: `APPROVED_GOOGLE_HOSTS` restricts allowable targets strictly to Google search domains (`google.com.et`, `www.google.com.et`, `google.com`, `www.google.com`). Arbitrary or internal URLs are rejected with `ValueError`.

### 2.2 Country & Location Context
- `gl=et`: Geolocation parameter enforces Ethiopian regional search results.
- `pws=0`: Disables Google personalized search biasing.
- `num=100`: Requests the top 100 search results in a single organic SERP view.

---

## 3. Supported Languages & Query Encoding

### 3.1 Multi-Lingual Query Preservation
Search terms in English, Amharic, and Afaan Oromoo are preserved verbatim without destructive normalization, transliteration, or script flattening:
- **English (`en`)**: standard Latin queries.
- **Amharic (`am`)**: Ethiopic (Ge'ez/Fidel) script UTF-8 encoded directly into URL query parameters (`q=...`). Google `hl=am`.
- **Oromo (`om`)**: Afaan Oromoo Latin orthography with apostrophes and accents (`q=...`). Google `hl=om`.

### 3.2 Accept-Language Negotiation
Headers sent with outbound requests mirror browser locales for Ethiopia:
- Amharic: `am,en;q=0.9,en-US;q=0.8`
- Oromo: `om,en;q=0.9,en-US;q=0.8`
- English: `en-US,en;q=0.9,am;q=0.8,om;q=0.7`

---

## 4. Device Context & Emulation

### 4.1 Desktop Emulation
- **User-Agent**: Chrome 128 on Windows 10 x64.
- **Client Hints**: `Sec-CH-UA-Mobile: ?0`, `Sec-CH-UA-Platform: "Windows"`.
- Emulates full-width SERP layout with right-hand side elements and desktop ad placements.

### 4.2 Mobile Emulation
- **User-Agent**: Chrome 128 on Android 14 (Pixel 8).
- **Client Hints**: `Sec-CH-UA-Mobile: ?1`, `Sec-CH-UA-Platform: "Android"`.
- Preserves mobile SERP layout and mobile-specific ad blocks (`.commercial-unit-mobile-top`, etc.).
- The device context (`desktop` vs `mobile`) is stored immutably in `KeywordRanking.device`.

---

## 5. Organic Position Definition & Tracking Window

### 5.1 Organic Position Calculation
- **1-Indexed Integer**: Position #1 represents the first true organic web search result.
- **Non-Organic Exclusion**: The following elements are stripped from the DOM and never counted toward ranking positions:
  - Google Ads (top ads `#tads`, bottom ads `#bottomads`, `#taw`, `div.uEierd`, `div[data-text-ad]`, `aria-label="Ads"` or `"Sponsored"`).
  - Multi-lingual ad labels (`Sponsored`, `Ad`, `Ads`, `ማስታወቂያ`, `Beeksisa`).
  - People Also Ask (PAA) accordions (`.related-question-pair`, `div[data-q]`, `div[jsname="yEVEwb"]`).
  - Knowledge Panels & RHS (`.kp-wholepage`, `.knowledge-panel`, `.osrp-blk`, `#rhs`, `#rhs_block`).
  - Google Universal widgets (Image packs, Video carousels, Google Maps / Local pack `div.o6juwe`).
  - Navigation, search header, and footer controls (`#searchform`, `#hdtb`, `#navcnt`, `#fbar`).
  - Internal Google service links (`support.google.com`, `maps.google.com`, etc.).
- **Featured Snippets**: If a website wins the featured snippet, its ranking link is captured as organic rank #1. Internal Google "About featured snippets" links are ignored, and child container duplicates are deduplicated.
- **Top-N Window**: Top 100 results (`rank_idx <= 100`).

### 5.2 Result Statuses (`RankingResultStatus`)
| Status | Position Value | Semantics |
| :--- | :--- | :--- |
| `found` | `1` to `100` | Target website found within the first 100 organic search results. |
| `not_found` | `null` | Target website does not appear in top 100 organic results on Google Ethiopia. (Position is **null**, NOT 100 or 101). |
| `error` | `null` | Check failed due to network timeout, HTTP error, consent screen, CAPTCHA, or malformed HTML. |

---

## 6. Response Validation & Failure Handling

### 6.1 Pre-Parsing Response Verification
Before extracting links, `SerpParser.validate_serp_response(html)` verifies:
1. **Non-Empty Response**: Empty or whitespace-only bodies are flagged as `ERROR`.
2. **Bot Block & CAPTCHA Detection**: Pages with `"detected unusual traffic"`, `id="captcha-form"`, `/sorry/index`, or Recaptcha markers are classified as `ERROR` ("Google automated query block / CAPTCHA detected").
3. **Cookie Consent Screens**: Pages from `consent.google.com` or containing `"Before you continue to Google"` are classified as `ERROR`.
4. **SERP Landmark Verification**: Requires Google search landmarks (`id="search"`, `id="rso"`, `id="center_col"`, `id="rcnt"`, `class="g"`, `class="MjjYud"`, `data-sokoban-container`) or valid zero-result indicators. Malformed HTML without search landmarks is rejected with `ERROR`.

### 6.2 Data Immutability & Deduplication
- Historical snapshots in `KeywordRanking` are immutable records of historical visibility.
- Concurrency protection: `update_or_create` on `(keyword, search_engine, country, language, device, recorded_at)` prevents unique constraint violations during rapid automated re-checks.
- Duplicate job prevention: ViewSet blocks launching new batch jobs when an active job is already `PENDING` or `RUNNING`.

---

## 7. Network Safety, Timeouts, and Rate Limiting

### 7.1 Explicit Granular Timeouts
Outbound HTTP requests through `GoogleEtSerpClient` use explicit `httpx.Timeout` settings:
- **Connect Timeout**: 5.0 seconds
- **Read Timeout**: 10.0 seconds
- **Write Timeout**: 5.0 seconds
- **Total/Pool Timeout**: 15.0 seconds
No request hangs indefinitely.

### 7.2 Controlled Request Pacing (Politeness)
- **Default Delay**: 0.5s politeness delay between consecutive keyword searches in batch checks and daily Celery Beat tasks.
- **Backoff on 429/503**: Exponential backoff (`delay * 2^attempt`) on transient rate limits (HTTP 429 / 503) or socket timeouts.
- **Bounded Concurrency**: Celery tasks execute sequentially per worker queue without bursting hundreds of parallel requests against Google.
- **Anti-Bot Ethics**: DoxaRank does **not** employ CAPTCHA bypasses, residential proxy rotation, or fingerprint evasion. Blocked requests cleanly surface diagnostic operational errors.

---

## 8. Celery Background Jobs & Scheduled Checks

### 8.1 Celery Tasks
- `apps.seo.tasks.check_keyword_ranking`: Single keyword asynchronous rank check.
- `apps.seo.tasks.run_project_rank_check`: Project-wide batch rank check tracking `RankCheckJob` transitions (`PENDING` -> `RUNNING` -> `COMPLETED` / `PARTIAL_FAILURE` / `FAILED`).
- `apps.seo.tasks.run_daily_rank_checks`: Periodic Celery Beat task executing daily at 00:00 UTC.

### 8.2 Daily Scheduled Check Idempotency & Safety
- **Subscription Gating**: Free plan users are skipped; Starter (up to 50 keywords) and Agency (up to 500 keywords) users are processed.
- **Daily Idempotency**: Keywords with a snapshot already recorded today (`recorded_at__date=today`) are skipped.
- **Error Isolation**: Failure on one keyword or project does not halt processing of other projects.

---

## 9. Subscription Entitlement Alignment
| Tier | Keyword Limit | Rank Tracking Access | Features Included |
| :--- | :--- | :--- | :--- |
| **Free** | 3 keywords | ❌ Blocked (`403 Forbidden`) | Basic SEO tools |
| **Starter** | 50 keywords | ✅ Full access | Google Ethiopia Rank Tracking, Technical Crawler |
| **Agency** | 500 keywords | ✅ Full access | Rank Tracking, Weekly Competitor SERP Snapshots |

---

## 10. Test Suite Coverage & Verification Matrix

### 10.1 Deterministic Test Suite (`apps.seo.tests_rank_tracker`)
- **65 Automated Tests**:
  - Model constraints, aliases (`TrackedKeyword`, `RankingSnapshot`), and indexes.
  - 16 Realistic Fixture-Based Parser Scenarios:
    1. Normal English SERP
    2. Amharic Ge'ez SERP
    3. Afaan Oromoo SERP
    4. Advertisements (top & bottom ads filtered)
    5. People Also Ask (PAA accordion links ignored)
    6. Featured Snippets (rank #1 detection, Google internal URLs ignored)
    7. Missing keywords (`NOT_FOUND`, `position=None`)
    8. Multiple organic results (monotonic 1-based order)
    9. Sitelink & duplicate URL deduplication
    10. Unicode punctuation (`፡`, `።`, `'`)
    11. Google Cookie Consent screens (`ERROR`)
    12. Malformed / unexpected HTML (`ERROR`)
    13. Empty SERP HTML (`ERROR`)
    14. HTTP 500/404 errors
    15. Connection timeouts
    16. HTTP 429 rate limit backoff
  - Service tests for single/multiple keywords, mixed languages, desktop/mobile devices, partial/complete job failures, tenant isolation, and subscription limits.

### 10.2 Downstream Compatibility Verification
- `apps.seo.tests_competitor_snapshots`: 28 tests passing (reusing `GoogleEtSerpClient` and `SerpParser`).
- `apps.seo.tests_recommendations`: 31 tests passing (consuming `RankingResultStatus.FOUND`, `NOT_FOUND`, position deltas).
- `apps.integrations apps.users apps.projects apps.subscriptions apps.seo.tools`: 218 tests passing.
- Dashboard frontend (`npm run build`): Clean TypeScript build with zero errors.

---

## 11. Known Google SERP Limitations & Real-World Realities

1. **SERP DOM Mutability**:
   Google frequently runs A/B experiments and alters container class names (e.g. `div.g` vs `div.MjjYud` vs `div[data-sokoban-container]`). The parser uses multiple fallback strategies (container inspection, anchor-H3 wrapping, landmark verification), but real-world monitoring is necessary.
2. **IP Rate Limiting & CAPTCHAs**:
   Requests originating from standard cloud hosting provider IPs (AWS, GCP, DigitalOcean, Hetzner) are frequently met with Google CAPTCHAs or 429 blocks. The service reports `RankingResultStatus.ERROR` cleanly and does not fabricate positions.
3. **Difference Between Deterministic Mocks and Live Google Testing**:
   Unit tests use static, reproducible fixtures to guarantee deterministic CI/CD builds. In real production deployments, outbound Google Ethiopia queries must be tested against live network conditions with appropriate network routing.
