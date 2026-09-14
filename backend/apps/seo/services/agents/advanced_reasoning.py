"""
DoxaRank Advanced Multi-Agent Reasoning & Consensus Service (Milestone 5.7).

Provides a bounded, evidence-driven, explainable multi-agent reasoning layer.
Supports independent agent analysis, competing hypotheses, empirical evidence provenance,
cross-agent critique, disagreement detection, non-majority consensus calculation,
and safe supervisor arbitration under strict human-in-the-loop (HITL) governance.
"""

import copy
import logging
import threading
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from django.utils import timezone

from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher, sanitize_event_payload
)
from .shared_memory import (
    SharedWorkingMemory,
    MemoryCategory,
    DecisionStatus,
    ConflictStatus,
    redact_secrets,
)

logger = logging.getLogger(__name__)

# Bounded reasoning limits and thresholds
MAX_REASONING_ROUNDS = 3
CONSENSUS_CONFIDENCE_THRESHOLD = 0.70
PARTIAL_CONSENSUS_THRESHOLD = 0.50
CONSENSUS_MARGIN_THRESHOLD = 0.20


class ConsensusState(str, Enum):
    """Lifecycle consensus states for multi-agent reasoning."""
    NO_CONSENSUS = "no_consensus"
    PARTIAL_CONSENSUS = "partial_consensus"
    CONSENSUS = "consensus"
    ESCALATED = "escalated"


class ChallengeType(str, Enum):
    """Structured taxonomy of valid critique challenge types."""
    UNSUPPORTED_CLAIM = "unsupported_claim"
    MISSING_EVIDENCE = "missing_evidence"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"
    INCORRECT_INFERENCE = "incorrect_inference"
    WEAK_CONFIDENCE = "weak_confidence"
    SCOPE_MISMATCH = "scope_mismatch"
    OUTDATED_EVIDENCE = "outdated_evidence"
    ALTERNATIVE_EXPLANATION = "alternative_explanation"
    METHODOLOGY_FLAW = "methodology_flaw"


class CritiqueSeverity(str, Enum):
    """Severity levels for structured agent critiques."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    FATAL = "fatal"


class DisagreementSeverity(str, Enum):
    """Severity classification for multi-agent disagreements."""
    MINOR = "minor"
    MATERIAL = "material"
    CRITICAL = "critical"


class ReasoningStatus(str, Enum):
    """Lifecycle status for a reasoning case."""
    INITIALIZED = "initialized"
    IN_PROGRESS = "in_progress"
    ACTIVE = "active"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    FAILED = "failed"


class EpistemicType(str, Enum):
    """Epistemic classification maintaining segregation between facts and inferences."""
    OBSERVED_FACT = "observed_fact"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    UNCERTAINTY = "uncertainty"
    ASSUMPTION = "assumption"


@dataclass
class ReasoningEvidence:
    """
    An empirical observation with strict provenance tracking.
    Must never be conflated with derived inferences or tentative hypotheses.
    """
    evidence_id: str
    fact: str = ""
    source_agent: str = "unknown"
    source_tool: Optional[str] = None
    confidence: float = 1.0
    quality_score: float = 1.0  # 0.0 to 1.0 (e.g. verified tool crawl/GSC = 1.0)
    provenance: Dict[str, Any] = field(default_factory=dict)
    epistemic_category: str = MemoryCategory.OBSERVED_FACT.value
    created_at: str = field(default_factory=lambda: timezone.now().isoformat())
    raw_data: Optional[Any] = None
    claim: Optional[str] = None
    empirical: bool = True

    def __post_init__(self):
        if not self.fact and self.claim:
            self.fact = self.claim
        elif not self.claim and self.fact:
            self.claim = self.fact
        self.fact = redact_secrets(self.fact or "")
        if self.claim:
            self.claim = redact_secrets(self.claim)
        if self.raw_data:
            self.raw_data = redact_secrets(self.raw_data)
        if self.provenance:
            self.provenance = redact_secrets(self.provenance)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "fact": self.fact,
            "claim": self.claim or self.fact,
            "source_agent": self.source_agent,
            "source_tool": self.source_tool,
            "confidence": round(self.confidence, 4),
            "quality_score": round(self.quality_score, 4),
            "provenance": self.provenance,
            "epistemic_category": self.epistemic_category,
            "created_at": self.created_at,
            "raw_data": self.raw_data,
            "empirical": self.empirical,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningEvidence":
        fact_val = data.get("fact") or data.get("claim", "")
        return cls(
            evidence_id=data.get("evidence_id", f"evi-{uuid.uuid4().hex[:8]}"),
            fact=fact_val,
            claim=data.get("claim") or fact_val,
            source_agent=data.get("source_agent", "unknown"),
            source_tool=data.get("source_tool"),
            confidence=data.get("confidence", 1.0),
            quality_score=data.get("quality_score", 1.0),
            provenance=data.get("provenance", {}),
            epistemic_category=data.get("epistemic_category", MemoryCategory.OBSERVED_FACT.value),
            created_at=data.get("created_at", timezone.now().isoformat()),
            raw_data=data.get("raw_data"),
            empirical=data.get("empirical", True),
        )


@dataclass
class ReasoningHypothesis:
    """
    A proposed, tentative explanation for an observed SEO situation.
    Clearly segregated from verified empirical facts.
    """
    hypothesis_id: str
    statement: str
    proposing_agent: str
    epistemic_type: str = "hypothesis"  # Must remain distinct from OBSERVED_FACT
    supporting_evidence_ids: List[str] = field(default_factory=list)
    contradicting_evidence_ids: List[str] = field(default_factory=list)
    confidence: float = 0.70
    status: str = "proposed"  # "proposed" | "challenged" | "supported" | "refuted" | "winning" | "discarded"
    reasoning_rationale: str = ""
    agent_support: List[str] = field(default_factory=list)
    agent_disagreement: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: timezone.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.statement = redact_secrets(self.statement)
        self.reasoning_rationale = redact_secrets(self.reasoning_rationale)
        if self.proposing_agent and self.proposing_agent not in self.agent_support:
            self.agent_support.append(self.proposing_agent)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "proposing_agent": self.proposing_agent,
            "epistemic_type": self.epistemic_type,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "contradicting_evidence_ids": list(self.contradicting_evidence_ids),
            "confidence": round(self.confidence, 4),
            "status": self.status,
            "reasoning_rationale": self.reasoning_rationale,
            "agent_support": list(self.agent_support),
            "agent_disagreement": list(self.agent_disagreement),
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningHypothesis":
        return cls(
            hypothesis_id=data.get("hypothesis_id", f"hypo-{uuid.uuid4().hex[:8]}"),
            statement=data.get("statement", ""),
            proposing_agent=data.get("proposing_agent", "unknown"),
            epistemic_type=data.get("epistemic_type", "hypothesis"),
            supporting_evidence_ids=data.get("supporting_evidence_ids", []),
            contradicting_evidence_ids=data.get("contradicting_evidence_ids", []),
            confidence=data.get("confidence", 0.70),
            status=data.get("status", "proposed"),
            reasoning_rationale=data.get("reasoning_rationale", ""),
            agent_support=data.get("agent_support", []),
            agent_disagreement=data.get("agent_disagreement", []),
            created_at=data.get("created_at", timezone.now().isoformat()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentReasoningResult:
    """
    An independent reasoning assessment produced by a specialized agent during a round.
    Isolated prior to cross-agent comparison so agents do not copy each other's conclusions.
    """
    agent_name: str = "unknown"
    case_id: str = ""
    round_number: int = 1
    hypotheses_proposed: List[str] = field(default_factory=list)  # hypothesis statements
    hypotheses_supported: List[str] = field(default_factory=list)  # hypothesis_ids
    evidence_collected: List[ReasoningEvidence] = field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.80
    isolated: bool = True
    created_at: str = field(default_factory=lambda: timezone.now().isoformat())
    agent: Optional[str] = None
    hypotheses: List[Any] = field(default_factory=list)
    critiques: List[Any] = field(default_factory=list)
    challenges_raised: List[Any] = field(default_factory=list)
    evidence_submitted: List[Any] = field(default_factory=list)

    def __post_init__(self):
        if self.agent and (not self.agent_name or self.agent_name == "unknown"):
            self.agent_name = self.agent
        elif not self.agent and self.agent_name:
            self.agent = self.agent_name
        if self.hypotheses and not self.hypotheses_proposed:
            for h in self.hypotheses:
                if hasattr(h, "statement"):
                    self.hypotheses_proposed.append(h.statement)
                elif isinstance(h, str):
                    self.hypotheses_proposed.append(h)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "case_id": self.case_id,
            "round_number": self.round_number,
            "hypotheses_proposed": list(self.hypotheses_proposed),
            "hypotheses_supported": list(self.hypotheses_supported),
            "evidence_collected": [e.to_dict() for e in self.evidence_collected],
            "rationale": self.rationale,
            "confidence": round(self.confidence, 4),
            "isolated": self.isolated,
            "created_at": self.created_at,
        }


@dataclass
class AgentCritique:
    """
    A structured challenge raised by one agent against another agent's reasoning result or hypothesis.
    Critiques may dispute inferences, confidence, or evidence, but CANNOT mutate empirical facts.
    """
    critique_id: str
    target_hypothesis_id: str
    target_result_agent: str
    critic_agent: str
    challenge_type: str  # ChallengeType value
    challenged_claim: str
    supporting_evidence_ids: List[str] = field(default_factory=list)
    severity: str = CritiqueSeverity.MEDIUM.value
    confidence: float = 0.80
    recommended_resolution: str = ""
    is_resolved: bool = False
    created_at: str = field(default_factory=lambda: timezone.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.challenged_claim = redact_secrets(self.challenged_claim)
        self.recommended_resolution = redact_secrets(self.recommended_resolution)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "critique_id": self.critique_id,
            "target_hypothesis_id": self.target_hypothesis_id,
            "target_result_agent": self.target_result_agent,
            "critic_agent": self.critic_agent,
            "challenge_type": self.challenge_type,
            "challenged_claim": self.challenged_claim,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "severity": self.severity,
            "confidence": round(self.confidence, 4),
            "recommended_resolution": self.recommended_resolution,
            "is_resolved": self.is_resolved,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentCritique":
        return cls(
            critique_id=data.get("critique_id", f"crit-{uuid.uuid4().hex[:8]}"),
            target_hypothesis_id=data.get("target_hypothesis_id", ""),
            target_result_agent=data.get("target_result_agent", ""),
            critic_agent=data.get("critic_agent", "unknown"),
            challenge_type=data.get("challenge_type", ChallengeType.UNSUPPORTED_CLAIM.value),
            challenged_claim=data.get("challenged_claim", ""),
            supporting_evidence_ids=data.get("supporting_evidence_ids", []),
            severity=data.get("severity", CritiqueSeverity.MEDIUM.value),
            confidence=data.get("confidence", 0.80),
            recommended_resolution=data.get("recommended_resolution", ""),
            is_resolved=data.get("is_resolved", False),
            created_at=data.get("created_at", timezone.now().isoformat()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DisagreementRecord:
    """
    A structured representation of an explicit disagreement detected between agents.
    Prevents the system from silently picking an arbitrary winner.
    """
    disagreement_id: str
    case_id: str
    disputed_hypothesis_ids: List[str]
    conflicting_conclusions: Dict[str, str]  # agent_name -> conclusion statement
    agents_involved: List[str]
    evidence_differences: Dict[str, List[str]] = field(default_factory=dict)  # agent_name -> [evidence_id]
    confidence_differences: Dict[str, float] = field(default_factory=dict)  # agent_name -> confidence
    severity: str = DisagreementSeverity.MATERIAL.value
    resolution_status: str = "open"  # "open" | "resolved" | "escalated"
    resolution_notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: timezone.now().isoformat())

    @property
    def agent_a(self) -> str:
        return self.agents_involved[0] if len(self.agents_involved) > 0 else ""

    @property
    def agent_b(self) -> str:
        return self.agents_involved[1] if len(self.agents_involved) > 1 else ""

    @property
    def description(self) -> str:
        return f"Conflict between {', '.join(self.agents_involved)} on {len(self.disputed_hypothesis_ids)} hypotheses"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "disagreement_id": self.disagreement_id,
            "case_id": self.case_id,
            "disputed_hypothesis_ids": list(self.disputed_hypothesis_ids),
            "conflicting_conclusions": dict(self.conflicting_conclusions),
            "agents_involved": list(self.agents_involved),
            "evidence_differences": dict(self.evidence_differences),
            "confidence_differences": {k: round(v, 4) for k, v in self.confidence_differences.items()},
            "severity": self.severity,
            "resolution_status": self.resolution_status,
            "resolution_notes": self.resolution_notes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DisagreementRecord":
        return cls(
            disagreement_id=data.get("disagreement_id", f"disag-{uuid.uuid4().hex[:8]}"),
            case_id=data.get("case_id", ""),
            disputed_hypothesis_ids=data.get("disputed_hypothesis_ids", []),
            conflicting_conclusions=data.get("conflicting_conclusions", {}),
            agents_involved=data.get("agents_involved", []),
            evidence_differences=data.get("evidence_differences", {}),
            confidence_differences=data.get("confidence_differences", {}),
            severity=data.get("severity", DisagreementSeverity.MATERIAL.value),
            resolution_status=data.get("resolution_status", "open"),
            resolution_notes=data.get("resolution_notes"),
            created_at=data.get("created_at", timezone.now().isoformat()),
        )


@dataclass
class ReasoningRound:
    """
    An explicit, bounded round of reasoning (e.g. Round 1: Analysis, Round 2: Critique, Round 3: Consensus).
    Enforces that reasoning discussions cannot loop infinitely.
    """
    round_number: int
    round_type: str = "independent_analysis"  # "independent_analysis" | "critique" | "resolution"
    case_id: Optional[str] = None
    participating_agents: List[str] = field(default_factory=list)
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    agent_results: List[Any] = field(default_factory=list)
    critiques: List[Any] = field(default_factory=list)
    disagreements: List[Any] = field(default_factory=list)
    new_evidence_count: int = 0
    critiques_count: int = 0
    disagreements_count: int = 0
    started_at: str = field(default_factory=lambda: timezone.now().isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_number": self.round_number,
            "round_type": self.round_type,
            "case_id": self.case_id,
            "participating_agents": list(self.participating_agents),
            "actions_taken": list(self.actions_taken),
            "agent_results": [r.to_dict() if hasattr(r, "to_dict") else r for r in self.agent_results],
            "critiques": [c.to_dict() if hasattr(c, "to_dict") else c for c in self.critiques],
            "disagreements": [d.to_dict() if hasattr(d, "to_dict") else d for d in self.disagreements],
            "new_evidence_count": self.new_evidence_count,
            "critiques_count": len(self.critiques) or self.critiques_count,
            "disagreements_count": len(self.disagreements) or self.disagreements_count,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningRound":
        return cls(
            round_number=data.get("round_number", 1),
            round_type=data.get("round_type", "independent_analysis"),
            case_id=data.get("case_id"),
            participating_agents=data.get("participating_agents", []),
            actions_taken=data.get("actions_taken", []),
            agent_results=data.get("agent_results", []),
            critiques=[AgentCritique.from_dict(c) if isinstance(c, dict) else c for c in data.get("critiques", [])],
            disagreements=[DisagreementRecord.from_dict(d) if isinstance(d, dict) else d for d in data.get("disagreements", [])],
            new_evidence_count=data.get("new_evidence_count", 0),
            critiques_count=data.get("critiques_count", 0),
            disagreements_count=data.get("disagreements_count", 0),
            started_at=data.get("started_at", timezone.now().isoformat()),
            completed_at=data.get("completed_at"),
        )


@dataclass
class ConsensusResult:
    """
    The explainable result of consensus evaluation.
    Provides clear reasoning rationale, winning hypothesis (if any), and uncertainty boundary.
    """
    consensus_state: str  # ConsensusState value
    winning_hypothesis_id: Optional[str] = None
    winning_hypothesis_statement: Optional[str] = None
    confidence: float = 0.0
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    unresolved_critiques: List[str] = field(default_factory=list)
    unresolved_disagreements: List[str] = field(default_factory=list)
    participating_agents: List[str] = field(default_factory=list)
    hypothesis_scores: Dict[str, float] = field(default_factory=dict)
    rationale: str = ""
    escalation_reason: Optional[str] = None

    @property
    def status(self) -> str:
        return self.consensus_state

    @property
    def confidence_score(self) -> float:
        return self.confidence

    @property
    def selected_hypothesis_id(self) -> Optional[str]:
        return self.winning_hypothesis_id

    @property
    def selected_conclusion(self) -> Optional[str]:
        return self.winning_hypothesis_statement

    def to_dict(self) -> Dict[str, Any]:
        return {
            "consensus_state": self.consensus_state,
            "winning_hypothesis_id": self.winning_hypothesis_id,
            "selected_hypothesis_id": self.winning_hypothesis_id,
            "winning_hypothesis_statement": self.winning_hypothesis_statement,
            "selected_conclusion": self.winning_hypothesis_statement,
            "confidence": round(self.confidence, 4),
            "supporting_evidence": list(self.supporting_evidence),
            "contradicting_evidence": list(self.contradicting_evidence),
            "unresolved_critiques": list(self.unresolved_critiques),
            "unresolved_disagreements": list(self.unresolved_disagreements),
            "participating_agents": list(self.participating_agents),
            "hypothesis_scores": {k: round(v, 4) for k, v in self.hypothesis_scores.items()},
            "rationale": self.rationale,
            "escalation_reason": self.escalation_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConsensusResult":
        return cls(
            consensus_state=data.get("consensus_state", ConsensusState.NO_CONSENSUS.value),
            winning_hypothesis_id=data.get("winning_hypothesis_id"),
            winning_hypothesis_statement=data.get("winning_hypothesis_statement"),
            confidence=data.get("confidence", 0.0),
            supporting_evidence=data.get("supporting_evidence", []),
            contradicting_evidence=data.get("contradicting_evidence", []),
            unresolved_critiques=data.get("unresolved_critiques", []),
            unresolved_disagreements=data.get("unresolved_disagreements", []),
            participating_agents=data.get("participating_agents", []),
            hypothesis_scores=data.get("hypothesis_scores", {}),
            rationale=data.get("rationale", ""),
            escalation_reason=data.get("escalation_reason"),
        )


@dataclass
class ReasoningCase:
    """
    The root aggregate container for a multi-agent reasoning session.
    Maintains tenant isolation, rounds, competing hypotheses, critiques, and consensus state.
    """
    case_id: str
    project_id: int
    objective: str
    correlation_id: str
    run_id: Optional[int] = None
    initiating_agent: str = "seo_supervisor"
    context_data: Dict[str, Any] = field(default_factory=dict)
    evidence_references: List[ReasoningEvidence] = field(default_factory=list)
    hypotheses: List[ReasoningHypothesis] = field(default_factory=list)
    participating_agents: List[str] = field(default_factory=list)
    reasoning_rounds: List[ReasoningRound] = field(default_factory=list)
    critiques: List[AgentCritique] = field(default_factory=list)
    disagreements: List[DisagreementRecord] = field(default_factory=list)
    consensus_state: str = ConsensusState.NO_CONSENSUS.value
    confidence: float = 0.0
    final_conclusion: Optional[str] = None
    winning_hypothesis_id: Optional[str] = None
    unresolved_uncertainty: List[str] = field(default_factory=list)
    status: str = "initialized"  # "initialized" | "active" | "completed" | "escalated" | "failed"
    created_at: str = field(default_factory=lambda: timezone.now().isoformat())
    updated_at: str = field(default_factory=lambda: timezone.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def rounds(self) -> List[ReasoningRound]:
        return self.reasoning_rounds

    @property
    def current_round(self) -> int:
        return self.metadata.get("current_round", len(self.reasoning_rounds) or 1)

    @current_round.setter
    def current_round(self, val: int):
        self.metadata["current_round"] = val

    def __post_init__(self):
        self.objective = redact_secrets(self.objective)
        if self.final_conclusion:
            self.final_conclusion = redact_secrets(self.final_conclusion)

    def get_evidence(self, evidence_id: str) -> Optional[ReasoningEvidence]:
        for e in self.evidence_references:
            if e.evidence_id == evidence_id:
                return e
        return None

    def get_hypothesis(self, hypothesis_id: str) -> Optional[ReasoningHypothesis]:
        for h in self.hypotheses:
            if h.hypothesis_id == hypothesis_id:
                return h
        return None

    def to_dict(self) -> Dict[str, Any]:
        cons_res = self.metadata.get("consensus_result")
        if not cons_res:
            cons_res = ConsensusResult(
                consensus_state=self.consensus_state,
                confidence=self.confidence,
                winning_hypothesis_id=self.winning_hypothesis_id,
                winning_hypothesis_statement=self.final_conclusion,
                participating_agents=list(self.participating_agents),
            ).to_dict()

        hypo_dicts = []
        for h in self.hypotheses:
            hd = h.to_dict()
            if self.winning_hypothesis_id and h.hypothesis_id == self.winning_hypothesis_id:
                hd["status"] = "winning"
            hypo_dicts.append(hd)

        return {
            "case_id": self.case_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "initiating_agent": self.initiating_agent,
            "objective": self.objective,
            "context_data": self.context_data,
            "evidence_references": [e.to_dict() for e in self.evidence_references],
            "hypotheses": hypo_dicts,
            "participating_agents": list(self.participating_agents),
            "reasoning_rounds": [r.to_dict() for r in self.reasoning_rounds],
            "rounds": [r.to_dict() for r in self.reasoning_rounds],
            "current_round": self.current_round,
            "critiques": [c.to_dict() for c in self.critiques],
            "disagreements": [d.to_dict() for d in self.disagreements],
            "consensus_state": self.consensus_state,
            "confidence": round(self.confidence, 4),
            "final_conclusion": self.final_conclusion,
            "winning_hypothesis_id": self.winning_hypothesis_id,
            "unresolved_uncertainty": list(self.unresolved_uncertainty),
            "consensus_result": cons_res,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningCase":
        return cls(
            case_id=data.get("case_id", f"case-{uuid.uuid4().hex[:8]}"),
            project_id=data.get("project_id", 0),
            run_id=data.get("run_id"),
            correlation_id=data.get("correlation_id", ""),
            initiating_agent=data.get("initiating_agent", "seo_supervisor"),
            objective=data.get("objective", ""),
            context_data=data.get("context_data", {}),
            evidence_references=[ReasoningEvidence.from_dict(e) for e in data.get("evidence_references", [])],
            hypotheses=[ReasoningHypothesis.from_dict(h) for h in data.get("hypotheses", [])],
            participating_agents=data.get("participating_agents", []),
            reasoning_rounds=[ReasoningRound.from_dict(r) for r in (data.get("reasoning_rounds") or data.get("rounds") or [])],
            critiques=[AgentCritique.from_dict(c) for c in data.get("critiques", [])],
            disagreements=[DisagreementRecord.from_dict(d) for d in data.get("disagreements", [])],
            consensus_state=data.get("consensus_state", ConsensusState.NO_CONSENSUS.value),
            confidence=data.get("confidence", 0.0),
            final_conclusion=data.get("final_conclusion"),
            winning_hypothesis_id=data.get("winning_hypothesis_id"),
            unresolved_uncertainty=data.get("unresolved_uncertainty", []),
            status=data.get("status", "initialized"),
            created_at=data.get("created_at", timezone.now().isoformat()),
            updated_at=data.get("updated_at", timezone.now().isoformat()),
            metadata=data.get("metadata", {}),
        )


class AdvancedReasoningService:
    """
    Advanced Multi-Agent Reasoning & Consensus Service.
    Coordinates independent analyses, structured cross-critique, disagreement detection,
    and evidence-driven consensus evaluation across specialized agents.
    """

    def __init__(
        self,
        project_id: int,
        publisher: Optional[AgentEventPublisher] = None,
        event_publisher: Optional[AgentEventPublisher] = None,
        max_rounds: int = MAX_REASONING_ROUNDS,
    ):
        if project_id <= 0:
            raise ValueError(f"AdvancedReasoningService requires a valid project_id > 0, got {project_id}")
        self.project_id = project_id
        self.publisher = publisher or event_publisher or get_event_publisher()
        self.max_rounds = max(1, min(10, max_rounds))
        self._cases: Dict[str, ReasoningCase] = {}
        self._lock = threading.RLock()

    def _emit_event(self, event_type: AgentEventType, payload: Dict[str, Any], correlation_id: str) -> None:
        """Sanitizes and safely emits structured reasoning telemetry."""
        clean_payload = sanitize_event_payload(payload)
        clean_payload["project_id"] = self.project_id
        clean_payload["correlation_id"] = correlation_id
        clean_payload["source"] = "advanced_reasoning_service"
        event = AgentEvent(
            event_type=event_type.value if hasattr(event_type, "value") else str(event_type),
            run_id=int(clean_payload.get("run_id") or 0),
            project_id=self.project_id,
            payload=clean_payload,
        )
        self.publisher.publish(event)

    def create_reasoning_case(
        self,
        objective: str,
        initiating_agent: str = "seo_supervisor",
        participating_agents: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
        run_id: Optional[int] = None,
        context_data: Optional[Dict[str, Any]] = None,
        case_id: Optional[str] = None,
    ) -> ReasoningCase:
        """Create and register a new multi-agent reasoning case."""
        with self._lock:
            cid = case_id or f"case-{uuid.uuid4().hex[:8]}"
            corr = correlation_id or f"corr-{uuid.uuid4().hex[:8]}"
            parts = list(participating_agents or [])
            if initiating_agent and initiating_agent not in parts:
                parts.append(initiating_agent)

            case = ReasoningCase(
                case_id=cid,
                project_id=self.project_id,
                objective=objective,
                correlation_id=corr,
                run_id=run_id,
                initiating_agent=initiating_agent,
                participating_agents=parts,
                context_data=redact_secrets(context_data or {}),
                status=ReasoningStatus.IN_PROGRESS.value,
            )
            r1 = ReasoningRound(round_number=1, case_id=cid, participating_agents=parts)
            case.reasoning_rounds.append(r1)
            self._cases[cid] = case
            ReasoningRegistry.get_instance().register(case)

            self._emit_event(
                AgentEventType.SEO_REASONING_CASE_STARTED,
                payload={
                    "case_id": case.case_id,
                    "run_id": case.run_id,
                    "objective": case.objective,
                },
                correlation_id=corr,
            )
            return case

    def create_case(
        self,
        objective: str,
        correlation_id: str,
        run_id: Optional[int] = None,
        context_data: Optional[Dict[str, Any]] = None,
        case_id: Optional[str] = None,
        initiating_agent: str = "seo_supervisor",
        participating_agents: Optional[List[str]] = None,
    ) -> ReasoningCase:
        """Create and register a new multi-agent reasoning case."""
        return self.create_reasoning_case(
            objective=objective,
            initiating_agent=initiating_agent,
            participating_agents=participating_agents,
            correlation_id=correlation_id,
            run_id=run_id,
            context_data=context_data,
            case_id=case_id,
        )

    def get_case(self, case_id: str) -> Optional[ReasoningCase]:
        with self._lock:
            case = self._cases.get(case_id) or ReasoningRegistry.get_instance().get_by_case_id(case_id)
            if case and self.project_id and case.project_id and case.project_id != self.project_id:
                return None
            return case

    def add_evidence(
        self,
        case_id: str,
        fact: str,
        source_agent: str,
        source_tool: Optional[str] = None,
        confidence: float = 1.0,
        quality_score: float = 1.0,
        raw_data: Optional[Any] = None,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> ReasoningEvidence:
        """
        Record verified empirical evidence with explicit provenance.
        Fact is never modified by downstream critiques.
        """
        with self._lock:
            case = self.get_case(case_id)
            if not case:
                raise ValueError(f"ReasoningCase '{case_id}' not found.")

            evi_id = f"evi-{uuid.uuid4().hex[:8]}"
            prov = dict(provenance or {})
            prov.setdefault("project_id", self.project_id)
            prov.setdefault("recorded_at", timezone.now().isoformat())
            prov.setdefault("source_agent", source_agent)

            evidence = ReasoningEvidence(
                evidence_id=evi_id,
                fact=fact,
                source_agent=source_agent,
                source_tool=source_tool,
                confidence=max(0.0, min(1.0, confidence)),
                quality_score=max(0.0, min(1.0, quality_score)),
                raw_data=raw_data,
                provenance=prov,
            )
            case.evidence_references.append(evidence)
            if source_agent not in case.participating_agents:
                case.participating_agents.append(source_agent)
            case.updated_at = timezone.now().isoformat()
            return evidence

    def add_hypothesis(
        self,
        case_id: str,
        statement: str,
        proposing_agent: str,
        confidence: float = 0.70,
        supporting_evidence_ids: Optional[List[str]] = None,
        contradicting_evidence_ids: Optional[List[str]] = None,
        rationale: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        epistemic_type: Optional[str] = None,
    ) -> ReasoningHypothesis:
        """
        Propose a competing hypothesis.
        Clearly typed as an epistemic hypothesis linked to empirical evidence.
        """
        with self._lock:
            case = self.get_case(case_id)
            if not case:
                raise ValueError(f"ReasoningCase '{case_id}' not found.")

            hypo_id = f"hypo-{uuid.uuid4().hex[:8]}"
            sup_ids = list(supporting_evidence_ids or [])
            con_ids = list(contradicting_evidence_ids or [])

            # Validate that referenced evidence exists in the case
            existing_evi_ids = {e.evidence_id for e in case.evidence_references}
            for sid in sup_ids:
                if sid not in existing_evi_ids:
                    logger.debug(f"Supporting evidence '{sid}' referenced before ingestion.")

            epistemic = (
                epistemic_type
                or (metadata.get("epistemic_type") if metadata else None)
                or "hypothesis"
            )

            hypo = ReasoningHypothesis(
                hypothesis_id=hypo_id,
                statement=statement,
                proposing_agent=proposing_agent,
                epistemic_type=epistemic,
                supporting_evidence_ids=sup_ids,
                contradicting_evidence_ids=con_ids,
                confidence=max(0.0, min(1.0, confidence)),
                status="proposed",
                reasoning_rationale=rationale,
                agent_support=[proposing_agent],
                metadata=metadata or {},
            )
            case.hypotheses.append(hypo)
            if proposing_agent not in case.participating_agents:
                case.participating_agents.append(proposing_agent)
            case.updated_at = timezone.now().isoformat()

            self._emit_event(
                AgentEventType.SEO_REASONING_HYPOTHESIS_CREATED,
                payload={
                    "case_id": case.case_id,
                    "hypothesis_id": hypo.hypothesis_id,
                    "statement": hypo.statement,
                    "proposing_agent": hypo.proposing_agent,
                    "supporting_evidence_count": len(hypo.supporting_evidence_ids),
                },
                correlation_id=case.correlation_id,
            )
            return hypo

    def create_hypothesis(
        self,
        case: Any,
        agent: str,
        summary: str,
        rationale: str = "",
        confidence: float = 0.70,
        supporting_evidence: Optional[List[ReasoningEvidence]] = None,
        contradicting_evidence: Optional[List[ReasoningEvidence]] = None,
        epistemic_type: str = EpistemicType.INFERENCE.value,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReasoningHypothesis:
        """Helper to create a hypothesis from either case object or case_id."""
        cid = case.case_id if hasattr(case, "case_id") else str(case)
        case_obj = self.get_case(cid)
        if not case_obj:
            raise ValueError(f"ReasoningCase '{cid}' not found.")

        sup_ids = []
        for e in (supporting_evidence or []):
            if hasattr(e, "evidence_id"):
                sup_ids.append(e.evidence_id)
                if not any(x.evidence_id == e.evidence_id for x in case_obj.evidence_references):
                    case_obj.evidence_references.append(e)
            elif isinstance(e, str):
                sup_ids.append(e)

        contra_ids = []
        for e in (contradicting_evidence or []):
            if hasattr(e, "evidence_id"):
                contra_ids.append(e.evidence_id)
                if not any(x.evidence_id == e.evidence_id for x in case_obj.evidence_references):
                    case_obj.evidence_references.append(e)
            elif isinstance(e, str):
                contra_ids.append(e)

        meta = dict(metadata or {})
        meta["epistemic_type"] = epistemic_type
        meta["summary"] = summary

        hypo = self.add_hypothesis(
            case_id=cid,
            statement=summary,
            proposing_agent=agent,
            confidence=confidence,
            supporting_evidence_ids=sup_ids,
            contradicting_evidence_ids=contra_ids,
            rationale=rationale,
            metadata=meta,
            epistemic_type=epistemic_type,
        )
        return hypo

    def record_independent_analysis(
        self,
        case_id: str,
        agent_name: str,
        round_number: int,
        hypotheses_proposed: List[str],
        hypotheses_supported: Optional[List[str]] = None,
        evidence_collected: Optional[List[ReasoningEvidence]] = None,
        rationale: str = "",
        confidence: float = 0.80,
    ) -> AgentReasoningResult:
        """
        Record an agent's independent analysis for a round.
        Analysis is isolated so agents formulate conclusions without peer pressure.
        """
        with self._lock:
            case = self.get_case(case_id)
            if not case:
                raise ValueError(f"ReasoningCase '{case_id}' not found.")

            result = AgentReasoningResult(
                agent_name=agent_name,
                case_id=case_id,
                round_number=round_number,
                hypotheses_proposed=list(hypotheses_proposed),
                hypotheses_supported=list(hypotheses_supported or []),
                evidence_collected=list(evidence_collected or []),
                rationale=rationale,
                confidence=confidence,
                isolated=True,
            )
            if agent_name not in case.participating_agents:
                case.participating_agents.append(agent_name)

            self._emit_event(
                AgentEventType.SEO_REASONING_AGENT_ANALYSIS_COMPLETED,
                payload={
                    "case_id": case.case_id,
                    "agent_name": agent_name,
                    "round_number": round_number,
                    "hypotheses_count": len(hypotheses_proposed),
                    "evidence_count": len(result.evidence_collected),
                },
                correlation_id=case.correlation_id,
            )
            return result

    def record_agent_result(self, case: Any, round_number: int, result: Any) -> None:
        """Store an agent's reasoning result in the designated round."""
        cid = case.case_id if hasattr(case, "case_id") else str(case)
        with self._lock:
            case_obj = self.get_case(cid)
            if not case_obj:
                return
            if case_obj.reasoning_rounds:
                target_round = case_obj.reasoning_rounds[round_number - 1] if round_number <= len(case_obj.reasoning_rounds) else case_obj.reasoning_rounds[-1]
                target_round.agent_results.append(result)

    def submit_critique(
        self,
        case: Any = None,
        case_id: Optional[str] = None,
        target_hypothesis_id: str = "",
        critic_agent: Optional[str] = None,
        critique_agent: Optional[str] = None,
        challenge_type: Any = ChallengeType.UNSUPPORTED_CLAIM,
        challenged_claim: Optional[str] = None,
        critique_text: Optional[str] = None,
        supporting_evidence_ids: Optional[List[str]] = None,
        severity: Any = CritiqueSeverity.MEDIUM,
        confidence: float = 0.80,
        recommended_resolution: str = "",
        suggested_verification: Optional[str] = None,
        round_number: Optional[int] = None,
        target_agent: Optional[str] = None,
    ) -> AgentCritique:
        """
        Record a structured critique against a hypothesis.
        Critiques question claims or inferences, but CANNOT mutate or delete empirical facts.
        """
        with self._lock:
            cid = case.case_id if hasattr(case, "case_id") else (case_id or str(case))
            case_obj = self.get_case(cid)
            if not case_obj:
                raise ValueError(f"ReasoningCase '{cid}' not found.")

            target_hypo = case_obj.get_hypothesis(target_hypothesis_id)
            if not target_hypo:
                raise ValueError(f"Target hypothesis '{target_hypothesis_id}' not found in case '{cid}'.")

            c_agent = critic_agent or critique_agent or "seo_critic"
            c_claim = challenged_claim or critique_text or ""
            c_rec = recommended_resolution or suggested_verification or ""
            c_type = challenge_type.value if hasattr(challenge_type, "value") else str(challenge_type)
            c_sev = severity.value if hasattr(severity, "value") else str(severity)

            critique = AgentCritique(
                critique_id=f"crit-{uuid.uuid4().hex[:8]}",
                target_hypothesis_id=target_hypothesis_id,
                target_result_agent=target_agent or target_hypo.proposing_agent,
                critic_agent=c_agent,
                challenge_type=c_type,
                challenged_claim=c_claim,
                supporting_evidence_ids=list(supporting_evidence_ids or []),
                severity=c_sev,
                confidence=max(0.0, min(1.0, confidence)),
                recommended_resolution=c_rec,
            )
            case_obj.critiques.append(critique)
            target_hypo.status = "challenged"
            if c_agent not in target_hypo.agent_disagreement:
                target_hypo.agent_disagreement.append(c_agent)
            if c_agent not in case_obj.participating_agents:
                case_obj.participating_agents.append(c_agent)

            # Record in round critiques if rounds exist
            if case_obj.reasoning_rounds:
                rnd_idx = (round_number - 1) if round_number and round_number <= len(case_obj.reasoning_rounds) else -1
                case_obj.reasoning_rounds[rnd_idx].critiques.append(critique)

            if supporting_evidence_ids:
                for eid in supporting_evidence_ids:
                    if eid not in target_hypo.contradicting_evidence_ids:
                        target_hypo.contradicting_evidence_ids.append(eid)

            case_obj.updated_at = timezone.now().isoformat()

            self._emit_event(
                AgentEventType.SEO_REASONING_CRITIQUE_CREATED,
                payload={
                    "case_id": case_obj.case_id,
                    "critique_id": critique.critique_id,
                    "critic_agent": critique.critic_agent,
                    "target_hypothesis_id": target_hypothesis_id,
                    "challenge_type": critique.challenge_type,
                    "severity": critique.severity,
                },
                correlation_id=case_obj.correlation_id,
            )
            return critique

    def detect_disagreements(self, case: Any = None, case_id: Optional[str] = None, round_number: Optional[int] = None) -> List[DisagreementRecord]:
        """
        Detect meaningful, structured disagreements across participating agents.
        Identifies competing explanations, opposing evidence, and confidence divergences.
        """
        with self._lock:
            cid = case.case_id if hasattr(case, "case_id") else (case_id or str(case))
            case_obj = self.get_case(cid)
            if not case_obj:
                raise ValueError(f"ReasoningCase '{cid}' not found.")

            detected: List[DisagreementRecord] = []
            hypotheses = case_obj.hypotheses

            # 1. Check for mutually exclusive or competing hypotheses supported by different agents
            for i in range(len(hypotheses)):
                for j in range(i + 1, len(hypotheses)):
                    h1 = hypotheses[i]
                    h2 = hypotheses[j]

                    # If agents propose different primary explanations for the same case objective
                    if h1.proposing_agent != h2.proposing_agent:
                        conflicting = {
                            h1.proposing_agent: h1.statement,
                            h2.proposing_agent: h2.statement,
                        }
                        agents = [h1.proposing_agent, h2.proposing_agent]
                        evi_diffs = {
                            h1.proposing_agent: list(h1.supporting_evidence_ids),
                            h2.proposing_agent: list(h2.supporting_evidence_ids),
                        }
                        conf_diffs = {
                            h1.proposing_agent: h1.confidence,
                            h2.proposing_agent: h2.confidence,
                        }

                        # Check if this disagreement is already recorded
                        existing = any(
                            set(d.disputed_hypothesis_ids) == {h1.hypothesis_id, h2.hypothesis_id}
                            for d in case_obj.disagreements
                        )
                        if not existing:
                            import re
                            words1 = set(re.findall(r'\w+', h1.statement.lower()))
                            words2 = set(re.findall(r'\w+', h2.statement.lower()))
                            stopwords = {"cause", "the", "a", "an", "of", "in", "is", "and", "to", "on", "for", "with", "by", "at", "as"}
                            shared_words = (words1 & words2) - stopwords
                            conf_diff = abs(h1.confidence - h2.confidence)
                            is_minor = len(shared_words) >= 2 and conf_diff <= 0.15
                            sev = DisagreementSeverity.MINOR.value if is_minor else DisagreementSeverity.MATERIAL.value

                            d_rec = DisagreementRecord(
                                disagreement_id=f"disag-{uuid.uuid4().hex[:8]}",
                                case_id=case_obj.case_id,
                                disputed_hypothesis_ids=[h1.hypothesis_id, h2.hypothesis_id],
                                conflicting_conclusions=conflicting,
                                agents_involved=agents,
                                evidence_differences=evi_diffs,
                                confidence_differences=conf_diffs,
                                severity=sev,
                            )
                            case_obj.disagreements.append(d_rec)
                            detected.append(d_rec)

                            self._emit_event(
                                AgentEventType.SEO_REASONING_DISAGREEMENT_DETECTED,
                                payload={
                                    "case_id": case_obj.case_id,
                                    "disagreement_id": d_rec.disagreement_id,
                                    "agents_involved": d_rec.agents_involved,
                                    "disputed_hypotheses": d_rec.disputed_hypothesis_ids,
                                },
                                correlation_id=case_obj.correlation_id,
                            )

            # 2. Check critiques with HIGH or FATAL severity
            for critique in case_obj.critiques:
                target_hypo = case_obj.get_hypothesis(critique.target_hypothesis_id)
                if target_hypo and critique.severity in [CritiqueSeverity.HIGH.value, CritiqueSeverity.FATAL.value]:
                    existing = any(
                        critique.target_hypothesis_id in d.disputed_hypothesis_ids
                        and critique.critic_agent in d.agents_involved
                        for d in case_obj.disagreements
                    )
                    if not existing:
                        d_rec = DisagreementRecord(
                            disagreement_id=f"disag-{uuid.uuid4().hex[:8]}",
                            case_id=case_obj.case_id,
                            disputed_hypothesis_ids=[target_hypo.hypothesis_id],
                            conflicting_conclusions={
                                target_hypo.proposing_agent: target_hypo.statement,
                                critique.critic_agent: f"Challenged: {critique.challenged_claim} ({critique.challenge_type})",
                            },
                            agents_involved=[target_hypo.proposing_agent, critique.critic_agent],
                            evidence_differences={
                                target_hypo.proposing_agent: list(target_hypo.supporting_evidence_ids),
                                critique.critic_agent: list(critique.supporting_evidence_ids),
                            },
                            confidence_differences={
                                target_hypo.proposing_agent: target_hypo.confidence,
                                critique.critic_agent: critique.confidence,
                            },
                            severity=DisagreementSeverity.CRITICAL.value if critique.severity == CritiqueSeverity.FATAL.value else DisagreementSeverity.MATERIAL.value,
                        )
                        case_obj.disagreements.append(d_rec)
                        detected.append(d_rec)

                        self._emit_event(
                            AgentEventType.SEO_REASONING_DISAGREEMENT_DETECTED,
                            payload={
                                "case_id": case_obj.case_id,
                                "disagreement_id": d_rec.disagreement_id,
                                "agents_involved": d_rec.agents_involved,
                                "disputed_hypotheses": d_rec.disputed_hypothesis_ids,
                            },
                            correlation_id=case_obj.correlation_id,
                        )

            # Record in round disagreements if rounds exist
            if case_obj.reasoning_rounds and detected:
                rnd_idx = (round_number - 1) if round_number and round_number <= len(case_obj.reasoning_rounds) else -1
                case_obj.reasoning_rounds[rnd_idx].disagreements.extend(detected)

            return detected

    def evaluate_consensus(
        self,
        case: Any = None,
        case_id: Optional[str] = None,
        round_number: Optional[int] = None,
        shared_memory: Optional[Any] = None,
    ) -> ConsensusResult:
        """
        Evaluate consensus across competing hypotheses.
        NON-MAJORITY VOTING GUARANTEE:
        A majority of agents agreeing without empirical evidence will NEVER beat
        a single agent with strong verified empirical evidence.
        """
        with self._lock:
            cid = case.case_id if hasattr(case, "case_id") else (case_id or str(case))
            case = self.get_case(cid)
            if not case:
                raise ValueError(f"ReasoningCase '{cid}' not found.")

            # Ensure disagreement detection is fresh
            self.detect_disagreements(case)

            if not case.hypotheses:
                res = ConsensusResult(
                    consensus_state=ConsensusState.NO_CONSENSUS.value,
                    confidence=0.0,
                    rationale="No hypotheses were proposed for evaluation.",
                )
                case.consensus_state = res.consensus_state
                case.confidence = 0.0
                return res

            hypothesis_scores: Dict[str, float] = {}
            hypo_evidence_map: Dict[str, Dict[str, Any]] = {}

            # Severity penalties for unresolved critiques
            severity_penalties = {
                CritiqueSeverity.LOW.value: 0.05,
                CritiqueSeverity.MEDIUM.value: 0.15,
                CritiqueSeverity.HIGH.value: 0.35,
                CritiqueSeverity.FATAL.value: 0.70,
            }

            for hypo in case.hypotheses:
                # 1. Supporting evidence weight (sum of verified empirical quality scores)
                sup_score = 0.0
                for eid in hypo.supporting_evidence_ids:
                    evi = case.get_evidence(eid)
                    if evi:
                        # Direct tool observation gets full quality weight
                        sup_score += (evi.quality_score * evi.confidence)
                    else:
                        # Unregistered evidence gets minimal weight
                        sup_score += 0.2

                # 2. Contradicting evidence weight (heavily penalized, 2.0x multiplier)
                con_score = 0.0
                for eid in hypo.contradicting_evidence_ids:
                    evi = case.get_evidence(eid)
                    if evi:
                        con_score += (evi.quality_score * evi.confidence * 2.0)
                    else:
                        con_score += 0.4

                # 3. Unresolved critique penalties
                critique_penalty = 0.0
                has_fatal_critique = False
                for crit in case.critiques:
                    if crit.target_hypothesis_id == hypo.hypothesis_id and not crit.is_resolved:
                        pen = severity_penalties.get(crit.severity, 0.15) * crit.confidence
                        critique_penalty += pen
                        if crit.severity == CritiqueSeverity.FATAL.value:
                            has_fatal_critique = True

                # 4. Agent support soft factor: bounded to +0.05 per agent, capped at 0.15 max
                # This explicitly ensures agent count can NEVER override missing evidence!
                # Even 10 agents agreeing cannot add more than 0.15 to an unsupported hypothesis.
                agent_agreement_factor = min(0.15, max(0.0, (len(hypo.agent_support) - 1) * 0.05))

                # Disagreement penalty
                agent_disagreement_factor = min(0.20, len(hypo.agent_disagreement) * 0.08)

                # Net Evidence Score Calculation
                # If sup_score is 0 (no evidence), base score is bounded to at most 0.10
                if sup_score <= 0.0:
                    base_score = min(0.10, hypo.confidence * 0.10 + agent_agreement_factor)
                else:
                    evi_count = len(hypo.supporting_evidence_ids)
                    avg_evi_score = sup_score / max(1, evi_count)
                    base_score = min(1.0, (hypo.confidence * 0.6) + (avg_evi_score * 0.4))

                net_score = base_score - con_score - critique_penalty - agent_disagreement_factor
                if not sup_score and agent_agreement_factor > 0:
                    # STRICT GUARD: Zero evidence hypothesis capped at 0.15 regardless of agent agreement
                    net_score = min(0.15, net_score)

                if has_fatal_critique:
                    net_score = min(0.10, net_score)

                final_hypo_score = max(0.0, min(1.0, net_score))
                hypothesis_scores[hypo.hypothesis_id] = final_hypo_score
                hypo_evidence_map[hypo.hypothesis_id] = {
                    "sup_score": sup_score,
                    "con_score": con_score,
                    "critique_penalty": critique_penalty,
                    "has_fatal_critique": has_fatal_critique,
                }

            # Rank hypotheses by evidence-driven score
            ranked_hypos = sorted(
                case.hypotheses,
                key=lambda h: (hypothesis_scores[h.hypothesis_id], len(h.supporting_evidence_ids)),
                reverse=True,
            )

            top_hypo = ranked_hypos[0]
            top_score = hypothesis_scores[top_hypo.hypothesis_id]
            second_score = hypothesis_scores[ranked_hypos[1].hypothesis_id] if len(ranked_hypos) > 1 else 0.0
            margin = top_score - second_score

            open_critiques = [c for c in case.critiques if not c.is_resolved]
            open_fatal = [c.critique_id for c in open_critiques if c.severity == CritiqueSeverity.FATAL.value]
            open_disagreements = [d.disagreement_id for d in case.disagreements if d.resolution_status == "open"]

            curr_round = round_number or len(case.reasoning_rounds)

            # Determine Consensus State
            if top_score >= CONSENSUS_CONFIDENCE_THRESHOLD and margin >= CONSENSUS_MARGIN_THRESHOLD and not open_fatal:
                state = ConsensusState.CONSENSUS.value
                winning_id = top_hypo.hypothesis_id
                top_hypo.status = "winning"
                # All open disagreements between competing hypotheses are resolved by consensus arbitration
                for d in case.disagreements:
                    if d.resolution_status == "open":
                        d.resolution_status = "resolved"
                        d.resolution_notes = (
                            f"Resolved by consensus arbitration in favor of hypothesis "
                            f"{top_hypo.hypothesis_id}: '{top_hypo.statement}'"
                        )
                open_disagreements = [d.disagreement_id for d in case.disagreements if d.resolution_status == "open"]
                rationale = (
                    f"Consensus reached: Hypothesis '{top_hypo.statement}' has decisive empirical backing "
                    f"(score: {round(top_score, 2)}, margin: +{round(margin, 2)}) supported by {top_hypo.proposing_agent}."
                )
                escalation = None

            elif top_score >= PARTIAL_CONSENSUS_THRESHOLD and not open_fatal:
                state = ConsensusState.PARTIAL_CONSENSUS.value
                winning_id = top_hypo.hypothesis_id
                top_hypo.status = "winning"
                # Primary dispute arbitrated and resolved in favor of top_hypo
                for d in case.disagreements:
                    if d.resolution_status == "open" and (top_hypo.hypothesis_id in d.disputed_hypothesis_ids or not d.disputed_hypothesis_ids):
                        d.resolution_status = "resolved"
                        d.resolution_notes = (
                            f"Resolved by partial consensus in favor of primary cause '{top_hypo.statement}'"
                        )
                open_disagreements = [d.disagreement_id for d in case.disagreements if d.resolution_status == "open"]
                second_hypo = ranked_hypos[1] if len(ranked_hypos) > 1 else None
                sec_text = f" with contributing factor: '{second_hypo.statement}'" if second_hypo else ""
                rationale = (
                    f"Partial consensus: Primary cause identified as '{top_hypo.statement}' (score: {round(top_score, 2)})"
                    f"{sec_text}. Remaining uncertainty acknowledged."
                )
                escalation = None

            else:
                # Disagreement remains material or evidence is insufficient
                winning_id = None
                if curr_round >= self.max_rounds or open_fatal or (open_disagreements and top_score < PARTIAL_CONSENSUS_THRESHOLD):
                    state = ConsensusState.ESCALATED.value
                    escalation = (
                        f"Material disagreement unresolved after {curr_round} reasoning rounds "
                        f"between agents {case.participating_agents}. Top hypothesis confidence ({round(top_score, 2)}) "
                        "insufficient to proceed autonomously."
                    )
                    rationale = f"Reasoning escalated to human supervisor. {escalation}"
                else:
                    state = ConsensusState.NO_CONSENSUS.value
                    rationale = (
                        f"No consensus reached in round {curr_round}. Top hypothesis score ({round(top_score, 2)}) "
                        "does not meet consensus threshold."
                    )
                    escalation = None

            res = ConsensusResult(
                consensus_state=state,
                winning_hypothesis_id=winning_id,
                winning_hypothesis_statement=top_hypo.statement if winning_id else None,
                confidence=top_score,
                supporting_evidence=list(top_hypo.supporting_evidence_ids) if winning_id else [],
                contradicting_evidence=list(top_hypo.contradicting_evidence_ids) if winning_id else [],
                unresolved_critiques=[c.critique_id for c in open_critiques],
                unresolved_disagreements=open_disagreements,
                participating_agents=list(case.participating_agents),
                hypothesis_scores=hypothesis_scores,
                rationale=rationale,
                escalation_reason=escalation,
            )

            # Update case state
            case.consensus_state = res.consensus_state
            case.confidence = res.confidence
            case.winning_hypothesis_id = res.winning_hypothesis_id
            if res.winning_hypothesis_statement:
                case.final_conclusion = res.winning_hypothesis_statement
            if res.consensus_state == ConsensusState.ESCALATED.value:
                case.status = "escalated"
                self._emit_event(
                    AgentEventType.SEO_REASONING_ESCALATED,
                    payload={"case_id": case.case_id, "escalation_reason": res.escalation_reason},
                    correlation_id=case.correlation_id,
                )
            elif res.consensus_state in [ConsensusState.CONSENSUS.value, ConsensusState.PARTIAL_CONSENSUS.value]:
                case.status = "completed"
                self._emit_event(
                    AgentEventType.SEO_REASONING_CONSENSUS_REACHED,
                    payload={
                        "case_id": case.case_id,
                        "state": res.consensus_state,
                        "winning_hypothesis": res.winning_hypothesis_statement,
                        "confidence": res.confidence,
                    },
                    correlation_id=case.correlation_id,
                )
            else:
                self._emit_event(
                    AgentEventType.SEO_REASONING_CONSENSUS_FAILED,
                    payload={"case_id": case.case_id, "round_number": curr_round, "rationale": res.rationale},
                    correlation_id=case.correlation_id,
                )

            case.metadata["consensus_result"] = res.to_dict()
            if shared_memory is not None:
                if hasattr(shared_memory, "record_reasoning_case"):
                    shared_memory.record_reasoning_case(case)
                if state in [ConsensusState.CONSENSUS.value, ConsensusState.PARTIAL_CONSENSUS.value] and hasattr(shared_memory, "record_decision"):
                    from apps.seo.services.agents.shared_memory import DecisionStatus
                    shared_memory.record_decision(
                        title=f"Multi-Agent Consensus: {res.winning_hypothesis_statement or case.final_conclusion}",
                        reason=res.rationale or f"Reached consensus with confidence {round(res.confidence, 2)}",
                        evidence_ids=[e.evidence_id for e in case.evidence_references],
                        decision_owner="seo_supervisor",
                        status=DecisionStatus.ACCEPTED.value,
                        metadata={"case_id": case.case_id, "confidence": res.confidence},
                    )

            case.updated_at = timezone.now().isoformat()
            return res

    def start_next_round(self, case: Any = None, case_id: Optional[str] = None) -> bool:
        """Advance case by one bounded reasoning round, returning False if max_rounds reached."""
        cid = case.case_id if hasattr(case, "case_id") else (case_id or str(case))
        with self._lock:
            case_obj = self.get_case(cid)
            if not case_obj:
                return False
            cur_round = len(case_obj.reasoning_rounds)
            if cur_round >= self.max_rounds:
                return False
            next_num = cur_round + 1
            r_obj = ReasoningRound(
                round_number=next_num,
                case_id=cid,
                participating_agents=list(case_obj.participating_agents),
                new_evidence_count=len(case_obj.evidence_references),
                critiques_count=len(case_obj.critiques),
                disagreements_count=len(case_obj.disagreements),
            )
            case_obj.reasoning_rounds.append(r_obj)
            case_obj.updated_at = timezone.now().isoformat()
            self._emit_event(
                AgentEventType.SEO_REASONING_ROUND_STARTED,
                payload={
                    "case_id": case_obj.case_id,
                    "round_number": next_num,
                    "max_rounds": self.max_rounds,
                },
                correlation_id=case_obj.correlation_id,
            )
            return True

    def execute_reasoning_round(self, case_id: str, round_type: str) -> ReasoningRound:
        """Advance the case by one bounded reasoning round."""
        with self._lock:
            case = self.get_case(case_id)
            if not case:
                raise ValueError(f"ReasoningCase '{case_id}' not found.")

            round_num = len(case.reasoning_rounds) + 1
            if round_num > self.max_rounds:
                logger.warning(f"[{case_id}] Max reasoning rounds ({self.max_rounds}) reached. Escalating.")
                case.status = "escalated"
                case.consensus_state = ConsensusState.ESCALATED.value

            r_obj = ReasoningRound(
                round_number=round_num,
                round_type=round_type,
                case_id=case_id,
                participating_agents=list(case.participating_agents),
                new_evidence_count=len(case.evidence_references),
                critiques_count=len(case.critiques),
                disagreements_count=len(case.disagreements),
            )
            case.reasoning_rounds.append(r_obj)
            case.updated_at = timezone.now().isoformat()

            self._emit_event(
                AgentEventType.SEO_REASONING_ROUND_STARTED,
                payload={
                    "case_id": case.case_id,
                    "round_number": round_num,
                    "round_type": round_type,
                    "max_rounds": self.max_rounds,
                },
                correlation_id=case.correlation_id,
            )
            return r_obj

    def arbitrate(self, case_id: str, supervisor_notes: Optional[str] = None) -> ConsensusResult:
        """
        SEOSupervisor arbitration entrypoint.
        Evaluates consensus, records final decision, and binds uncertainty.
        """
        with self._lock:
            case = self.get_case(case_id)
            if not case:
                raise ValueError(f"ReasoningCase '{case_id}' not found.")

            consensus = self.evaluate_consensus(case_id)
            if supervisor_notes:
                case.metadata["supervisor_arbitration_notes"] = redact_secrets(supervisor_notes)

            self._emit_event(
                AgentEventType.SEO_REASONING_CASE_COMPLETED,
                payload={
                    "case_id": case.case_id,
                    "consensus_state": consensus.consensus_state,
                    "confidence": consensus.confidence,
                    "final_conclusion": case.final_conclusion,
                    "unresolved_disagreements": len(consensus.unresolved_disagreements),
                },
                correlation_id=case.correlation_id,
            )
            return consensus

    def ingest_into_shared_memory(self, case: ReasoningCase, shared_memory: SharedWorkingMemory) -> None:
        """
        Synchronizes reasoning outcomes into SharedWorkingMemory preserving epistemic categories:
        - Evidence -> OBSERVED_FACT
        - Hypotheses -> INFERENCE
        - Disagreements -> MemoryConflict
        - Consensus -> DECISION (owned by seo_supervisor)
        """
        # 1. Ingest evidence items as OBSERVED_FACT
        for evi in case.evidence_references:
            shared_memory.add_evidence(
                fact=evi.fact,
                source_agent=evi.source_agent,
                source_tool=evi.source_tool,
                confidence=evi.confidence,
                raw_data=evi.raw_data,
                metadata={"case_id": case.case_id, "evidence_id": evi.evidence_id, "quality_score": evi.quality_score},
            )

        # 2. Ingest hypotheses as INFERENCE
        for hypo in case.hypotheses:
            shared_memory.add_inference(
                hypothesis=hypo.statement,
                source_agent=hypo.proposing_agent,
                supporting_fact_ids=hypo.supporting_evidence_ids,
                confidence=hypo.confidence,
                derivation_rationale=hypo.reasoning_rationale,
                metadata={
                    "case_id": case.case_id,
                    "hypothesis_id": hypo.hypothesis_id,
                    "status": hypo.status,
                    "contradicting_evidence_ids": hypo.contradicting_evidence_ids,
                    "agent_support": hypo.agent_support,
                    "agent_disagreement": hypo.agent_disagreement,
                },
            )

        # 3. Ingest critiques as structured verification records
        for crit in case.critiques:
            shared_memory.record_verification_result(
                action_id=crit.critique_id,
                target_url=f"hypothesis://{crit.target_hypothesis_id}",
                verified=crit.severity not in [CritiqueSeverity.HIGH.value, CritiqueSeverity.FATAL.value],
                details={
                    "critique_id": crit.critique_id,
                    "target_hypothesis_id": crit.target_hypothesis_id,
                    "critic_agent": crit.critic_agent,
                    "challenge_type": crit.challenge_type,
                    "severity": crit.severity,
                    "confidence": crit.confidence,
                    "challenged_claim": crit.challenged_claim,
                    "recommended_resolution": crit.recommended_resolution,
                }
            )

        # 4. Ingest active disagreements as conflicts in memory
        for disag in case.disagreements:
            if disag.resolution_status == "open":
                conflict_id = f"conf-{disag.disagreement_id[:8]}"
                already_exists = any(c.conflict_id == conflict_id for c in shared_memory._conflicts)
                if not already_exists:
                    shared_memory.record_conflict(
                        conflict_id=conflict_id,
                        topic=f"Disagreement on {case.objective[:60]}",
                        claim_a={"agent": disag.agents_involved[0], "claim": list(disag.conflicting_conclusions.values())[0]},
                        claim_b={"agent": disag.agents_involved[1], "claim": list(disag.conflicting_conclusions.values())[1]},
                        responsible_agents=disag.agents_involved,
                    )

        # 5. Record supervisor decision if consensus or partial consensus reached
        if case.consensus_state in [ConsensusState.CONSENSUS.value, ConsensusState.PARTIAL_CONSENSUS.value]:
            shared_memory.record_decision(
                title=f"Multi-Agent Consensus: {case.final_conclusion}",
                reason=case.metadata.get("supervisor_arbitration_notes") or f"Reached {case.consensus_state} with confidence {round(case.confidence, 2)}.",
                evidence_ids=[e.evidence_id for e in case.evidence_references],
                decision_owner="seo_supervisor",
                status=DecisionStatus.ACCEPTED.value,
                metadata={"case_id": case.case_id, "confidence": case.confidence},
            )

        # 6. Record the complete structured reasoning case
        if hasattr(shared_memory, "record_reasoning_case"):
            shared_memory.record_reasoning_case(case)


class ReasoningRegistry:
    """
    Thread-safe in-memory cache/registry for active and completed ReasoningCase instances.
    Keyed by case_id, correlation_id, and optional run_id.
    """
    _instance: Optional["ReasoningRegistry"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._cases_by_id: Dict[str, ReasoningCase] = {}
        self._cases_by_correlation: Dict[str, List[ReasoningCase]] = {}
        self._cases_by_run_id: Dict[int, List[ReasoningCase]] = {}
        self._registry_lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "ReasoningRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, case: ReasoningCase) -> None:
        with self._registry_lock:
            self._cases_by_id[case.case_id] = case
            if case.correlation_id:
                corr_list = self._cases_by_correlation.setdefault(str(case.correlation_id), [])
                if not any(c.case_id == case.case_id for c in corr_list):
                    corr_list.append(case)
            if case.run_id:
                run_list = self._cases_by_run_id.setdefault(int(case.run_id), [])
                if not any(c.case_id == case.case_id for c in run_list):
                    run_list.append(case)

    def get_by_case_id(self, case_id: str) -> Optional[ReasoningCase]:
        with self._registry_lock:
            return self._cases_by_id.get(str(case_id))

    def get_case(self, case_id: str) -> Optional[ReasoningCase]:
        """Alias for get_by_case_id."""
        return self.get_by_case_id(case_id)

    def get_by_correlation_id(self, correlation_id: str) -> List[ReasoningCase]:
        with self._registry_lock:
            return list(self._cases_by_correlation.get(str(correlation_id), []))

    def get_cases_for_correlation(self, correlation_id: str) -> List[ReasoningCase]:
        """Alias for get_by_correlation_id."""
        return self.get_by_correlation_id(correlation_id)

    def get_by_run_id(self, run_id: int) -> List[ReasoningCase]:
        with self._registry_lock:
            return list(self._cases_by_run_id.get(int(run_id), []))

    def register_case(self, case: ReasoningCase) -> None:
        """Alias for register."""
        self.register(case)

    def clear(self) -> None:
        """Testing utility to reset in-memory registry."""
        with self._registry_lock:
            self._cases_by_id.clear()
            self._cases_by_correlation.clear()
            self._cases_by_run_id.clear()
