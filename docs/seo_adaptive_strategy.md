# DoxaRank — Adaptive SEO Strategy & Historical Learning Architecture (Phase 4.6)

## 1. Overview & Closed-Loop Lifecycle

Phase 4.6 connects historical outcome measurement with autonomous strategy formulation, completing DoxaRank's closed adaptive learning loop:

```text
OBSERVE ──> INVESTIGATE ──> DETECT OPPORTUNITY ──> GENERATE ACTION PLAN (Adaptive Calibration)
   ▲                                                              │
   │                                                              ▼
 LEARN <── MEASURE OUTCOME <── VERIFY <── EXECUTE <── APPROVE <── CLASSIFY RISK
```

Prior to Phase 4.6, historical learning was passive: outcomes were classified and aggregated, but future recommendations relied strictly on heuristic opportunity scores. With Phase 4.6, the agent dynamically checks past action efficacy on this domain and adjusts planning priority accordingly.

---

## 2. Core Mathematical Formulation

### 2.1 Why Naive "Win Rate = Truth" Fails
A naive win rate ($\frac{\text{improved}}{\text{total}}$) suffers from severe sample size distortion:
- An action type tried once and succeeding would have a $100\%$ win rate, causing runaway over-prioritization.
- An action type tried once and failing would have a $0\%$ win rate, causing premature, unjustified suppression.

### 2.2 Laplace / Bayesian Smoothing (Beta Prior)
To prevent extreme values on small sample sizes, we initialize a symmetric prior ($\alpha = 1, \beta = 1$, representing a prior expected win rate of $50\%$):

$$\hat{p} = \frac{\text{improved} + 1}{\text{evaluatable} + 2}$$

Where:
- $\text{evaluatable} = \text{improved} + \text{no\_change} + \text{declined}$.
- Actions with outcome `INSUFFICIENT_DATA` or `UNKNOWN` are excluded from the denominator to avoid penalizing actions that have not completed their observation window.

**Behavior Examples:**
- 0 attempts: $\hat{p} = \frac{0 + 1}{0 + 2} = 0.50$ (perfectly neutral prior).
- 1 success out of 1: $\hat{p} = \frac{1 + 1}{1 + 2} = 0.67$ (modest positive signal, not $100\%$).
- 1 failure out of 1: $\hat{p} = \frac{0 + 1}{1 + 2} = 0.33$ (modest negative signal, not $0\%$).
- 8 successes out of 10: $\hat{p} = \frac{8 + 1}{10 + 2} = 0.75$ (high statistical confidence).

### 2.3 Confidence Tiers
Confidence is determined deterministically based on evaluatable sample size and average outcome measurement confidence:

| Tier | Minimum Evaluatable Actions | Average Confidence | Description |
|---|---|---|---|
| `high` | $\ge 5$ | $\ge 0.70$ | Statistically robust historical evidence on this domain. |
| `medium` | $2 \text{ to } 4$ | Any | Emerging domain trend; moderate evidentiary weight. |
| `low` | $1$ | Any | Preliminary single-sample observation; low evidentiary weight. |
| `none` | $0$ | N/A | No prior evaluatable actions; defaults to neutral baseline. |

### 2.4 Bounded Priority Adjustment
Historical adjustments are clamped strictly within $[-0.15, +0.15]$:

$$\Delta = (\hat{p} - 0.50) \times 0.30 \times w$$

Where the sample weight $w$ is defined as:

$$w = \min\left(1.0, \frac{N_{\text{eval}}}{8}\right) \times C_{\text{avg}}$$

- For $N_{\text{eval}} = 0$: $w = 0$, so $\Delta = 0.00$.
- For $N_{\text{eval}} = 1$ (win, $\hat{p} = 0.67$): $w \approx 0.125 \times 0.70 = 0.0875$, so $\Delta \approx +0.004$ (negligible shift).
- For $N_{\text{eval}} = 8$ (7 wins, $\hat{p} = 0.80$): $w \approx 1.0 \times 0.85 = 0.85$, so $\Delta \approx +0.0765$ (calibrated high-confidence boost).

### 2.5 Action Classification
Action types on a project are categorized into:
- **`preferred_actions`**: $\Delta \ge +0.02$ and $\hat{p} \ge 0.55$.
- **`deprioritized_actions`**: $\Delta \le -0.02$ and $\hat{p} \le 0.45$.
- **`neutral_actions`**: all other action types.

---

## 3. Four-Tier Reasoning & Evidence Hierarchy

To maintain scientific integrity and prevent hallucinations, agent reasoning strictly adheres to the 4-tier evidence hierarchy:

1. **Tier 1 — Observed Facts**: Real-time directly measured data from Google Search Console and live site audit diagnostics (e.g. CTR, impressions, missing H1, HTTP 404).
2. **Tier 2 — Historical Evidence**: Empirically measured before/after search performance from past actions on this specific project (e.g. 6 of 8 title tag updates showed measured ranking lift).
3. **Tier 3 — Inferences**: Deductions combining observed facts and historical performance patterns (e.g. low CTR on page /pricing is likely fixable via title optimization).
4. **Tier 4 — Recommendations**: Action proposals with calibrated priority scores.

> [!IMPORTANT]
> **Evidence Integrity Rule**: Historical evidence must NEVER be stated as guaranteed future fact.
> - **Prohibited**: "Changing the title will increase clicks by 25%."
> - **Required**: "Historically, title optimizations on this project improved performance in 6 of 8 measured actions (75% smoothed win rate), justifying an elevated planning priority."

---

## 4. Safety & Governance Boundaries

1. **Human Approval Invariance**: Priority adjustments influence the ordering and priority tier (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) of proposals. They **NEVER** bypass human approval or reduce an action's risk level.
2. **High-Risk Action Protection**: High-risk actions (`FIX_CANONICAL`, `REMOVE_REDIRECT_CHAIN`) retain `requires_human_approval = True` regardless of historical success rates.
3. **Tenant Isolation**: All adaptive calculations query only actions where `project.owner == request.user`. Outcomes from one tenant's project are never leaked or factored into another tenant's strategy.

---

## 5. Agent Tool & API Reference

### 5.1 Tool: `get_adaptive_seo_strategy`
- **Category**: `READ_ONLY`
- **Mutating**: `False`
- **Requires Approval**: `False`
- **Parameters**: `action_type` (optional string)

### 5.2 REST API Endpoints
- `GET /api/seo/ai/strategy/?project_id=<id>`
- `GET /api/seo/ai/actions/strategy/?project_id=<id>`

### Response Schema:
```json
{
  "project_id": 1,
  "project_name": "Example Store",
  "strategy_confidence": "high",
  "historical_sample_size": 14,
  "evaluatable_sample_size": 12,
  "overall_success_rate": 0.75,
  "overall_smoothed_rate": 0.71,
  "preferred_actions": ["optimize_title", "add_missing_meta_description"],
  "deprioritized_actions": ["thin_content_expansion"],
  "neutral_actions": ["fix_broken_internal_links"],
  "action_prioritizations": {
    "optimize_title": {
      "action_type": "optimize_title",
      "historical_sample_size": 6,
      "improved": 5,
      "no_change": 1,
      "declined": 0,
      "insufficient_data": 0,
      "historical_success_rate": 0.833,
      "historical_smoothed_rate": 0.75,
      "historical_confidence": 0.88,
      "confidence_level": "high",
      "historical_adjustment": 0.063,
      "learning_signal": "positive",
      "reasoning": "High historical confidence (6 samples, 75.0% smoothed win rate) justifies +6% priority boost."
    }
  },
  "reason": "Evaluated 12 historical actions with high confidence. Preferred actions: optimize_title, add_missing_meta_description.",
  "evidence_hierarchy": {
    "tier_1_observed_facts": "GSC clicks, impressions, and live audit findings.",
    "tier_2_historical_evidence": "12 past actions with 71% smoothed improvement rate.",
    "tier_3_inferences": "Title optimizations yield reliable CTR improvements for this domain.",
    "tier_4_recommendations": "Prioritize optimize_title while preserving human review gates."
  }
}
```
