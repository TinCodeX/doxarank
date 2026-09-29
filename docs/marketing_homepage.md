# DoxaRank Marketing Homepage & Website Architecture

## Overview
This document details the production marketing homepage and marketing site structure for **DoxaRank**, the Ethiopia-first SEO platform. Built with **Astro 7** and **Tailwind CSS v4**, the marketing site provides a high-converting, accessible, and fast presentation of DoxaRank's localized capabilities without client-heavy hydration or fabricated marketing claims.

---

## 1. Homepage Structure & Major Sections (`/`)

The homepage (`marketing/src/pages/index.astro`) is organized into sequential sections designed to guide visitors from positioning to proof, product utility, and conversion:

1. **Navigation Bar (`<Navbar />`)**
   - Brand logo with Ethiopia flag badge (`🇪🇹 ET`).
   - Desktop and responsive mobile links: `Features`, `Pricing`, `About`, `Blog`, `Case Studies`, `Contact`.
   - Primary action CTA: `Start Free` (`/signup`).
   - Secondary action CTA: `Sign In` (`/login`).
   - Fully accessible mobile hamburger drawer with ARIA attributes and zero runtime dependencies.

2. **Hero Section**
   - **Headline**: *"SEO Built for Ethiopia. Rank Higher on Google Ethiopia."*
   - **Supporting Copy**: Focuses on `google.com.et` rank tracking, Amharic & Oromo search demand, technical SEO auditing on `.et` domains, and competitor SERP snapshots.
   - **Badges & Trust Signals**: Highlights free tier, local telemetry, and one-click integrations for Google Search Console, Google Analytics 4, Microsoft Clarity, and Google Tag Manager.
   - **Dual CTAs**: `Start Free` and `Explore Features` anchor.

3. **Illustrative Product Visual (Dashboard Mockup)**
   - High-fidelity static dashboard preview demonstrating realistic DoxaRank telemetry without fabricating production customer metrics.
   - Includes:
     - Project context banner (e.g., Ethiopian Hospitality & Tourism domain).
     - Localized SERP rankings table showcasing bilingual tracking (English & Amharic: e.g., `hotels in addis ababa`, `የኢትዮጵያ ሆቴሎች`, `ethiopian coffee exporter`, `hawassa resort booking`).
     - Real-time rank changes, search volumes, and advertiser CPC estimates.
     - Technical health audit breakdown (HTTP 200s, redirects, canonical status).
     - Prioritized recommendations feed (High, Medium, Low severity items).

4. **Ethiopia-First Differentiation (4 Core Pillars)**
   - **Google Ethiopia Indexing**: Native query routing for `google.com.et` desktop and mobile SERPs.
   - **Amharic & Oromo Search**: Fidel engine with homophone normalization (ሀ/ሐ/ኀ, ሰ/ሠ, አ/ዐ, ጸ/ፀ).
   - **.et Domain Architecture**: Crawler diagnostics tuned for `.et`, `.com.et`, `.org.et`, and `.edu.et` web infrastructure.
   - **Search Demand & CPC**: Search volume estimation and advertiser CPC bid benchmarks for Ethiopian queries.

5. **Core Platform Features Grid (8 SRS Capabilities)**
   - Daily Rank Tracker (`google.com.et`)
   - Technical SEO Crawler (Crawl depth, status codes, canonicals, robots.txt, sitemaps)
   - Keyword Intelligence & CPC (Search volume, intent scoring, advertiser CPC bids)
   - Competitor SERP Snapshots (Historical position benchmarks)
   - SEO Recommendations Feed (Rule-based prioritized action items)
   - Native Analytics Integrations (GSC, GA4, Clarity, GTM)
   - Agency White-Label Reports (Branded client PDFs)
   - Standalone Free SEO Tools (Meta tag generator, robots.txt validator, Amharic normalizer)

6. **How It Works (4-Step Workflow)**
   - Step 1: *Add your website* (Domain registration and language target selection).
   - Step 2: *Connect your SEO data* (OAuth connection to GSC, GA4, Clarity).
   - Step 3: *Audit & track rankings* (Automated crawl and google.com.et tracking).
   - Step 4: *Act on recommendations* (Prioritized resolution of high-impact SEO issues).

7. **Use Cases (Audience-Specific Solutions)**
   - Ethiopian Businesses & E-Commerce
   - In-House SEO & Marketing Teams
   - Digital Agencies & Consultants
   - Developers & Web Agencies

8. **Pricing CTA & Tier Breakdown**
   - Features the 3 official DoxaRank SRS subscription tiers:
     - **Free**: ETB 0 / forever (1 website, 10 keywords, weekly crawl, basic tools).
     - **Starter**: ETB 1,500 / month (5 websites, 100 keywords, daily tracking, competitor snapshots, full integrations).
     - **Agency**: ETB 6,000 / month (unlimited websites, 500 keywords, white-label PDF reports, priority SLA).
   - Note on local payment rails: Telebirr and local bank transfer via Doxa Payments.

9. **Final Conversion CTA**
   - Final call to action with `Start Free` and `View Pricing Plans` buttons.

10. **Site Footer (`<Footer />`)**
    - 5-column responsive layout with categorized links for Product, Company, Platform, Legal/Support, and copyright notice.

---

## 2. Routes & Navigation Matrix

All routes link to real, fully-rendered Astro pages adhering to the global design system:

| Route | Page File | Purpose & Content |
|---|---|---|
| `/` | `src/pages/index.astro` | Full production marketing homepage. |
| `/features` | `src/pages/features.astro` | In-depth breakdown of all 6 core feature groups and tools. |
| `/pricing` | `src/pages/pricing.astro` | Comprehensive tier comparison table, feature matrix, and ETB billing FAQ. |
| `/about` | `src/pages/about.astro` | DoxaRank mission, Ethiopian search challenges, and engineering principles. |
| `/blog` | `src/pages/blog/index.astro` | Educational guides on Google Ethiopia, Fidel normalization, and .et crawling. |
| `/case-studies` | `src/pages/case-studies/index.astro` | Illustrative architecture frameworks and hypothetical workflows for Banking, E-Commerce, and Media. |
| `/contact` | `src/pages/contact.astro` | Direct channels (support@, sales@) in Addis Ababa and inquiry form. |
| `/login` | `src/pages/login.astro` | Clean gateway linking to dashboard authentication (`/login` or `http://localhost:5173/login`). |
| `/signup` | `src/pages/signup.astro` | Free plan onboarding gateway linking to dashboard registration (`/register`). |

---

## 3. SEO & Open Graph Metadata

Each page is wrapped in `marketing/src/layouts/Layout.astro`, which configures:
- **Title**: Descriptive, unique page titles adhering to the format `[Page Name] — DoxaRank | Ethiopia SEO SaaS`.
- **Meta Description**: Compelling descriptions summarizing localized features and target benefits.
- **Canonical URL**: Dynamic `Astro.site` canonical tagging.
- **Open Graph**: `og:title`, `og:description`, `og:type="website"`, and `og:locale="en_ET"`.
- **Twitter Cards**: `twitter:card="summary_large_image"`, title, and description.
- **JSON-LD Structured Data**: Schema.org `SoftwareApplication` and `Organization` metadata documenting DoxaRank's operating application category, Ethiopian target market, and pricing currency (`ETB`).
- **Semantic HTML**: Exactly one `<h1>` per page, hierarchical `<h2>` and `<h3>` tags, `<main>`, `<section>`, `<article>`, `<nav>`, and `<footer>` landmarks.

---

## 4. Responsive Design & Performance

- **Fluid Breakpoints**: Tested across mobile (390px), tablet (768px), laptop (1024px/1280px), and wide desktop (1440px+).
- **Zero Horizontal Overflow**: Guaranteed via `overflow-x-hidden` containers and responsive grid column definitions (`grid-cols-1 md:grid-cols-2 lg:grid-cols-3`).
- **Lightweight Static Delivery**: Compiled with `astro build` into pure static HTML/CSS with negligible JavaScript (only the lightweight mobile navigation toggle script).
- **Typography**: Inter font with fallback to Ethiopic font stacks (`Noto Sans Ethiopic`, `Nyala`, system font stack) for seamless Amharic rendering.

---

## 5. Assumptions & Constraints Preserved

1. **Original DoxaRank SRS Compliance**: All features, capabilities, pricing numbers (ETB 0 / ETB 1,500 / ETB 6,000), and positioning reflect the core SRS requirements.
2. **Zero Fabrication**: No fake customer counts (e.g. "Trusted by 10,000+ businesses"), fake customer logos, fake review ratings, or fabricated user testimonials were added.
3. **Preservation of Backend & Dashboard**: Zero files in `backend/` or `dashboard/` were modified. Agentic AI milestones (5.1–6.7) and SEO Tools 1–10 remain completely untouched.
