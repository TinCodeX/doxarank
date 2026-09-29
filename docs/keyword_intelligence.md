# DoxaRank Keyword Intelligence: Search Volume & CPC

**Original DoxaRank SRS Feature**  
**Audience:** Core Engineering, Product, SEO Operations  
**Status:** Implemented & Verified  

---

## 1. Executive Summary

Keyword Intelligence extends DoxaRank's tracked keywords beyond ranking positions by providing macroeconomic search demand data, including:
- **Monthly Search Volume:** Average monthly query impressions on Google.
- **Cost Per Click (CPC):** Advertiser bid estimates in USD/ETB.
- **Competition:** Categorical (`LOW`, `MEDIUM`, `HIGH`) and numerical index (`0.0`–`1.0`).
- **Keyword Difficulty:** Organic ranking competitiveness estimate (0–100).
- **Search Intent:** Deterministic multilingual query classification (`transactional`, `commercial`, `informational`, `navigational`).
- **Data Source & Freshness:** Distinguishes live third-party provider data from mock and unconfigured states with clear error transparency.

---

## 2. Architecture & Data Model

Keyword Intelligence directly augments the existing `Keyword` model architecture without duplicating systems.

```
┌─────────────────────────────────┐
│         Project (Tenant)        │
└────────────────┬────────────────┘
                 │ 1
                 │ *
┌────────────────▼────────────────┐
│             Keyword             │◄────────────┐
│  - keyword: str                 │             │
│  - search_engine: google        │             │
│  - search_domain: google.com.et │             │
│  - country: ET                  │             │
│  - language: en | am | om       │             │
└────────┬────────────────────────┘             │
         │ 1                              1     │
         │ 1                              *     │
┌────────▼────────────────────────┐ ┌───────────┴─────────────────────┐
│       KeywordIntelligence       │ │    KeywordIntelligenceSnapshot   │
│ (Current cached intelligence)   │ │ (Historical trend snapshots)     │
│  - search_volume: int           │ │  - search_volume: int           │
│  - cpc: Decimal(10, 4)          │ │  - cpc: Decimal(10, 4)          │
│  - currency: str (USD/ETB)      │ │  - competition: LOW/MED/HIGH    │
│  - competition: LOW/MED/HIGH    │ │  - recorded_at: DateTime        │
│  - intent: transactional/...    │ └─────────────────────────────────┘
│  - status: FRESH/STALE/...      │
│  - last_refreshed_at: DateTime  │
└─────────────────────────────────┘
```

### Database Tables:
1. `seo_keywords`: Existing keyword tracking table.
2. `seo_keyword_intelligence`: One-to-one current cached state with `status` (`FRESH`, `STALE`, `REFRESHING`, `UNAVAILABLE`, `ERROR`), `last_refreshed_at`, and raw metadata.
3. `seo_keyword_intelligence_snapshots`: Point-in-time historical records preserved across refreshes.

---

## 3. Ethiopia-First Search Intelligence

DoxaRank is purpose-built for the Ethiopian digital economy:
- **Target Country:** `ET` (Ethiopia)
- **Target Domain:** `google.com.et`
- **Supported Languages:**
  - `en` (English)
  - `am` (Amharic / አማርኛ)
  - `om` (Afaan Oromoo)
- **Full Unicode Support:** Amharic Ge'ez characters (`የአዲስ አበባ ሆቴል`, `የኢትዮጵያ ሆቴሎች`, `ቡና መግዛት`) and Oromo characters (`hoteelaa Finfinnee`, `buna bituu`) are preserved without destructive normalization.

---

## 4. Provider Layer Abstraction

To ensure testability and prevent vendor lock-in or fabricated random numbers:
```
           BaseKeywordIntelligenceProvider
                         │
     ┌───────────────────┼───────────────────┐
     ▼                   ▼                   ▼
UnconfiguredProvider   MockProvider    DataForSEOProvider
  (Safe fallback)      (Test suite)     (Live API ET=2231)
```

1. **`UnconfiguredProvider`**:
   - Safe fallback when credentials are not configured on the server.
   - Sets `status = UNAVAILABLE`.
   - **Never generates random numbers or fake search volumes.**
2. **`MockKeywordIntelligenceProvider`**:
   - Used in automated unit and regression testing (`settings.KEYWORD_INTELLIGENCE_PROVIDER = 'mock'`).
   - Returns deterministic volumes, CPCs, and competition levels for test fixtures.
   - Flags `source = 'mock'` so mock data is never mistaken for live provider data.
3. **`DataForSEOProvider`**:
   - Production provider integrating DataForSEO Google Ads Search Volume & CPC API.
   - Location code: `2231` (Ethiopia).
   - Authenticates via Basic HTTP Auth using `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD`.
   - Handles HTTP 401/403, 429 rate limits, timeouts, and partial responses safely.

---

## 5. Deterministic Multilingual Search Intent

Search intent is classified strictly through deterministic pattern matching (**zero LLM or Agentic AI dependency**):

| Intent | English Indicators | Amharic Indicators | Oromo Indicators |
| :--- | :--- | :--- | :--- |
| **Transactional** | buy, purchase, price, cheap, booking, reserve, order | ግዛ, መግዛት, ሽያጭ, ዋጋ, ክፈያ, ኪራይ | bituu, bitaa, gurgurtaa, gatii, kaffaltii |
| **Commercial** | best, top, review, vs, compare, agency, hotel, software | ምርጥ, ደረጃ, አወዳድር, ግምገማ, ድርጅት, ሆቴል | filatamaa, caalaa, madaallii, hoteela |
| **Informational** | how, what, why, when, guide, tutorial, tips | እንዴት, ምንድን, ምንድነው, ለምን, መመሪያ | akkamiin, maal, maaliif, qajeelfama |
| **Navigational** | login, sign in, portal, app, official, website | ግባ, መግቢያ, ድህረ ገጽ, መተግበሪያ | seensaa, seeni, marsariitii |

---

## 6. Caching & Freshness Strategy

External SEO keyword APIs carry per-request costs and rate limits. The freshness engine enforces:
1. **Cache TTL:** Defaults to 7 days (`KEYWORD_INTELLIGENCE_CACHE_DAYS = 7`). If data is fresh, cached records are served immediately without making provider calls.
2. **Cooldown Anti-Spam:** Refreshes enforce a 60-second cooldown (`KEYWORD_INTELLIGENCE_REFRESH_COOLDOWN_SECONDS = 60`) unless `force=True`.
3. **Duplicate Prevention:** If an in-progress refresh is already running (`status = REFRESHING`), duplicate Celery tasks or worker calls are avoided.
4. **Failure Preservation:** If a provider refresh fails (timeout, network error), the system marks `status = ERROR` with the diagnostic message, but **never overwrites or wipes previous valid search volume and CPC numbers**.

---

## 7. Subscription Gating & Quotas

Keyword Intelligence is gated under `FeatureCode.RANK_TRACKING`:
- **Free Plan:** Does not include rank tracking or keyword intelligence. Requests to refresh receive `HTTP 403 Forbidden` (`FEATURE_NOT_ENTITLED`).
- **Starter Plan:** Up to 50 tracked keywords with full search volume, CPC, and competition access.
- **Agency Plan:** Up to 500 tracked keywords with full search volume, CPC, and competition access.

---

## 8. API Reference

All endpoints enforce JWT authentication and project ownership isolation.

### `GET /api/seo/keywords/{id}/intelligence/`
Retrieve the current intelligence metrics for a tracked keyword.
```json
{
  "id": 12,
  "keyword": 45,
  "keyword_name": "የአዲስ አበባ ሆቴል",
  "search_volume": 2400,
  "cpc": "0.3500",
  "currency": "USD",
  "competition": "MEDIUM",
  "competition_index": 0.45,
  "difficulty": 28,
  "intent": "commercial",
  "source": "mock",
  "status": "FRESH",
  "error_message": "",
  "last_refreshed_at": "2026-09-29T11:30:00Z",
  "is_fresh": true
}
```

### `POST /api/seo/keywords/{id}/intelligence/refresh/`
Request an updated intelligence fetch from the configured provider.
- Body: `{"force": false}`

### `GET /api/seo/keyword-intelligence/`
List intelligence records belonging to the authenticated user.
- Query parameters: `?project_id=123&keyword_id=45&status=FRESH`

### `POST /api/seo/keyword-intelligence/refresh/`
Bulk refresh intelligence for all active keywords of a project.
- Body: `{"project_id": 123, "force": false}`

### `GET /api/seo/keyword-intelligence/{id}/history/`
Retrieve point-in-time snapshot history for trend analysis.

---

## 9. Configuration & Environment Variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `KEYWORD_INTELLIGENCE_PROVIDER` | `unconfigured` | Provider choice: `unconfigured`, `mock`, `dataforseo`. |
| `KEYWORD_INTELLIGENCE_CACHE_DAYS` | `7` | Cache validity window in days. |
| `KEYWORD_INTELLIGENCE_REFRESH_COOLDOWN_SECONDS` | `60` | Minimum interval before manual re-fetching is allowed. |
| `DATAFORSEO_LOGIN` | `""` | DataForSEO API username/login. |
| `DATAFORSEO_PASSWORD` | `""` | DataForSEO API password/key. |
| `DATAFORSEO_API_URL` | `https://api.dataforseo.com/v3` | DataForSEO base endpoint. |

---

## 10. Known Limitations

1. **Third-Party Credentials:** Without `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD`, production instances safely report `UNAVAILABLE` status and prompt the operator to configure credentials.
2. **Google Ads Data Granularity:** Google Ads Search Volume API aggregates data at the monthly bucket level; daily fluctuations are not provided.
