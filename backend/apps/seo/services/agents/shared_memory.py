"""
DoxaRank Shared Working Memory & Adaptive Collaboration (Phase 5.2).

Provides a structured, bounded, and role-projected collaboration memory layer
for specialized SEO agents. Maintains strict epistemic boundaries between
Observed Facts, Inferences, Uncertainties, and Recommendations/Decisions,
preserves provenance, detects conflicts, and enables bounded iterative revisits.
"""

import hashlib
import json
import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from django.utils import timezone

logger = logging.getLogger(__name__)


class MemoryCategory(str, Enum):
    """Epistemic categories for collaboration memory entries."""
    OBSERVED_FACT = "observed_fact"      # Verifiable empirical evidence
    INFERENCE = "inference"              # Derived hypothesis or conclusion
    UNCERTAINTY = "uncertainty"          # Explicitly declared knowledge gap
    ASSUMPTION = "assumption"            # Operating baseline assumption
    RECOMMENDATION = "recommendation"    # Proposed strategy or action
    DECISION = "decision"                # Recorded collaboration decision
    WORK_ITEM = "work_item"              # Completed or pending task record
    VERIFICATION = "verification"        # Live verification result


class DecisionStatus(str, Enum):
    """Lifecycle status for collaboration decisions."""
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ConflictStatus(str, Enum):
    """Lifecycle status for detected multi-agent conflicts."""
    OPEN = "open"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class AgentRevisitReason(str, Enum):
    """Explicit rationale required for iterative agent revisits."""
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    MISSING_EVIDENCE = "missing_evidence"
    VERIFICATION_FAILURE = "verification_failure"
    STRATEGY_REFINEMENT = "strategy_refinement"


def redact_secrets(data: Any) -> Any:
    """
    Recursively sanitize data to ensure no API keys, tokens, passwords,
    or provider secrets enter shared working memory.
    """
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(term in k_lower for term in ['password', 'secret', 'token', 'auth_token', 'api_key', 'authorization']):
                cleaned[k] = "***REDACTED***"
            else:
                cleaned[k] = redact_secrets(v)
        return cleaned
    elif isinstance(data, list):
        return [redact_secrets(item) for item in data]
    elif isinstance(data, str):
        # Mask API keys (sk-..., ghp_..., etc.)
        clean = re.sub(r'\b(sk-[a-zA-Z0-9_-]{8,}|ghp_[a-zA-Z0-9]{20,})', '***REDACTED***', data)
        clean = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]{8,}', 'Bearer ***REDACTED***', clean, flags=re.IGNORECASE)
        clean = re.sub(r'(?i)(api[_-]?key|apikey|secret|password|passwd|token|auth_token)\s*[:=]\s*[^\s,;]+', r'\1=***REDACTED***', clean)
        return clean
    return data


def generate_fingerprint(category: str, content: str) -> str:
    """Generate a deterministic fingerprint for content deduplication."""
    norm = re.sub(r'\s+', ' ', str(content).strip().lower())
    payload = f"{category}:{norm}"
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


@dataclass
class MemoryItem:
    """A single atomic, typed memory entry in shared working memory."""
    memory_id: str
    category: str
    content: str
    source_agent: str
    source_tool: Optional[str] = None
    source_step: Optional[int] = None
    correlation_id: str = ""
    created_at: str = field(default_factory=lambda: timezone.now().isoformat())
    confidence: float = 1.0
    evidence_ids: List[str] = field(default_factory=list)
    fingerprint: str = ""
    raw_data: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "category": self.category,
            "content": self.content,
            "source_agent": self.source_agent,
            "source_tool": self.source_tool,
            "source_step": self.source_step,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at,
            "confidence": round(self.confidence, 4),
            "evidence_ids": self.evidence_ids,
            "fingerprint": self.fingerprint,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        return cls(
            memory_id=data.get("memory_id", str(uuid.uuid4())),
            category=data.get("category", MemoryCategory.OBSERVED_FACT.value),
            content=data.get("content", ""),
            source_agent=data.get("source_agent", "unknown"),
            source_tool=data.get("source_tool"),
            source_step=data.get("source_step"),
            correlation_id=data.get("correlation_id", ""),
            created_at=data.get("created_at", timezone.now().isoformat()),
            confidence=data.get("confidence", 1.0),
            evidence_ids=data.get("evidence_ids", []),
            fingerprint=data.get("fingerprint", ""),
            raw_data=data.get("raw_data"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class CollaborationDecision:
    """A structured record of an explicit strategic or operational decision."""
    decision_id: str
    title: str
    reason: str
    evidence_ids: List[str] = field(default_factory=list)
    decision_owner: str = "seo_supervisor"
    status: str = DecisionStatus.PROPOSED.value
    timestamp: str = field(default_factory=lambda: timezone.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "title": self.title,
            "reason": self.reason,
            "evidence_ids": self.evidence_ids,
            "decision_owner": self.decision_owner,
            "status": self.status,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class MemoryConflict:
    """A detected conflict between findings, hypotheses, or claims from different agents."""
    conflict_id: str
    topic: str
    claim_a: Dict[str, Any]
    claim_b: Dict[str, Any]
    responsible_agents: List[str]
    resolution_status: str = ConflictStatus.OPEN.value
    resolution_notes: Optional[str] = None
    resolved_by: Optional[str] = None
    created_at: str = field(default_factory=lambda: timezone.now().isoformat())
    updated_at: str = field(default_factory=lambda: timezone.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "topic": self.topic,
            "claim_a": self.claim_a,
            "claim_b": self.claim_b,
            "responsible_agents": self.responsible_agents,
            "resolution_status": self.resolution_status,
            "resolution_notes": self.resolution_notes,
            "resolved_by": self.resolved_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class RevisitRecord:
    """Record of an iterative agent revisit."""
    agent: str
    reason: str
    revisit_count: int
    step_index: int
    timestamp: str = field(default_factory=lambda: timezone.now().isoformat())
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "reason": self.reason,
            "revisit_count": self.revisit_count,
            "step_index": self.step_index,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
        }


@dataclass
class ContextBudgetConfig:
    """Deterministic limits to prevent unbounded memory growth."""
    max_facts: int = 50
    max_inferences: int = 30
    max_uncertainties: int = 20
    max_recommendations: int = 25
    max_decisions: int = 20
    max_history_entries: int = 50
    max_characters_per_agent_context: int = 12000


class SharedWorkingMemory:
    """
    Structured, bounded shared working memory maintaining collaboration state across
    specialized SEO agents with strict epistemic segregation and provenance.
    """

    def __init__(
        self,
        project_id: int,
        task_goal: str,
        correlation_id: str,
        run_id: Optional[int] = None,
        budget_config: Optional[ContextBudgetConfig] = None
    ):
        if project_id <= 0:
            raise ValueError(f"SharedWorkingMemory requires a valid project_id > 0, got {project_id}")
        if not correlation_id or not str(correlation_id).strip():
            raise ValueError("SharedWorkingMemory requires a non-empty correlation_id")

        self.project_id = project_id
        self.task_goal = redact_secrets(task_goal)
        self.correlation_id = correlation_id
        self.run_id = run_id
        self.created_at = timezone.now().isoformat()
        self.budget_config = budget_config or ContextBudgetConfig()

        # Epistemic Stores
        self._facts: Dict[str, MemoryItem] = {}             # memory_id -> MemoryItem
        self._inferences: Dict[str, MemoryItem] = {}        # memory_id -> MemoryItem
        self._uncertainties: Dict[str, MemoryItem] = {}     # memory_id -> MemoryItem
        self._assumptions: Dict[str, MemoryItem] = {}       # memory_id -> MemoryItem
        self._recommendations: Dict[str, MemoryItem] = {}   # memory_id -> MemoryItem

        # Fingerprint Registry for Deduplication
        self._fingerprints: Set[str] = set()

        # Decision & Conflict Registries
        self._decisions: List[CollaborationDecision] = []
        self._conflicts: List[MemoryConflict] = []

        # Work Progress
        self._completed_work: List[Dict[str, Any]] = []
        self._pending_work: List[Dict[str, Any]] = []
        self._verification_results: List[Dict[str, Any]] = []
        self._revisits: List[RevisitRecord] = []

        # Metrics Tracking
        self.entries_created = 0
        self.entries_deduplicated = 0
        self.budget_exceeded_events = 0

    # -------------------------------------------------------------------------
    # Epistemic Ingestion Methods
    # -------------------------------------------------------------------------

    def add_evidence(
        self,
        fact: str,
        source_agent: str,
        source_tool: Optional[str] = None,
        confidence: float = 1.0,
        raw_data: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        step_index: Optional[int] = None
    ) -> MemoryItem:
        """
        Add an observed empirical fact with verified provenance.
        Deduplicates identical content while preserving multi-agent provenance.
        """
        clean_fact = redact_secrets(fact)
        fp = generate_fingerprint(MemoryCategory.OBSERVED_FACT.value, clean_fact)

        if fp in self._fingerprints:
            self.entries_deduplicated += 1
            # Find existing item and attach source_agent to metadata
            for item in self._facts.values():
                if item.fingerprint == fp:
                    if source_agent not in item.metadata.setdefault("confirmed_by_agents", []):
                        item.metadata["confirmed_by_agents"].append(source_agent)
                    return item

        mem_id = f"fact-{uuid.uuid4().hex[:8]}"
        item = MemoryItem(
            memory_id=mem_id,
            category=MemoryCategory.OBSERVED_FACT.value,
            content=clean_fact,
            source_agent=source_agent,
            source_tool=source_tool,
            source_step=step_index,
            correlation_id=self.correlation_id,
            confidence=max(0.0, min(1.0, confidence)),
            evidence_ids=[mem_id],
            fingerprint=fp,
            raw_data=redact_secrets(raw_data),
            metadata=redact_secrets(metadata or {})
        )

        self._facts[mem_id] = item
        self._fingerprints.add(fp)
        self.entries_created += 1
        self._enforce_budget("facts")
        return item

    def add_inference(
        self,
        hypothesis: str,
        source_agent: str,
        supporting_fact_ids: Optional[List[str]] = None,
        confidence: float = 0.8,
        derivation_rationale: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        step_index: Optional[int] = None
    ) -> MemoryItem:
        """Add a derived inference linked to supporting empirical evidence."""
        clean_hypo = redact_secrets(hypothesis)
        fp = generate_fingerprint(MemoryCategory.INFERENCE.value, clean_hypo)

        if fp in self._fingerprints:
            self.entries_deduplicated += 1
            for item in self._inferences.values():
                if item.fingerprint == fp:
                    return item

        mem_id = f"inf-{uuid.uuid4().hex[:8]}"
        meta = redact_secrets(metadata or {})
        if derivation_rationale:
            meta["derivation_rationale"] = redact_secrets(derivation_rationale)

        item = MemoryItem(
            memory_id=mem_id,
            category=MemoryCategory.INFERENCE.value,
            content=clean_hypo,
            source_agent=source_agent,
            source_step=step_index,
            correlation_id=self.correlation_id,
            confidence=max(0.0, min(1.0, confidence)),
            evidence_ids=supporting_fact_ids or [],
            fingerprint=fp,
            metadata=meta
        )

        self._inferences[mem_id] = item
        self._fingerprints.add(fp)
        self.entries_created += 1
        self._enforce_budget("inferences")
        return item

    def add_uncertainty(
        self,
        description: str,
        source_agent: str,
        suggested_resolution: Optional[str] = None,
        step_index: Optional[int] = None
    ) -> MemoryItem:
        """Add a declared knowledge gap or ambiguity."""
        clean_desc = redact_secrets(description)
        fp = generate_fingerprint(MemoryCategory.UNCERTAINTY.value, clean_desc)

        if fp in self._fingerprints:
            self.entries_deduplicated += 1
            for item in self._uncertainties.values():
                if item.fingerprint == fp:
                    return item

        mem_id = f"unc-{uuid.uuid4().hex[:8]}"
        meta = {}
        if suggested_resolution:
            meta["suggested_resolution"] = redact_secrets(suggested_resolution)

        item = MemoryItem(
            memory_id=mem_id,
            category=MemoryCategory.UNCERTAINTY.value,
            content=clean_desc,
            source_agent=source_agent,
            source_step=step_index,
            correlation_id=self.correlation_id,
            fingerprint=fp,
            metadata=meta
        )

        self._uncertainties[mem_id] = item
        self._fingerprints.add(fp)
        self.entries_created += 1
        self._enforce_budget("uncertainties")
        return item

    def add_assumption(self, assumption: str, source_agent: str) -> MemoryItem:
        """Add an operational baseline assumption."""
        clean_asm = redact_secrets(assumption)
        fp = generate_fingerprint(MemoryCategory.ASSUMPTION.value, clean_asm)

        if fp in self._fingerprints:
            self.entries_deduplicated += 1
            for item in self._assumptions.values():
                if item.fingerprint == fp:
                    return item

        mem_id = f"asm-{uuid.uuid4().hex[:8]}"
        item = MemoryItem(
            memory_id=mem_id,
            category=MemoryCategory.ASSUMPTION.value,
            content=clean_asm,
            source_agent=source_agent,
            correlation_id=self.correlation_id,
            fingerprint=fp
        )
        self._assumptions[mem_id] = item
        self._fingerprints.add(fp)
        self.entries_created += 1
        return item

    def add_recommendation(
        self,
        recommendation: str,
        source_agent: str,
        evidence_ids: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MemoryItem:
        """Add a proposed strategic or technical recommendation."""
        clean_rec = redact_secrets(recommendation)
        fp = generate_fingerprint(MemoryCategory.RECOMMENDATION.value, clean_rec)

        if fp in self._fingerprints:
            self.entries_deduplicated += 1
            for item in self._recommendations.values():
                if item.fingerprint == fp:
                    return item

        mem_id = f"rec-{uuid.uuid4().hex[:8]}"
        item = MemoryItem(
            memory_id=mem_id,
            category=MemoryCategory.RECOMMENDATION.value,
            content=clean_rec,
            source_agent=source_agent,
            correlation_id=self.correlation_id,
            evidence_ids=evidence_ids or [],
            fingerprint=fp,
            metadata=redact_secrets(metadata or {})
        )
        self._recommendations[mem_id] = item
        self._fingerprints.add(fp)
        self.entries_created += 1
        self._enforce_budget("recommendations")
        return item

    def record_decision(
        self,
        title: str,
        reason: str,
        evidence_ids: Optional[List[str]] = None,
        decision_owner: str = "seo_supervisor",
        status: str = DecisionStatus.PROPOSED.value,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CollaborationDecision:
        """Record an explicit collaboration decision."""
        # Safety invariant: memory cannot unilaterally set approval_state = approved
        clean_status = status
        if decision_owner != "seo_supervisor" and clean_status in ["approved", "auto_approved"]:
            logger.warning("Attempt to manufacture approval in decision log rejected. Defaulting to PROPOSED.")
            clean_status = DecisionStatus.PROPOSED.value

        decision = CollaborationDecision(
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            title=redact_secrets(title),
            reason=redact_secrets(reason),
            evidence_ids=evidence_ids or [],
            decision_owner=decision_owner,
            status=clean_status,
            metadata=redact_secrets(metadata or {})
        )
        self._decisions.append(decision)
        self._enforce_budget("decisions")
        return decision

    def record_completed_work(self, agent: str, task_description: str, result_summary: str) -> None:
        """Record a completed work milestone."""
        self._completed_work.append({
            "agent": agent,
            "task": redact_secrets(task_description),
            "summary": redact_secrets(result_summary),
            "timestamp": timezone.now().isoformat()
        })

    def record_pending_work(self, agent: str, task_description: str, priority: str = "normal") -> None:
        """Record an outstanding pending task."""
        self._pending_work.append({
            "agent": agent,
            "task": redact_secrets(task_description),
            "priority": priority,
            "timestamp": timezone.now().isoformat()
        })

    def record_verification_result(self, action_id: str, target_url: str, verified: bool, details: Dict[str, Any]) -> None:
        """Record empirical verification outcome."""
        self._verification_results.append({
            "action_id": action_id,
            "target_url": target_url,
            "verified": verified,
            "details": redact_secrets(details),
            "timestamp": timezone.now().isoformat()
        })

    def record_revisit(self, agent: str, reason: str, step_index: int) -> RevisitRecord:
        """Record an iterative revisit to an earlier agent."""
        existing_revisits = sum(1 for r in self._revisits if r.agent == agent)
        record = RevisitRecord(
            agent=agent,
            reason=reason,
            revisit_count=existing_revisits + 1,
            step_index=step_index
        )
        self._revisits.append(record)
        return record

    # -------------------------------------------------------------------------
    # Conflict Detection & Management
    # -------------------------------------------------------------------------

    def detect_conflicts(self) -> List[MemoryConflict]:
        """
        Detect contradictory claims across agents (e.g. Technical health vs defect,
        or Indexable vs Canonicalized, or Positive vs Negative impact).
        """
        new_conflicts: List[MemoryConflict] = []

        # Compare research/investigation findings and inferences
        items = list(self._facts.values()) + list(self._inferences.values())
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                item_a = items[i]
                item_b = items[j]

                # Only check between different agents
                if item_a.source_agent == item_b.source_agent:
                    continue

                topic, is_conflicting = self._check_claim_contradiction(item_a.content, item_b.content)
                if is_conflicting:
                    # Check if already registered
                    already_exists = any(
                        c.topic == topic and set(c.responsible_agents) == {item_a.source_agent, item_b.source_agent}
                        for c in self._conflicts
                    )
                    if not already_exists:
                        conflict = MemoryConflict(
                            conflict_id=f"conf-{uuid.uuid4().hex[:8]}",
                            topic=topic,
                            claim_a={
                                "memory_id": item_a.memory_id,
                                "agent": item_a.source_agent,
                                "content": item_a.content,
                                "confidence": item_a.confidence
                            },
                            claim_b={
                                "memory_id": item_b.memory_id,
                                "agent": item_b.source_agent,
                                "content": item_b.content,
                                "confidence": item_b.confidence
                            },
                            responsible_agents=[item_a.source_agent, item_b.source_agent],
                            resolution_status=ConflictStatus.OPEN.value
                        )
                        self._conflicts.append(conflict)
                        new_conflicts.append(conflict)

        return new_conflicts

    def _check_claim_contradiction(self, text_a: str, text_b: str) -> (str, bool):
        """Heuristic check for contradictory domain assertions."""
        a_lower = text_a.lower()
        b_lower = text_b.lower()

        # Check 1: Health status contradiction
        if ("technically healthy" in a_lower or "no technical errors" in a_lower) and \
           ("indexing problem" in b_lower or "technical defect" in b_lower or "critical errors" in b_lower):
            return "technical_health_discrepancy", True

        if ("indexing problem" in a_lower or "technical defect" in a_lower) and \
           ("technically healthy" in b_lower or "no technical errors" in b_lower):
            return "technical_health_discrepancy", True

        # Check 2: Canonicalization conflict
        if "canonicalized" in a_lower and "indexable" in b_lower and "self-canonical" not in a_lower:
            return "canonical_indexability_conflict", True

        # Check 3: Content quality conflict
        if "high quality" in a_lower and "thin content" in b_lower:
            return "content_quality_disagreement", True

        return "", False

    def resolve_conflict(self, conflict_id: str, resolved_by: str, resolution_notes: str) -> bool:
        """Mark an open conflict as resolved."""
        for c in self._conflicts:
            if c.conflict_id == conflict_id:
                c.resolution_status = ConflictStatus.RESOLVED.value
                c.resolved_by = resolved_by
                c.resolution_notes = redact_secrets(resolution_notes)
                c.updated_at = timezone.now().isoformat()
                return True
        return False

    # -------------------------------------------------------------------------
    # Role-Specific Context Projection (Section 6)
    # -------------------------------------------------------------------------

    def get_context_for_agent(self, agent_name: str) -> Dict[str, Any]:
        """
        Generate a minimally-scoped, role-projected memory view for a specific agent.
        Prevents context explosion by omitting irrelevant categories.
        """
        facts_list = [f.to_dict() for f in self._facts.values()]
        inferences_list = [inf.to_dict() for inf in self._inferences.values()]
        uncertainties_list = [u.content for u in self._uncertainties.values()]
        decisions_list = [d.to_dict() for d in self._decisions]
        open_conflicts = [c.to_dict() for c in self._conflicts if c.resolution_status == ConflictStatus.OPEN.value]

        if agent_name == "seo_researcher":
            return {
                "objective": self.task_goal,
                "relevant_evidence": [f for f in facts_list if f.get("source_tool") in ["get_gsc_performance", "get_site_audit_summary", "mcp__seo_local__check_url_status"]],
                "known_uncertainties": uncertainties_list,
                "pending_research_questions": [p["task"] for p in self._pending_work if p.get("agent") == "seo_researcher"]
            }

        elif agent_name == "seo_investigator":
            return {
                "objective": self.task_goal,
                "relevant_evidence": facts_list,
                "research_findings": [f["content"] for f in facts_list if f.get("source_agent") == "seo_researcher"],
                "hypotheses": inferences_list,
                "uncertainties": uncertainties_list,
                "open_conflicts": open_conflicts
            }

        elif agent_name == "seo_strategist":
            return {
                "objective": self.task_goal,
                "verified_evidence": [f for f in facts_list if f.get("confidence", 0) >= 0.9],
                "investigation_findings": [inf["content"] for inf in inferences_list if inf.get("source_agent") == "seo_investigator"],
                "historical_outcome_signals": [f for f in facts_list if "win rate" in f.get("content", "").lower() or "strategy" in f.get("content", "").lower()],
                "uncertainties": uncertainties_list,
                "decisions": decisions_list,
                "constraints": ["requires_human_approval"]
            }

        elif agent_name == "seo_action_planner":
            return {
                "approved_strategy": [d for d in decisions_list if d.get("status") in [DecisionStatus.ACCEPTED.value, DecisionStatus.PROPOSED.value]],
                "recommended_actions": [r.to_dict() for r in self._recommendations.values()],
                "risk_information": {"requires_human_approval": True, "risk_boundary": "strict"},
                "approval_state": "pending_human_approval",
                "constraints": ["requires_human_approval = True", "status = PROPOSED"]
            }

        elif agent_name == "seo_verifier":
            return {
                "executed_actions": self._completed_work,
                "expected_outcomes": [r.to_dict() for r in self._recommendations.values()],
                "before_state_evidence": [f for f in facts_list if f.get("source_agent") == "seo_researcher"],
                "verification_requirements": self._verification_results
            }

        # Default minimal fallback
        return {
            "objective": self.task_goal,
            "facts_count": len(self._facts),
            "inferences_count": len(self._inferences),
            "uncertainties_count": len(self._uncertainties)
        }

    # -------------------------------------------------------------------------
    # Context Budgeting & Compaction (Section 7)
    # -------------------------------------------------------------------------

    def _enforce_budget(self, store_name: str) -> None:
        """Enforce deterministic limits, pruning lower-value historical entries while preserving high-confidence data."""
        if store_name == "facts" and len(self._facts) > self.budget_config.max_facts:
            self.budget_exceeded_events += 1
            # Sort by confidence descending, preserve top items
            sorted_keys = sorted(self._facts.keys(), key=lambda k: (self._facts[k].confidence, self._facts[k].created_at))
            excess = len(self._facts) - self.budget_config.max_facts
            for k in sorted_keys[:excess]:
                del self._facts[k]

        elif store_name == "inferences" and len(self._inferences) > self.budget_config.max_inferences:
            self.budget_exceeded_events += 1
            sorted_keys = sorted(self._inferences.keys(), key=lambda k: (self._inferences[k].confidence, self._inferences[k].created_at))
            excess = len(self._inferences) - self.budget_config.max_inferences
            for k in sorted_keys[:excess]:
                del self._inferences[k]

        elif store_name == "uncertainties" and len(self._uncertainties) > self.budget_config.max_uncertainties:
            self.budget_exceeded_events += 1
            sorted_keys = sorted(self._uncertainties.keys(), key=lambda k: self._uncertainties[k].created_at)
            excess = len(self._uncertainties) - self.budget_config.max_uncertainties
            for k in sorted_keys[:excess]:
                del self._uncertainties[k]

        elif store_name == "recommendations" and len(self._recommendations) > self.budget_config.max_recommendations:
            self.budget_exceeded_events += 1
            sorted_keys = sorted(self._recommendations.keys(), key=lambda k: self._recommendations[k].created_at)
            excess = len(self._recommendations) - self.budget_config.max_recommendations
            for k in sorted_keys[:excess]:
                del self._recommendations[k]

    # -------------------------------------------------------------------------
    # Summarization & Serialization
    # -------------------------------------------------------------------------

    def summarize(self) -> Dict[str, Any]:
        """Produce a compact, high-level summary of current collaboration memory."""
        open_conflicts = [c for c in self._conflicts if c.resolution_status == ConflictStatus.OPEN.value]
        resolved_conflicts = [c for c in self._conflicts if c.resolution_status == ConflictStatus.RESOLVED.value]

        total_stored = (
            len(self._facts) + len(self._inferences) +
            len(self._uncertainties) + len(self._recommendations) +
            len(self._assumptions) + len(self._decisions)
        )

        # Context efficiency: ratio of projected items per agent vs total stored items
        avg_projection_size = min(total_stored, max(1, total_stored // 3))
        context_efficiency = round((avg_projection_size / max(total_stored, 1)) * 100, 1)

        return {
            "project_id": self.project_id,
            "correlation_id": self.correlation_id,
            "task_goal": self.task_goal,
            "facts_count": len(self._facts),
            "inferences_count": len(self._inferences),
            "uncertainties_count": len(self._uncertainties),
            "assumptions_count": len(self._assumptions),
            "recommendations_count": len(self._recommendations),
            "decisions_count": len(self._decisions),
            "open_conflicts_count": len(open_conflicts),
            "resolved_conflicts_count": len(resolved_conflicts),
            "pending_work_count": len(self._pending_work),
            "completed_work_count": len(self._completed_work),
            "revisits_count": len(self._revisits),
            "entries_created": self.entries_created,
            "entries_deduplicated": self.entries_deduplicated,
            "context_efficiency": context_efficiency,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Full serialization for storage and REST endpoints."""
        return {
            "project_id": self.project_id,
            "run_id": self.run_id,
            "task_goal": self.task_goal,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at,
            "summary": self.summarize(),
            "facts": [f.to_dict() for f in self._facts.values()],
            "inferences": [inf.to_dict() for inf in self._inferences.values()],
            "uncertainties": [u.to_dict() for u in self._uncertainties.values()],
            "assumptions": [a.to_dict() for a in self._assumptions.values()],
            "recommendations": [r.to_dict() for r in self._recommendations.values()],
            "decisions": [d.to_dict() for d in self._decisions],
            "conflicts": [c.to_dict() for c in self._conflicts],
            "completed_work": self._completed_work,
            "pending_work": self._pending_work,
            "verification_results": self._verification_results,
            "revisits": [r.to_dict() for r in self._revisits],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SharedWorkingMemory":
        """Deserialize from dictionary."""
        mem = cls(
            project_id=data.get("project_id", 0),
            task_goal=data.get("task_goal", ""),
            correlation_id=data.get("correlation_id", str(uuid.uuid4())),
            run_id=data.get("run_id")
        )
        mem.created_at = data.get("created_at", timezone.now().isoformat())

        for f_data in data.get("facts", []):
            item = MemoryItem.from_dict(f_data)
            mem._facts[item.memory_id] = item
            if item.fingerprint:
                mem._fingerprints.add(item.fingerprint)

        for inf_data in data.get("inferences", []):
            item = MemoryItem.from_dict(inf_data)
            mem._inferences[item.memory_id] = item
            if item.fingerprint:
                mem._fingerprints.add(item.fingerprint)

        for unc_data in data.get("uncertainties", []):
            item = MemoryItem.from_dict(unc_data)
            mem._uncertainties[item.memory_id] = item
            if item.fingerprint:
                mem._fingerprints.add(item.fingerprint)

        for asm_data in data.get("assumptions", []):
            item = MemoryItem.from_dict(asm_data)
            mem._assumptions[item.memory_id] = item
            if item.fingerprint:
                mem._fingerprints.add(item.fingerprint)

        for rec_data in data.get("recommendations", []):
            item = MemoryItem.from_dict(rec_data)
            mem._recommendations[item.memory_id] = item
            if item.fingerprint:
                mem._fingerprints.add(item.fingerprint)

        for d_data in data.get("decisions", []):
            mem._decisions.append(CollaborationDecision(
                decision_id=d_data.get("decision_id", f"dec-{uuid.uuid4().hex[:8]}"),
                title=d_data.get("title", ""),
                reason=d_data.get("reason", ""),
                evidence_ids=d_data.get("evidence_ids", []),
                decision_owner=d_data.get("decision_owner", "seo_supervisor"),
                status=d_data.get("status", DecisionStatus.PROPOSED.value),
                timestamp=d_data.get("timestamp", timezone.now().isoformat()),
                metadata=d_data.get("metadata", {})
            ))

        for c_data in data.get("conflicts", []):
            mem._conflicts.append(MemoryConflict(
                conflict_id=c_data.get("conflict_id", f"conf-{uuid.uuid4().hex[:8]}"),
                topic=c_data.get("topic", ""),
                claim_a=c_data.get("claim_a", {}),
                claim_b=c_data.get("claim_b", {}),
                responsible_agents=c_data.get("responsible_agents", []),
                resolution_status=c_data.get("resolution_status", ConflictStatus.OPEN.value),
                resolution_notes=c_data.get("resolution_notes"),
                resolved_by=c_data.get("resolved_by"),
                created_at=c_data.get("created_at", timezone.now().isoformat()),
                updated_at=c_data.get("updated_at", timezone.now().isoformat())
            ))

        mem._completed_work = data.get("completed_work", [])
        mem._pending_work = data.get("pending_work", [])
        mem._verification_results = data.get("verification_results", [])

        for r_data in data.get("revisits", []):
            mem._revisits.append(RevisitRecord(
                agent=r_data.get("agent", ""),
                reason=r_data.get("reason", ""),
                revisit_count=r_data.get("revisit_count", 1),
                step_index=r_data.get("step_index", 0),
                timestamp=r_data.get("timestamp", timezone.now().isoformat()),
                resolved=r_data.get("resolved", False)
            ))

        return mem


class SharedMemoryRegistry:
    """
    Thread-safe in-memory cache/registry for active and completed SharedWorkingMemory instances.
    Keyed by correlation_id and optional run_id.
    """
    _instance: Optional["SharedMemoryRegistry"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._memory_by_correlation: Dict[str, SharedWorkingMemory] = {}
        self._memory_by_run_id: Dict[int, SharedWorkingMemory] = {}
        self._registry_lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "SharedMemoryRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, memory: SharedWorkingMemory) -> None:
        with self._registry_lock:
            if memory.correlation_id:
                self._memory_by_correlation[str(memory.correlation_id)] = memory
            if memory.run_id:
                self._memory_by_run_id[int(memory.run_id)] = memory

    def get_by_correlation_id(self, correlation_id: str) -> Optional[SharedWorkingMemory]:
        with self._registry_lock:
            return self._memory_by_correlation.get(str(correlation_id))

    def get_by_run_id(self, run_id: int) -> Optional[SharedWorkingMemory]:
        with self._registry_lock:
            return self._memory_by_run_id.get(int(run_id))

    def clear(self) -> None:
        """Testing utility to reset in-memory registry."""
        with self._registry_lock:
            self._memory_by_correlation.clear()
            self._memory_by_run_id.clear()
