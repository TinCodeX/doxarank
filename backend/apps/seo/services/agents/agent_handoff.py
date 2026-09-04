"""
DoxaRank Structured Agent Handoffs & Collaboration State (Phase 5.1).

Defines strongly-typed, controlled handoff contexts between specialized agents,
evidence provenance preservation, multi-agent collaboration state, and strict
pre-acceptance validation rules.
"""

import logging
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Set
from django.utils import timezone

logger = logging.getLogger(__name__)

# Canonical set of recognized specialized agents in DoxaRank
KNOWN_AGENTS: Set[str] = {
    "seo_supervisor",
    "seo_researcher",
    "seo_investigator",
    "seo_strategist",
    "seo_action_planner",
    "seo_verifier",
}

# Immutable class-level tool allowlists for privilege validation
KNOWN_AGENT_ALLOWED_TOOLS: Dict[str, Set[str]] = {
    "seo_supervisor": set(),
    "seo_researcher": {
        "get_gsc_performance",
        "get_gsc_queries",
        "get_gsc_pages",
        "analyze_gsc_performance",
        "get_keyword_rankings",
        "get_ranking_history",
        "get_tracked_keywords",
        "get_site_audit_summary",
        "get_audit_issues",
        "get_action_outcomes",
        "get_adaptive_seo_strategy",
        "mcp__seo_local__check_url_status",
        "mcp__seo_local__get_page_metadata",
        "mcp__seo_local__get_external_page_signals",
    },
    "seo_investigator": {
        "get_gsc_performance",
        "get_gsc_queries",
        "get_gsc_pages",
        "analyze_gsc_performance",
        "get_site_audit_summary",
        "get_audit_issues",
        "analyze_seo_opportunities",
        "investigate_seo_opportunity",
        "get_action_outcomes",
        "get_adaptive_seo_strategy",
        "mcp__seo_local__check_url_status",
        "mcp__seo_local__get_page_metadata",
        "mcp__seo_local__get_external_page_signals",
    },
    "seo_strategist": {
        "get_adaptive_seo_strategy",
        "get_action_outcomes",
        "analyze_seo_opportunities",
    },
    "seo_action_planner": {
        "plan_seo_actions",
        "get_action_plan",
        "propose_seo_action",
        "get_action",
        "preview_action",
    },
    "seo_verifier": {
        "verify_seo_action",
        "verify_action_plan",
        "get_action_outcomes",
    },
}

VALID_APPROVAL_STATES: Set[str] = {
    "none",
    "pending_human_approval",
    "approved",
    "rejected",
}


class AgentHandoffValidationError(ValueError):
    """Raised when an agent handoff fails schema, tenant, permission, or security validation."""
    pass


@dataclass
class EvidenceItem:
    """
    An empirical observation with strict provenance tracking.
    Must never be conflated with derived inferences or hypotheses.
    """
    fact: str
    source: str
    timestamp: str = field(default_factory=lambda: timezone.now().isoformat())
    confidence: float = 1.0
    raw_data: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact": self.fact,
            "source": self.source,
            "timestamp": self.timestamp,
            "confidence": round(self.confidence, 4),
            "raw_data": self.raw_data,
            "metadata": self.metadata,
        }


@dataclass
class InferenceItem:
    """
    A causal conclusion or diagnostic hypothesis derived from evidence.
    Must be kept distinct from directly observed facts.
    """
    inference: str
    based_on: List[str] = field(default_factory=list)
    confidence: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inference": self.inference,
            "based_on": self.based_on,
            "confidence": round(self.confidence, 4),
            "metadata": self.metadata,
        }


@dataclass
class UncertaintyItem:
    """
    An unverified assumption, missing data point, or knowledge boundary.
    """
    uncertainty: str
    missing_data: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uncertainty": self.uncertainty,
            "missing_data": self.missing_data,
            "metadata": self.metadata,
        }


@dataclass
class AgentHandoffContext:
    """
    Controlled context package transferred explicitly between specialized agents.
    Carries only the minimal, relevant domain data required by the receiving agent.
    Guarantees tenant isolation, tool permissions immutability, and approval state integrity.
    """
    project_id: int
    source_agent: str
    target_agent: str
    user_goal: str
    task_type: str
    correlation_id: str
    task_id: Optional[int] = None
    run_id: Optional[int] = None

    # Scoped evidence & domain artifacts
    relevant_evidence: Dict[str, Any] = field(default_factory=dict)
    observed_facts: List[Dict[str, Any]] = field(default_factory=list)
    inferences: List[Dict[str, Any]] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)

    # Workflow & next step recommendations
    findings: List[str] = field(default_factory=list)
    recommended_next_step: Optional[str] = None
    previous_agent_steps: List[Dict[str, Any]] = field(default_factory=list)

    # Security & governance boundaries
    allowed_tools: List[str] = field(default_factory=list)
    risk_information: Dict[str, Any] = field(default_factory=dict)
    approval_state: str = "none"  # "none" | "pending_human_approval" | "approved" | "rejected"
    timestamp: str = field(default_factory=lambda: timezone.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "task_id": self.task_id or self.run_id,
            "run_id": self.run_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "user_goal": self.user_goal,
            "task_type": self.task_type,
            "correlation_id": self.correlation_id,
            "relevant_evidence": self.relevant_evidence,
            "observed_facts": self.observed_facts,
            "inferences": self.inferences,
            "uncertainties": self.uncertainties,
            "assumptions": self.assumptions,
            "findings": self.findings,
            "recommended_next_step": self.recommended_next_step,
            "previous_agent_steps": self.previous_agent_steps,
            "allowed_tools": self.allowed_tools,
            "risk_information": self.risk_information,
            "approval_state": self.approval_state,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentHandoffContext":
        return cls(
            project_id=data.get("project_id", 0),
            task_id=data.get("task_id"),
            run_id=data.get("run_id"),
            source_agent=data.get("source_agent", ""),
            target_agent=data.get("target_agent", ""),
            user_goal=data.get("user_goal", ""),
            task_type=data.get("task_type", "general"),
            correlation_id=data.get("correlation_id", ""),
            relevant_evidence=data.get("relevant_evidence", {}),
            observed_facts=data.get("observed_facts", []),
            inferences=data.get("inferences", []),
            uncertainties=data.get("uncertainties", []),
            assumptions=data.get("assumptions", []),
            findings=data.get("findings", []),
            recommended_next_step=data.get("recommended_next_step"),
            previous_agent_steps=data.get("previous_agent_steps", []),
            allowed_tools=data.get("allowed_tools", []),
            risk_information=data.get("risk_information", {}),
            approval_state=data.get("approval_state", "none"),
            timestamp=data.get("timestamp", timezone.now().isoformat()),
        )


@dataclass
class CollaborationState:
    """
    Lightweight, deterministic collaboration state maintained by the supervisor.
    Provides clear observability into agent execution stages, handoffs, and failures.
    """
    project_id: int
    task_goal: str
    task_type: str
    correlation_id: str
    status: str = "initialized"  # "initialized" | "running" | "completed" | "degraded" | "failed"
    current_agent: Optional[str] = None
    completed_agents: List[str] = field(default_factory=list)
    pending_agents: List[str] = field(default_factory=list)
    failed_agents: List[str] = field(default_factory=list)
    handoff_history: List[Dict[str, Any]] = field(default_factory=list)
    current_evidence: Dict[str, Any] = field(default_factory=dict)
    unresolved_questions: List[str] = field(default_factory=list)
    final_result: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "task_goal": self.task_goal,
            "task_type": self.task_type,
            "correlation_id": self.correlation_id,
            "status": self.status,
            "current_agent": self.current_agent,
            "completed_agents": self.completed_agents,
            "pending_agents": self.pending_agents,
            "failed_agents": self.failed_agents,
            "handoff_history": self.handoff_history,
            "current_evidence": self.current_evidence,
            "unresolved_questions": self.unresolved_questions,
            "final_result": self.final_result,
            "errors": self.errors,
        }


class AgentHandoffValidator:
    """
    Strict security and integrity validator for all agent handoffs.
    Enforces:
    1. Source and target agents are registered in KNOWN_AGENTS.
    2. Tenant project_id strictly matches active project context.
    3. Required fields exist and are non-empty.
    4. Observed evidence has explicit source provenance.
    5. Tool permissions cannot be escalated above target agent's immutable allowlist.
    6. Approval state cannot be escalated autonomously by an agent.
    """

    @classmethod
    def validate(cls, handoff: AgentHandoffContext, expected_project_id: int) -> None:
        """
        Validate an AgentHandoffContext before allowing execution to proceed.
        Raises AgentHandoffValidationError if any validation check fails.
        """
        # 1. Source and Target agent recognition
        if not handoff.source_agent or handoff.source_agent not in KNOWN_AGENTS:
            raise AgentHandoffValidationError(
                f"Invalid handoff: Unrecognized source agent '{handoff.source_agent}'. "
                f"Known agents: {sorted(list(KNOWN_AGENTS))}"
            )

        if not handoff.target_agent or handoff.target_agent not in KNOWN_AGENTS:
            raise AgentHandoffValidationError(
                f"Invalid handoff: Unrecognized target agent '{handoff.target_agent}'. "
                f"Known agents: {sorted(list(KNOWN_AGENTS))}"
            )

        # 2. Tenant / Project isolation
        if handoff.project_id <= 0 or handoff.project_id != expected_project_id:
            raise AgentHandoffValidationError(
                f"Tenant Security Violation: Handoff project_id {handoff.project_id} does not "
                f"match active project_id {expected_project_id}."
            )

        # 3. Required fields
        if not handoff.correlation_id or not str(handoff.correlation_id).strip():
            raise AgentHandoffValidationError("Invalid handoff: Missing or empty correlation_id.")

        if not handoff.task_type or not str(handoff.task_type).strip():
            raise AgentHandoffValidationError("Invalid handoff: Missing or empty task_type.")

        # 4. Evidence provenance check: Every observed fact must declare a source
        for idx, fact in enumerate(handoff.observed_facts):
            if isinstance(fact, dict):
                src = fact.get("source")
                if not src or not str(src).strip():
                    raise AgentHandoffValidationError(
                        f"Evidence Provenance Error: Observed fact at index {idx} lacks a declared source: {fact}"
                    )
            elif isinstance(fact, EvidenceItem):
                if not fact.source or not str(fact.source).strip():
                    raise AgentHandoffValidationError(
                        f"Evidence Provenance Error: Observed fact at index {idx} lacks a declared source."
                    )

        # 5. Tool permission validation: No privilege escalation
        target_known_tools = KNOWN_AGENT_ALLOWED_TOOLS.get(handoff.target_agent, set())
        for tool in handoff.allowed_tools:
            # MCP tools have an mcp__ prefix and are governed by MCP permissions
            if tool.startswith("mcp__"):
                continue
            if tool not in target_known_tools:
                raise AgentHandoffValidationError(
                    f"Privilege Escalation Violation: Handoff declares tool '{tool}' for "
                    f"'{handoff.target_agent}', but this tool is not authorized for that agent. "
                    f"Allowed tools: {sorted(list(target_known_tools))}"
                )

        # 6. Approval state integrity: Cannot be escalated by an agent
        if handoff.approval_state not in VALID_APPROVAL_STATES:
            raise AgentHandoffValidationError(
                f"Invalid approval state: '{handoff.approval_state}'. Valid states: {sorted(list(VALID_APPROVAL_STATES))}"
            )

        # If source is an agent (not supervisor/user), it cannot unilaterally assert 'approved'
        if handoff.source_agent != "seo_supervisor" and handoff.approval_state in ["approved", "auto_approved"]:
            raise AgentHandoffValidationError(
                f"Security Boundary Violation: Agent '{handoff.source_agent}' attempted to escalate "
                f"approval state to '{handoff.approval_state}'. Approval must remain with the user/supervisor."
            )
