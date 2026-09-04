"""
DoxaRank Specialized SEO Agents — Strategy Agent (Phase 4.7)

Responsible for deciding action prioritization, domain-specific historical win rates,
and Bayesian priority adjustments while maintaining strict 4-tier reasoning integrity.
Reuses SEOAdaptiveStrategyService and SEOHistoricalLearningService.
"""

import logging
from typing import Dict, Any, List
from .base_agent import BaseSpecializedAgent, AgentResult, SharedContext
from apps.seo.services.seo_adaptive_strategy import SEOAdaptiveStrategyService

logger = logging.getLogger(__name__)


class SEOStrategyAgent(BaseSpecializedAgent):
    """
    SEO Strategy Agent.
    Formulates data-grounded domain strategy by combining live opportunity signals
    with empirical historical performance. Enforces 4-tier reasoning hierarchy.
    Allowed Tools: Strategy and historical outcome tools.
    """

    name: str = "seo_strategist"
    purpose: str = "Synthesize empirical strategy, prioritize opportunities, and evaluate historical action efficacy."

    allowed_tools: List[str] = [
        "get_adaptive_seo_strategy",
        "get_action_outcomes",
        "analyze_seo_opportunities"
    ]

    def _execute(self, context: SharedContext) -> AgentResult:
        findings: List[str] = []
        recommendations: List[Dict[str, Any]] = []
        observed_facts: List[Dict[str, Any]] = []
        inferences: List[Dict[str, Any]] = []
        uncertainties: List[str] = []

        service = SEOAdaptiveStrategyService(project=self.project, publisher=self.publisher)
        strategy = service.evaluate_strategy()

        # Extract strategy parameters
        conf_level = strategy.get("strategy_confidence", "none")
        sample_size = strategy.get("historical_sample_size", 0)
        eval_size = strategy.get("evaluatable_sample_size", 0)
        smoothed_rate = strategy.get("overall_smoothed_rate", 0.50)
        preferred = strategy.get("preferred_actions", [])
        deprioritized = strategy.get("deprioritized_actions", [])
        evidence_hierarchy = strategy.get("evidence_hierarchy", {})

        # Tier 1 & 2 findings
        fact_str = (
            f"Strategy Evaluation ({conf_level.upper()} confidence): "
            f"{sample_size} historical actions analyzed ({eval_size} evaluatable), "
            f"smoothed domain win rate {round(smoothed_rate*100, 1)}%."
        )
        findings.append(fact_str)
        observed_facts.append({
            "fact": fact_str,
            "source": "get_adaptive_seo_strategy",
            "confidence": 1.0,
            "raw_data": {"sample_size": sample_size, "eval_size": eval_size, "smoothed_rate": smoothed_rate}
        })

        # Base strategy inference
        inferences.append({
            "inference": f"Domain strategy posture evaluated at confidence '{conf_level}' with baseline win rate {smoothed_rate:.1%}.",
            "based_on": ["get_adaptive_seo_strategy"],
            "confidence": 0.80
        })

        if preferred:
            findings.append(f"Empirically Preferred Action Types: {', '.join(preferred)}")
            inferences.append({
                "inference": f"Historically preferred action types ({', '.join(preferred)}) have demonstrated higher efficacy on this domain.",
                "based_on": ["get_adaptive_seo_strategy"],
                "confidence": 0.85
            })
        if deprioritized:
            findings.append(f"Historically Deprioritized Action Types: {', '.join(deprioritized)}")
            inferences.append({
                "inference": f"Historically deprioritized action types ({', '.join(deprioritized)}) should receive lower ranking weight.",
                "based_on": ["get_adaptive_seo_strategy"],
                "confidence": 0.85
            })

        findings.append(f"Strategy Rationale: {strategy.get('reason', '')}")

        if eval_size < 5:
            uncertainties.append(f"Low domain evaluation sample size ({eval_size} evaluatable actions); Laplace Bayesian priors dominate win rate.")

        # Formulate recommendations based on investigation findings + strategy signals
        for inv in context.investigation_findings:
            rec_actions = inv.get("recommended_actions", [])
            for rec in rec_actions:
                act_type = rec.get("action_type")
                prio_data = service.prioritize_action(action_type=act_type, base_priority=0.60, strategy_data=strategy)
                recommendations.append({
                    "action_type": act_type,
                    "target_url": inv.get("target_url"),
                    "target_query": inv.get("target_query"),
                    "base_priority": prio_data["base_priority"],
                    "historical_adjustment": prio_data["historical_adjustment"],
                    "final_priority": prio_data["final_priority"],
                    "learning_signal": prio_data["learning_signal"],
                    "reasoning": prio_data["reasoning"]
                })
                inferences.append({
                    "inference": f"Action '{act_type}' calibrated with priority {prio_data['final_priority']} (adjustment: {prio_data['historical_adjustment']:+.2f}).",
                    "based_on": ["get_adaptive_seo_strategy"],
                    "confidence": 0.80
                })

        # Save into shared context
        context.strategy_signals.update(strategy)

        # Map confidence level to score
        conf_map = {"high": 0.90, "medium": 0.75, "low": 0.60, "none": 0.50}
        confidence_score = conf_map.get(conf_level, 0.50)

        return AgentResult(
            agent=self.name,
            status="completed",
            confidence=confidence_score,
            evidence={
                "strategy": strategy,
                "evidence_hierarchy": evidence_hierarchy
            },
            findings=findings,
            recommendations=recommendations,
            observed_facts=observed_facts,
            inferences=inferences,
            uncertainties=uncertainties,
            assumptions=["Historical performance lift accurately signals future probability of improvement."],
            next_step="action_planning",
            metadata={
                "preferred_actions": preferred,
                "deprioritized_actions": deprioritized,
                "confidence_level": conf_level
            }
        )
