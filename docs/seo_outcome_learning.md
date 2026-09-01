# DoxaRank — SEO Outcome Learning & Adaptive Agent Intelligence (Phase 4.5)

## 1. Executive Overview & Core Principle

In production search engine optimization, **execution success is not SEO success**, and **verification success is not ranking success**.

- **Execution Success**: The CMS / WordPress / file mutation succeeded without raising an exception.
- **Verification Success**: The live HTML on the target URL reflects the updated `<title>`, meta description, or canonical tag.
- **SEO Outcome Success**: The technical change persisted, the defect disappeared, and search performance (clicks, CTR, impressions, average position) improved or stabilized relative to historical baseline.

Phase 4.5 builds the closed-loop **LEARN** stage of DoxaRank's autonomous cycle:

$$\text{OBSERVE} \to \text{INVESTIGATE} \to \text{DETECT} \to \text{CHECK HISTORICAL OUTCOMES} \to \text{PLAN} \to \text{CLASSIFY RISK} \to \text{REQUEST APPROVAL} \to \text{EXECUTE} \to \text{VERIFY} \to \text{MEASURE} \to \text{LEARN}$$

This architecture introduces **no black-box machine learning or fine-tuning**. Instead, it uses **deterministic outcome measurement**, **noise-resistant classification thresholds**, and **structured historical evidence** to guide agent confidence and decision-making.

---

## 2. Measurement Lifecycle & Time Windows

Outcome measurement is performed symmetrically around the action's execution timestamp ($T_{\text{exec}}$):

$$\text{Pre-Period} = [T_{\text{exec}} - W \text{ days}, \, T_{\text{exec}}]$$
$$\text{Post-Period} = [T_{\text{exec}}, \, T_{\text{exec}} + W \text{ days}]$$

Default measurement window $W = 14$ days (configurable up to 90 days).

### Lifecycle Events:
1. `seo.outcome.measurement.started`: Initiates measurement job.
2. `seo.outcome.evidence.collected`: Aggregates GSC daily search performance before and after execution.
3. `seo.outcome.classified`: Computes metric deltas and classifies outcome into deterministic states.
4. `seo.learning.signal.generated`: Stores win/loss statistics indexed by `(project_id, action_type)`.
5. `seo.outcome.completed`: Finalizes outcome persistence on the `SEOAction` and parent `SEOActionPlan`.

---

## 3. Deterministic Outcome Classification

### State Hierarchy (`SEOOutcome`):
- `IMPROVED`: Significant positive search performance lift or position gain beyond deadbands.
- `NO_CHANGE`: Metric fluctuations remain within the expected noise deadband.
- `DECLINED`: Significant degradation in rankings, CTR, or clicks after mutation.
- `INSUFFICIENT_DATA`: Total search impressions in pre- or post-period are below statistical threshold ($< 50$ impressions).
- `UNKNOWN`: Action has not yet been measured.

### Action Plan Outcomes (`PlanSEOOutcome`):
- `EFFECTIVE`: $>60\%$ of constituent atomic actions improved with zero critical regressions.
- `PARTIALLY_EFFECTIVE`: Mixed results with overall positive trend.
- `NO_CHANGE`: No significant movement across child actions.
- `INEFFECTIVE`: Child actions failed to yield positive search lift.
- `DECLINED`: Aggregate search performance decreased.
- `INSUFFICIENT_DATA`: Insufficient telemetry data across actions.

### Noise Deadbands & Thresholds:
To prevent overreacting to ordinary Google SERP volatility, DoxaRank enforces minimum deadbands:
- **Position Gain Threshold**: $\Delta \text{Position} \ge +1.0$ spot (e.g. #8.4 to #7.2).
- **Position Loss Threshold**: $\Delta \text{Position} \le -1.5$ spots.
- **CTR Lift Threshold**: $\Delta \text{CTR} \ge +1.5\%$ absolute lift ($+0.015$).
- **CTR Drop Threshold**: $\Delta \text{CTR} \le -1.5\%$.
- **Click Lift Threshold**: $\Delta \text{Clicks} \ge +10\%$ relative or $+10$ net clicks.
- **Minimum Telemetry Floor**: Pre-period or post-period impressions $\ge 50$.

---

## 4. Four-Tier Agent Reasoning Framework

When the agent evaluates SEO opportunities and generates recommendations, it categorizes its reasoning into four distinct tiers:

1. **Tier 1: Observed Facts**: Direct measurements from Google Search Console, crawl status codes, and verified HTML tags.
2. **Tier 2: Historical Evidence**: Empirical win rates, sample sizes, and average position deltas from previously executed actions of the same type in this project.
3. **Tier 3: Inferences**: Causal deductions drawn from connecting observed facts with historical patterns.
4. **Tier 4: Recommendations**: Specific, risk-classified actions backed by evidence and calibrated confidence scores.

### Agent Tool Integration (`get_action_outcomes`):
The agent queries historical outcomes via the `get_action_outcomes` tool (25 core tools total). It analyzes:
- Win rate per action type (e.g., `optimize_title` has an $83\%$ historical success rate).
- Average CTR lift and position changes.
- Previously ineffective tactics on the specific project to avoid repeating failed mutations.

---

## 5. Confidence Score Calibration

Agent plan and action confidence scores are dynamically calibrated based on historical evidence quality:

$$\text{Confidence} = w_b \cdot C_{\text{baseline}} + w_h \cdot \text{WinRate}_{\text{action\_type}}$$

Where:
- If historical data has $\ge 5$ samples: Evidence quality is `HIGH`, historical weight $w_h = 0.6$.
- If historical data has $2\text{--}4$ samples: Evidence quality is `MEDIUM`, historical weight $w_h = 0.3$.
- If historical data has $< 2$ samples: Evidence quality is `LOW` or `NONE`, defaults to domain baseline confidence.

---

## 6. REST API Endpoints

- `POST /api/seo/ai/actions/<id>/measure-outcome/`: Triggers empirical outcome measurement for an individual action.
- `GET /api/seo/ai/actions/outcomes-summary/?project_id=<id>`: Returns project-wide historical win/loss signals and per-action-type statistics.
- `POST /api/seo/ai/action-plans/<id>/measure-outcome/`: Triggers aggregate outcome measurement across all child actions in an action plan.

---

## 7. Quality & Safety Guarantees

1. **Non-Destructive Measurement**: Outcome analysis is strictly read-only against telemetry tables (`GSCSearchQueryPerformance`, `GSCPagePerformance`, `SiteAudit`).
2. **Tenant Isolation**: Historical signals and outcome calculations are strictly partitioned by `project_id` and authorized tenant.
3. **Asynchronous Background Execution**: Celery workers handle intensive time-series window evaluations without blocking REST request cycles.
4. **Empirical Grounding**: Prevents hallucinated AI confidence by tying all predictions directly to real search performance deltas.
