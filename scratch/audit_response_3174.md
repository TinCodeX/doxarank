# DoxaRank Original SRS Compliance Audit

**Audit Date:** September 24, 2026  
**Audited Repository:** `TinCodeX/doxarank`  
**Audit Scope:** Original Foundational Software Requirements Specification (SRS) for DoxaRank (Ethiopia-First SEO SaaS).  
**Strict Constraint Applied:** All Agentic AI Milestones (Phase 4.1–4.7 and Milestones 5.1–6.7) are **strictly excluded** from fulfilling original SRS requirements.

---

## 1. Executive Summary

| Metric | Count | Percentage |
| :--- | :--- | :--- |
| **Total Original SRS Requirements Audited** | **66** | **100.0%** |
| 🟢 **COMPLETE** | **30** | **45.5%** |
| 🟡 **PARTIAL** | **7** | **10.6%** |
| 🔴 **MISSING** | **28** | **42.4%** |
| ⚪ **NOT VERIFIABLE (External Dependency)** | **1** | **1.5%** |
| **Overall Strict Implementation Percentage (Complete Only)** | — | **45.5%** |
| **Weighted Implementation Percentage (Complete + 50% Partial)** | — | **50.8%** |

### High-Level Audit Findings
1. **Core Backend & Data Layer (Strong):** The backend Django REST Framework architecture is well-structured. Foundational models (`Project`, `Keyword`, `KeywordRanking`, `SiteAudit`, `AuditIssue`, `SearchConsoleConnection`, `SearchAnalyticsData`, `SEOInsight`, `SEORecommendation`) are implemented with strict multi-tenant isolation, automated `seo_` table prefixes, and comprehensive test coverage.
2. **The 10 Standalone SEO Tools (Critical Deficit):** 8 of the 10 original tools are completely **missing**. The Amharic Normalizer exists as a pure backend Python service and model property, while Link Checking exists only within the internal site audit crawler. None of the 10 tools exist as interactive, standalone tools on either the marketing website or the dashboard.
3. **Marketing Site (Stub Only):** The Astro marketing site is an unstyled, empty shell. Key pages (`pricing.astro`, `about.astro`, `contact.astro`, `login.astro`, `signup.astro`, blog, and case studies) are either 0-byte blank files or single-heading stubs.
4. **Integrations (Split):** Google Search Console and Google OAuth2 are implemented in code with AES-256 token encryption at rest. GA4, Microsoft Clarity, Google Tag Manager, and Doxa Payments (Telebirr, Chapa, CBE Birr, Stripe) have **zero backend or frontend implementation**.
5. **Crawler & Rank Tracking (Deviated from SRS):** The crawler was implemented with `httpx` + `BeautifulSoup4` instead of the mandated **Playwright** headless browser. Keyword rankings are recorded manually or via API; automated scheduled scraping of live `google.com.et` SERPs is missing.
6. **Pricing & Monetization (Zero Enforcement):** No tiers (Free / Starter / Agency), feature gating, subscription records, or payment webhook handlers exist anywhere in the backend codebase.
7. **Production & Deployment (Missing):** No Dockerfiles, no `docker-compose.yml`, no Dokploy deployment manifests, and no production domain routing exist.

---

## 2. Product / Architecture

| Requirement | Status | Evidence | Missing / Remaining Work |
| :--- | :--- | :--- | :--- |
| **Django & DRF Backend Structure** | 🟢 COMPLETE | [backend/config/settings.py](file:///c:/Users/bizra/Documents/doxarank/backend/config/settings.py#L39-L60), [backend/config/urls.py](file:///c:/Users/bizra/Documents/doxarank/backend/config/urls.py#L20-L25). Modular apps `users`, `projects`, and `seo` cleanly configured with DRF. | None for foundational backend structure. |
| **Neon PostgreSQL Database Configuration** | 🟢 COMPLETE | [backend/config/settings.py](file:///c:/Users/bizra/Documents/doxarank/backend/config/settings.py#L108-L114), [backend/.env](file:///c:/Users/bizra/Documents/doxarank/backend/.env#L1). Configured using `dj_database_url` with SSL required (`neondb` connection string). | Live cloud connectivity depends on active Neon instance. |
| **`seo_` Database Table Naming Convention** | 🟢 COMPLETE | [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L73), [backend/apps/seo/migrations/0001_initial.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/migrations/0001_initial.py). Models specify `db_table = 'seo_keywords'`, `'seo_keyword_rankings'`, `'seo_site_audits'`, `'seo_audit_issues'`, etc. | `Project` is `projects_project` and `User` is `users_user` (app-namespaced). |
| **RESTful API with DRF ViewSets & Routers** | 🟢 COMPLETE | [backend/apps/seo/urls.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/urls.py#L33-L40), [backend/apps/projects/urls.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/projects/urls.py#L7-L11). DefaultRouter registers `keywords`, `rankings`, `audits`, `issues`, `search-console`, `search-analytics`, and `insights`. | Standalone tool endpoints. |
| **Multi-Project Workspace Data Model** | 🟢 COMPLETE | [backend/apps/projects/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/projects/models.py#L5-L35), [backend/apps/projects/views.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/projects/views.py#L6-L31). `Project` model with `owner` FK to custom User, auto-attribution on create, strict query filtering. | Team collaboration / multi-user workspace roles (currently 1 owner per project). |
| **Celery & Redis Worker Infrastructure** | 🟢 COMPLETE | [backend/config/settings.py](file:///c:/Users/bizra/Documents/doxarank/backend/config/settings.py#L191-L227), [backend/apps/seo/tasks.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/tasks.py#L225-L270). Celery configured with Redis broker and results backend; `run_site_audit` task operational. | Production process supervisor / systemd / Docker service files to run workers in staging/prod. |

---

## 3. Marketing Website

| Requirement | Status | Evidence | Missing / Remaining Work |
| :--- | :--- | :--- | :--- |
| **Landing / Home Page** | 🔴 MISSING | [marketing/src/pages/index.astro](file:///c:/Users/bizra/Documents/doxarank/marketing/src/pages/index.astro#L5-L20). Contains placeholder text `"Tailwind is working!"` and a test button. No product hero, value proposition, or features. | Complete marketing homepage design, copy, testimonials, and feature highlights. |
| **Pricing Page** | 🔴 MISSING | [marketing/src/pages/pricing.astro](file:///c:/Users/bizra/Documents/doxarank/marketing/src/pages/pricing.astro#L5-L10). Only contains a single `<h1>Pricing</h1>` tag (11 lines total). | Complete pricing tables for Free, Starter, and Agency tiers with feature matrices and signup buttons. |
| **Features Overview Page** | 🔴 MISSING | [marketing/src/pages/features.astro](file:///c:/Users/bizra/Documents/doxarank/marketing/src/pages/features.astro#L5-L14). Contains only `<h1>DoxaRank Features</h1>` and `<p>Explore the SEO tools inside DoxaRank.</p>`. | Feature breakdown, screenshots, capability explanations. |
| **Company Pages (About, Contact)** | 🔴 MISSING | `marketing/src/pages/about.astro` (0 bytes), `marketing/src/pages/contact.astro` (0 bytes). Completely empty files. | About company narrative, contact inquiry form, office location. |
| **Content Marketing (Blog & Case Studies)** | 🔴 MISSING | `marketing/src/pages/blog/` (empty directory), `marketing/src/pages/case-studies/` (empty directory). | Astro content collections, markdown blog posts, Ethiopian SEO case studies. |
| **Free Trial & Account Onboarding Links** | 🔴 MISSING | `marketing/src/pages/signup.astro` (0 bytes), `marketing/src/pages/login.astro` (0 bytes). [marketing/src/components/Navbar.astro](file:///c:/Users/bizra/Documents/doxarank/marketing/src/components/Navbar.astro#L33-L46) links to these empty pages instead of dashboard. | Link marketing CTA buttons directly to dashboard auth routes or implement Astro auth redirects. |
| **Public Hosting / Access to 10 Free SEO Tools** | 🔴 MISSING | Zero SEO tools exist anywhere under `marketing/src/pages/`. | Build public interactive pages for each of the 10 SEO tools. |

---

## 4. Authentication & Accounts

| Requirement | Status | Evidence | Missing / Remaining Work |
| :--- | :--- | :--- | :--- |
| **Custom Email-Based User Model** | 🟢 COMPLETE | [backend/apps/users/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/users/models.py#L43-L74). `User` inherits `AbstractBaseUser`, uses `email` as `USERNAME_FIELD`, with `UserManager`. | Tier / subscription fields on User. |
| **User Registration API** | 🟢 COMPLETE | [backend/apps/users/views.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/users/views.py#L12-L30), [backend/test_auth_api.py](file:///c:/Users/bizra/Documents/doxarank/backend/test_auth_api.py#L29-L51). `POST /api/auth/register/` creates user, validates passwords, returns JWT pair. | Email confirmation verification flow. |
| **JWT Login & Token Refresh** | 🟢 COMPLETE | [backend/apps/users/views.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/users/views.py#L32-L55), [backend/test_auth_api.py](file:///c:/Users/bizra/Documents/doxarank/backend/test_auth_api.py#L53-L97). `POST /api/auth/login/` and `POST /api/auth/token/refresh/` using SimpleJWT. | Rate-limiting brute-force login attempts. |
| **Protected Profile Endpoint (`/me/`)** | 🟢 COMPLETE | [backend/apps/users/views.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/users/views.py#L70-L83), [backend/test_auth_api.py](file:///c:/Users/bizra/Documents/doxarank/backend/test_auth_api.py#L74-L88). `GET /api/auth/me/` returns email, first name, last name, date joined. | Profile update (PATCH) endpoint. |
| **Token Blacklisting & Logout** | 🟢 COMPLETE | [backend/apps/users/views.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/users/views.py#L57-L68), [backend/test_auth_api.py](file:///c:/Users/bizra/Documents/doxarank/backend/test_auth_api.py#L100-L121). `POST /api/auth/logout/` blacklists refresh token in `token_blacklist_outstandingtoken`. | None. |
| **Tenant Isolation & Horizontal Security** | 🟢 COMPLETE | [backend/apps/projects/views.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/projects/views.py#L19-L31), [backend/test_projects_api.py](file:///c:/Users/bizra/Documents/doxarank/backend/test_projects_api.py#L75-L105). Cross-tenant reads, updates, and deletes return `404 Not Found`. | Workspace team sharing (if multi-user per project is required). |

---

## 5. 10 SEO Tools

Audit each of the 10 tools individually:

### 1. Meta Tag Generator
- **Status:** 🔴 MISSING
- **Evidence:** Zero files or endpoints exist. No API view in [backend/apps/seo/views.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/views.py), no route in [backend/apps/seo/urls.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/urls.py), and no UI component in [dashboard/src/components](file:///c:/Users/bizra/Documents/doxarank/dashboard/src/components) or [marketing/src/pages](file:///c:/Users/bizra/Documents/doxarank/marketing/src/pages). *(Note: Mentioned only in AI content brief generation prompt in Milestone 4).*
- **Missing / Remaining Work:** Implement a dedicated API endpoint (`POST /api/seo/tools/meta-tag-generator/`) and an interactive frontend form to input title, description, keywords, viewport, and author to generate standard HTML `<meta>` tags with copy-to-clipboard functionality.

### 2. Open Graph / Twitter Card Previewer
- **Status:** 🔴 MISSING
- **Evidence:** Only exists as an internal extraction function in the read-only MCP diagnostics server (`apps/seo/services/mcp/server.py`). No user-facing tool endpoint or preview UI exists in the repository.
- **Missing / Remaining Work:** Build an endpoint (`POST /api/seo/tools/social-preview/`) that parses or takes inputs for `og:title`, `og:image`, `og:description`, `twitter:card` and renders real-time interactive previews of Facebook, LinkedIn, and Twitter feed cards.

### 3. Schema.org / JSON-LD Generator
- **Status:** 🔴 MISSING
- **Evidence:** No standalone tool. The only JSON-LD generation occurs internally inside the LLM prompt of `SEOContentDraftService` ([apps/seo/services/ai_providers.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/ai_providers.py#L955)). No dedicated endpoint or interactive builder exists.
- **Missing / Remaining Work:** Create a dedicated JSON-LD generation engine supporting Article, LocalBusiness (Addis Ababa / Ethiopia schemas), Organization, FAQPage, and BreadcrumbList, with validation against schema.org specifications and an interactive UI generator.

### 4. Robots.txt Tester / Generator
- **Status:** 🔴 MISSING
- **Evidence:** [backend/apps/seo/services/live_site_crawler.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/live_site_crawler.py#L278-L315) parses `robots.txt` using Python's `urllib.robotparser` strictly for crawler compliance. There is no interactive generator, tester, or standalone API endpoint.
- **Missing / Remaining Work:** Implement `POST /api/seo/tools/robots-tester/` (tests user-agent and path rules against input robots.txt) and `POST /api/seo/tools/robots-generator/` with syntax highlighting and validation UI.

### 5. Sitemap Validator / Generator
- **Status:** 🔴 MISSING
- **Evidence:** No sitemap XML parser, validator, or generator exists in `apps/seo/` or frontend.
- **Missing / Remaining Work:** Create an XML sitemap validator checking URL limits (<50,000 URLs), file size (<50MB), valid XML tags (`<loc>`, `<lastmod>`, `<changefreq>`, `<priority>`), and an XML sitemap generator.

### 6. hreflang Builder
- **Status:** 🔴 MISSING
- **Evidence:** Zero code references across the entire repository.
- **Missing / Remaining Work:** Implement an interactive hreflang builder supporting multi-language targeting specifically for Ethiopia (`am-ET`, `en-ET`, `om-ET`, `ti-ET`, `x-default`) generating HTML `<link rel="alternate" hreflang="..." />` tags, HTTP headers, and XML sitemap hreflang annotations.

### 7. SERP Snippet Preview / Pixel-Length Checker
- **Status:** 🔴 MISSING
- **Evidence:** No pixel-length calculation algorithms (e.g. Arial 600px desktop title limit, 960px snippet limit) exist in frontend or backend.
- **Missing / Remaining Work:** Implement an interactive Google SERP simulator component with exact pixel length calculation for desktop (600px max title, ~960px description) and mobile (simulating Google mobile search cards) with real-time truncation warning indicators.

### 8. PageSpeed / Core Web Vitals Analyzer
- **Status:** 🔴 MISSING
- **Evidence:** No Google PageSpeed Insights API client, Lighthouse runner, or Core Web Vitals (LCP, FID/INP, CLS) metric ingestion exists in backend or frontend.
- **Missing / Remaining Work:** Integrate Google PageSpeed Insights REST API (`https://www.googleapis.com/pagespeedonline/v5/runPagespeed`) to fetch mobile/desktop performance, accessibility, best practices, SEO scores, and CrUX field data.

### 9. Single-Page Broken Link Checker
- **Status:** 🟡 PARTIAL
- **Evidence:** [backend/apps/seo/services/live_site_crawler.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/live_site_crawler.py#L540-L600) extracts all links from HTML and records 404 / 500 status codes as `AuditIssue` items during full site audits. However, there is no standalone single-page link checker API or interactive UI tool.
- **Missing / Remaining Work:** Create a lightweight single-URL endpoint (`POST /api/seo/tools/broken-links/`) that scans a single target webpage, tests all internal/external links concurrently, and returns broken links, anchor text, and HTTP status codes in an interactive table.

### 10. Amharic Fidel Keyword Normalizer
- **Status:** 🟡 PARTIAL
- **Evidence:** 
  - Backend service: [backend/apps/seo/services/amharic_normalizer.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/amharic_normalizer.py#L68-L103) (`normalize_amharic_query`, `are_keywords_equivalent`, `GEEZ_HOMOPHONE_MAP` covering Ha, Se, A, Tse homophones across 1st-7th orders, plus Ethiopic punctuation collapsing).
  - Model integration: [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L88-L94) exposes `Keyword.normalized_keyword`.
  - Tests: [backend/apps/seo/tests.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/tests.py#L11416-L11450) validates with 22 dedicated test assertions.
  - **Gap:** No standalone public API endpoint (`POST /api/seo/tools/amharic-normalizer/`) and no dedicated interactive UI tool for users to paste Amharic text and inspect normalized forms.
- **Missing / Remaining Work:** Add a dedicated public API endpoint and an interactive frontend widget demonstrating Amharic Fidel homophone normalization with before/after diffs.

---

## 6. SEO Tracking & Analytics

| Requirement | Status | Evidence | Missing / Remaining Work |
| :--- | :--- | :--- | :--- |
| **Track Target Keywords** | 🟢 COMPLETE | [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L26-L86), [backend/apps/seo/views.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/views.py) (`KeywordViewSet`). Full CRUD with project association, active toggle, and uniqueness constraints. | None. |
| **Keyword Language & Country Settings** | 🟢 COMPLETE | [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L47-L58). `country` defaults to `Country.ET`, `language` choices `en` and `am`, `device` desktop/mobile. | Regional languages (Oromo, Tigrinya). |
| **Keyword Search Volume & Tags** | 🔴 MISSING | [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L26-L70). `Keyword` model has no `search_volume`, `cpc`, `competition`, or `tags` fields. | Add `search_volume`, `cpc`, and tagging fields/models to `Keyword`. |
| **Keyword Ranking Position History** | 🟢 COMPLETE | [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L97-L161) (`KeywordRanking`). Records `position`, `ranking_url`, `recorded_at`, `device`, `country`. Verified in [backend/test_seo_rankings_api.py](file:///c:/Users/bizra/Documents/doxarank/backend/test_seo_rankings_api.py). | Best/worst rank aggregate helper methods on model. |
| **Rank Position Change Calculation** | 🟢 COMPLETE | [backend/apps/seo/serializers.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/serializers.py#L100-L150) calculates previous position, delta, and trend direction. Exposes changes on ranking endpoints. | Historical 30-day sparkline serialization. |
| **Automated Live SERP Scraper** | 🔴 MISSING | [backend/apps/seo/tasks.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/tasks.py). No periodic Celery task or scraping service exists to fetch live search results. Rankings can only be recorded via manual REST API POST. | Implement a live SERP fetcher (or DataForSEO/SerpAPI provider) and schedule daily tracking runs in Celery Beat. |
| **Competitor Domain & SERP Tracking** | 🔴 MISSING | [docs/phase_4_9_gap_analysis.md](file:///c:/Users/bizra/Documents/doxarank/docs/phase_4_9_gap_analysis.md#L27). No `Competitor` model, no competitor domain tracking, and no SERP competitor overlap matrix. | Create `CompetitorDomain` model, track competitor rankings against shared keywords, calculate visibility share. |
| **Rule-Based SEO Insights Engine** | 🟢 COMPLETE | [backend/apps/seo/services/seo_intelligence.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/seo_intelligence.py#L1-L250), [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L320-L400) (`SEOInsight`). Generates deterministic insights on rank drops, low CTR, missing meta tags. | Live event webhooks on new critical insights. |
| **Explainable SEO Recommendations** | 🟢 COMPLETE | [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L410-L480) (`SEORecommendation`), [backend/apps/seo/views.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/views.py) (`SEORecommendationViewSet`). Structured action proposals linked to originating insights. | User feedback rating on recommendations. |

---

## 7. Integrations

Distinction categories:
- **A. Implemented in Code:** Code architecture and logic are written in the repo.
- **B. Credentials Required:** External API keys / OAuth credentials are required in configuration.
- **C. Configured:** Configuration variables exist in active `.env` or settings.
- **D. Verified:** Tested via end-to-end integration or mocked test suites.
- **E. Operational:** Functioning in production.

| Integration | Code Exists | Credentials Required | Configured | Verified | Operational | Audit Status | Evidence & Details |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Google OAuth2** | YES | YES | NO (Empty in `.env`) | YES (Mocked) | NO | 🟢 COMPLETE (Code) / ⚪ NOT VERIFIABLE (Prod) | [apps/seo/services/google_oauth.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/google_oauth.py#L1-L150). State encryption, code exchange, refresh token handling. Tested in [test_search_console_api.py](file:///c:/Users/bizra/Documents/doxarank/backend/test_search_console_api.py). |
| **Google Search Console (GSC)** | YES | YES | NO | YES (Mocked) | NO | 🟢 COMPLETE (Code) / ⚪ NOT VERIFIABLE (Prod) | [apps/seo/services/google_search_console.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/google_search_console.py#L1-L200), [models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L250-L320). Ingests query, page, country, device, clicks, impressions, CTR, position. |
| **Google Analytics 4 (GA4)** | NO | YES | NO | NO | NO | 🔴 MISSING | Zero code, models, or views exist. Confirmed in [docs/phase_4_9_gap_analysis.md](file:///c:/Users/bizra/Documents/doxarank/docs/phase_4_9_gap_analysis.md#L25). |
| **Microsoft Clarity** | NO | YES | NO | NO | NO | 🔴 MISSING | Zero code, models, or UI embed scripts exist. Confirmed in [docs/phase_4_9_gap_analysis.md](file:///c:/Users/bizra/Documents/doxarank/docs/phase_4_9_gap_analysis.md#L25). |
| **Google Tag Manager (GTM)** | NO | YES | NO | NO | NO | 🔴 MISSING | Zero GTM container ID management or tracking code injection exists. |
| **Doxa Payments (Telebirr / Chapa / CBE / Stripe)** | NO | YES | NO | NO | NO | 🔴 MISSING | Zero payment models, webhooks, or gateway SDKs exist. Confirmed in [docs/phase_4_9_gap_analysis.md](file:///c:/Users/bizra/Documents/doxarank/docs/phase_4_9_gap_analysis.md#L31). |

---

## 8. Crawler & Technical SEO

| Requirement | Status | Evidence | Missing / Remaining Work |
| :--- | :--- | :--- | :--- |
| **Website Crawler Engine** | 🟢 COMPLETE | [backend/apps/seo/services/live_site_crawler.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/live_site_crawler.py#L1-L150). Bounded BFS crawler using `httpx` + `BeautifulSoup4`. Extracts title, meta, canonical, H1-H6, images, links. | Headless JS execution. |
| **Playwright Dynamic JS Rendering** | 🔴 MISSING | Grep search for `playwright` yields 0 matches in repository. Requirements in [requirements.txt](file:///c:/Users/bizra/Documents/doxarank/backend/requirements.txt) only list `httpx`, `beautifulsoup4`. | Install `playwright`, configure Chromium headless worker, execute client-side SPA rendering. |
| **Robots.txt Crawl Compliance** | 🟢 COMPLETE | [backend/apps/seo/services/live_site_crawler.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/live_site_crawler.py#L278-L315). Fetches `/robots.txt`, parses directives, skips disallowed paths, handles 404/500 safe fallbacks. Tested in [tests.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/tests.py#L7233). | None for crawler compliance. |
| **Crawl Boundaries & Politeness** | 🟢 COMPLETE | [backend/apps/seo/services/live_site_crawler.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/live_site_crawler.py#L40-L70). Enforces `max_pages`, `max_depth`, `timeout`, `max_response_size`, `polite_delay`, same-domain constraint. | Configurable per-project polite delay. |
| **Celery Asynchronous Crawl Execution** | 🟢 COMPLETE | [backend/apps/seo/tasks.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/tasks.py#L225-L270) (`run_site_audit`). Dispatches crawl asynchronously, tracks status, updates progress. | Real-time crawl progress percentage over WebSockets. |
| **Technical SEO Audit Engine & Scoring** | 🟢 COMPLETE | [backend/apps/seo/services/seo_audit_engine.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/seo_audit_engine.py#L1-L200). Generates 0–100 SEO health score based on weighted deductions. | Configurable weight thresholds per project. |
| **Audit Issue Classification** | 🟢 COMPLETE | [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L170-L175) (`IssueSeverity.CRITICAL`, `WARNING`, `NOTICE`). Models store `issue_type`, `description`, `url`, `recommendation`. | Bulk issue status resolution in API. |

---

## 9. Rank Tracking & SERP

| Requirement | Status | Evidence | Missing / Remaining Work |
| :--- | :--- | :--- | :--- |
| **Amharic Keyword Tracking** | 🟢 COMPLETE | [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L18) (`Language.AM`). Normalized via [apps/seo/services/amharic_normalizer.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/amharic_normalizer.py#L68). | Automated scraping of Amharic queries. |
| **English Keyword Tracking** | 🟢 COMPLETE | [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L17) (`Language.EN`). Default language for tracking. | Automated scraping of English queries. |
| **`google.com.et` Target Search Engine** | 🟡 PARTIAL | [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L47-L52). Model sets `country='ET'` and `search_engine='google'`. However, no live scraper connects to `google.com.et`. | Build or integrate external scraper specifically targeting `google.com.et` localized SERPs. |
| **`.et` Domain Tracking** | 🟢 COMPLETE | [backend/apps/projects/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/projects/models.py#L20-L23). Supports `.et` canonical URLs (e.g. `https://ethiotelecom.et` verified in [test_seo_keywords_api.py](file:///c:/Users/bizra/Documents/doxarank/backend/test_seo_keywords_api.py#L53)). | Local registrar / WHOIS lookup for `.et` domains. |
| **Competitor SERP Snapshots** | 🔴 MISSING | No snapshot model or top 10/100 organic result storage exists in the database. | Implement `SERPSnapshot` model storing top 100 ranking URLs, titles, and snippets per query. |
| **Ranking Persistence & Time-Series History** | 🟢 COMPLETE | [backend/apps/seo/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/models.py#L142-L157). `KeywordRanking` indexed by `recorded_at` with unique constraint per observation. | Aggregated weekly/monthly rollups for long-term retention. |
| **Automated Rank Tracking Scheduling** | 🔴 MISSING | [backend/config/settings.py](file:///c:/Users/bizra/Documents/doxarank/backend/config/settings.py#L210-L227). `CELERY_BEAT_SCHEDULE` contains continuous AI operations but **zero** keyword ranking check tasks. | Add periodic Celery Beat task `schedule_daily_keyword_rankings`. |

---

## 10. Pricing & Monetization

| Requirement | Status | Evidence | Missing / Remaining Work |
| :--- | :--- | :--- | :--- |
| **Pricing Tiers (Free, Starter, Agency)** | 🔴 MISSING | Neither [apps/users/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/users/models.py) nor [apps/projects/models.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/projects/models.py) contains any tier definition or enum. | Define `SubscriptionTier` (`FREE`, `STARTER`, `AGENCY`) on User/Project models. |
| **Backend Subscription Logic** | 🔴 MISSING | No subscription models, billing status, expiration timestamps, or invoices exist anywhere in backend. | Create `Subscription` model tracking status, plan, billing period, and renewal dates. |
| **Feature Gating & Limits Enforcement** | 🔴 MISSING | Views allow unlimited projects, keywords, and audits for any authenticated user. No limit checks exist in serializers or views. | Implement limit enforcement: Free (1 project, 10 keywords, 100 crawl pages), Starter, Agency tiers. |
| **Payment Gateway Webhooks** | 🔴 MISSING | No webhook endpoints for Chapa, Telebirr, CBE Birr, or Stripe exist in [backend/apps/users/urls.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/users/urls.py) or `urls.py`. | Implement webhook handlers verifying HMAC signatures and updating subscription states. |

---

## 11. Dashboard

| Requirement | Status | Evidence | Missing / Remaining Work |
| :--- | :--- | :--- | :--- |
| **Active Project Switcher & Context** | 🟢 COMPLETE | [dashboard/src/pages/Dashboard.tsx](file:///c:/Users/bizra/Documents/doxarank/dashboard/src/pages/Dashboard.tsx#L83-L105). Persists active project in `localStorage`, refreshes child panels upon selection. | Multi-user team workspace switcher. |
| **Tracked Keywords Table & CRUD** | 🟢 COMPLETE | [dashboard/src/pages/Dashboard.tsx](file:///c:/Users/bizra/Documents/doxarank/dashboard/src/pages/Dashboard.tsx#L378-L450), [dashboard/src/components/KeywordFormModal.tsx](file:///c:/Users/bizra/Documents/doxarank/dashboard/src/components/KeywordFormModal.tsx). Full create, edit, delete, and filtering. | Bulk keyword upload via CSV. |
| **Ranking Observations & Position Visualization** | 🟢 COMPLETE | [dashboard/src/pages/Dashboard.tsx](file:///c:/Users/bizra/Documents/doxarank/dashboard/src/pages/Dashboard.tsx#L460-L540), [dashboard/src/components/RankingFormModal.tsx](file:///c:/Users/bizra/Documents/doxarank/dashboard/src/components/RankingFormModal.tsx). Displays positions, ranking URLs, recorded dates. | Interactive charting (e.g. Chart.js / Recharts 30-day position graph). |
| **Site Audit Dashboard & Issue Inspector** | 🟢 COMPLETE | [dashboard/src/components/SiteAuditPanel.tsx](file:///c:/Users/bizra/Documents/doxarank/dashboard/src/components/SiteAuditPanel.tsx#L1-L200), [dashboard/src/components/AuditIssueFormModal.tsx](file:///c:/Users/bizra/Documents/doxarank/dashboard/src/components/AuditIssueFormModal.tsx). Health score badge, issue breakdown by severity. | Historical audit comparison diff. |
| **Search Console Analytics Panel** | 🟢 COMPLETE | [dashboard/src/components/SearchConsoleAnalyticsPanel.tsx](file:///c:/Users/bizra/Documents/doxarank/dashboard/src/components/SearchConsoleAnalyticsPanel.tsx#L1-L250). Clicks, impressions, CTR, average position with dimension filtering. | Multi-date range comparison. |
| **SEO Insights & Action Proposals** | 🟢 COMPLETE | [dashboard/src/components/SEOInsightsPanel.tsx](file:///c:/Users/bizra/Documents/doxarank/dashboard/src/components/SEOInsightsPanel.tsx#L1-L200), [dashboard/src/components/AIRecommendationsPanel.tsx](file:///c:/Users/bizra/Documents/doxarank/dashboard/src/components/AIRecommendationsPanel.tsx). Real-time insight list with severity badges. | None. |
| **Dashboard Standalone SEO Tools Tab** | 🔴 MISSING | No tab or navigation exists in Dashboard for the 10 standalone SEO tools. | Build tools navigation tab exposing interactive widgets for the 10 SEO tools. |
| **Billing & Subscription Management UI** | 🔴 MISSING | No billing tab, plan indicator, or upgrade modal exists in the dashboard UI. | Add subscription management screen displaying current tier, usage limits, and payment options. |

---

## 12. Production / Deployment

| Requirement | Status | Evidence | Missing / Remaining Work |
| :--- | :--- | :--- | :--- |
| **Dokploy Deployment Configuration** | 🔴 MISSING | Grep search for `dokploy` yields 0 matches in repository. No Dokploy compose files, nixpacks, or webhook scripts exist. | Create Dokploy configuration and deployment build scripts. |
| **Docker Containerization** | 🔴 MISSING | No `Dockerfile` or `docker-compose.yml` in repository root or subfolders. | Create production multi-stage Dockerfiles for Django backend, Astro marketing, and Vite dashboard. |
| **Production Environment Separation** | 🟡 PARTIAL | [backend/.env](file:///c:/Users/bizra/Documents/doxarank/backend/.env) contains only `DATABASE_URL` and `SECRET_KEY`. No `.env.example` exists. `DEBUG` defaults to `True` in [settings.py](file:///c:/Users/bizra/Documents/doxarank/backend/config/settings.py#L30). | Create `.env.example`, make `DEBUG` configurable via environment variable, mandate secure production defaults. |
| **Domain & Subdomain Routing** | 🔴 MISSING | [backend/config/settings.py](file:///c:/Users/bizra/Documents/doxarank/backend/config/settings.py#L32) only allows `['127.0.0.1', 'localhost', 'testserver']`. No Nginx or Caddy reverse-proxy configs exist. | Configure Nginx/Caddy reverse proxy and add `doxarank.com`, `app.doxarank.com`, `api.doxarank.com` to `ALLOWED_HOSTS` and CORS. |
| **PostgreSQL Database Deployment** | 🟢 COMPLETE | Neon cloud PostgreSQL configured via connection pooling URL in [backend/.env](file:///c:/Users/bizra/Documents/doxarank/backend/.env#L1). | None. |
| **Redis & Celery Production Worker Setup** | 🟡 PARTIAL | Celery and Redis configured in Django settings, but no systemd unit files or supervisor configurations exist to run worker/beat in production. | Add worker process management configurations (supervisord / systemd / Docker compose). |

---

## 13. Security

| Requirement | Status | Evidence | Missing / Remaining Work |
| :--- | :--- | :--- | :--- |
| **Authentication & Token Expiration** | 🟢 COMPLETE | [backend/config/settings.py](file:///c:/Users/bizra/Documents/doxarank/backend/config/settings.py#L173-L181). Access token lifetime 60 minutes, refresh token 7 days, rotation enabled, blacklisting enabled. | None. |
| **Tenant Isolation & Horizontal Access Control** | 🟢 COMPLETE | [backend/apps/projects/views.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/projects/views.py#L19-L25), [backend/apps/seo/views.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/views.py). All querysets strictly filtered by `owner=request.user` or `project__owner=request.user`. Verified in [test_projects_api.py](file:///c:/Users/bizra/Documents/doxarank/backend/test_projects_api.py). | None. |
| **Secret Encryption at Rest** | 🟢 COMPLETE | [backend/apps/seo/services/encryption.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/encryption.py#L1-L80). AES-256 (Fernet) encryption for OAuth refresh tokens prior to database storage. | Key rotation mechanism. |
| **Crawler SSRF Mitigation** | 🟡 PARTIAL | [backend/apps/seo/services/live_site_crawler.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/live_site_crawler.py#L140-L180). Restricts crawling to identical domain and scheme. **Vulnerability:** Does not resolve hostnames to IP addresses or block private/loopback IP ranges (`127.0.0.1`, `169.254.169.254`, `10.0.0.0/8`). | Add DNS pre-resolution and IP blacklist filter blocking loopback, link-local (cloud metadata), and RFC 1918 private subnets. |
| **API Parameter Sanitization & Injection Defense** | 🟢 COMPLETE | DRF serializers validate and sanitize all payload inputs with typed fields and model constraints. | None. |
| **Hardcoded Secrets in Repository** | 🟢 COMPLETE | Git scan shows secrets are loaded from `.env` via `python-decouple`. *(Note: Ensure `backend/.env` is kept out of public VCS tracking).* | Verify `.env` is listed in `.gitignore` at root. |

---

## 14. Final Gap List

Categorized strictly into remaining **Original SRS Work** (excluding Agentic AI Milestones 5.1–6.7):

### P0 — Blocking / Essential (Core Platform Foundation)
1. **SSRF Mitigation in Website Crawler:**
   - **What needs to be implemented:** In [apps/seo/services/live_site_crawler.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/live_site_crawler.py), add DNS IP resolution before making HTTP requests. Block all private, loopback (`127.0.0.1`, `localhost`), and cloud metadata (`169.254.169.254`) IP addresses to prevent server-side request forgery.
2. **Production Environment & Security Hardening:**
   - **What needs to be implemented:** In [backend/config/settings.py](file:///c:/Users/bizra/Documents/doxarank/backend/config/settings.py), read `DEBUG` from environment (cast to bool, default `False`), configure production `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` via environment variables, and create a root `.env.example`.
3. **Automated Keyword Rank Tracking Scheduler:**
   - **What needs to be implemented:** In [backend/apps/seo/tasks.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/tasks.py) and [settings.py](file:///c:/Users/bizra/Documents/doxarank/backend/config/settings.py), implement and schedule a periodic Celery Beat task that iterates over active keywords and records daily ranking positions.

### P1 — Required for SRS Completeness (User-Facing Value & Scope)
4. **Build the 10 Standalone SEO Tools (Backend & Frontend):**
   - **What needs to be implemented:**
     1. *Meta Tag Generator:* Endpoint and interactive form to generate standard HTML meta tags.
     2. *Open Graph / Twitter Card Previewer:* Live social card preview component with Facebook/Twitter mockup rendering.
     3. *Schema.org / JSON-LD Generator:* Form generator for Article, Organization, and LocalBusiness schema markup.
     4. *Robots.txt Tester / Generator:* Validator and rule syntax generator.
     5. *Sitemap Validator / Generator:* XML syntax and URL health validator.
     6. *hreflang Builder:* Multi-language tag generator supporting `am-ET`, `en-ET`, `om-ET`, `ti-ET`.
     7. *SERP Snippet Preview / Pixel-Length Checker:* Visual SERP mockup with real-time 600px desktop / mobile pixel calculation.
     8. *PageSpeed / Core Web Vitals Analyzer:* Service integrating Google PageSpeed Insights REST API.
     9. *Single-Page Broken Link Checker:* Standalone single-page link validation API and UI table.
     10. *Amharic Fidel Keyword Normalizer Tool UI:* Standalone API endpoint (`POST /api/seo/tools/amharic-normalizer/`) and interactive UI card demonstrating Fidel homophone collapsing.
5. **Marketing Website Development:**
   - **What needs to be implemented:** In `marketing/src/pages/`, replace the blank placeholder files (`index.astro`, `pricing.astro`, `features.astro`, `about.astro`, `contact.astro`) with complete production pages, pricing comparison tables, and direct links to the dashboard registration flow.
6. **Pricing Tiers, Feature Gating & Subscription Models:**
   - **What needs to be implemented:** In `backend/apps/users/models.py` and `apps/projects/models.py`, create a `SubscriptionTier` model (`FREE`, `STARTER`, `AGENCY`). Enforce quota limits (maximum projects, keywords, and crawl pages) inside DRF viewsets and serializers.
7. **Playwright Dynamic Crawler:**
   - **What needs to be implemented:** In [backend/apps/seo/services/live_site_crawler.py](file:///c:/Users/bizra/Documents/doxarank/backend/apps/seo/services/live_site_crawler.py), add an optional Playwright headless browser rendering mode for JavaScript-heavy single-page applications.

### P2 — Important But Can Follow (Polish & Advanced Analytics)
8. **White-Label Agency Client Reporting:**
   - **What needs to be implemented:** Create an automated PDF report generation service allowing agency users to upload custom logos and export branded SEO performance reports.
9. **Competitor Domain & SERP Tracking Matrix:**
   - **What needs to be implemented:** Add `CompetitorDomain` model and a SERP comparison view showing keyword ranking overlap against competitors.
10. **Google Analytics 4 (GA4) Integration:**
    - **What needs to be implemented:** Connect to Google Analytics Data API to ingest project session, bounce rate, and conversion metrics alongside GSC data.

### P3 — Senior-Team / Post-Internship Responsibility (Commercialization & Live Infrastructure)
11. **Doxa Payments & Ethiopian Payment Gateways:**
    - **What needs to be implemented:** Integrate Telebirr, Chapa, CBE Birr, and Stripe webhook handlers and payment checkout sessions to automate subscription upgrades.
12. **Microsoft Clarity & Google Tag Manager Integration:**
    - **What needs to be implemented:** Backend fields for Clarity project IDs and GTM container IDs with dashboard session-replay embed links.
13. **Dokploy Deployment & Containerization:**
    - **What needs to be implemented:** Write production Dockerfiles, `docker-compose.yml`, and Dokploy deployment manifests for multi-service hosting.

---

## 15. SRS Compliance Checklist

| Item | Requirement Description | Status |
| :---: | :--- | :---: |
| 1 | Django & DRF Backend Structure | 🟢 Complete |
| 2 | Neon PostgreSQL Database Configuration | 🟢 Complete |
| 3 | `seo_` Database Table Naming Convention | 🟢 Complete |
| 4 | RESTful API with DRF ViewSets & Routers | 🟢 Complete |
| 5 | Multi-Project Workspace Data Model & Tenancy | 🟢 Complete |
| 6 | Celery & Redis Background Worker Infrastructure | 🟢 Complete |
| 7 | Marketing Landing / Home Page | 🔴 Missing |
| 8 | Marketing Pricing Page (Free / Starter / Agency) | 🔴 Missing |
| 9 | Marketing Features Overview Page | 🔴 Missing |
| 10 | Marketing Company Pages (About / Contact) | 🔴 Missing |
| 11 | Marketing Content Blog & Case Studies | 🔴 Missing |
| 12 | Marketing Free Trial / Onboarding Flow | 🔴 Missing |
| 13 | Marketing Public Hosting of the 10 SEO Tools | 🔴 Missing |
| 14 | Custom Email-Based User Model | 🟢 Complete |
| 15 | User Registration API | 🟢 Complete |
| 16 | JWT Login & Token Refresh Flow | 🟢 Complete |
| 17 | Protected User Profile Endpoint (`/me/`) | 🟢 Complete |
| 18 | Token Blacklisting & Logout API | 🟢 Complete |
| 19 | Tenant Isolation & Cross-Tenant Security | 🟢 Complete |
| 20 | SEO Tool 1: Meta Tag Generator | 🔴 Missing |
| 21 | SEO Tool 2: Open Graph / Twitter Card Previewer | 🔴 Missing |
| 22 | SEO Tool 3: Schema.org / JSON-LD Generator | 🔴 Missing |
| 23 | SEO Tool 4: Robots.txt Tester / Generator | 🔴 Missing |
| 24 | SEO Tool 5: Sitemap Validator / Generator | 🔴 Missing |
| 25 | SEO Tool 6: hreflang Builder | 🔴 Missing |
| 26 | SEO Tool 7: SERP Snippet Preview / Pixel-Length Checker | 🔴 Missing |
| 27 | SEO Tool 8: PageSpeed / Core Web Vitals Analyzer | 🔴 Missing |
| 28 | SEO Tool 9: Single-Page Broken Link Checker | 🟡 Partial |
| 29 | SEO Tool 10: Amharic Fidel Keyword Normalizer | 🟡 Partial |
| 30 | Target Keyword Tracking CRUD Management | 🟢 Complete |
| 31 | Keyword Language (`en`, `am`) & Country (`ET`) Settings | 🟢 Complete |
| 32 | Keyword Search Volume, CPC & Tags | 🔴 Missing |
| 33 | Keyword Ranking History Persistence | 🟢 Complete |
| 34 | Rank Position Change Calculation & Trend Direction | 🟢 Complete |
| 35 | Automated Live SERP Scraping Scheduler | 🔴 Missing |
| 36 | Competitor Domain & SERP Overlap Tracking | 🔴 Missing |
| 37 | Rule-Based SEO Insights Engine | 🟢 Complete |
| 38 | Explainable SEO Recommendations Engine | 🟢 Complete |
| 39 | Google OAuth2 Authentication Flow | 🟢 Complete (Code) / ⚪ External Verification |
| 40 | Google Search Console (GSC) Analytics Sync & Storage | 🟢 Complete (Code) / ⚪ External Verification |
| 41 | Google Analytics 4 (GA4) Integration | 🔴 Missing |
| 42 | Microsoft Clarity Integration | 🔴 Missing |
| 43 | Google Tag Manager (GTM) Integration | 🔴 Missing |
| 44 | Doxa Payments (Telebirr / Chapa / CBE Birr / Stripe) | 🔴 Missing |
| 45 | Website Crawler Engine (Bounded BFS, HTML Extraction) | 🟢 Complete |
| 46 | Playwright Headless Browser Crawler | 🔴 Missing |
| 47 | Robots.txt Crawl Compliance | 🟢 Complete |
| 48 | Crawl Boundaries, Same-Domain & Politeness Limits | 🟢 Complete |
| 49 | Celery Asynchronous Crawl Execution | 🟢 Complete |
| 50 | Technical SEO Audit Engine & 0–100 Scoring | 🟢 Complete |
| 51 | Audit Issue Classification (Critical, Warning, Notice) | 🟢 Complete |
| 52 | Amharic Keyword Tracking Support | 🟢 Complete |
| 53 | English Keyword Tracking Support | 🟢 Complete |
| 54 | `google.com.et` Target Search Engine Support | 🟡 Partial |
| 55 | `.et` Domain Tracking Support | 🟢 Complete |
| 56 | Competitor SERP Snapshots | 🔴 Missing |
| 57 | Pricing Tiers Definition in Backend | 🔴 Missing |
| 58 | Backend Subscription Logic & Billing Models | 🔴 Missing |
| 59 | Feature Gating & Quota Limit Enforcement | 🔴 Missing |
| 60 | White-Label Agency PDF/Email Client Reports | 🟡 Partial |
| 61 | Dashboard Active Project Switcher & Workspace Context | 🟢 Complete |
| 62 | Dashboard Keywords & Rankings Management UI | 🟢 Complete |
| 63 | Dashboard Technical Site Audit & Issues UI | 🟢 Complete |
| 64 | Dashboard Search Console Analytics Visualization | 🟢 Complete |
| 65 | Dashboard SEO Insights & Action Proposals UI | 🟢 Complete |
| 66 | Production Dokploy & Docker Deployment Configuration | 🔴 Missing |