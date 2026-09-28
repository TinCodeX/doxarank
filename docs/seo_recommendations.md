# DoxaRank Actionable SEO Recommendations Architecture

## 1. Overview & Purpose

The SEO Recommendations Feed implements the original DoxaRank SRS requirement for a user-facing, actionable SEO recommendations feed.

Its purpose is to synthesize findings from DoxaRank's core subsystems:
1. **Technical SEO Crawler** (`CrawlJob`, `CrawlPage`, crawl issues)
2. **Rank Tracker** (`Keyword`, `KeywordRanking`, rank declines, striking-distance opportunities)
3. **Competitor SERP Snapshots** (`Competitor`, `CompetitorSnapshot`, visibility gaps, outranking rivals)

and transform them into prioritized, explainable recommendations for each project.

> **CRITICAL ARCHITECTURAL BOUNDARY:**  
> This first milestone is **strictly deterministic and rule-based**. It does **NOT** introduce an LLM, agent framework, or probabilistic model. All metrics, problems, and recommended actions are backed directly by actual crawl or SERP data.

---

## 2. Architecture & System Flow

```
+-----------------------------------------------------------------------------------+
|                            DoxaRank Project Data Subsystems                       |
|                                                                                   |
|  +--------------------+    +--------------------+    +-------------------------+  |
|  | Technical Crawler  |    |    Rank Tracker    |    |  Competitor Snapshots   |  |
|  | - Status codes     |    | - Top 100 presence |    | - Rival outranking      |  |
|  | - Title / Meta     |    | - Position decline |    | - Competitor found while|  |
|  | - H1 / Canonical   |    | - Page 2 striking  |    |   project unranked      |  |
|  | - Speed / Images   |    | - Low rankings     |    | - Top 3 dominance       |  |
|  +--------------------+    +--------------------+    +-------------------------+  |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                        RecommendationEngine (Service Layer)                       |
|                                                                                   |
|   1. evaluate_crawler_findings(project)                                           |
|   2. evaluate_rank_tracker_findings(project)                                      |
|   3. evaluate_competitor_findings(project)                                        |
|   4. calculate_recommendation_priority(...) [Deterministic 1 - 100]               |
|   5. Fingerprint deduplication & active state updates                             |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                     Recommendation Model (PostgreSQL / SQLite)                    |
|                                                                                   |
|   - project_id (Tenant Isolated)                                                  |
|   - source_type & source_id                                                       |
|   - category (technical_seo, on_page_seo, performance, indexing, rankings...)    |
|   - severity (critical, high, medium, low, info)                                  |
|   - status (open, acknowledged, resolved, dismissed)                              |
|   - priority (1 - 100)                                                            |
|   - fingerprint (deterministic deduplication key)                                 |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                         REST API & Dashboard Feed                                 |
|                                                                                   |
|   GET   /api/seo/recommendations/?project_id=<id>&status=open                     |
|   PATCH /api/seo/recommendations/<id>/ (acknowledge, resolve, dismiss)            |
|   POST  /api/seo/recommendations/generate/ (Synchronous or Celery async task)     |
+-----------------------------------------------------------------------------------+
```

---

## 3. Data Model

The `Recommendation` model (`seo_project_recommendations`) represents an actionable recommendation for a specific project.

### 3.1. Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `project` | `ForeignKey(Project)` | Project owning this recommendation (`CASCADE`). |
| `source_type` | `CharField` | `crawler`, `rank_tracker`, `competitor_snapshot`, `seo_tool`, `system`. |
| `source_id` | `CharField(100)` | Reference to originating entity (e.g. `crawl_page_id`, `keyword_id`). |
| `category` | `CharField` | `technical_seo`, `on_page_seo`, `performance`, `indexing`, `rankings`, `content`, `competitors`. |
| `severity` | `CharField` | `critical`, `high`, `medium`, `low`, `info`. |
| `title` | `CharField(255)` | User-facing headline. |
| `description` | `TextField` | Detailed structured breakdown: Problem detected and Why it matters. |
| `recommended_action` | `TextField` | Concrete step-by-step guidance for remediation. |
| `affected_url` | `CharField(1000)` | Target page URL affected, if applicable. |
| `affected_keyword` | `CharField(255)` | Target search keyword affected, if applicable. |
| `status` | `CharField` | `open`, `acknowledged`, `resolved`, `dismissed`. |
| `priority` | `PositiveIntegerField` | Deterministic priority score between `1` and `100`. |
| `fingerprint` | `CharField(255)` | Unique deduplication key: `rule_code:resource_identifier`. |
| `metadata` | `JSONField` | Diagnostic contextual details, metrics, and hops. |
| `created_at` | `DateTimeField` | When the recommendation was first created. |
| `updated_at` | `DateTimeField` | When the recommendation was last modified or resurfaced. |
| `resolved_at` | `DateTimeField` | Timestamp when the recommendation was marked resolved/dismissed. |

### 3.2. Indexes
- `['project', 'status']`
- `['project', 'severity']`
- `['project', 'category']`
- `['project', 'source_type']`
- `['project', '-priority']`
- `['project', 'fingerprint']`
- `['project', '-created_at']`

---

## 4. Supported Deterministic Rules

### 4.1. Technical SEO Crawler Rules
Evaluated from the project's latest completed `CrawlJob`:

| Rule ID | Finding Condition | Severity | Category | Base Title |
| :--- | :--- | :--- | :--- | :--- |
| `crawler_broken` | `is_broken == True` or `status_code >= 400` | `critical` | `indexing` | Fix broken internal page (HTTP {status_code}) |
| `crawler_missing_title` | `<title>` is empty or whitespace | `high` | `on_page_seo` | Add missing <title> tag on {url} |
| `crawler_duplicate_title` | Multiple crawled pages share identical `<title>` | `medium` | `on_page_seo` | Resolve duplicate <title> across {count} pages |
| `crawler_missing_meta_desc` | `meta_description` is empty | `medium` | `on_page_seo` | Add missing meta description on {url} |
| `crawler_missing_h1` | `h1_count == 0` | `medium` | `on_page_seo` | Add primary <h1> heading to {url} |
| `crawler_multiple_h1` | `h1_count > 1` | `low` | `on_page_seo` | Consolidate multiple <h1> headings on {url} |
| `crawler_missing_canonical` | `canonical_url` is empty | `medium` | `technical_seo` | Specify canonical URL for {url} |
| `crawler_slow_page` | `response_time_ms > 3000` or `is_slow` | `medium` | `performance` | Optimize slow page load time ({ms}ms) on {url} |
| `crawler_missing_alt` | `images_missing_alt_count > 0` | `low` | `content` | Add alt attributes to {count} image(s) on {url} |
| `crawler_redirect_chain` | `has_redirect` with `len(chain) > 1` | `medium` | `technical_seo` | Eliminate redirect chain ({hops} hops) for {url} |

### 4.2. Rank Tracker Rules
Evaluated from active keywords and latest `KeywordRanking` observations:

| Rule ID | Finding Condition | Severity | Category | Base Title |
| :--- | :--- | :--- | :--- | :--- |
| `rank_not_found` | `result_status == 'not_found'` or `position is None` | `high` | `rankings` | Target keyword not ranking in Top 100: "{kw}" |
| `rank_decline` | Position dropped by >= 3 positions vs previous check | `high` | `rankings` | Ranking decline for "{kw}" (dropped {drop} to #{pos}) |
| `rank_page_two` | Position between 11 and 20 (striking distance) | `medium` | `rankings` | Striking distance opportunity: "{kw}" at #{pos} |
| `rank_low_position` | Position > 20 | `low` | `rankings` | Improve low ranking position (#{pos}) for "{kw}" |

### 4.3. Competitor SERP Snapshot Rules
Evaluated from active competitors and their latest `CompetitorSnapshot` vs project rankings:

| Rule ID | Finding Condition | Severity | Category | Base Title |
| :--- | :--- | :--- | :--- | :--- |
| `comp_proj_not_found` | Competitor found (1-100) while project unranked | `high` | `competitors` | Competitor {domain} ranks (#{pos}) while site unranked |
| `comp_outranks` | Competitor position < project position for same keyword | `high` | `competitors` | {domain} (#{comp_pos}) outranks your site (#{proj_pos}) |
| `comp_top_three` | Competitor holds position <= 3 | `medium` | `competitors` | {domain} holds dominant Top 3 rank (#{pos}) for "{kw}" |

---

## 5. Deterministic Priority Calculation

Priority is calculated as an integer score between **1 and 100** via `calculate_recommendation_priority()`:

$$\text{Priority} = \text{clamp}_{[1, 100]}(\text{Base Score} + \text{Modifiers})$$

### Base Scores by Severity
- `critical`: **90**
- `high`: **70**
- `medium`: **50**
- `low`: **30**
- `info`: **15**

### Deterministic Modifiers
- **Broken / Inaccessible Resource:** $+10$ (e.g., HTTP 4xx/5xx or broken crawl page).
- **Ranking Decline or Direct Outranking:** $+8$ (e.g., competitor ahead or position drop).
- **Systemic / Multi-Item Frequency:** $+\min(10, \text{count} \times 2)$ (e.g., duplicate title across 4 pages adds $+8$).

Every priority score maps directly to documented factual attributes.

---

## 6. Deduplication & Idempotency Strategy

Recommendations use a deterministic `fingerprint`:
```python
fingerprint = f"{rule_code}:{resource_identifier}"
```
Examples:
- `crawler_broken:https://bolehotel.et/missing`
- `rank_decline:14`
- `comp_outranks:3:14`

When `RecommendationEngine.generate_project_recommendations(project)` executes:
1. It queries existing recommendations for the project matching `(project, fingerprint)`.
2. If an **`open`** or **`acknowledged`** recommendation exists:
   - Its priority, severity, description, recommended action, and metadata are updated with the latest metrics.
   - **No duplicate record is created.**
3. If no active recommendation exists:
   - A new recommendation is created with status **`open`**.
4. Multiple repeated executions produce identical results (idempotent).

---

## 7. Lifecycle & Status Transitions

```
[ New Issue Detected ]
         |
         v
     ( OPEN ) <--------------------------+
      |    |                              |
      |    +---------> ( ACKNOWLEDGED )   | Re-opened
      |                       |           |
      +--------+   +----------+           |
               |   |                      |
               v   v                      |
            ( RESOLVED ) -----------------+
               |
               v
           ( DISMISSED )
```

- When status transitions to `resolved` or `dismissed`, `resolved_at` is set to `timezone.now()`.
- When re-opened, `resolved_at` is cleared to `None`.

---

## 8. REST API Endpoints

All endpoints require JWT authentication and strictly enforce tenant/project isolation:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/seo/recommendations/?project_id=<id>` | List recommendations for a project. |
| `GET` | `/api/seo/recommendations/?project_id=<id>&status=open&severity=high` | Filter by status, severity, category, or source_type. |
| `GET` | `/api/seo/recommendations/<id>/` | Retrieve recommendation details. |
| `PATCH` | `/api/seo/recommendations/<id>/` | Update lifecycle status (`{"status": "resolved"}`). |
| `POST` | `/api/seo/recommendations/<id>/acknowledge/` | Convenience action to acknowledge. |
| `POST` | `/api/seo/recommendations/<id>/resolve/` | Convenience action to mark resolved. |
| `POST` | `/api/seo/recommendations/<id>/dismiss/` | Convenience action to dismiss. |
| `POST` | `/api/seo/recommendations/generate/` | Trigger evaluation (`{"project_id": <id>, "async": false}`). |

---

## 9. Celery Background Execution

- Task: `apps.seo.tasks.generate_project_recommendations_task`
- Signature: `generate_project_recommendations_task(project_id: int) -> Dict[str, Any]`
- Handles asynchronous batch generation without blocking the HTTP request thread.
- Logs sanitized execution metrics without exposing credentials.

---

## 10. Dashboard Integration

Mounted in `dashboard/src/components/SEORecommendationsPanel.tsx`:
- **KPI Summary Cards:** Total Open, Critical, High, Medium, and Resolved counts.
- **Filter Bar:** All Active, Critical/High, Technical SEO, Rankings, Competitors, Resolved.
- **Actions:** Quick-action buttons to Acknowledge, Mark Resolved, Re-open, or Dismiss.
- **Detailed Explanation:** Expandable view showing Problem breakdown, Why it matters, and concrete Remediation Steps.
- **Manual Refresh:** "⚡ Generate Recommendations" button for on-demand evaluation.

---

## 11. Security & Tenant Isolation

- **Tenant Isolation:** Enforced via `project__owner=self.request.user` on all queries. User A cannot view, modify, or generate recommendations for User B's project.
- **No SSRF / No Outbound Crawling:** The recommendation engine only reads existing internal database records (`CrawlPage`, `KeywordRanking`, `CompetitorSnapshot`). It never makes outbound HTTP requests to user-supplied URLs.
- **XSS Prevention:** All text rendered in the dashboard is safely encoded in React JSX.

---

## 12. Known Limitations & Future Roadmap

1. **Deterministic Rule Scope:** The engine only surfaces recommendations supported by active crawl and SERP data. It does not speculate or guess without evidence.
2. **Historical Retention:** Resolved recommendations are preserved for historical auditability unless explicitly purged by project deletion.
