# Agentic Google Search Console Intelligence & Reasoning Architecture

## 1. Overview & Objective

Phase 4.1.4 transforms DoxaRank's Google Search Console (GSC) integration from passive data-access endpoints into an **Agentic Intelligence & Reasoning Engine**.

The autonomous ReAct agent leverages statistical heuristics and multi-dimensional Search Console metrics to:
1. Discover high-ROI search opportunities (Page Two rankings, SERP snippet CTR underperformance, keyword cannibalization, emerging queries).
2. Quantify performance trends across time periods (consecutive 28-day deltas, top gainers, top decliners, and lost queries).
3. Correlate search intent from top queries to landing page URLs and metadata.
4. Synthesize explainable SEO recommendations and optimized content briefs/drafts.
5. Gate any executable, mutating actions through the human-in-the-loop approval mechanism.

---

## 2. End-to-End Execution Flow

```text
Google Search Console API
 (Live API / OAuth2 Refresh)
             │
             ▼
   GSC Intelligence Service (`apps.seo.services.gsc_intelligence.py`)
   ├── Heuristic Detectors (Page 2, CTR Anomaly, Cannibalization, Emerging)
   └── Period Comparison Engine (Deltas, Top Gainers/Decliners)
             │
             ▼
   Agent Tool Registry (`apps.seo.services.tool_registry.py`)
   ├── `gsc_top_queries`          (Read-Only: Live top search queries)
   ├── `gsc_top_pages`            (Read-Only: Live top landing pages)
   ├── `gsc_search_analytics`     (Read-Only: Live multi-dimensional query)
   ├── `gsc_opportunity_audit`    (Safe-Internal: Structured opportunity findings)
   └── `gsc_performance_comparison`(Read-Only: Period-over-period trend analysis)
             │
             ▼
   ReAct Agent Orchestrator & AI Provider Loop
   (Goal → Dynamic Tool Selection → Execution → Observation → Multi-Step Reasoning)
             │
             ▼
   SEO Recommendation & Content Synthesis (`generate_recommendation`, `generate_content_brief`)
             │
             ▼
   Human Approval Checkpoint (`propose_seo_action` → `AgentRunStatus.WAITING_FOR_APPROVAL`)
             │
             ▼
   Safe Post-Approval Execution (`SEOActionService` → CMS / Webmaster Implementation)
```

---

## 3. Heuristic Detectors & Statistical Benchmarks

### 3.1 Page Two Ranking Opportunities (`gsc_page_two_opportunity`)
- **Criteria**: Query ranks between position `10.1` and `20.0` with impression volume $\ge 10$.
- **Rationale**: Page 2 queries have proven search demand and domain relevance; modest on-page optimization, FAQ additions, or internal link equity can move them onto Page 1 where >90% of clicks occur.
- **Confidence**: Dynamic scale $0.70$ to $0.95$ based on total impressions.

### 3.2 SERP Snippet CTR Underperformance (`gsc_high_impressions_low_ctr`)
- **Criteria**: Query ranks in top 10 (Positions 1.0 - 10.0) with impressions $\ge 20$, but observed CTR is $< 60\%$ of position benchmark:
  - Top 3 (Positions 1.0 - 3.0): Benchmark $\ge 15.0\%$ CTR.
  - Page 1 (Positions 3.1 - 10.0): Benchmark $\ge 3.0\%$ CTR.
- **Rationale**: Indicates that competitors have superior meta titles or compelling rich snippets, causing searchers to skip the domain.
- **Recommendation**: Optimize meta title (primary keyword in first 40 chars) and meta description with clear action CTA.

### 3.3 Keyword Cannibalization (`gsc_keyword_cannibalization`)
- **Criteria**: Multiple URLs ($\ge 2$) receive impressions/clicks for the identical search query with total impressions $\ge 15$.
- **Rationale**: Splitting search equity across competing URLs confuses Google's canonical indexing and suppresses peak rank.
- **Recommendation**: Establish canonical tag, consolidate thin content, or differentiate secondary pages to distinct intent.

### 3.4 Emerging Long-Tail Opportunities (`gsc_emerging_query`)
- **Criteria**: Queries with position $\ge 4.0$, impressions $\ge 10$, and CTR $\ge 10.0\%$.
- **Rationale**: High CTR at non-#1 positions signals exceptionally strong user intent and topical fit.

### 3.5 Period-over-Period Performance Comparison (`compare_periods`)
- **Metrics**: Computes base vs comparison period deltas for clicks, impressions, CTR, and average position.
- **Categorization**: Groups queries into `top_gainers`, `top_decliners`, `lost_queries`, and `new_queries`.
- **Alerting**: Produces a `critical` or `warning` finding if organic clicks decline by $> 15\%$.

---

## 4. Multi-Tenant Security & Human Safety Boundaries

1. **Strict Multi-Tenant Isolation**: All GSC intelligence calls require an authenticated `Project` context. Google Search Console API credentials are bound exclusively to the verified project owner.
2. **Zero Credential Exposure**: OAuth refresh tokens, access tokens, and authorization headers are never passed to the LLM context, recorded in `AgentToolCall` database rows, or published via Redis / Channels WebSocket events.
3. **Non-Destructive Boundary**: GSC intelligence, analytics queries, and comparisons are strictly read-only or safe-internal. Any proposed external or mutating change (e.g. meta tag updates, draft publishing) MUST create a proposal via `propose_seo_action` and enter `waiting_for_approval`.

---

## 5. Structured Finding Schema

```json
{
  "finding_type": "gsc_page_two_opportunity",
  "severity": "opportunity",
  "confidence": 0.85,
  "title": "Page 2 Opportunity: \"best enterprise seo software\" (Rank #12.4, 450 Impressions)",
  "insight": "Query \"best enterprise seo software\" is ranking on page 2 at position #12.4 with 450 search impressions. Moving this query into the top 10 yields the highest ROI for organic click growth.",
  "recommendation": "1. Update primary landing page H1 and H2 headings to include \"best enterprise seo software\" naturally.\n2. Add dedicated FAQ section.\n3. Build internal links from high-authority blog posts.",
  "evidence": [
    { "query": "best enterprise seo software", "impressions": 450, "clicks": 8, "position": 12.4, "ctr_percent": 1.78 }
  ],
  "metrics": {
    "query": "best enterprise seo software",
    "position": 12.4,
    "impressions": 450,
    "clicks": 8,
    "ctr_percent": 1.78
  },
  "requires_approval": false,
  "suggested_action_type": "optimize_existing_content",
  "target_query": "best enterprise seo software"
}
```
