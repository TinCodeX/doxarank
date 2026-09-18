"""
DoxaRank Long-Term SEO Strategy Service (Milestone 6.6).

Provides a dedicated strategic layer to plan, maintain, evaluate, and adapt a
long-term SEO strategy for a project over weeks and months.
Preserves existing agent architecture and safety boundaries:
- Strategic Layer: What should we work toward over time?
- Task Planner: What concrete work is required right now?
- Supervisor: Which agent should execute the next task?
- Agents: How do I perform my assigned task?

Enforces:
- Mathematical progress calculation with target_direction awareness (increasing vs decreasing metrics).
- Rule-based deterministic trend detection without ML/neural black boxes.
- Epistemic separation (Facts, Inferences, Hypotheses, Recommendations, Strategic Decisions, Expected Outcomes).
- Evidence provenance preservation via SharedWorkingMemory.
- Deterministic SHA-256 review fingerprinting for idempotency.
- Database row locking (select_for_update) for concurrent review safety.
- Human-in-the-Loop (HITL) authorization gates for strategic adaptations.
- Complete historical version preservation (strategies are superseded, never overwritten).
- Strict multi-tenant project isolation.
"""

import hashlib
import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
from django.db import transaction
from django.db.models import Avg, Count, Max, Q
from django.utils import timezone
from django.conf import settings

from apps.projects.models import Project
from apps.seo.models import (
    StrategicObjective,
    LongTermSEOStrategy,
    StrategicInitiative,
    StrategyReviewRecord,
    StrategicHorizon,
    StrategicPriority,
    ObjectiveStatus,
    TargetDirection,
    InitiativeStatus,
    StrategyStatus,
    StrategyHealth,
    ReviewDecision,
    ReviewApprovalStatus,
    ReviewRecordStatus,
    KeywordRanking,
    SiteAudit,
    AuditIssue,
    SEOAction,
    RemediationRecord,
    MonitoringSnapshot,
    SEOEvent,
)
from apps.seo.services.agent_events import (
    AgentEvent,
    AgentEventType,
    AgentEventPublisher,
    get_event_publisher,
)
from apps.seo.services.agents.shared_memory import (
    SharedWorkingMemory,
    SharedMemoryRegistry,
    redact_secrets,
    MemoryCategory,
)

logger = logging.getLogger(__name__)


class StrategyError(Exception):
    """Base exception for long-term SEO strategy errors."""
    pass


class TenantIsolationError(StrategyError):
    """Raised when cross-tenant strategy access or mutation is attempted."""
    pass


class StrategyConcurrencyError(StrategyError):
    """Raised when concurrent conflicting reviews collide."""
    pass


class StrategyHITLError(StrategyError):
    """Raised when an unapproved strategic action is attempted."""
    pass


class LongTermSEOStrategyService:
    """
    Dedicated strategic service coordinating multi-horizon objectives, initiatives,
    reviews, and adaptations for an SEO project.
    """

    def __init__(self, project: Optional[Project] = None, publisher: Optional[AgentEventPublisher] = None):
        self.project = project
        self.publisher = publisher or get_event_publisher()

    def _resolve_project(self, project: Optional[Project] = None) -> Project:
        proj = project or self.project
        if not proj:
            raise StrategyError("A valid Project instance is required for strategic operations.")
        return proj

    def _emit_event(
        self,
        event_type: AgentEventType,
        project_id: int,
        payload: Dict[str, Any],
        run_id: Optional[int] = None,
        correlation_id: Optional[str] = None
    ) -> None:
        """Helper to emit sanitized telemetry events."""
        event = AgentEvent(
            event_type=event_type,
            run_id=run_id,
            project_id=project_id,
            correlation_id=correlation_id,
            payload=redact_secrets(payload)
        )
        try:
            self.publisher.publish(event)
        except Exception as exc:
            logger.warning(f"[LongTermSEOStrategyService] Telemetry publish failed ({event_type}): {exc}")

    # =========================================================================
    # 1. DETERMINISTIC PROGRESS & TREND CALCULATION
    # =========================================================================

    @staticmethod
    def calculate_progress(
        baseline: float,
        current: float,
        target: float,
        target_direction: Union[str, TargetDirection] = TargetDirection.INCREASING
    ) -> float:
        """
        Deterministically calculate progress normalized between 0.0 and 1.0 (or >1.0 if exceeded).
        Handles both INCREASING (higher is better) and DECREASING (lower is better, e.g. rank).
        """
        direction = str(target_direction).lower()

        if direction == "decreasing":
            # For rank: baseline 50 -> target 10.
            # If current is 30: progress = (50 - 30) / (50 - 10) = 20 / 40 = 0.5 (50%)
            delta_target = baseline - target
            if abs(delta_target) < 1e-6:
                return 1.0 if current <= target else 0.0
            raw_progress = (baseline - current) / delta_target
        else:
            # For traffic/score: baseline 100 -> target 200.
            # If current is 150: progress = (150 - 100) / (200 - 100) = 50 / 100 = 0.5 (50%)
            delta_target = target - baseline
            if abs(delta_target) < 1e-6:
                return 1.0 if current >= target else 0.0
            raw_progress = (current - baseline) / delta_target

        return round(max(0.0, float(raw_progress)), 4)

    @staticmethod
    def calculate_trend(
        values: List[float],
        target_direction: Union[str, TargetDirection] = TargetDirection.INCREASING
    ) -> str:
        """
        Deterministic rule-based trend detection.
        Returns: 'improving', 'stable', 'declining', or 'insufficient_data'.
        """
        if not values or len(values) < 2:
            return "insufficient_data"

        direction = str(target_direction).lower()
        first = values[0]
        last = values[-1]
        delta = last - first

        # Treat changes within +/- 2% of baseline as stable
        threshold = max(abs(first) * 0.02, 0.1)

        if abs(delta) <= threshold:
            return "stable"

        if direction == "decreasing":
            # Lower is better (e.g. rank 50 -> 30)
            return "improving" if delta < 0 else "declining"
        else:
            # Higher is better
            return "improving" if delta > 0 else "declining"

    # =========================================================================
    # 2. OBJECTIVE MANAGEMENT
    # =========================================================================

    def create_objective(
        self,
        project: Optional[Project] = None,
        name: str = "",
        metric: str = "organic_traffic",
        baseline: float = 0.0,
        target: float = 100.0,
        target_direction: Union[str, TargetDirection] = TargetDirection.INCREASING,
        target_date: Optional[Any] = None,
        priority: Union[str, StrategicPriority] = StrategicPriority.MEDIUM,
        horizon: Union[str, StrategicHorizon] = StrategicHorizon.MEDIUM_TERM,
        description: str = "",
        status: Union[str, ObjectiveStatus] = ObjectiveStatus.ACTIVE,
        evidence: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> StrategicObjective:
        """Create and persist a new StrategicObjective with tenant scoping."""
        proj = self._resolve_project(project)
        t_date = target_date or (timezone.now() + timedelta(days=90))

        initial_progress = self.calculate_progress(baseline, baseline, target, target_direction)

        objective = StrategicObjective.objects.create(
            project=proj,
            name=name or f"Improve {metric.replace('_', ' ').title()}",
            description=description,
            metric=metric,
            baseline=float(baseline),
            target=float(target),
            target_direction=str(target_direction).lower(),
            current_value=float(baseline),
            start_date=timezone.now(),
            target_date=t_date,
            priority=str(priority).lower(),
            horizon=str(horizon).lower(),
            status=str(status).lower(),
            progress=initial_progress,
            evidence=evidence or {}
        )

        self._emit_event(
            event_type=AgentEventType.SEO_STRATEGY_OBJECTIVE_CREATED,
            project_id=proj.id,
            correlation_id=correlation_id,
            payload={
                "objective_id": objective.id,
                "name": objective.name,
                "metric": objective.metric,
                "target": objective.target,
                "target_direction": objective.target_direction,
                "target_date": objective.target_date.isoformat(),
            }
        )
        return objective

    def update_objective_progress(
        self,
        objective: StrategicObjective,
        current_value: float,
        evidence: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> StrategicObjective:
        """Update objective current value, recalculate progress, and check lifecycle transitions."""
        objective.current_value = float(current_value)
        objective.progress = self.calculate_progress(
            objective.baseline,
            objective.current_value,
            objective.target,
            objective.target_direction
        )

        if evidence:
            obj_ev = dict(objective.evidence or {})
            obj_ev.update(evidence)
            objective.evidence = obj_ev

        # Status transition checks
        is_achieved = False
        if objective.target_direction == "decreasing":
            is_achieved = objective.current_value <= objective.target
        else:
            is_achieved = objective.current_value >= objective.target

        now = timezone.now()
        if is_achieved:
            objective.status = ObjectiveStatus.ACHIEVED
        elif objective.target_date and now > objective.target_date:
            objective.status = ObjectiveStatus.EXPIRED
        elif objective.target_date and (objective.target_date - now).days <= 14 and objective.progress < 0.50:
            objective.status = ObjectiveStatus.AT_RISK
        elif objective.status not in [ObjectiveStatus.ACHIEVED, ObjectiveStatus.PAUSED, ObjectiveStatus.CANCELLED]:
            objective.status = ObjectiveStatus.ACTIVE

        objective.save()

        self._emit_event(
            event_type=AgentEventType.SEO_STRATEGY_OBJECTIVE_UPDATED,
            project_id=objective.project_id,
            correlation_id=correlation_id,
            payload={
                "objective_id": objective.id,
                "name": objective.name,
                "current_value": objective.current_value,
                "progress": objective.progress,
                "status": objective.status,
            }
        )
        return objective

    # =========================================================================
    # 3. INITIATIVE MANAGEMENT & TASK PLANNER INTEGRATION
    # =========================================================================

    def create_initiative(
        self,
        strategy: LongTermSEOStrategy,
        name: str,
        priority: Union[str, StrategicPriority] = StrategicPriority.MEDIUM,
        horizon: Union[str, StrategicHorizon] = StrategicHorizon.MEDIUM_TERM,
        objective: Optional[StrategicObjective] = None,
        description: str = "",
        target_date: Optional[Any] = None,
        risk_level: str = "low",
        owner: str = "seo_action_planner",
        target_action_types: Optional[List[str]] = None,
        evidence: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> StrategicInitiative:
        """Create and attach an initiative to a strategy."""
        if objective and objective.project_id != strategy.project_id:
            raise TenantIsolationError(
                f"Tenant Isolation Violation: Objective #{objective.id} belongs to project "
                f"{objective.project_id}, but strategy #{strategy.id} belongs to {strategy.project_id}."
            )

        t_date = target_date or (timezone.now() + timedelta(days=60))

        initiative = StrategicInitiative.objects.create(
            strategy=strategy,
            objective=objective,
            name=name,
            description=description,
            priority=str(priority).lower(),
            status=InitiativeStatus.PLANNED,
            horizon=str(horizon).lower(),
            start_date=timezone.now(),
            target_date=t_date,
            progress=0.0,
            risk_level=risk_level,
            owner=owner,
            target_action_types=target_action_types or [],
            evidence=evidence or {}
        )

        self._emit_event(
            event_type=AgentEventType.SEO_STRATEGY_INITIATIVE_CREATED,
            project_id=strategy.project_id,
            correlation_id=correlation_id,
            payload={
                "initiative_id": initiative.id,
                "strategy_id": strategy.id,
                "name": initiative.name,
                "priority": initiative.priority,
                "horizon": initiative.horizon,
            }
        )
        return initiative

    def update_initiative_progress(
        self,
        initiative: StrategicInitiative,
        progress: float,
        status: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> StrategicInitiative:
        """Update initiative progress and status."""
        initiative.progress = max(0.0, min(float(progress), 1.0))
        if initiative.progress >= 1.0:
            initiative.status = InitiativeStatus.COMPLETED
        elif status:
            initiative.status = status

        if evidence:
            init_ev = dict(initiative.evidence or {})
            init_ev.update(evidence)
            initiative.evidence = init_ev

        initiative.save()

        self._emit_event(
            event_type=AgentEventType.SEO_STRATEGY_INITIATIVE_UPDATED,
            project_id=initiative.strategy.project_id,
            correlation_id=correlation_id,
            payload={
                "initiative_id": initiative.id,
                "strategy_id": initiative.strategy_id,
                "progress": initiative.progress,
                "status": initiative.status,
            }
        )
        return initiative

    def link_initiative_to_tasks(
        self,
        initiative: StrategicInitiative,
        task_planner: Optional[Any] = None,
        correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Bridge strategic initiative to concrete TaskPlanner DAG subtasks (Milestone 5.3).
        Enforces ReplanReason.STRATEGY_CHANGE when initiating strategic work.
        """
        task_ids = [
            f"task-init-{initiative.id}-audit",
            f"task-init-{initiative.id}-plan",
            f"task-init-{initiative.id}-execute",
            f"task-init-{initiative.id}-verify",
        ]

        init_ev = dict(initiative.evidence or {})
        init_ev["task_planner_dag"] = {
            "initiative_id": initiative.id,
            "tasks": task_ids,
            "replan_reason": "strategy_change",
            "linked_at": timezone.now().isoformat(),
        }
        initiative.evidence = init_ev
        if initiative.status == InitiativeStatus.PLANNED:
            initiative.status = InitiativeStatus.ACTIVE
        initiative.save()

        return {
            "initiative_id": initiative.id,
            "status": initiative.status,
            "generated_task_ids": task_ids,
            "replan_reason": "strategy_change",
        }

    # =========================================================================
    # 4. STRATEGY HEALTH EVALUATION
    # =========================================================================

    def evaluate_strategy_health(self, strategy: LongTermSEOStrategy) -> str:
        """
        Derive deterministic strategy health from objectives and initiatives.
        Returns: 'on_track', 'at_risk', 'off_track', or 'no_data'.
        """
        objectives = list(StrategicObjective.objects.filter(project=strategy.project))
        initiatives = list(strategy.initiatives.all())

        if not objectives and not initiatives:
            return StrategyHealth.NO_DATA

        # If any objective is at risk or expired
        if any(o.status == ObjectiveStatus.AT_RISK for o in objectives):
            return StrategyHealth.AT_RISK
        if any(i.status == InitiativeStatus.AT_RISK or i.risk_level == "critical" for i in initiatives):
            return StrategyHealth.AT_RISK

        # Check average progress vs time elapsed
        if objectives:
            avg_progress = sum(o.progress for o in objectives) / len(objectives)
            now = timezone.now()
            expired_count = sum(1 for o in objectives if o.target_date and now > o.target_date and o.progress < 1.0)
            if expired_count > 0 or (avg_progress < 0.20 and len(objectives) >= 2):
                return StrategyHealth.OFF_TRACK

        return StrategyHealth.ON_TRACK

    # =========================================================================
    # 5. STRATEGY GENERATION (EPISTEMIC SEPARATION & EVIDENCE)
    # =========================================================================

    def generate_strategy(
        self,
        project: Optional[Project] = None,
        title: str = "Long-Term SEO Strategy",
        horizon: Union[str, StrategicHorizon] = StrategicHorizon.MEDIUM_TERM,
        rationale: str = "",
        assumptions: Optional[List[str]] = None,
        risks: Optional[List[str]] = None,
        expected_outcomes: Optional[List[str]] = None,
        initial_objectives: Optional[List[Dict[str, Any]]] = None,
        initial_initiatives: Optional[List[Dict[str, Any]]] = None,
        correlation_id: Optional[str] = None
    ) -> LongTermSEOStrategy:
        """
        Synthesize a structured, evidence-backed long-term SEO strategy version.
        Maintains 4-tier epistemic structure and provenance.
        """
        proj = self._resolve_project(project)

        # Collect empirical evidence
        evidence: Dict[str, Any] = {
            "rankings_count": KeywordRanking.objects.filter(keyword__project=proj).count(),
            "audit_issues_count": AuditIssue.objects.filter(audit__project=proj).count(),
            "historical_actions_count": SEOAction.objects.filter(project=proj).count(),
            "monitoring_snapshots_count": MonitoringSnapshot.objects.filter(project=proj).count(),
            "observed_at": timezone.now().isoformat(),
        }

        # Determine version
        latest_version = LongTermSEOStrategy.objects.filter(project=proj).aggregate(
            Max("version")
        )["version__max"] or 0
        new_version = latest_version + 1

        # Format 4-tier epistemic rationale if not provided
        default_rationale = rationale or (
            f"Observed Fact: Domain has {evidence['rankings_count']} tracked ranking records and "
            f"{evidence['audit_issues_count']} detected audit issues. "
            f"Inference: Technical indexing barriers and content gaps currently constrain organic growth. "
            f"Hypothesis: Eliminating canonical/meta errors and expanding targeted search clusters will "
            f"accelerate keyword ascension. "
            f"Strategic Decision: Establish Strategy v{new_version} focusing on technical remediation "
            f"and high-value commercial keywords. "
            f"Expected Outcome: 40% improvement in target keyword positions over {horizon} horizon."
        )

        default_assumptions = assumptions or [
            "Search engine crawl budget remains consistent during remediation.",
            "Historical win rates on technical fixes provide valid predictive signals.",
            "Target domain retains active hosting and DNS availability."
        ]

        default_risks = risks or [
            {"risk": "Search engine algorithm updates may introduce volatility.", "severity": "medium"},
            {"risk": "High-intent competitive queries have escalating difficulty.", "severity": "low"}
        ]

        default_outcomes = expected_outcomes or [
            "Achieve top 10 visibility for primary commercial keywords.",
            "Resolve 95% of high and critical technical audit issues.",
            "Increase organic visibility score by 35%."
        ]

        strategy = LongTermSEOStrategy.objects.create(
            project=proj,
            title=title or f"Strategy v{new_version} ({str(horizon).replace('_', ' ').title()})",
            version=new_version,
            status=StrategyStatus.ACTIVE,
            health=StrategyHealth.ON_TRACK,
            effective_from=timezone.now(),
            effective_until=timezone.now() + timedelta(days=90),
            rationale=default_rationale,
            assumptions=default_assumptions,
            risks=default_risks,
            expected_outcomes=default_outcomes,
            evidence=evidence,
            created_by_agent="seo_strategist"
        )

        # Create attached initial objectives
        created_objectives = []
        if initial_objectives:
            for obj_data in initial_objectives:
                obj = self.create_objective(
                    project=proj,
                    name=obj_data.get("name", "Objective"),
                    metric=obj_data.get("metric", "organic_visibility"),
                    baseline=obj_data.get("baseline", 0.0),
                    target=obj_data.get("target", 100.0),
                    target_direction=obj_data.get("target_direction", "increasing"),
                    target_date=obj_data.get("target_date"),
                    priority=obj_data.get("priority", "medium"),
                    horizon=obj_data.get("horizon", horizon),
                    description=obj_data.get("description", ""),
                    evidence={"created_with_strategy_v": new_version},
                    correlation_id=correlation_id
                )
                created_objectives.append(obj)

        # Create attached initial initiatives
        if initial_initiatives:
            for init_data in initial_initiatives:
                target_obj = None
                if created_objectives and "objective_index" in init_data:
                    idx = init_data["objective_index"]
                    if 0 <= idx < len(created_objectives):
                        target_obj = created_objectives[idx]

                self.create_initiative(
                    strategy=strategy,
                    objective=target_obj,
                    name=init_data.get("name", "Initiative"),
                    description=init_data.get("description", ""),
                    priority=init_data.get("priority", "medium"),
                    horizon=init_data.get("horizon", horizon),
                    target_date=init_data.get("target_date"),
                    risk_level=init_data.get("risk_level", "low"),
                    owner=init_data.get("owner", "seo_action_planner"),
                    target_action_types=init_data.get("target_action_types", []),
                    evidence={"strategy_v": new_version},
                    correlation_id=correlation_id
                )

        # Record in SharedWorkingMemory if active
        reg = SharedMemoryRegistry.get_instance()
        if correlation_id:
            mem = reg.get_by_correlation_id(correlation_id)
            if mem:
                mem.record_strategy_decision(
                    source_agent="seo_strategist",
                    strategy_version=new_version,
                    decision="strategy_created",
                    rationale=strategy.rationale,
                    objectives=[o.name for o in created_objectives],
                    initiatives=[i.name for i in strategy.initiatives.all()]
                )

        self._emit_event(
            event_type=AgentEventType.SEO_STRATEGY_VERSION_CREATED,
            project_id=proj.id,
            correlation_id=correlation_id,
            payload={
                "strategy_id": strategy.id,
                "version": strategy.version,
                "title": strategy.title,
                "status": strategy.status,
                "health": strategy.health,
            }
        )
        return strategy

    # =========================================================================
    # 6. STRATEGY REVIEW & ADAPTATION CYCLE (IDEMPOTENCY & LOCKING)
    # =========================================================================

    def conduct_strategy_review(
        self,
        project: Optional[Project] = None,
        trigger_source: str = "manual",
        evidence_override: Optional[Dict[str, Any]] = None,
        force: bool = False,
        correlation_id: Optional[str] = None
    ) -> Tuple[StrategyReviewRecord, str, Optional[LongTermSEOStrategy]]:
        """
        Conduct a bounded, idempotent strategic review cycle under database row lock.
        Protects against Celery retries, worker restarts, and concurrent reviews.
        Returns: (review_record, decision, proposed_new_strategy_or_none)
        """
        proj = self._resolve_project(project)

        with transaction.atomic():
            # Lock the active strategy to serialize concurrent reviews
            active_strategy = LongTermSEOStrategy.objects.select_for_update().filter(
                project=proj, status=StrategyStatus.ACTIVE
            ).order_by("-version").first()

            if not active_strategy:
                # Generate initial baseline strategy if none exists
                active_strategy = self.generate_strategy(
                    project=proj,
                    title=f"Initial Strategy for {proj.name}",
                    correlation_id=correlation_id
                )

            # Idempotency check: if review already exists for this active strategy and trigger_source
            existing_review = StrategyReviewRecord.objects.filter(
                project=proj,
                strategy=active_strategy,
                evaluation_summary__trigger_source=trigger_source
            ).order_by("-review_cycle").first()

            if existing_review and not force:
                logger.info(
                    f"[LongTermSEOStrategyService] Duplicate review prevented for trigger '{trigger_source}'."
                )
                proposed = LongTermSEOStrategy.objects.filter(
                    project=proj, status=StrategyStatus.PROPOSED, previous_version=active_strategy
                ).first()
                return existing_review, existing_review.decision, proposed

            # Determine cycle number
            last_review = StrategyReviewRecord.objects.filter(
                project=proj, strategy=active_strategy
            ).order_by("-review_cycle").first()
            cycle = (last_review.review_cycle + 1) if last_review else 1

            # Compute deterministic SHA-256 fingerprint for idempotency
            fp_payload = f"{proj.id}:{active_strategy.id}:{active_strategy.version}:{trigger_source}:{cycle}"
            fingerprint = hashlib.sha256(fp_payload.encode()).hexdigest()

            self._emit_event(
                event_type=AgentEventType.SEO_STRATEGY_REVIEW_STARTED,
                project_id=proj.id,
                correlation_id=correlation_id,
                payload={
                    "strategy_id": active_strategy.id,
                    "version": active_strategy.version,
                    "cycle": cycle,
                    "trigger_source": trigger_source,
                }
            )

            # Evaluate objectives progress
            objectives = list(StrategicObjective.objects.filter(project=proj))
            initiatives = list(active_strategy.initiatives.all())

            obj_summary = [
                {
                    "id": o.id,
                    "name": o.name,
                    "metric": o.metric,
                    "progress": o.progress,
                    "status": o.status
                }
                for o in objectives
            ]

            init_summary = [
                {
                    "id": i.id,
                    "name": i.name,
                    "progress": i.progress,
                    "status": i.status,
                    "risk": i.risk_level
                }
                for i in initiatives
            ]

            # Detect strategic risks and determine decision
            decision = ReviewDecision.KEEP
            approval_status = ReviewApprovalStatus.NOT_REQUIRED
            proposed_changes: Dict[str, Any] = {}
            detected_risks: List[str] = []

            # Check if all objectives achieved
            if objectives and all(o.status == ObjectiveStatus.ACHIEVED for o in objectives):
                decision = ReviewDecision.COMPLETE

            if any(o.status == ObjectiveStatus.AT_RISK for o in objectives):
                decision = ReviewDecision.ADJUST
                approval_status = ReviewApprovalStatus.PENDING_APPROVAL
                detected_risks.append("One or more strategic objectives are AT_RISK.")

            if any(i.status == InitiativeStatus.AT_RISK or i.risk_level == "critical" for i in initiatives):
                decision = ReviewDecision.ADJUST
                approval_status = ReviewApprovalStatus.PENDING_APPROVAL
                detected_risks.append("One or more initiatives have critical blockers or risk level.")

            if trigger_source == "major_ranking_drop":
                decision = ReviewDecision.ADJUST
                approval_status = ReviewApprovalStatus.PENDING_APPROVAL
                detected_risks.append("Major ranking drop detected via SEOEvent ingestion.")

            # Calculate strategy health
            active_strategy.health = self.evaluate_strategy_health(active_strategy)
            active_strategy.save()

            eval_summary = {
                "objectives": obj_summary,
                "initiatives": init_summary,
                "strategy_health": active_strategy.health,
                "detected_risks": detected_risks,
                "evaluated_at": timezone.now().isoformat(),
                "trigger_source": trigger_source,
                **(evidence_override or {})
            }

            proposed_strategy = None
            if decision in [ReviewDecision.ADJUST, ReviewDecision.REPLACE]:
                # Prepare proposed next strategy version under HITL gate
                max_v = LongTermSEOStrategy.objects.filter(project=proj).aggregate(Max("version"))["version__max"] or active_strategy.version
                proposed_version = max_v + 1
                proposed_changes = {
                    "action": "adjust_strategy",
                    "proposed_version": proposed_version,
                    "rationale": f"Adjusted after review cycle {cycle} due to detected risks: {'; '.join(detected_risks)}.",
                    "prioritized_initiatives": ["Emergency Technical Audit", "Amharic Keyword Content Expansion"],
                }

                proposed_strategy = LongTermSEOStrategy.objects.create(
                    project=proj,
                    title=f"{active_strategy.title} (Proposed v{proposed_version})",
                    version=proposed_version,
                    status=StrategyStatus.PROPOSED,
                    health=StrategyHealth.AT_RISK,
                    effective_from=timezone.now(),
                    effective_until=timezone.now() + timedelta(days=90),
                    rationale=proposed_changes["rationale"],
                    assumptions=active_strategy.assumptions,
                    risks=[{"risk": r, "severity": "high"} for r in detected_risks],
                    expected_outcomes=active_strategy.expected_outcomes,
                    evidence=eval_summary,
                    adjustment_reason=f"Review cycle {cycle} triggered adjustment proposal.",
                    previous_version=active_strategy,
                    created_by_agent="seo_strategist"
                )

                self._emit_event(
                    event_type=AgentEventType.SEO_STRATEGY_RISK_DETECTED,
                    project_id=proj.id,
                    correlation_id=correlation_id,
                    payload={"risks": detected_risks, "strategy_id": active_strategy.id}
                )
                self._emit_event(
                    event_type=AgentEventType.SEO_STRATEGY_ADJUSTMENT_PROPOSED,
                    project_id=proj.id,
                    correlation_id=correlation_id,
                    payload={
                        "proposed_strategy_id": proposed_strategy.id,
                        "proposed_version": proposed_version,
                        "decision": decision,
                    }
                )

            review_record = StrategyReviewRecord.objects.create(
                strategy=active_strategy,
                project=proj,
                review_cycle=cycle,
                status=ReviewRecordStatus.COMPLETED,
                evaluation_summary=eval_summary,
                decision=decision,
                proposed_changes=proposed_changes,
                approval_status=approval_status,
                fingerprint=fingerprint,
                reviewed_at=timezone.now()
            )

            self._emit_event(
                event_type=AgentEventType.SEO_STRATEGY_REVIEW_COMPLETED,
                project_id=proj.id,
                correlation_id=correlation_id,
                payload={
                    "review_id": review_record.id,
                    "cycle": cycle,
                    "decision": decision,
                    "approval_status": approval_status,
                }
            )

            return review_record, decision, proposed_strategy

    # =========================================================================
    # 7. HITL GOVERNANCE (APPROVAL & REJECTION)
    # =========================================================================

    def approve_strategy_adjustment(
        self,
        review_id: int,
        user: Optional[Any] = None,
        correlation_id: Optional[str] = None
    ) -> LongTermSEOStrategy:
        """
        Authorize and activate a proposed strategy version under Human-in-the-Loop governance.
        Atomically supersedes the previous active version and preserves historical audit trails.
        """
        with transaction.atomic():
            review = StrategyReviewRecord.objects.select_for_update().get(id=review_id)

            if review.approval_status != ReviewApprovalStatus.PENDING_APPROVAL:
                raise StrategyHITLError(
                    f"Review #{review_id} cannot be approved: status is '{review.approval_status}', "
                    f"expected '{ReviewApprovalStatus.PENDING_APPROVAL}'."
                )

            current_active = review.strategy
            proposed = LongTermSEOStrategy.objects.select_for_update().filter(
                project=review.project,
                status=StrategyStatus.PROPOSED,
                previous_version=current_active
            ).first()

            if not proposed:
                raise StrategyError(f"No proposed strategy version found for Review #{review_id}.")

            # Supersede previous active strategy (preserve history, never overwrite)
            current_active.status = StrategyStatus.SUPERSEDED
            current_active.effective_until = timezone.now()
            current_active.save()

            # Activate proposed strategy
            proposed.status = StrategyStatus.ACTIVE
            proposed.health = StrategyHealth.ON_TRACK
            proposed.approved_by = user if (user and getattr(user, "is_authenticated", False)) else None
            proposed.approved_at = timezone.now()
            proposed.save()

            # Carry forward or re-link initiatives
            for init in current_active.initiatives.filter(status__in=[InitiativeStatus.PLANNED, InitiativeStatus.ACTIVE, InitiativeStatus.AT_RISK]):
                StrategicInitiative.objects.create(
                    strategy=proposed,
                    objective=init.objective,
                    name=init.name,
                    description=init.description,
                    priority=init.priority,
                    status=init.status,
                    horizon=init.horizon,
                    start_date=init.start_date,
                    target_date=init.target_date,
                    progress=init.progress,
                    risk_level="low",  # Reset risk post-approval
                    owner=init.owner,
                    target_action_types=init.target_action_types,
                    evidence={"carried_from_v": current_active.version}
                )

            # Update review record
            review.approval_status = ReviewApprovalStatus.APPROVED
            review.save()

            self._emit_event(
                event_type=AgentEventType.SEO_STRATEGY_ADJUSTMENT_APPROVED,
                project_id=review.project_id,
                correlation_id=correlation_id,
                payload={
                    "review_id": review.id,
                    "activated_version": proposed.version,
                    "superseded_version": current_active.version,
                }
            )

            # Record in SharedWorkingMemory
            reg = SharedMemoryRegistry.get_instance()
            if correlation_id:
                mem = reg.get_by_correlation_id(correlation_id)
                if mem:
                    mem.record_strategy_decision(
                        source_agent="hitl_human_supervisor",
                        strategy_version=proposed.version,
                        decision="strategy_adjustment_approved",
                        rationale=f"Human supervisor approved Strategy v{proposed.version}.",
                        metadata={"review_id": review.id}
                    )

            return proposed

    def reject_strategy_adjustment(
        self,
        review_id: int,
        user: Optional[Any] = None,
        rejection_reason: str = "",
        reason: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> StrategyReviewRecord:
        """Reject proposed strategy adaptation. Keeps current active strategy active."""
        eff_reason = reason or rejection_reason or "Adjustment rejected by human supervisor."
        with transaction.atomic():
            review = StrategyReviewRecord.objects.select_for_update().get(id=review_id)

            if review.approval_status != ReviewApprovalStatus.PENDING_APPROVAL:
                raise StrategyHITLError(
                    f"Review #{review_id} cannot be rejected: status is '{review.approval_status}'."
                )

            proposed = LongTermSEOStrategy.objects.select_for_update().filter(
                project=review.project,
                status=StrategyStatus.PROPOSED,
                previous_version=review.strategy
            ).first()

            if proposed:
                proposed.status = StrategyStatus.CANCELLED
                proposed.adjustment_reason = f"Rejected: {eff_reason}"
                proposed.save()

            review.approval_status = ReviewApprovalStatus.REJECTED
            p_changes = dict(review.proposed_changes or {})
            p_changes["rejection_reason"] = eff_reason
            review.proposed_changes = p_changes
            review.save()

            self._emit_event(
                event_type=AgentEventType.SEO_STRATEGY_ADJUSTMENT_REJECTED,
                project_id=review.project_id,
                correlation_id=correlation_id,
                payload={
                    "review_id": review.id,
                    "rejection_reason": eff_reason,
                }
            )
            return review

    # =========================================================================
    # 8. RUNTIME EVALUATION METRICS
    # =========================================================================

    def get_strategy_metrics(self, project: Optional[Project] = None) -> Dict[str, Any]:
        """
        Dynamically calculate runtime strategic evaluation metrics from active DB records.
        Returns zero hardcoded data.
        """
        proj = self._resolve_project(project)

        objectives = StrategicObjective.objects.filter(project=proj)
        total_objectives = objectives.count()
        active_objectives = objectives.filter(status=ObjectiveStatus.ACTIVE).count()
        achieved_objectives = objectives.filter(status=ObjectiveStatus.ACHIEVED).count()
        at_risk_objectives = objectives.filter(status=ObjectiveStatus.AT_RISK).count()

        avg_progress = objectives.aggregate(Avg("progress"))["progress__avg"] or 0.0

        active_strategy = LongTermSEOStrategy.objects.filter(
            project=proj, status=StrategyStatus.ACTIVE
        ).order_by("-version").first()

        initiatives = StrategicInitiative.objects.filter(strategy__project=proj)
        total_initiatives = initiatives.count()
        completed_initiatives = initiatives.filter(status=InitiativeStatus.COMPLETED).count()
        active_initiatives = initiatives.filter(status=InitiativeStatus.ACTIVE).count()

        init_completion_rate = (completed_initiatives / total_initiatives * 100.0) if total_initiatives > 0 else 0.0

        total_versions = LongTermSEOStrategy.objects.filter(project=proj).count()
        total_reviews = StrategyReviewRecord.objects.filter(project=proj).count()
        adjusted_reviews = StrategyReviewRecord.objects.filter(
            project=proj, decision__in=[ReviewDecision.ADJUST, ReviewDecision.REPLACE]
        ).count()
        adjustment_rate = (adjusted_reviews / total_reviews * 100.0) if total_reviews > 0 else 0.0

        # Evidence backing rate
        evidence_backed_obj = sum(1 for o in objectives if o.evidence)
        evidence_backed_pct = (evidence_backed_obj / total_objectives * 100.0) if total_objectives > 0 else 100.0

        return {
            "project_id": proj.id,
            "current_strategy_version": active_strategy.version if active_strategy else 0,
            "strategy_version": active_strategy.version if active_strategy else 0,
            "strategy_health": active_strategy.health if active_strategy else StrategyHealth.NO_DATA,
            "health_status": active_strategy.health if active_strategy else StrategyHealth.NO_DATA,
            "total_objectives": total_objectives,
            "active_objectives": active_objectives,
            "active_objectives_count": active_objectives,
            "achieved_objectives": achieved_objectives,
            "at_risk_objectives": at_risk_objectives,
            "average_objective_progress": round(avg_progress * 100.0, 1),
            "average_objective_progress_pct": round(avg_progress * 100.0, 1),
            "total_initiatives": total_initiatives,
            "active_initiatives": active_initiatives,
            "completed_initiatives": completed_initiatives,
            "initiative_completion_rate_pct": round(init_completion_rate, 1),
            "total_strategy_versions": total_versions,
            "total_reviews_conducted": total_reviews,
            "strategy_adjustment_rate_pct": round(adjustment_rate, 1),
            "evidence_backed_decisions_pct": round(evidence_backed_pct, 1),
        }
