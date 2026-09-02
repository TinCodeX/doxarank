"""
DoxaRank SEO Adaptive Strategy & Historical Learning Engine.

Transforms empirical historical outcome measurements into calibrated action planning signals.
Enforces deterministic Bayesian-style smoothing to prevent naive "win rate = truth" errors,
protects against small sample bias, respects multi-tenant project isolation, and exposes
structured, explainable 4-tier reasoning.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from django.utils import timezone

from apps.projects.models import Project
from apps.seo.models import (
    SEOAction, SEOActionPlan, ActionType, ActionStatus,
    SEOOutcome, PlanSEOOutcome
)
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher
)
from apps.seo.services.seo_outcome_learning import SEOHistoricalLearningService

logger = logging.getLogger(__name__)

# Minimum evaluatable samples required to classify an action as preferred or deprioritized
MIN_SAMPLE_FOR_CLASSIFICATION = 2

# Sample count threshold for high confidence historical grounding
MIN_SAMPLE_HIGH_CONFIDENCE = 5


class SEOAdaptiveStrategyService:
    """
    Adaptive Strategy Engine.
    Evaluates past measured SEOAction outcomes for a Project, applies explainable Bayesian
    smoothing, and yields deterministic action prioritization adjustments and confidence tiers.
    """

    def __init__(
        self,
        project: Project,
        publisher: Optional[AgentEventPublisher] = None
    ):
        self.project = project
        self.publisher = publisher or get_event_publisher()

    def _emit_event(
        self,
        event_type: Union[AgentEventType, str],
        payload: Dict[str, Any],
        run_id: Optional[int] = None
    ) -> None:
        try:
            event = AgentEvent(
                event_type=event_type,
                run_id=run_id or 0,
                project_id=self.project.id,
                payload=payload
            )
            self.publisher.publish(event)
        except Exception as exc:
            logger.debug(f"[SEOAdaptiveStrategyService] Event emission skipped: {exc}")

    @staticmethod
    def calculate_smoothed_rate(improved: int, evaluatable: int) -> float:
        """
        Deterministic Laplace/Bayesian smoothed win rate with pseudo-counts:
        prior mean = 0.50, pseudo-count weight = 2 (1 success, 1 failure).
        Formula: (improved + 1) / (evaluatable + 2)
        """
        if evaluatable < 0:
            return 0.50
        return round((improved + 1.0) / (evaluatable + 2.0), 3)

    @staticmethod
    def determine_confidence_level(evaluatable_count: int, avg_confidence: float) -> str:
        """
        Classify statistical confidence in historical signal:
        - HIGH: >= 5 evaluatable outcomes with avg outcome confidence >= 0.70
        - MEDIUM: 2-4 evaluatable outcomes, or >= 5 with lower outcome confidence
        - LOW: 1 evaluatable outcome or low-quality telemetry
        - NONE: 0 evaluatable outcomes
        """
        if evaluatable_count == 0:
            return "none"
        elif evaluatable_count == 1:
            return "low"
        elif evaluatable_count >= MIN_SAMPLE_HIGH_CONFIDENCE and avg_confidence >= 0.70:
            return "high"
        elif evaluatable_count >= MIN_SAMPLE_FOR_CLASSIFICATION:
            return "medium"
        return "low"

    @classmethod
    def calculate_priority_adjustment(
        cls,
        smoothed_rate: float,
        evaluatable_count: int,
        avg_confidence: float
    ) -> float:
        """
        Calculate bounded historical priority adjustment:
        Delta = (smoothed_rate - 0.50) * max_adjustment_scale * effective_weight
        where effective_weight = min(1.0, evaluatable / 8) * avg_confidence.
        Result is bounded between -0.15 and +0.15.
        """
        if evaluatable_count < 1:
            return 0.0

        sample_scale = min(1.0, evaluatable_count / 8.0)
        # Bounded confidence factor (fallback to 0.6 if avg_confidence is zero)
        conf_factor = avg_confidence if avg_confidence > 0.1 else 0.60
        effective_weight = sample_scale * conf_factor

        # Max adjustment magnitude is +/- 0.15
        delta = (smoothed_rate - 0.50) * 0.30 * effective_weight
        clamped_delta = max(-0.15, min(0.15, delta))
        return round(clamped_delta, 3)

    def evaluate_strategy(
        self,
        action_type_filter: Optional[str] = None,
        target_url_filter: Optional[str] = None,
        run_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive, project-scoped adaptive SEO strategy from historical learning signals.
        """
        # 1. Emit learning started event
        self._emit_event(
            AgentEventType.SEO_STRATEGY_LEARNING_STARTED,
            payload={
                "project_id": self.project.id,
                "action_type_filter": action_type_filter,
                "target_url_filter": target_url_filter,
            },
            run_id=run_id
        )

        # 2. Gather historical outcome signals via existing authoritative learning service
        signals = SEOHistoricalLearningService.get_historical_outcome_signals(
            project=self.project,
            action_type=action_type_filter,
            target_url=target_url_filter,
            limit=50
        )

        # 3. Emit evidence collected event
        self._emit_event(
            AgentEventType.SEO_STRATEGY_EVIDENCE_COLLECTED,
            payload={
                "total_actions": signals.get("total_actions", 0),
                "total_measured": signals.get("total_measured", 0),
                "improved": signals.get("improved", 0),
                "action_types_count": len(signals.get("by_action_type", {}))
            },
            run_id=run_id
        )

        total_measured = signals.get("total_measured", 0)
        improved = signals.get("improved", 0)
        no_change = signals.get("no_change", 0)
        declined = signals.get("declined", 0)
        insufficient_data = signals.get("insufficient_data", 0)
        unknown = signals.get("unknown", 0)
        avg_confidence = float(signals.get("average_confidence", 0.0))

        evaluatable_total = improved + no_change + declined
        overall_confidence_level = self.determine_confidence_level(evaluatable_total, avg_confidence)
        overall_smoothed_rate = self.calculate_smoothed_rate(improved, evaluatable_total) if evaluatable_total > 0 else 0.50
        overall_raw_rate = float(signals.get("success_rate", 0.0))

        preferred_actions: List[str] = []
        deprioritized_actions: List[str] = []
        neutral_actions: List[str] = []
        prioritizations: Dict[str, Dict[str, Any]] = {}

        by_action_type = signals.get("by_action_type", {})

        for at_key, at_data in by_action_type.items():
            at_improved = at_data.get("improved", 0)
            at_no_change = at_data.get("no_change", 0)
            at_declined = at_data.get("declined", 0)
            at_eval = at_improved + at_no_change + at_declined
            at_insufficient = at_data.get("insufficient_data", 0)

            at_raw_rate = float(at_data.get("success_rate", 0.0))
            at_smoothed_rate = self.calculate_smoothed_rate(at_improved, at_eval)
            at_conf_level = self.determine_confidence_level(at_eval, avg_confidence)
            at_adjustment = self.calculate_priority_adjustment(at_smoothed_rate, at_eval, avg_confidence)

            # Classify learning signal
            if at_eval == 0:
                signal = "insufficient_data"
                reason_detail = f"No evaluatable historical measurements for {at_key} (insufficient telemetry)."
            elif at_adjustment > 0.03:
                signal = "positive"
                reason_detail = (
                    f"Positive historical signal: {at_improved}/{at_eval} measured actions improved "
                    f"(raw: {int(at_raw_rate*100)}%, smoothed: {int(at_smoothed_rate*100)}%). "
                    f"Receives +{at_adjustment:.2f} priority boost."
                )
            elif at_adjustment < -0.03:
                signal = "negative"
                reason_detail = (
                    f"Subdued historical signal: {at_improved}/{at_eval} measured actions improved "
                    f"with {at_declined} regressions (smoothed: {int(at_smoothed_rate*100)}%). "
                    f"Receives {at_adjustment:.2f} priority adjustment."
                )
            else:
                signal = "neutral"
                reason_detail = (
                    f"Neutral historical signal for {at_key}: outcomes are balanced or sample size ({at_eval}) "
                    f"is not yet conclusive (smoothed: {int(at_smoothed_rate*100)}%)."
                )

            # Categorize action
            if at_eval >= MIN_SAMPLE_FOR_CLASSIFICATION and at_smoothed_rate >= 0.58 and at_adjustment > 0.02:
                preferred_actions.append(at_key)
            elif at_eval >= MIN_SAMPLE_FOR_CLASSIFICATION and at_smoothed_rate <= 0.42 and at_adjustment < -0.02:
                deprioritized_actions.append(at_key)
            else:
                neutral_actions.append(at_key)

            prioritizations[at_key] = {
                "action_type": at_key,
                "historical_sample_size": at_eval,
                "total_recorded": at_data.get("total", 0),
                "improved": at_improved,
                "no_change": at_no_change,
                "declined": at_declined,
                "insufficient_data": at_insufficient,
                "historical_success_rate": at_raw_rate,
                "historical_smoothed_rate": at_smoothed_rate,
                "historical_confidence": avg_confidence,
                "confidence_level": at_conf_level,
                "historical_adjustment": at_adjustment,
                "learning_signal": signal,
                "reasoning": reason_detail
            }

        # Build explainable executive summary reason
        if evaluatable_total == 0:
            summary_reason = (
                f"No conclusive historical outcome measurements available for '{self.project.name}'. "
                f"Strategy defaults to standard opportunity strength without empirical weighting."
            )
        else:
            summary_reason = (
                f"Evaluated {evaluatable_total} measured historical actions ({improved} improved, {declined} declined) "
                f"with {int(overall_raw_rate * 100)}% observed win rate (smoothed: {int(overall_smoothed_rate * 100)}%). "
            )
            if preferred_actions:
                summary_reason += f"Preferred historically effective actions: {', '.join(preferred_actions[:3])}. "
            if deprioritized_actions:
                summary_reason += f"Deprioritized historical laggards: {', '.join(deprioritized_actions[:3])}."

        strategy_payload = {
            "project_id": self.project.id,
            "project_name": self.project.name,
            "strategy_confidence": overall_confidence_level,
            "historical_sample_size": total_measured,
            "evaluatable_sample_size": evaluatable_total,
            "overall_success_rate": overall_raw_rate,
            "overall_smoothed_rate": overall_smoothed_rate,
            "preferred_actions": preferred_actions,
            "deprioritized_actions": deprioritized_actions,
            "neutral_actions": neutral_actions,
            "action_prioritizations": prioritizations,
            "reason": summary_reason,
            "evidence_hierarchy": {
                "tier_1_observed_facts": "Real-time Google Search Console performance and live website audit diagnostics",
                "tier_2_historical_evidence": f"{evaluatable_total} measured post-execution outcomes on this domain",
                "tier_3_inferences": "Empirical historical win/loss rates modulate future action planning priority without overriding current opportunity strength",
                "tier_4_recommendations": "Actions prioritized by combined opportunity strength, safety risk, and historical efficacy"
            }
        }

        # 4. Emit strategy generated event
        self._emit_event(
            AgentEventType.SEO_STRATEGY_GENERATED,
            payload={
                "project_id": self.project.id,
                "strategy_confidence": overall_confidence_level,
                "historical_sample_size": total_measured,
                "preferred_actions": preferred_actions,
                "deprioritized_actions": deprioritized_actions,
                "neutral_actions_count": len(neutral_actions)
            },
            run_id=run_id
        )

        logger.info(
            f"[SEOAdaptiveStrategyService] Strategy evaluated for '{self.project.name}': "
            f"Confidence={overall_confidence_level.upper()}, Preferred={preferred_actions}, Deprioritized={deprioritized_actions}"
        )

        return strategy_payload

    def prioritize_action(
        self,
        action_type: str,
        base_priority: float = 0.60,
        strategy_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Deterministically prioritize an individual action proposal using project historical strategy.
        """
        strategy = strategy_data or self.evaluate_strategy(action_type_filter=action_type)
        prio_map = strategy.get("action_prioritizations", {})
        at_info = prio_map.get(action_type)

        if not at_info:
            # No specific historical data for this action type
            return {
                "action_type": action_type,
                "base_priority": round(base_priority, 2),
                "historical_adjustment": 0.0,
                "final_priority": round(base_priority, 2),
                "historical_sample_size": 0,
                "historical_success_rate": 0.0,
                "historical_confidence": 0.0,
                "learning_signal": "insufficient_data",
                "confidence_level": "none",
                "reasoning": f"No historical outcome measurements for action type '{action_type}'. Standard baseline priority applied."
            }

        adj = float(at_info.get("historical_adjustment", 0.0))
        final_prio = round(max(0.10, min(1.0, base_priority + adj)), 2)

        return {
            "action_type": action_type,
            "base_priority": round(base_priority, 2),
            "historical_adjustment": adj,
            "final_priority": final_prio,
            "historical_sample_size": at_info.get("historical_sample_size", 0),
            "historical_success_rate": at_info.get("historical_success_rate", 0.0),
            "historical_confidence": at_info.get("historical_confidence", 0.0),
            "learning_signal": at_info.get("learning_signal", "neutral"),
            "confidence_level": at_info.get("confidence_level", "low"),
            "reasoning": at_info.get("reasoning", "")
        }
