"""
DoxaRank SEO Outcome Learning & Adaptive Intelligence Engine.

Provides deterministic before/after SEO measurement, empirical outcome classification,
evidence gathering (GSC analytics, live verification state, site audit defect resolution),
and historical learning signals for autonomous agent reasoning.

Core Principles:
1. Execution Success != SEO Success.
2. Verification Success != Ranking Success.
3. Deterministic, explainable, auditable, and evidence-based (NO opaque ML / fine-tuning).
4. Strictly isolated by Project context (multi-tenant safety).
5. Statistical grounding: distinguishes statistical movement from natural SEO volatility and insufficient data.
"""

import logging
from datetime import timedelta
from typing import Dict, Any, List, Optional, Tuple, Union
from django.db import transaction
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone

from apps.projects.models import Project
from apps.seo.models import (
    SEOAction, SEOActionPlan, ActionType, ActionStatus,
    VerificationStatus, SEOOutcome, PlanSEOOutcome, EvidenceQuality,
    AuditIssue, SiteAudit, SearchAnalyticsData, SearchConsoleConnection
)
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher
)
from apps.seo.services.seo_intelligence import normalize_url_path_for_matching

logger = logging.getLogger(__name__)

# Minimum impression thresholds for statistical evaluation
MIN_IMPRESSIONS_HIGH_CONFIDENCE = 100
MIN_IMPRESSIONS_MEDIUM_CONFIDENCE = 30
MIN_IMPRESSIONS_LOW_CONFIDENCE = 10

# Volatility deadband thresholds (fluctuations within these bounds are classified as NO_CHANGE)
POSITION_NOISE_THRESHOLD = 0.5  # Position change within +/- 0.5 is noise
CTR_NOISE_THRESHOLD = 0.002     # CTR change within +/- 0.2% is noise


class SEOOutcomeClassifier:
    """
    Deterministic SEO Outcome Classifier.
    Evaluates multi-source empirical evidence (GSC pre/post metrics, live verification, audit defect resolution)
    to classify the real-world impact of an SEO action without fabricating data.
    """

    @classmethod
    def classify(
        cls,
        action: SEOAction,
        before_metrics: Dict[str, Any],
        after_metrics: Dict[str, Any],
        verification_state: str,
        technical_resolved: Optional[bool] = None,
        has_gsc_connection: bool = True
    ) -> Dict[str, Any]:
        """
        Deterministically classify SEO action outcome based on gathered empirical evidence.
        """
        reasons: List[str] = []
        is_verified = verification_state == VerificationStatus.VERIFIED
        is_partially_verified = verification_state == VerificationStatus.PARTIALLY_VERIFIED
        is_verification_failed = verification_state == VerificationStatus.FAILED

        # 1. Verification Evidence
        if is_verified:
            reasons.append("Live technical page verification passed (changes persisted in real-world HTML).")
        elif is_partially_verified:
            reasons.append("Live verification partially confirmed intended changes.")
        elif is_verification_failed:
            reasons.append("Live verification failed (intended HTML/metadata changes were not detected).")
        else:
            reasons.append("Live verification has not been performed or is pending.")

        # 2. Technical Audit Defect Resolution
        if technical_resolved is True:
            reasons.append("Targeted technical SEO issue or crawl defect was resolved in subsequent audits.")
        elif technical_resolved is False:
            reasons.append("Targeted technical SEO issue remains open in site audit diagnostics.")

        # 3. Search Console Data Sufficiency Evaluation
        if not has_gsc_connection:
            outcome = SEOOutcome.UNKNOWN
            confidence = 0.20 if is_verified else 0.0
            reasons.append("Google Search Console connection is not configured or unavailable.")
            explanation = "SEO outcome is UNKNOWN because Search Console performance data is not connected."
            return {
                "seo_outcome": outcome,
                "confidence_score": round(confidence, 2),
                "evidence_quality": EvidenceQuality.INSUFFICIENT,
                "is_statistically_significant": False,
                "reasons": reasons,
                "explanation": explanation,
                "deltas": {}
            }

        before_impressions = before_metrics.get("impressions", 0)
        after_impressions = after_metrics.get("impressions", 0)
        before_clicks = before_metrics.get("clicks", 0)
        after_clicks = after_metrics.get("clicks", 0)
        before_ctr = float(before_metrics.get("ctr", 0.0))
        after_ctr = float(after_metrics.get("ctr", 0.0))
        before_pos = float(before_metrics.get("position", 0.0))
        after_pos = float(after_metrics.get("position", 0.0))

        # Check total data availability
        total_after_volume = after_impressions + after_clicks
        if total_after_volume < MIN_IMPRESSIONS_LOW_CONFIDENCE:
            outcome = SEOOutcome.INSUFFICIENT_DATA
            confidence = 0.30 if is_verified else 0.15
            reasons.append(
                f"Insufficient search volume after execution ({after_impressions} impressions, {after_clicks} clicks). "
                f"Minimum threshold is {MIN_IMPRESSIONS_LOW_CONFIDENCE} impressions."
            )
            explanation = (
                f"Outcome classified as INSUFFICIENT_DATA due to low post-execution search impressions "
                f"({after_impressions} impressions observed)."
            )
            return {
                "seo_outcome": outcome,
                "confidence_score": round(confidence, 2),
                "evidence_quality": EvidenceQuality.INSUFFICIENT,
                "is_statistically_significant": False,
                "reasons": reasons,
                "explanation": explanation,
                "deltas": {
                    "impressions_delta": after_impressions - before_impressions,
                    "clicks_delta": after_clicks - before_clicks,
                    "ctr_delta": round(after_ctr - before_ctr, 4),
                    "position_delta": round(after_pos - before_pos, 2),
                }
            }

        # Calculate metric deltas
        # Note: Lower position number is better (e.g. pos 5 is better than pos 12)
        pos_delta = before_pos - after_pos if (before_pos > 0 and after_pos > 0) else 0.0  # positive = rank improved
        ctr_delta = after_ctr - before_ctr
        clicks_delta = after_clicks - before_clicks
        impressions_delta = after_impressions - before_impressions

        # Determine evidence quality based on sample size
        if after_impressions >= MIN_IMPRESSIONS_HIGH_CONFIDENCE:
            evidence_quality = EvidenceQuality.HIGH
            base_confidence = 0.85
        elif after_impressions >= MIN_IMPRESSIONS_MEDIUM_CONFIDENCE:
            evidence_quality = EvidenceQuality.MEDIUM
            base_confidence = 0.70
        else:
            evidence_quality = EvidenceQuality.LOW
            base_confidence = 0.50

        # Adjust confidence for verification status
        if is_verified:
            base_confidence = min(1.0, base_confidence + 0.10)
        elif is_verification_failed:
            base_confidence = max(0.1, base_confidence - 0.25)

        # 4. Deterministic Metric Evaluation
        is_pos_improved = pos_delta > POSITION_NOISE_THRESHOLD
        is_pos_declined = pos_delta < -POSITION_NOISE_THRESHOLD
        is_ctr_improved = ctr_delta > CTR_NOISE_THRESHOLD
        is_ctr_declined = ctr_delta < -CTR_NOISE_THRESHOLD
        is_clicks_improved = clicks_delta > 0
        is_clicks_declined = clicks_delta < 0

        # Record specific metric reasons
        if before_pos > 0 and after_pos > 0:
            if is_pos_improved:
                reasons.append(f"Average ranking position improved from {before_pos:.1f} to {after_pos:.1f} (+{pos_delta:.1f} spots).")
            elif is_pos_declined:
                reasons.append(f"Average ranking position dropped from {before_pos:.1f} to {after_pos:.1f} ({pos_delta:.1f} spots).")
            else:
                reasons.append(f"Average ranking position remained stable ({before_pos:.1f} vs {after_pos:.1f}).")

        if is_ctr_improved:
            reasons.append(f"Click-through rate (CTR) increased from {before_ctr*100:.1f}% to {after_ctr*100:.1f}% (+{ctr_delta*100:.1f}%).")
        elif is_ctr_declined:
            reasons.append(f"Click-through rate (CTR) decreased from {before_ctr*100:.1f}% to {after_ctr*100:.1f}% ({ctr_delta*100:.1f}%).")

        if clicks_delta != 0:
            reasons.append(f"Organic clicks shifted by {clicks_delta:+d} ({before_clicks} -> {after_clicks}).")
        if impressions_delta != 0:
            reasons.append(f"Organic impressions shifted by {impressions_delta:+d} ({before_impressions} -> {after_impressions}).")

        # Score positive vs negative signals
        positive_signals = 0
        negative_signals = 0

        if is_pos_improved:
            positive_signals += 2
        if is_ctr_improved:
            positive_signals += 1.5
        if is_clicks_improved:
            positive_signals += 1
        if technical_resolved is True:
            positive_signals += 1

        if is_pos_declined:
            negative_signals += 2
        if is_ctr_declined:
            negative_signals += 1.5
        if is_clicks_declined and not is_pos_improved:
            negative_signals += 1
        if technical_resolved is False:
            negative_signals += 0.5
        if is_verification_failed:
            negative_signals += 1.5

        # Decision rule
        is_statistically_significant = (
            after_impressions >= MIN_IMPRESSIONS_MEDIUM_CONFIDENCE and
            (abs(pos_delta) > POSITION_NOISE_THRESHOLD or abs(ctr_delta) > CTR_NOISE_THRESHOLD)
        )

        if positive_signals >= 2 and positive_signals > negative_signals:
            outcome = SEOOutcome.IMPROVED
            confidence = min(0.95, base_confidence)
            explanation = (
                f"SEO performance IMPROVED post-execution. Observed ranking position gained +{pos_delta:.1f} spots "
                f"and CTR shifted by {ctr_delta*100:+.1f}% across {after_impressions} post-change impressions."
            )
        elif negative_signals >= 2 and negative_signals > positive_signals:
            outcome = SEOOutcome.DECLINED
            confidence = min(0.90, base_confidence)
            explanation = (
                f"SEO performance DECLINED post-execution. Observed ranking position dropped by {pos_delta:.1f} spots "
                f"or CTR reduced by {ctr_delta*100:.1f}%."
            )
        else:
            outcome = SEOOutcome.NO_CHANGE
            confidence = min(0.80, base_confidence)
            explanation = (
                f"SEO performance showed NO SIGNIFICANT CHANGE. Metrics remained within normal fluctuation boundaries "
                f"(position: {before_pos:.1f} -> {after_pos:.1f}, CTR: {before_ctr*100:.1f}% -> {after_ctr*100:.1f}%)."
            )

        return {
            "seo_outcome": outcome,
            "confidence_score": round(confidence, 2),
            "evidence_quality": evidence_quality,
            "is_statistically_significant": is_statistically_significant,
            "reasons": reasons,
            "explanation": explanation,
            "deltas": {
                "impressions_delta": impressions_delta,
                "clicks_delta": clicks_delta,
                "ctr_delta": round(ctr_delta, 4),
                "position_delta": round(pos_delta, 2),
            }
        }


class SEOOutcomeMeasurementService:
    """
    Temporal SEO Outcome Measurement Service.
    Measures and records empirical before/after performance for executed SEOActions and SEOActionPlans.
    """

    def __init__(
        self,
        project: Project,
        publisher: Optional[AgentEventPublisher] = None,
        default_window_days: int = 14
    ):
        self.project = project
        self.publisher = publisher or get_event_publisher()
        self.default_window_days = default_window_days

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
            logger.debug(f"[SEOOutcomeMeasurementService] Event emission skipped: {exc}")

    def gather_action_metrics(
        self,
        action: SEOAction,
        window_days: int = 14
    ) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
        """
        Gather symmetric before/after GSC metrics for an executed action based on its completion date.
        Returns (before_metrics, after_metrics, has_gsc_connection).
        """
        gsc_conn = SearchConsoleConnection.objects.filter(
            project=self.project,
            is_connected=True
        ).first()

        if not gsc_conn:
            return {}, {}, False

        # Determine reference execution date
        ref_date = action.completed_at or action.execution_started_at or action.updated_at or timezone.now()
        exec_date = ref_date.date() if hasattr(ref_date, 'date') else ref_date

        before_start = exec_date - timedelta(days=window_days)
        before_end = exec_date - timedelta(days=1)
        after_start = exec_date
        after_end = exec_date + timedelta(days=window_days)

        # Base query for analytics data
        qs = SearchAnalyticsData.objects.filter(connection=gsc_conn)

        target_url = action.target_url
        target_kw = action.target_keyword

        # Filter by URL if available
        if target_url:
            norm_path = normalize_url_path_for_matching(target_url)
            if norm_path and norm_path != '/':
                qs = qs.filter(page__icontains=norm_path)
            else:
                qs = qs.filter(page__icontains=target_url)
        elif target_kw:
            qs = qs.filter(query__icontains=target_kw)

        # Pre-execution window aggregation
        before_qs = qs.filter(date__gte=before_start, date__lte=before_end)
        before_agg = before_qs.aggregate(
            total_clicks=Sum('clicks'),
            total_impressions=Sum('impressions'),
            avg_ctr=Avg('ctr'),
            avg_position=Avg('position')
        )

        # Post-execution window aggregation
        after_qs = qs.filter(date__gte=after_start, date__lte=after_end)
        after_agg = after_qs.aggregate(
            total_clicks=Sum('clicks'),
            total_impressions=Sum('impressions'),
            avg_ctr=Avg('ctr'),
            avg_position=Avg('position')
        )

        before_metrics = {
            "start_date": before_start.isoformat(),
            "end_date": before_end.isoformat(),
            "clicks": before_agg['total_clicks'] or 0,
            "impressions": before_agg['total_impressions'] or 0,
            "ctr": float(before_agg['avg_ctr'] or 0.0),
            "position": float(before_agg['avg_position'] or 0.0),
            "rows_count": before_qs.count()
        }

        after_metrics = {
            "start_date": after_start.isoformat(),
            "end_date": after_end.isoformat(),
            "clicks": after_agg['total_clicks'] or 0,
            "impressions": after_agg['total_impressions'] or 0,
            "ctr": float(after_agg['avg_ctr'] or 0.0),
            "position": float(after_agg['avg_position'] or 0.0),
            "rows_count": after_qs.count()
        }

        return before_metrics, after_metrics, True

    def check_technical_issue_resolution(self, action: SEOAction) -> Optional[bool]:
        """
        Check if the originating or relevant AuditIssue on the target URL was resolved.
        """
        target_url = action.target_url
        if not target_url:
            return None

        norm_path = normalize_url_path_for_matching(target_url)
        latest_audit = SiteAudit.objects.filter(project=self.project).order_by('-created_at').first()
        if not latest_audit:
            return None

        # Check if matching issue exists in the latest audit
        matching_issues = AuditIssue.objects.filter(audit=latest_audit)
        if norm_path and norm_path != '/':
            matching_issues = matching_issues.filter(page_url__icontains=norm_path)
        else:
            matching_issues = matching_issues.filter(page_url__icontains=target_url)

        # Map action type to issue category if possible
        action_type = (action.action_type or "").lower()
        if "title" in action_type:
            matching_issues = matching_issues.filter(issue_type__icontains="title")
        elif "meta_description" in action_type:
            matching_issues = matching_issues.filter(issue_type__icontains="meta")
        elif "h1" in action_type:
            matching_issues = matching_issues.filter(issue_type__icontains="h1")
        elif "canonical" in action_type:
            matching_issues = matching_issues.filter(issue_type__icontains="canonical")
        elif "alt" in action_type:
            matching_issues = matching_issues.filter(issue_type__icontains="alt")

        # If zero matching issues remain in latest audit, it is resolved
        return not matching_issues.exists()

    def measure_action_outcome(
        self,
        action: SEOAction,
        window_days: Optional[int] = None,
        run_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Gather empirical evidence, classify SEO outcome, persist result to SEOAction,
        and emit structured AgentEvents.
        """
        action_id = action.id
        days = window_days or self.default_window_days

        # 1. Emit measurement started event
        self._emit_event(
            AgentEventType.SEO_OUTCOME_MEASUREMENT_STARTED,
            payload={
                "action_id": action_id,
                "action_type": action.action_type,
                "target_url": action.target_url,
                "window_days": days
            },
            run_id=run_id
        )

        # 2. Gather Evidence
        before_metrics, after_metrics, has_gsc = self.gather_action_metrics(action, window_days=days)
        verification_state = action.verification_status or VerificationStatus.PENDING
        technical_resolved = self.check_technical_issue_resolution(action)

        # 3. Emit evidence collected event
        self._emit_event(
            AgentEventType.SEO_OUTCOME_EVIDENCE_COLLECTED,
            payload={
                "action_id": action_id,
                "has_gsc_data": has_gsc,
                "before_impressions": before_metrics.get("impressions", 0),
                "after_impressions": after_metrics.get("impressions", 0),
                "verification_status": verification_state,
                "technical_resolved": technical_resolved
            },
            run_id=run_id
        )

        # 4. Classify Outcome
        classification = SEOOutcomeClassifier.classify(
            action=action,
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            verification_state=verification_state,
            technical_resolved=technical_resolved,
            has_gsc_connection=has_gsc
        )

        # 5. Build Comprehensive Evidence Snapshot
        outcome_evidence = {
            "action_id": action_id,
            "action_type": action.action_type,
            "target_url": action.target_url,
            "target_keyword": action.target_keyword,
            "window_days": days,
            "measured_at": timezone.now().isoformat(),
            "execution_state": "executed" if action.completed_at else "not_executed",
            "verification_state": verification_state,
            "technical_issue_resolved": technical_resolved,
            "before_metrics": before_metrics,
            "after_metrics": after_metrics,
            "deltas": classification.get("deltas", {}),
            "evidence_quality": classification.get("evidence_quality"),
            "is_statistically_significant": classification.get("is_statistically_significant"),
            "reasons": classification.get("reasons", []),
            "explanation": classification.get("explanation", "")
        }

        # 6. Persist to Database Atomically
        with transaction.atomic():
            target_action = SEOAction.objects.select_for_update().get(id=action_id)
            target_action.seo_outcome = classification["seo_outcome"]
            target_action.outcome_confidence = classification["confidence_score"]
            target_action.outcome_evidence = outcome_evidence
            target_action.outcome_measured_at = timezone.now()
            target_action.save(update_fields=[
                'seo_outcome',
                'outcome_confidence',
                'outcome_evidence',
                'outcome_measured_at',
                'updated_at'
            ])

        # Sync in-memory model
        action.seo_outcome = classification["seo_outcome"]
        action.outcome_confidence = classification["confidence_score"]
        action.outcome_evidence = outcome_evidence
        action.outcome_measured_at = target_action.outcome_measured_at

        # 7. Emit classified & completed events
        self._emit_event(
            AgentEventType.SEO_OUTCOME_CLASSIFIED,
            payload={
                "action_id": action_id,
                "seo_outcome": action.seo_outcome,
                "confidence_score": action.outcome_confidence,
                "explanation": outcome_evidence["explanation"]
            },
            run_id=run_id
        )

        self._emit_event(
            AgentEventType.SEO_OUTCOME_COMPLETED,
            payload={
                "action_id": action_id,
                "seo_outcome": action.seo_outcome,
                "confidence_score": action.outcome_confidence,
                "measured_at": action.outcome_measured_at.isoformat()
            },
            run_id=run_id
        )

        logger.info(
            f"[SEOOutcomeMeasurementService] Action #{action_id} classified -> {action.seo_outcome} "
            f"(Confidence: {action.outcome_confidence:.2f})"
        )

        return outcome_evidence

    def measure_plan_outcome(
        self,
        plan: SEOActionPlan,
        window_days: Optional[int] = None,
        run_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Measure outcome for all child actions of an SEOActionPlan, aggregate results,
        and assign a holistic plan effectiveness outcome.
        """
        plan_id = plan.id
        days = window_days or self.default_window_days
        actions = plan.actions.all()

        if not actions.exists():
            summary = {
                "plan_id": plan_id,
                "total_actions": 0,
                "measured_actions": 0,
                "improved": 0,
                "no_change": 0,
                "declined": 0,
                "insufficient_data": 0,
                "unknown": 0,
                "effectiveness_rate": 0.0,
                "overall_outcome": PlanSEOOutcome.UNKNOWN,
                "measured_at": timezone.now().isoformat(),
                "action_outcomes": []
            }
            return summary

        action_results = []
        counts = {
            SEOOutcome.IMPROVED: 0,
            SEOOutcome.NO_CHANGE: 0,
            SEOOutcome.DECLINED: 0,
            SEOOutcome.INSUFFICIENT_DATA: 0,
            SEOOutcome.UNKNOWN: 0
        }
        total_confidence = 0.0

        for act in actions:
            res = self.measure_action_outcome(act, window_days=days, run_id=run_id)
            act_outcome = act.seo_outcome
            counts[act_outcome] = counts.get(act_outcome, 0) + 1
            total_confidence += act.outcome_confidence
            action_results.append({
                "action_id": act.id,
                "action_type": act.action_type,
                "title": act.title,
                "outcome": act.seo_outcome,
                "confidence": act.outcome_confidence,
                "verification_status": act.verification_status,
                "explanation": res.get("explanation", "")
            })

        total_actions = len(actions)
        improved_cnt = counts[SEOOutcome.IMPROVED]
        unchanged_cnt = counts[SEOOutcome.NO_CHANGE]
        declined_cnt = counts[SEOOutcome.DECLINED]
        insufficient_cnt = counts[SEOOutcome.INSUFFICIENT_DATA]
        unknown_cnt = counts[SEOOutcome.UNKNOWN]

        evaluatable_cnt = improved_cnt + unchanged_cnt + declined_cnt
        effectiveness_rate = round(improved_cnt / evaluatable_cnt, 3) if evaluatable_cnt > 0 else 0.0
        avg_confidence = round(total_confidence / total_actions, 2) if total_actions > 0 else 0.0

        # Deterministic aggregate plan classification
        if evaluatable_cnt == 0:
            if insufficient_cnt > 0:
                overall_outcome = PlanSEOOutcome.INSUFFICIENT_DATA
            else:
                overall_outcome = PlanSEOOutcome.UNKNOWN
        elif improved_cnt > 0 and declined_cnt == 0:
            if improved_cnt == total_actions:
                overall_outcome = PlanSEOOutcome.EFFECTIVE
            else:
                overall_outcome = PlanSEOOutcome.PARTIALLY_EFFECTIVE
        elif improved_cnt > 0 and improved_cnt > declined_cnt:
            overall_outcome = PlanSEOOutcome.PARTIALLY_EFFECTIVE
        elif declined_cnt > 0 and declined_cnt >= improved_cnt:
            overall_outcome = PlanSEOOutcome.DECLINED
        elif unchanged_cnt > 0 and improved_cnt == 0 and declined_cnt == 0:
            overall_outcome = PlanSEOOutcome.INEFFECTIVE
        else:
            overall_outcome = PlanSEOOutcome.PARTIALLY_EFFECTIVE

        plan_summary = {
            "plan_id": plan_id,
            "title": plan.title,
            "total_actions": total_actions,
            "measured_actions": total_actions,
            "improved": improved_cnt,
            "no_change": unchanged_cnt,
            "declined": declined_cnt,
            "insufficient_data": insufficient_cnt,
            "unknown": unknown_cnt,
            "effectiveness_rate": effectiveness_rate,
            "average_confidence": avg_confidence,
            "overall_outcome": overall_outcome,
            "measured_at": timezone.now().isoformat(),
            "action_outcomes": action_results
        }

        # Persist to database atomically
        with transaction.atomic():
            target_plan = SEOActionPlan.objects.select_for_update().get(id=plan_id)
            target_plan.seo_outcome = overall_outcome
            target_plan.outcome_confidence = avg_confidence
            target_plan.outcome_summary = plan_summary
            target_plan.outcome_measured_at = timezone.now()
            target_plan.save(update_fields=[
                'seo_outcome',
                'outcome_confidence',
                'outcome_summary',
                'outcome_measured_at',
                'updated_at'
            ])

        plan.seo_outcome = overall_outcome
        plan.outcome_confidence = avg_confidence
        plan.outcome_summary = plan_summary
        plan.outcome_measured_at = target_plan.outcome_measured_at

        logger.info(
            f"[SEOOutcomeMeasurementService] Plan #{plan_id} classified -> {overall_outcome} "
            f"({improved_cnt}/{total_actions} actions improved, rate: {effectiveness_rate*100:.1f}%)"
        )

        return plan_summary


class SEOHistoricalLearningService:
    """
    Historical Learning & Evidence Aggregation Service.
    Transforms past measured SEOAction outcomes into structured empirical learning signals
    to ground future autonomous agent decisions without claiming correlation is causation.
    """

    @classmethod
    def get_historical_outcome_signals(
        cls,
        project: Project,
        action_type: Optional[str] = None,
        target_url: Optional[str] = None,
        outcome_filter: Optional[str] = None,
        limit: int = 20,
        publisher: Optional[AgentEventPublisher] = None,
        run_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Aggregate historical action outcomes into compact, token-efficient learning signals.
        Strict multi-tenant security guarantees: strictly filters by project.
        """
        # Ensure project isolation
        qs = SEOAction.objects.filter(project=project)

        if action_type:
            qs = qs.filter(action_type=action_type)
        if target_url:
            norm = normalize_url_path_for_matching(target_url)
            if norm and norm != '/':
                qs = qs.filter(target_url__icontains=norm)
            else:
                qs = qs.filter(target_url__icontains=target_url)
        if outcome_filter:
            qs = qs.filter(seo_outcome=outcome_filter)

        total_actions = qs.count()

        # Aggregate counts by outcome
        outcome_counts = qs.values('seo_outcome').annotate(count=Count('id'))
        counts_dict = {
            SEOOutcome.IMPROVED: 0,
            SEOOutcome.NO_CHANGE: 0,
            SEOOutcome.DECLINED: 0,
            SEOOutcome.INSUFFICIENT_DATA: 0,
            SEOOutcome.UNKNOWN: 0
        }
        for item in outcome_counts:
            o_key = item['seo_outcome']
            if o_key in counts_dict:
                counts_dict[o_key] = item['count']

        improved = counts_dict[SEOOutcome.IMPROVED]
        no_change = counts_dict[SEOOutcome.NO_CHANGE]
        declined = counts_dict[SEOOutcome.DECLINED]
        insufficient = counts_dict[SEOOutcome.INSUFFICIENT_DATA]
        unknown = counts_dict[SEOOutcome.UNKNOWN]

        evaluatable = improved + no_change + declined
        success_rate = round(improved / evaluatable, 3) if evaluatable > 0 else 0.0

        # Compute average confidence for measured items
        measured_qs = qs.filter(outcome_measured_at__isnull=False)
        avg_conf = measured_qs.aggregate(avg=Avg('outcome_confidence'))['avg'] or 0.0

        # Retrieve recent sample outcomes (compact representation)
        recent_samples = []
        for a in measured_qs.order_by('-outcome_measured_at')[:limit]:
            ev = a.outcome_evidence or {}
            recent_samples.append({
                "action_id": a.id,
                "action_type": a.action_type,
                "target_url": a.target_url,
                "target_keyword": a.target_keyword,
                "outcome": a.seo_outcome,
                "confidence": a.outcome_confidence,
                "verification_status": a.verification_status,
                "explanation": ev.get("explanation", ""),
                "measured_at": a.outcome_measured_at.isoformat() if a.outcome_measured_at else None
            })

        # By Action-Type Breakdown
        type_breakdown = {}
        type_groups = qs.values('action_type', 'seo_outcome').annotate(count=Count('id'))
        for row in type_groups:
            at = row['action_type']
            oc = row['seo_outcome']
            if at not in type_breakdown:
                type_breakdown[at] = {
                    "total": 0,
                    "improved": 0,
                    "no_change": 0,
                    "declined": 0,
                    "insufficient_data": 0,
                    "unknown": 0,
                    "success_rate": 0.0
                }
            type_breakdown[at]["total"] += row['count']
            if oc in type_breakdown[at]:
                type_breakdown[at][oc] += row['count']

        for at, data in type_breakdown.items():
            ev_sub = data["improved"] + data["no_change"] + data["declined"]
            data["success_rate"] = round(data["improved"] / ev_sub, 3) if ev_sub > 0 else 0.0

        signal_payload = {
            "project_id": project.id,
            "project_name": project.name,
            "filtered_action_type": action_type,
            "filtered_target_url": target_url,
            "total_actions": total_actions,
            "total_measured": measured_qs.count(),
            "improved": improved,
            "no_change": no_change,
            "declined": declined,
            "insufficient_data": insufficient,
            "unknown": unknown,
            "success_rate": success_rate,
            "average_confidence": round(avg_conf, 2),
            "by_action_type": type_breakdown,
            "recent_samples": recent_samples
        }

        # Emit learning signal event
        pub = publisher or get_event_publisher()
        try:
            event = AgentEvent(
                event_type=AgentEventType.SEO_LEARNING_SIGNAL_GENERATED,
                run_id=run_id or 0,
                project_id=project.id,
                payload={
                    "total_measured": signal_payload["total_measured"],
                    "improved": improved,
                    "success_rate": success_rate,
                    "action_types_evaluated": list(type_breakdown.keys())
                }
            )
            pub.publish(event)
        except Exception as exc:
            logger.debug(f"[SEOHistoricalLearningService] Signal event skipped: {exc}")

        return signal_payload
