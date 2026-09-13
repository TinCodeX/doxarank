"""
DoxaRank Agent Learning & Performance Optimization (Milestone 5.6).

Provides bounded, deterministic, explainable, and multi-tenant isolated learning
from historical execution, verification, and routing outcomes to inform future
agent selection and coordination decisions.

Core Principle:
"Based on what happened before, how should the system make better decisions next time?"

Safety Invariants:
1. Learning is strictly ADVISORY and BOUNDED (soft scoring contribution <= 0.08).
2. Historical evidence NEVER overrides hard capability constraints, ToolRegistry allowlists,
   MCP permission boundaries, risk level gates, HITL governance, or tenant isolation.
3. System will NOT autonomously retrain models, modify code, or grant itself permissions.
4. Human rejection and safety blocks are classified distinctly and not treated as simple agent failures.
5. Strict tenant isolation: private tenant data (URLs, keywords, queries) is never exposed across tenants.
"""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from django.utils import timezone

from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher, sanitize_event_payload
)

logger = logging.getLogger(__name__)


class FailureCategory(str, Enum):
    """
    Categorized taxonomy of task failure modes.
    Differentiates internal agent failure from external tool issues, safety blocks, or human rejection.
    """
    NONE = "none"
    AGENT_FAILURE = "agent_failure"
    TOOL_FAILURE = "tool_failure"
    DEPENDENCY_FAILURE = "dependency_failure"
    SAFETY_BLOCK = "safety_block"
    HUMAN_REJECTION = "human_rejection"
    VERIFICATION_FAILURE = "verification_failure"
    SYSTEM_FAILURE = "system_failure"


@dataclass
class AgentPerformanceRecord:
    """
    Atomic historical record capturing the execution and routing outcome of a single task.
    Serves as the empirical foundation for runtime-derived learning signals.
    """
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = ""
    task_id: str = ""
    task_type: str = "general"
    task_objective: str = ""
    project_id: int = 0
    success: bool = False
    execution_duration_ms: int = 0
    predicted_confidence: float = 0.85
    verification_status: str = "none"  # "verified" | "failed" | "unverified" | "none"
    reassignment_count: int = 0
    tool_usage: List[str] = field(default_factory=list)
    failure_category: FailureCategory = FailureCategory.NONE
    failure_reason: Optional[str] = None
    was_fallback: bool = False
    routing_metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: timezone.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "agent_name": self.agent_name,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "task_objective": self.task_objective,
            "project_id": self.project_id,
            "success": self.success,
            "execution_duration_ms": self.execution_duration_ms,
            "predicted_confidence": round(self.predicted_confidence, 4),
            "verification_status": self.verification_status,
            "reassignment_count": self.reassignment_count,
            "tool_usage": list(self.tool_usage),
            "failure_category": self.failure_category.value if isinstance(self.failure_category, FailureCategory) else str(self.failure_category),
            "failure_reason": self.failure_reason,
            "was_fallback": self.was_fallback,
            "routing_metadata": sanitize_event_payload(self.routing_metadata),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentPerformanceRecord":
        fc = data.get("failure_category", FailureCategory.NONE)
        if isinstance(fc, str):
            try:
                fc = FailureCategory(fc)
            except ValueError:
                fc = FailureCategory.NONE
        return cls(
            record_id=data.get("record_id", str(uuid.uuid4())),
            agent_name=data.get("agent_name", ""),
            task_id=data.get("task_id", ""),
            task_type=data.get("task_type", "general"),
            task_objective=data.get("task_objective", ""),
            project_id=data.get("project_id", 0),
            success=data.get("success", False),
            execution_duration_ms=data.get("execution_duration_ms", 0),
            predicted_confidence=data.get("predicted_confidence", 0.85),
            verification_status=data.get("verification_status", "none"),
            reassignment_count=data.get("reassignment_count", 0),
            tool_usage=data.get("tool_usage", []),
            failure_category=fc,
            failure_reason=data.get("failure_reason"),
            was_fallback=data.get("was_fallback", False),
            routing_metadata=data.get("routing_metadata", {}),
            timestamp=data.get("timestamp", timezone.now().isoformat()),
        )


@dataclass
class AgentPerformanceStats:
    """
    Aggregated statistical performance summary for an agent or agent/task_type pair.
    Computed deterministically from actual historical execution records.
    """
    agent_name: str
    task_type: Optional[str] = None
    sample_size: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    success_rate: float = 0.0
    failure_rate: float = 0.0
    verification_attempts: int = 0
    verified_successes: int = 0
    verification_success_rate: float = 0.0
    average_duration_ms: float = 0.0
    reassignment_count: int = 0
    reassignment_rate: float = 0.0
    average_confidence: float = 0.0
    confidence_calibration_gap: float = 0.0
    routing_quality_score: float = 0.0
    failure_breakdown: Dict[str, int] = field(default_factory=dict)
    has_sufficient_evidence: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "task_type": self.task_type,
            "sample_size": self.sample_size,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate": round(self.success_rate, 4),
            "failure_rate": round(self.failure_rate, 4),
            "verification_attempts": self.verification_attempts,
            "verified_successes": self.verified_successes,
            "verification_success_rate": round(self.verification_success_rate, 4),
            "average_duration_ms": round(self.average_duration_ms, 1),
            "reassignment_count": self.reassignment_count,
            "reassignment_rate": round(self.reassignment_rate, 4),
            "average_confidence": round(self.average_confidence, 4),
            "confidence_calibration_gap": round(self.confidence_calibration_gap, 4),
            "routing_quality_score": round(self.routing_quality_score, 4),
            "failure_breakdown": self.failure_breakdown,
            "has_sufficient_evidence": self.has_sufficient_evidence,
        }


@dataclass
class HistoricalSignal:
    """
    Deterministic soft scoring signal provided to AdaptiveAgentSelector.
    Bounded strictly between [-0.08, +0.08] to prevent learning instability or runaway preference.
    """
    agent_name: str
    task_type: str
    signal_applied: bool = False
    score_contribution: float = 0.0
    sample_size: int = 0
    min_sample_threshold: int = 3
    success_rate: float = 0.0
    smoothed_success_rate: float = 0.0
    evidence_weight: float = 0.0
    verification_rate: float = 0.0
    reassignment_rate: float = 0.0
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "task_type": self.task_type,
            "signal_applied": self.signal_applied,
            "score_contribution": round(self.score_contribution, 4),
            "sample_size": self.sample_size,
            "min_sample_threshold": self.min_sample_threshold,
            "success_rate": round(self.success_rate, 4),
            "smoothed_success_rate": round(self.smoothed_success_rate, 4),
            "evidence_weight": round(self.evidence_weight, 4),
            "verification_rate": round(self.verification_rate, 4),
            "reassignment_rate": round(self.reassignment_rate, 4),
            "explanation": self.explanation,
        }


class AgentPerformanceStore:
    """
    Thread-safe in-memory performance store and aggregation engine.
    Maintains historical performance records partitioned by tenant (project_id)
    while also computing global anonymized rollups without exposing private tenant secrets.
    """
    _instance: Optional["AgentPerformanceStore"] = None
    _singleton_lock = threading.Lock()

    def __init__(self, min_sample_threshold: int = 3, max_signal_magnitude: float = 0.08):
        self._lock = threading.Lock()
        self.min_sample_threshold = max(1, min_sample_threshold)
        self.max_signal_magnitude = min(0.15, max(0.01, max_signal_magnitude))
        # Partitioned store: project_id -> list of records
        self._project_records: Dict[int, List[AgentPerformanceRecord]] = {}
        # Global store for cross-tenant benchmark aggregation
        self._global_records: List[AgentPerformanceRecord] = []

    @classmethod
    def get_instance(cls) -> "AgentPerformanceStore":
        """Retrieve or initialize the global singleton store."""
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def reset(self) -> None:
        """Reset all historical records in the store (used for test isolation)."""
        with self._lock:
            self._project_records.clear()
            self._global_records.clear()

    def record_outcome(self, record: AgentPerformanceRecord) -> None:
        """
        Record a task execution outcome.
        Maintains both project-partitioned storage and global benchmark aggregation.
        """
        with self._lock:
            pid = record.project_id
            if pid not in self._project_records:
                self._project_records[pid] = []
            self._project_records[pid].append(record)
            self._global_records.append(record)

    def get_records(
        self,
        project_id: Optional[int] = None,
        agent_name: Optional[str] = None,
        task_type: Optional[str] = None
    ) -> List[AgentPerformanceRecord]:
        """Query performance records with optional filtering."""
        with self._lock:
            if project_id is not None:
                records = list(self._project_records.get(project_id, []))
            else:
                records = list(self._global_records)

        if agent_name:
            records = [r for r in records if r.agent_name == agent_name]
        if task_type:
            records = [r for r in records if r.task_type.lower() == task_type.lower()]
        return records

    def compute_stats(self, records: List[AgentPerformanceRecord], agent_name: str, task_type: Optional[str] = None) -> AgentPerformanceStats:
        """Compute deterministic statistical performance metrics from a set of records."""
        sample_size = len(records)
        if sample_size == 0:
            return AgentPerformanceStats(
                agent_name=agent_name,
                task_type=task_type,
                sample_size=0,
                has_sufficient_evidence=False
            )

        # Exclude non-agent failures from agent success rate degradation:
        # Safety blocks and human rejections are governance outcomes, not agent operational incompetence
        evaluable_records = [
            r for r in records
            if r.failure_category not in [FailureCategory.SAFETY_BLOCK, FailureCategory.HUMAN_REJECTION]
        ]
        eval_sample = len(evaluable_records) or sample_size

        successful_tasks = sum(1 for r in evaluable_records if r.success)
        failed_tasks = eval_sample - successful_tasks
        success_rate = successful_tasks / max(eval_sample, 1)
        failure_rate = failed_tasks / max(eval_sample, 1)

        # Verification metrics
        verif_records = [r for r in records if r.verification_status in ["verified", "failed"]]
        verif_attempts = len(verif_records)
        verified_successes = sum(1 for r in verif_records if r.verification_status == "verified")
        verif_rate = (verified_successes / verif_attempts) if verif_attempts > 0 else 0.0

        # Duration
        durations = [r.execution_duration_ms for r in records if r.execution_duration_ms > 0]
        avg_duration = (sum(durations) / len(durations)) if durations else 0.0

        # Reassignment
        reassignments = sum(r.reassignment_count for r in records)
        fallback_tasks = sum(1 for r in records if r.was_fallback or r.reassignment_count > 0)
        reassignment_rate = fallback_tasks / max(sample_size, 1)

        # Confidence Calibration
        confidences = [r.predicted_confidence for r in records]
        avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.85
        # Calibration gap: mean |predicted_confidence - actual_outcome (1.0 for success, 0.0 for failure)|
        calibration_gaps = [
            abs(r.predicted_confidence - (1.0 if r.success else 0.0))
            for r in records
        ]
        avg_calib_gap = (sum(calibration_gaps) / len(calibration_gaps)) if calibration_gaps else 0.0

        # Failure breakdown
        failure_counts: Dict[str, int] = {}
        for r in records:
            if not r.success:
                cat = r.failure_category.value if isinstance(r.failure_category, FailureCategory) else str(r.failure_category)
                failure_counts[cat] = failure_counts.get(cat, 0) + 1

        # Routing Quality Score: combination of success rate and low reassignment
        routing_quality = max(0.0, min(1.0, (success_rate * 0.80) + ((1.0 - reassignment_rate) * 0.20)))

        has_sufficient = sample_size >= self.min_sample_threshold

        return AgentPerformanceStats(
            agent_name=agent_name,
            task_type=task_type,
            sample_size=sample_size,
            successful_tasks=successful_tasks,
            failed_tasks=failed_tasks,
            success_rate=success_rate,
            failure_rate=failure_rate,
            verification_attempts=verif_attempts,
            verified_successes=verified_successes,
            verification_success_rate=verif_rate,
            average_duration_ms=avg_duration,
            reassignment_count=reassignments,
            reassignment_rate=reassignment_rate,
            average_confidence=avg_conf,
            confidence_calibration_gap=avg_calib_gap,
            routing_quality_score=routing_quality,
            failure_breakdown=failure_counts,
            has_sufficient_evidence=has_sufficient
        )

    def get_agent_stats(
        self,
        agent_name: str,
        task_type: Optional[str] = None,
        project_id: Optional[int] = None
    ) -> AgentPerformanceStats:
        """
        Retrieve performance stats for an agent.
        Prefers project-scoped records when project_id is provided and has sufficient data.
        Falls back to global anonymized rollup if project data has insufficient sample size.
        """
        if project_id is not None:
            proj_records = self.get_records(project_id=project_id, agent_name=agent_name, task_type=task_type)
            if len(proj_records) >= self.min_sample_threshold:
                return self.compute_stats(proj_records, agent_name=agent_name, task_type=task_type)

        # Global fallback (anonymized performance rates)
        global_records = self.get_records(project_id=None, agent_name=agent_name, task_type=task_type)
        return self.compute_stats(global_records, agent_name=agent_name, task_type=task_type)

    def compute_historical_signal(
        self,
        agent_name: str,
        task_type: str,
        project_id: Optional[int] = None
    ) -> HistoricalSignal:
        """
        Compute bounded soft scoring signal for AdaptiveAgentSelector.
        Enforces cold-start fallback when sample size is below min_sample_threshold.
        """
        stats = self.get_agent_stats(agent_name=agent_name, task_type=task_type, project_id=project_id)

        k = stats.successful_tasks
        n_eval = (stats.successful_tasks + stats.failed_tasks) if (stats.successful_tasks + stats.failed_tasks) > 0 else stats.sample_size

        # Bayesian smoothed success rate (Laplace prior alpha=2, beta=2, prior mean=0.50):
        # p_hat = (k + 2) / (N + 4)
        p_hat = (k + 2.0) / (n_eval + 4.0) if (n_eval + 4.0) > 0 else 0.50

        # Evidence weight scaling linearly from 0.0 at N=0 to 1.0 at N>=10:
        # w_evidence = min(1.0, N / 10)
        w_evidence = min(1.0, n_eval / 10.0)

        if not stats.has_sufficient_evidence:
            return HistoricalSignal(
                agent_name=agent_name,
                task_type=task_type,
                signal_applied=False,
                score_contribution=0.0,
                sample_size=stats.sample_size,
                min_sample_threshold=self.min_sample_threshold,
                success_rate=stats.success_rate,
                smoothed_success_rate=p_hat,
                evidence_weight=w_evidence,
                verification_rate=stats.verification_success_rate,
                reassignment_rate=stats.reassignment_rate,
                explanation=f"insufficient sample size ({stats.sample_size} observations; minimum {self.min_sample_threshold})"
            )

        # Bounded Soft Signal Contribution Formula (DEF-02):
        # 1. Success component with Bayesian smoothed success rate and evidence weighting:
        #    success_component = (p_hat - 0.70) * 0.15 * w_evidence
        # 2. Reassignment penalty: up to -0.03 for 100% reassignment
        # 3. Verification bonus: up to +0.02 for high verification rate
        success_component = (p_hat - 0.70) * 0.15 * w_evidence

        reassign_penalty = stats.reassignment_rate * 0.03
        verif_bonus = 0.0
        if stats.verification_attempts > 0:
            verif_bonus = (stats.verification_success_rate - 0.70) * 0.03

        raw_contribution = success_component - reassign_penalty + verif_bonus
        # Strict bounding to prevent runaway preference or destabilizing hard constraints
        bounded_contribution = max(-self.max_signal_magnitude, min(self.max_signal_magnitude, raw_contribution))

        pct_success = int(round(stats.success_rate * 100))
        pct_verif = int(round(stats.verification_success_rate * 100))
        pct_reassign = int(round(stats.reassignment_rate * 100))

        explanation = (
            f"historical_success: {pct_success}% (n={stats.sample_size}), "
            f"verif: {pct_verif}%, reassign: {pct_reassign}%, "
            f"signal_contribution: {bounded_contribution:+.4f}"
        )

        return HistoricalSignal(
            agent_name=agent_name,
            task_type=task_type,
            signal_applied=True,
            score_contribution=bounded_contribution,
            sample_size=stats.sample_size,
            min_sample_threshold=self.min_sample_threshold,
            success_rate=stats.success_rate,
            smoothed_success_rate=p_hat,
            evidence_weight=w_evidence,
            verification_rate=stats.verification_success_rate,
            reassignment_rate=stats.reassignment_rate,
            explanation=explanation
        )

    def get_anonymized_global_stats(self) -> Dict[str, Any]:
        """
        Generate global anonymized performance benchmarks across all specialized agents.
        Guarantees zero leakage of tenant URLs, search terms, or private project content.
        """
        with self._lock:
            all_records = list(self._global_records)

        agent_names = sorted(list(set(r.agent_name for r in all_records)))
        task_types = sorted(list(set(r.task_type for r in all_records)))

        agent_breakdown = {}
        for a in agent_names:
            a_records = [r for r in all_records if r.agent_name == a]
            agent_breakdown[a] = self.compute_stats(a_records, agent_name=a).to_dict()

        type_breakdown = {}
        for tt in task_types:
            tt_records = [r for r in all_records if r.task_type.lower() == tt.lower()]
            if tt_records:
                sample = len(tt_records)
                successes = sum(1 for r in tt_records if r.success)
                type_breakdown[tt] = {
                    "task_type": tt,
                    "sample_size": sample,
                    "success_rate": round(successes / max(sample, 1), 4),
                    "average_duration_ms": round(sum(r.execution_duration_ms for r in tt_records) / max(sample, 1), 1),
                }

        total_records = len(all_records)
        overall_success = sum(1 for r in all_records if r.success) / max(total_records, 1) if total_records > 0 else 0.0

        return {
            "total_records": total_records,
            "overall_success_rate": round(overall_success, 4),
            "agent_performance": agent_breakdown,
            "task_type_performance": type_breakdown,
        }

    def get_project_stats(self, project_id: int) -> Dict[str, Any]:
        """Retrieve tenant-scoped performance stats isolated to a specific project."""
        with self._lock:
            p_records = list(self._project_records.get(project_id, []))

        agent_names = sorted(list(set(r.agent_name for r in p_records)))
        agent_breakdown = {}
        for a in agent_names:
            a_records = [r for r in p_records if r.agent_name == a]
            agent_breakdown[a] = self.compute_stats(a_records, agent_name=a).to_dict()

        total = len(p_records)
        successful = sum(1 for r in p_records if r.success)
        success_rate = (successful / total) if total > 0 else 0.0

        return {
            "project_id": project_id,
            "total_tasks": total,
            "success_rate": round(success_rate, 4),
            "agent_performance": agent_breakdown,
        }


class AgentLearningService:
    """
    High-level Learning Service coordinating outcome recording, event publication,
    and adaptive learning updates across the multi-agent system.
    """
    def __init__(
        self,
        store: Optional[AgentPerformanceStore] = None,
        publisher: Optional[AgentEventPublisher] = None
    ):
        self.store = store or AgentPerformanceStore.get_instance()
        self.publisher = publisher or get_event_publisher()

    def record_task_outcome(
        self,
        agent_name: str,
        task_id: str,
        task_type: str,
        task_objective: str,
        project_id: int,
        success: bool,
        duration_ms: int = 0,
        predicted_confidence: float = 0.85,
        verification_status: str = "none",
        reassignment_count: int = 0,
        tool_usage: Optional[List[str]] = None,
        failure_category: FailureCategory = FailureCategory.NONE,
        failure_reason: Optional[str] = None,
        was_fallback: bool = False,
        routing_metadata: Optional[Dict[str, Any]] = None,
        correlation_id: str = ""
    ) -> AgentPerformanceRecord:
        """
        Record a task execution outcome into historical memory and emit telemetry.
        """
        record = AgentPerformanceRecord(
            agent_name=agent_name,
            task_id=task_id,
            task_type=task_type or "general",
            task_objective=task_objective,
            project_id=project_id,
            success=success,
            execution_duration_ms=duration_ms,
            predicted_confidence=predicted_confidence,
            verification_status=verification_status,
            reassignment_count=reassignment_count,
            tool_usage=list(tool_usage or []),
            failure_category=failure_category,
            failure_reason=failure_reason,
            was_fallback=was_fallback,
            routing_metadata=dict(routing_metadata or {})
        )

        self.store.record_outcome(record)

        # Emit structured telemetry events
        corr_id = correlation_id or str(uuid.uuid4())
        sanitized_payload = sanitize_event_payload(record.to_dict())
        sanitized_payload["correlation_id"] = corr_id

        # 1. Learning record created event
        self._emit_event(
            AgentEventType.SEO_LEARNING_RECORD_CREATED,
            payload=sanitized_payload,
            project_id=project_id,
            correlation_id=corr_id
        )

        # 2. Performance updated event
        agent_stats = self.store.get_agent_stats(agent_name=agent_name, task_type=task_type, project_id=project_id)
        self._emit_event(
            AgentEventType.SEO_AGENT_PERFORMANCE_UPDATED,
            payload={
                "agent_name": agent_name,
                "task_type": task_type,
                "sample_size": agent_stats.sample_size,
                "success_rate": agent_stats.success_rate,
                "verification_success_rate": agent_stats.verification_success_rate,
                "reassignment_rate": agent_stats.reassignment_rate,
                "has_sufficient_evidence": agent_stats.has_sufficient_evidence,
                "correlation_id": corr_id,
            },
            project_id=project_id,
            correlation_id=corr_id
        )

        # 3. Routing outcome recorded event
        if routing_metadata:
            self._emit_event(
                AgentEventType.SEO_ROUTING_OUTCOME_RECORDED,
                payload={
                    "task_id": task_id,
                    "agent_name": agent_name,
                    "success": success,
                    "was_fallback": was_fallback,
                    "predicted_confidence": predicted_confidence,
                    "calibration_gap": abs(predicted_confidence - (1.0 if success else 0.0)),
                    "correlation_id": corr_id,
                },
                project_id=project_id,
                correlation_id=corr_id
            )

        return record

    def _emit_event(
        self,
        event_type: AgentEventType,
        payload: Dict[str, Any],
        project_id: int,
        correlation_id: str
    ) -> None:
        """Publish sanitized event."""
        event = AgentEvent(
            event_type=event_type,
            run_id=None,
            project_id=project_id,
            sequence_number=1,
            payload=payload
        )
        try:
            self.publisher.publish(event)
        except Exception as exc:
            logger.warning(f"[AgentLearningService] Event publication failed ({event_type}): {exc}")


_default_learning_service: Optional[AgentLearningService] = None
_service_lock = threading.Lock()


def get_agent_learning_service() -> AgentLearningService:
    """Retrieve or initialize the global AgentLearningService singleton."""
    global _default_learning_service
    with _service_lock:
        if _default_learning_service is None:
            _default_learning_service = AgentLearningService()
        return _default_learning_service
