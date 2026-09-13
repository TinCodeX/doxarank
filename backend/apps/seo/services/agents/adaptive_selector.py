"""
DoxaRank Adaptive Agent Coordination & Dynamic Agent Selection (Milestone 5.5).

Provides deterministic, explainable, workload-aware, and safety-constrained dynamic
selection of specialized SEO agents for ready AgentTasks. Enforces hard safety
boundaries (capabilities, ToolRegistry permissions, MCP authorization, HITL governance,
and tenant isolation) while evaluating soft signals (workload, task-type fit, past success)
with bounded fallback reassignment.
"""

import copy
import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from django.utils import timezone

from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher, sanitize_event_payload
)
from apps.seo.services.tool_registry import ToolRegistry, get_tool_registry
from .agent_handoff import KNOWN_AGENTS, KNOWN_AGENT_ALLOWED_TOOLS
from .task_planner import AgentTask, TaskStatus

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """Normalize text by converting hyphens, underscores, and punctuation to spaces."""
    if not text:
        return ""
    cleaned = re.sub(r"[-_]+", " ", text.lower())
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def extract_word_tokens(text: str) -> Set[str]:
    """Extract individual lowercased word tokens."""
    return set(re.findall(r"\b\w+\b", text.lower()))


def matches_token_or_phrase(pattern: str, norm_text: str, tokens: Set[str]) -> bool:
    """Match pattern against normalized text or tokens using phrase containment, token matching, or stem matching."""
    norm_pattern = normalize_text(pattern)
    if not norm_pattern:
        return False
    if " " in norm_pattern:
        return f" {norm_pattern} " in f" {norm_text} "
    return norm_pattern in tokens or any(t.startswith(norm_pattern) for t in tokens if len(norm_pattern) >= 4)


@dataclass
class AgentCapabilityProfile:
    """
    Structured representation of a specialized SEO agent's capabilities,
    supported scopes, tool authorizations, and safety governance boundaries.
    """
    agent_name: str
    role: str
    capabilities: Set[str] = field(default_factory=set)
    supported_task_types: Set[str] = field(default_factory=set)
    supported_domains: Set[str] = field(default_factory=set)
    allowed_tools: Set[str] = field(default_factory=set)
    forbidden_tools: Set[str] = field(default_factory=set)
    max_risk_level: str = "low"  # "low" | "medium" | "high"
    requires_hitl: bool = False
    confidence_baseline: float = 0.85

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "role": self.role,
            "capabilities": sorted(list(self.capabilities)),
            "supported_task_types": sorted(list(self.supported_task_types)),
            "supported_domains": sorted(list(self.supported_domains)),
            "allowed_tools": sorted(list(self.allowed_tools)),
            "forbidden_tools": sorted(list(self.forbidden_tools)),
            "max_risk_level": self.max_risk_level,
            "requires_hitl": self.requires_hitl,
            "confidence_baseline": self.confidence_baseline,
        }


# Canonical DoxaRank Agent Capability Profiles
CANONICAL_CAPABILITY_PROFILES: Dict[str, AgentCapabilityProfile] = {
    "seo_researcher": AgentCapabilityProfile(
        agent_name="seo_researcher",
        role="SEO Research & Evidence Specialist",
        capabilities={
            "keyword_research",
            "serp_research",
            "competitor_research",
            "search_intent_analysis",
            "empirical_data_collection",
            "audit_data_collection",
            "performance_analysis",
            "ranking_analysis",
        },
        supported_task_types={
            "research",
            "audit",
            "crawl",
            "benchmark",
            "serp_analysis",
            "keyword_analysis",
            "data_collection",
            "rank_analysis",
            "performance_audit",
            "keyword_research",
            "keyword research",
            "serp",
            "ranking_analysis",
            "ranking analysis",
        },
        supported_domains={"technical_seo", "content_seo", "serp", "analytics", "general"},
        allowed_tools=KNOWN_AGENT_ALLOWED_TOOLS.get("seo_researcher", set()),
        forbidden_tools={"plan_seo_actions", "propose_seo_action", "verify_seo_action", "verify_action_plan"},
        max_risk_level="low",
        requires_hitl=False,
        confidence_baseline=0.88,
    ),
    "seo_investigator": AgentCapabilityProfile(
        agent_name="seo_investigator",
        role="SEO Diagnostic & Root-Cause Investigator",
        capabilities={
            "root_cause_analysis",
            "technical_diagnosis",
            "evidence_correlation",
            "opportunity_investigation",
            "anomaly_detection",
            "diagnostic_correlation",
            "technical_audit",
            "cannibalization_diagnosis",
        },
        supported_task_types={
            "investigation",
            "investigate",
            "diagnosis",
            "diagnose",
            "diagnostic",
            "diagnostics",
            "root_cause",
            "root cause",
            "anomaly",
            "anomalies",
            "anomaly_detection",
            "audit",
            "correlation",
            "technical_audit",
            "technical audit",
        },
        supported_domains={"technical_seo", "analytics", "traffic_loss", "cannibalization", "general"},
        allowed_tools=KNOWN_AGENT_ALLOWED_TOOLS.get("seo_investigator", set()),
        forbidden_tools={"plan_seo_actions", "propose_seo_action", "verify_seo_action", "verify_action_plan"},
        max_risk_level="medium",
        requires_hitl=False,
        confidence_baseline=0.90,
    ),
    "seo_strategist": AgentCapabilityProfile(
        agent_name="seo_strategist",
        role="SEO Strategy & Prioritization Architect",
        capabilities={
            "seo_strategy",
            "prioritization",
            "recommendation_generation",
            "historical_learning",
            "opportunity_scoring",
            "strategic_planning",
            "portfolio_prioritization",
        },
        supported_task_types={
            "strategy",
            "strategic",
            "prioritization",
            "prioritize",
            "recommendation",
            "planning_strategy",
            "opportunity_ranking",
            "strategic_planning",
            "strategic planning",
        },
        supported_domains={"strategy", "portfolio", "growth", "general"},
        allowed_tools=KNOWN_AGENT_ALLOWED_TOOLS.get("seo_strategist", set()),
        forbidden_tools={"plan_seo_actions", "propose_seo_action", "verify_seo_action", "verify_action_plan"},
        max_risk_level="medium",
        requires_hitl=False,
        confidence_baseline=0.87,
    ),
    "seo_action_planner": AgentCapabilityProfile(
        agent_name="seo_action_planner",
        role="SEO Action & Remediation Planner",
        capabilities={
            "action_planning",
            "approved_mutation_execution",
            "action_synthesis",
            "remediation_design",
            "proposal_generation",
            "code_fix_design",
        },
        supported_task_types={
            "action_planning",
            "action planning",
            "action_plan",
            "action plan",
            "remediation",
            "remediate",
            "action_proposal",
            "action proposal",
            "plan_synthesis",
            "plan synthesis",
            "action_generation",
            "code fix",
            "mutation_planning",
        },
        supported_domains={"technical_seo", "content_seo", "on_page", "action_execution", "general"},
        allowed_tools=KNOWN_AGENT_ALLOWED_TOOLS.get("seo_action_planner", set()),
        forbidden_tools={"verify_seo_action", "verify_action_plan"},
        max_risk_level="high",
        requires_hitl=True,
        confidence_baseline=0.85,
    ),
    "seo_verifier": AgentCapabilityProfile(
        agent_name="seo_verifier",
        role="SEO Verification & Outcome Lift Agent",
        capabilities={
            "outcome_verification",
            "post_action_validation",
            "lift_measurement",
            "impact_verification",
            "outcome_tracking",
            "regression_verification",
        },
        supported_task_types={
            "verification",
            "verify",
            "validation",
            "validate",
            "outcome",
            "outcome_verification",
            "outcome verification",
            "post_action",
            "post action",
            "post_action_check",
            "lift",
            "impact_measurement",
            "regression_verification",
            "regression",
        },
        supported_domains={"verification", "post_deployment", "outcome", "general"},
        allowed_tools=KNOWN_AGENT_ALLOWED_TOOLS.get("seo_verifier", set()),
        forbidden_tools={"plan_seo_actions", "propose_seo_action"},
        max_risk_level="medium",
        requires_hitl=False,
        confidence_baseline=0.89,
    ),
    "seo_supervisor": AgentCapabilityProfile(
        agent_name="seo_supervisor",
        role="SEO Orchestration & Coordination Supervisor",
        capabilities={
            "agent_coordination",
            "workflow_routing",
            "task_orchestration",
        },
        supported_task_types={"coordination", "supervision"},
        supported_domains={"general"},
        allowed_tools=set(),
        forbidden_tools=set(),
        max_risk_level="low",
        requires_hitl=False,
        confidence_baseline=0.95,
    ),
}


class WorkloadTracker:
    """
    Thread-safe tracker for active running tasks across specialized agents.
    Enables workload-aware routing decisions without distributed scheduler overhead.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._active_tasks: Dict[str, int] = {}

    def get_workload(self, agent_name: str) -> int:
        with self._lock:
            return self._active_tasks.get(agent_name, 0)

    def increment(self, agent_name: str) -> None:
        with self._lock:
            self._active_tasks[agent_name] = self._active_tasks.get(agent_name, 0) + 1

    def decrement(self, agent_name: str) -> None:
        with self._lock:
            val = self._active_tasks.get(agent_name, 0)
            if val > 0:
                self._active_tasks[agent_name] = val - 1

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._active_tasks)

    def set_workloads(self, workloads: Dict[str, int]) -> None:
        with self._lock:
            self._active_tasks = dict(workloads)


@dataclass
class CandidateScoreBreakdown:
    """Detailed score decomposition for an evaluated candidate agent."""
    agent_name: str
    total_score: float
    capability_score: float
    task_type_score: float
    role_score: float
    tool_score: float
    workload_score: float
    historical_score: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_score": round(self.total_score, 4),
            "capability_score": round(self.capability_score, 4),
            "task_type_score": round(self.task_type_score, 4),
            "role_score": round(self.role_score, 4),
            "tool_score": round(self.tool_score, 4),
            "workload_score": round(self.workload_score, 4),
            "historical_score": round(self.historical_score, 4),
            "reasons": list(self.reasons),
        }


@dataclass
class RejectedCandidate:
    """Record of an agent eliminated by a hard safety/permission constraint."""
    agent_name: str
    reason: str
    hard_constraint: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent_name,
            "reason": self.reason,
            "hard_constraint": self.hard_constraint,
        }


@dataclass
class RoutingDecision:
    """
    Deterministic, explainable routing decision produced by AdaptiveAgentSelector.
    Records why an agent was chosen and why other candidates were rejected or ranked lower.
    """
    task_id: str
    selected_agent: str
    score: float
    confidence: float
    reasons: List[str] = field(default_factory=list)
    rejected_candidates: List[Dict[str, str]] = field(default_factory=list)
    candidate_scores: Dict[str, float] = field(default_factory=dict)
    score_breakdowns: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    ranked_candidates: List[str] = field(default_factory=list)
    fallback_attempt: int = 0
    fallback_reason: Optional[str] = None
    is_low_confidence: bool = False
    requires_human_review: bool = False
    project_id: int = 0
    timestamp: str = field(default_factory=lambda: timezone.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "selected_agent": self.selected_agent,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "reasons": list(self.reasons),
            "rejected_candidates": list(self.rejected_candidates),
            "candidate_scores": {k: round(v, 4) for k, v in self.candidate_scores.items()},
            "score_breakdowns": self.score_breakdowns,
            "ranked_candidates": list(self.ranked_candidates),
            "fallback_attempt": self.fallback_attempt,
            "fallback_reason": self.fallback_reason,
            "is_low_confidence": self.is_low_confidence,
            "requires_human_review": self.requires_human_review,
            "project_id": self.project_id,
            "timestamp": self.timestamp,
        }


class AdaptiveAgentSelector:
    """
    Adaptive Agent Selection & Coordination Engine (Milestone 5.5).

    Evaluates ready AgentTasks against specialized agent capability profiles,
    strictly enforces hard safety constraints, scores eligible candidates with
    workload awareness, calculates evidence-derived routing confidence, supports
    bounded fallback, and emits auditable telemetry.
    """

    # Deterministic scoring weights (sum = 1.00)
    WEIGHT_CAPABILITY = 0.35
    WEIGHT_TASK_TYPE = 0.25
    WEIGHT_ROLE_MATCH = 0.15
    WEIGHT_TOOL_COMPAT = 0.15
    WEIGHT_WORKLOAD = 0.10

    def __init__(
        self,
        project_id: int,
        tool_registry: Optional[ToolRegistry] = None,
        publisher: Optional[AgentEventPublisher] = None,
        workload_tracker: Optional[WorkloadTracker] = None,
        min_confidence_threshold: float = 0.50,
        max_concurrency: int = 3
    ):
        self.project_id = project_id
        self.tool_registry = tool_registry or get_tool_registry()
        self.publisher = publisher or get_event_publisher()
        self.workload_tracker = workload_tracker or WorkloadTracker()
        self.min_confidence_threshold = min_confidence_threshold
        self.max_concurrency = max(1, max_concurrency)
        self.profiles: Dict[str, AgentCapabilityProfile] = dict(CANONICAL_CAPABILITY_PROFILES)

    def register_profile(self, profile: AgentCapabilityProfile) -> None:
        """Register or override an agent capability profile."""
        self.profiles[profile.agent_name] = profile

    def get_profile(self, agent_name: str) -> Optional[AgentCapabilityProfile]:
        return self.profiles.get(agent_name)

    def _infer_task_requirements(self, task: AgentTask) -> Dict[str, Any]:
        """
        Extract explicit and domain-inferred capability and tool requirements from a task.
        Explicit requirements from metadata act as non-negotiable hard constraints.
        Domain-inferred capabilities act as soft scoring signals.
        """
        meta = task.metadata or {}
        req_caps = set(meta.get("required_capabilities", []))
        req_tools = set(meta.get("required_tools", []))
        is_mutating = bool(meta.get("is_mutating", False))
        risk_level = meta.get("risk_level", "low")

        norm_obj = normalize_text(task.objective)
        norm_desc = normalize_text(task.description)
        norm_text = f"{norm_obj} {norm_desc}".strip()
        obj_tokens = extract_word_tokens(norm_obj)
        text_tokens = extract_word_tokens(norm_text)
        text = norm_text

        # Domain capability inference for soft scoring match
        inferred_caps = set()

        # 1. Investigation / Diagnostic Anomaly Inference
        is_investigation = any(
            matches_token_or_phrase(p, norm_text, text_tokens)
            for p in ["root cause", "diagnos", "traffic drop", "cannibaliz", "investigat", "anomaly", "anomalies", "why"]
        )
        if is_investigation:
            inferred_caps.add("root_cause_analysis")
            inferred_caps.add("technical_diagnosis")

        # 2. Crawl & Empirical Data Collection Inference
        is_crawl_in_obj = "crawl" in obj_tokens or any(matches_token_or_phrase(p, norm_obj, obj_tokens) for p in ["site crawl", "crawl inspection"])
        if is_crawl_in_obj or ("crawl" in text_tokens and not is_investigation):
            inferred_caps.add("audit_data_collection")
            inferred_caps.add("empirical_data_collection")

        # 3. Technical Audit / Site Audit Inference
        is_tech_audit = any(matches_token_or_phrase(p, norm_obj, obj_tokens) for p in ["technical audit", "site audit"])
        if is_tech_audit:
            inferred_caps.add("technical_audit")
            inferred_caps.add("technical_diagnosis")

        # 3. Keyword / Ranking Analysis Inference
        is_ranking_keyword = (
            any(matches_token_or_phrase(p, norm_obj, obj_tokens) for p in ["keyword", "serp", "competitor", "search intent", "ranking analysis", "rank analysis"]) or
            ("ranking" in obj_tokens and not any(w in obj_tokens for w in ["anomaly", "anomalies", "drop", "loss", "investigate", "investigation", "root cause"]))
        )
        if is_ranking_keyword:
            inferred_caps.add("ranking_analysis")
            inferred_caps.add("keyword_research")

        # 4. Strategy Inference
        if any(matches_token_or_phrase(p, norm_text, text_tokens) for p in ["strategy", "prioritiz", "portfolio", "recommendation", "opportunities", "win rate"]):
            inferred_caps.add("seo_strategy")
            inferred_caps.add("prioritization")

        # 5. Verification vs Action Planning
        is_verification = any(
            matches_token_or_phrase(p, norm_text, text_tokens)
            for p in ["verif", "verify", "validate", "validation", "lift", "outcome check", "post action", "outcome verification"]
        )
        if is_verification:
            inferred_caps.add("outcome_verification")

        # Action planning is only inferred if NOT in a verification / post-action context
        if any(matches_token_or_phrase(p, norm_text, text_tokens) for p in ["plan action", "action plan", "synthesize action plan", "action proposals", "propose fix", "draft remediation", "execute remediation", "code fix", "tag fix"]) and not is_verification:
            inferred_caps.add("action_planning")
            is_mutating = True
            risk_level = "high"

        return {
            "required_capabilities": req_caps,
            "inferred_capabilities": inferred_caps,
            "required_tools": req_tools,
            "is_mutating": is_mutating,
            "is_verification": is_verification,
            "risk_level": risk_level,
            "text": text,
            "norm_text": norm_text,
            "norm_obj": norm_obj,
            "text_tokens": text_tokens,
            "obj_tokens": obj_tokens,
        }

    def evaluate_hard_constraints(
        self,
        profile: AgentCapabilityProfile,
        task: AgentTask,
        task_reqs: Dict[str, Any],
        context_project_id: Optional[int] = None
    ) -> Tuple[bool, Optional[RejectedCandidate]]:
        """
        Apply non-negotiable hard safety constraints.
        Any failure immediately eliminates the candidate agent.
        """
        # 1. Tenant Isolation Constraint
        target_pid = context_project_id or self.project_id
        task_pid = task.metadata.get("project_id") if task.metadata else None
        if task_pid is not None and task_pid != target_pid:
            return False, RejectedCandidate(
                agent_name=profile.agent_name,
                reason=f"Tenant isolation mismatch: task project {task_pid} != context {target_pid}",
                hard_constraint="tenant_isolation"
            )

        # 2. Required Capabilities Constraint
        req_caps = task_reqs["required_capabilities"]
        if req_caps:
            missing_caps = [c for c in req_caps if c not in profile.capabilities]
            if missing_caps:
                return False, RejectedCandidate(
                    agent_name=profile.agent_name,
                    reason=f"Missing required capabilities: {', '.join(missing_caps)}",
                    hard_constraint="missing_required_capability"
                )

        # 3. Tool Permissions & Allowlist Constraint
        req_tools = task_reqs["required_tools"]
        if req_tools:
            unauthorized_tools = []
            for t in req_tools:
                if t not in profile.allowed_tools:
                    # Check MCP permission policy if external MCP tool
                    if t.startswith("mcp__"):
                        from apps.seo.services.mcp.permissions import MCPPermissionPolicy
                        if not MCPPermissionPolicy.is_agent_authorized(profile.agent_name, t):
                            unauthorized_tools.append(t)
                    else:
                        unauthorized_tools.append(t)
            if unauthorized_tools:
                return False, RejectedCandidate(
                    agent_name=profile.agent_name,
                    reason=f"Lacks required tool permissions: {', '.join(unauthorized_tools)}",
                    hard_constraint="tool_permission_denied"
                )

        # 4. Forbidden Tools Constraint
        if req_tools:
            forbidden_overlap = [t for t in req_tools if t in profile.forbidden_tools]
            if forbidden_overlap:
                return False, RejectedCandidate(
                    agent_name=profile.agent_name,
                    reason=f"Required tools are explicitly forbidden: {', '.join(forbidden_overlap)}",
                    hard_constraint="forbidden_tool_violation"
                )

        # 5. Risk Level Compatibility
        task_risk = task_reqs["risk_level"]
        risk_hierarchy = {"low": 1, "medium": 2, "high": 3}
        agent_max_risk = risk_hierarchy.get(profile.max_risk_level, 1)
        needed_risk = risk_hierarchy.get(task_risk, 1)
        if needed_risk > agent_max_risk:
            return False, RejectedCandidate(
                agent_name=profile.agent_name,
                reason=f"Agent max risk level '{profile.max_risk_level}' cannot perform task risk '{task_risk}'",
                hard_constraint="risk_level_exceeded"
            )

        # 6. Human-in-the-Loop (HITL) Safety Boundary
        # Agent selection CANNOT authorize mutations.
        # If the task attempts a mutation and the agent does not enforce HITL requirements, reject.
        if task_reqs["is_mutating"] and not profile.requires_hitl:
            return False, RejectedCandidate(
                agent_name=profile.agent_name,
                reason="Mutating task requires strict HITL governance profile",
                hard_constraint="hitl_governance_required"
            )

        return True, None

    def compute_candidate_score(
        self,
        profile: AgentCapabilityProfile,
        task: AgentTask,
        task_reqs: Dict[str, Any],
        historical_success_rate: float = 0.0
    ) -> CandidateScoreBreakdown:
        """
        Compute explicit, deterministic, and explainable multi-factor candidate score.
        """
        reasons = []
        norm_text = task_reqs.get("norm_text", normalize_text(task_reqs.get("text", "")))
        norm_obj = task_reqs.get("norm_obj", normalize_text(task.objective))
        text_tokens = task_reqs.get("text_tokens", extract_word_tokens(norm_text))
        obj_tokens = task_reqs.get("obj_tokens", extract_word_tokens(norm_obj))

        # 1. Capability Match Score (0.0 to 1.0)
        matched_caps = [
            c for c in profile.capabilities
            if c in task_reqs["required_capabilities"] or c in task_reqs.get("inferred_capabilities", set()) or normalize_text(c) in norm_text
        ]
        # In addition, check token/phrase semantic overlap with agent capabilities
        if not matched_caps:
            is_verification_task = bool(task_reqs.get("is_verification", False))
            for cap in profile.capabilities:
                # Guard: Do not match action planning capabilities on verification tasks
                if is_verification_task and cap in ["action_planning", "action_synthesis", "remediation_design", "code_fix_design"]:
                    continue

                norm_cap = normalize_text(cap)
                cap_words = norm_cap.split()
                if len(cap_words) > 1:
                    if norm_cap in norm_text or all(w in text_tokens for w in cap_words if len(w) > 3):
                        matched_caps.append(cap)
                else:
                    if norm_cap in text_tokens:
                        matched_caps.append(cap)

        target_cap_count = max(1, len(task_reqs["required_capabilities"]) or len(task_reqs.get("inferred_capabilities", set())) or 2)
        cap_score = min(1.0, len(matched_caps) / target_cap_count)
        if matched_caps:
            reasons.append(f"capability_match: {', '.join(sorted(list(set(matched_caps))))}")

        # 2. Task Type / Objective Match Score (0.0 to 1.0)
        # Check primary objective match first, then secondary description match
        matched_obj_types = [tt for tt in profile.supported_task_types if matches_token_or_phrase(tt, norm_obj, obj_tokens)]
        matched_text_types = [tt for tt in profile.supported_task_types if matches_token_or_phrase(tt, norm_text, text_tokens)]

        if matched_obj_types:
            task_type_score = 1.0
            reasons.append(f"task_type_match: {matched_obj_types[0]}")
        elif matched_text_types:
            task_type_score = 0.70  # secondary description match
            reasons.append(f"task_type_match_secondary: {matched_text_types[0]}")
        else:
            task_type_score = 0.35  # baseline compatibility

        # 3. Role Suitability / Baseline Planned Assignment Score (0.0 to 1.0)
        role_score = 0.5
        if task.responsible_agent == profile.agent_name:
            role_score = 1.0
            reasons.append(f"baseline_assigned_role: {profile.agent_name}")

        # 4. Tool Compatibility Score (0.0 to 1.0)
        req_tools = task_reqs["required_tools"]
        if req_tools:
            allowed_count = sum(1 for t in req_tools if t in profile.allowed_tools)
            tool_score = allowed_count / len(req_tools)
            reasons.append(f"tool_compatibility: {allowed_count}/{len(req_tools)} tools available")
        else:
            tool_score = 1.0
            reasons.append("required_tools_available")

        # 5. Workload Factor (0.0 to 1.0)
        current_workload = self.workload_tracker.get_workload(profile.agent_name)
        workload_score = max(0.0, 1.0 - (current_workload / self.max_concurrency))
        if current_workload > 0:
            reasons.append(f"workload_penalty: {current_workload} active tasks")
        else:
            reasons.append("workload_idle")

        # 6. Soft Historical Performance (bounded bonus)
        hist_score = min(0.05, max(0.0, historical_success_rate * 0.05))

        total_score = (
            (self.WEIGHT_CAPABILITY * cap_score) +
            (self.WEIGHT_TASK_TYPE * task_type_score) +
            (self.WEIGHT_ROLE_MATCH * role_score) +
            (self.WEIGHT_TOOL_COMPAT * tool_score) +
            (self.WEIGHT_WORKLOAD * workload_score) +
            hist_score
        )
        total_score = min(1.0, max(0.0, total_score))

        return CandidateScoreBreakdown(
            agent_name=profile.agent_name,
            total_score=total_score,
            capability_score=cap_score,
            task_type_score=task_type_score,
            role_score=role_score,
            tool_score=tool_score,
            workload_score=workload_score,
            historical_score=hist_score,
            reasons=reasons
        )

    def _calculate_confidence(
        self,
        best_candidate: CandidateScoreBreakdown,
        second_candidate: Optional[CandidateScoreBreakdown]
    ) -> float:
        """
        Calculate routing confidence derived from actual selection evidence.
        Score margin between 1st and 2nd candidate acts as preference clarity indicator.
        """
        margin = 0.50
        if second_candidate is not None:
            margin = max(0.0, best_candidate.total_score - second_candidate.total_score)

        # Baseline agent profile confidence
        profile = self.get_profile(best_candidate.agent_name)
        base_conf = profile.confidence_baseline if profile else 0.85

        conf = (
            (best_candidate.capability_score * 0.40) +
            (best_candidate.task_type_score * 0.30) +
            (best_candidate.tool_score * 0.20) +
            (min(1.0, margin * 2.0) * 0.10)
        )
        # Blend with profile baseline
        final_conf = round(0.7 * conf + 0.3 * base_conf, 3)
        return min(1.0, max(0.1, final_conf))

    def _emit_telemetry(
        self,
        event_type: AgentEventType,
        payload: Dict[str, Any],
        correlation_id: str
    ) -> None:
        """Emit sanitized routing lifecycle event to event publisher."""
        full_payload = sanitize_event_payload(dict(payload or {}))
        full_payload["project_id"] = self.project_id
        full_payload["correlation_id"] = correlation_id
        full_payload["timestamp"] = timezone.now().isoformat()

        event = AgentEvent(
            event_type=event_type,
            run_id=None,
            project_id=self.project_id,
            sequence_number=1,
            payload=full_payload
        )
        try:
            self.publisher.publish(event)
        except Exception as exc:
            logger.warning(f"[AdaptiveAgentSelector] Telemetry publication failed ({event_type}): {exc}")

    def select_agent(
        self,
        task: AgentTask,
        available_agents: Optional[List[str]] = None,
        context_project_id: Optional[int] = None,
        correlation_id: str = "",
        historical_stats: Optional[Dict[str, float]] = None
    ) -> RoutingDecision:
        """
        Select the best eligible specialized agent for a ready AgentTask.
        Applies hard constraints, scores candidates deterministically, breaks ties,
        and returns an explainable RoutingDecision.
        """
        corr_id = correlation_id or task.correlation_id or str(uuid.uuid4())
        task_reqs = self._infer_task_requirements(task)

        # Candidate universe: exclude supervisor from worker candidates unless explicitly specified
        candidate_names = available_agents or [a for a in KNOWN_AGENTS if a != "seo_supervisor"]

        self._emit_telemetry(
            AgentEventType.SEO_AGENT_SELECTION_STARTED,
            payload={
                "task_id": task.task_id,
                "objective": task.objective,
                "candidates_count": len(candidate_names),
                "candidates": candidate_names,
            },
            correlation_id=corr_id
        )

        eligible_breakdowns: List[CandidateScoreBreakdown] = []
        rejected_candidates: List[RejectedCandidate] = []
        historical_stats = historical_stats or {}

        # Evaluate each candidate
        for agent_name in candidate_names:
            profile = self.get_profile(agent_name)
            if not profile:
                rej = RejectedCandidate(
                    agent_name=agent_name,
                    reason=f"Agent '{agent_name}' has no registered capability profile.",
                    hard_constraint="unregistered_agent"
                )
                rejected_candidates.append(rej)
                self._emit_telemetry(
                    AgentEventType.SEO_AGENT_CANDIDATE_REJECTED,
                    payload={"task_id": task.task_id, **rej.to_dict()},
                    correlation_id=corr_id
                )
                continue

            # Check hard constraints
            eligible, rejection = self.evaluate_hard_constraints(
                profile=profile,
                task=task,
                task_reqs=task_reqs,
                context_project_id=context_project_id
            )
            if not eligible and rejection:
                rejected_candidates.append(rejection)
                self._emit_telemetry(
                    AgentEventType.SEO_AGENT_CANDIDATE_REJECTED,
                    payload={"task_id": task.task_id, **rejection.to_dict()},
                    correlation_id=corr_id
                )
                continue

            # Compute soft score for eligible candidate
            hist_rate = historical_stats.get(agent_name, 0.0)
            score_breakdown = self.compute_candidate_score(
                profile=profile,
                task=task,
                task_reqs=task_reqs,
                historical_success_rate=hist_rate
            )
            eligible_breakdowns.append(score_breakdown)

            self._emit_telemetry(
                AgentEventType.SEO_AGENT_CANDIDATE_EVALUATED,
                payload={
                    "task_id": task.task_id,
                    "agent": agent_name,
                    "score": score_breakdown.total_score,
                    "breakdown": score_breakdown.to_dict()
                },
                correlation_id=corr_id
            )

        # If no eligible candidate found
        if not eligible_breakdowns:
            self._emit_telemetry(
                AgentEventType.SEO_AGENT_SELECTION_FAILED,
                payload={
                    "task_id": task.task_id,
                    "reason": "All candidates eliminated by hard constraints",
                    "rejected_candidates": [r.to_dict() for r in rejected_candidates]
                },
                correlation_id=corr_id
            )
            # Safe fallback default (never fall back to seo_supervisor)
            default_agent = (
                task.responsible_agent
                if task.responsible_agent and task.responsible_agent in self.profiles and task.responsible_agent != "seo_supervisor"
                else "seo_investigator"
            )
            return RoutingDecision(
                task_id=task.task_id,
                selected_agent=default_agent,
                score=0.0,
                confidence=0.0,
                reasons=["No candidate satisfied hard constraints; routing failed."],
                rejected_candidates=[r.to_dict() for r in rejected_candidates],
                candidate_scores={},
                score_breakdowns={},
                ranked_candidates=[],
                is_low_confidence=True,
                requires_human_review=True,
                project_id=self.project_id
            )

        # Deterministic Ranking & Tie-Breaking:
        # 1. Total score (descending)
        # 2. Active workload (ascending: lower workload preferred)
        # 3. Capability score (descending)
        # 4. Agent name (ascending lexicographical: deterministic zero-randomness guarantee)
        def _sort_key(item: CandidateScoreBreakdown):
            workload = self.workload_tracker.get_workload(item.agent_name)
            return (-item.total_score, workload, -item.capability_score, item.agent_name)

        ranked = sorted(eligible_breakdowns, key=_sort_key)
        best = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None

        confidence = self._calculate_confidence(best, second)
        is_low_conf = confidence < self.min_confidence_threshold
        requires_review = is_low_conf and task_reqs["risk_level"] in ["medium", "high"]

        decision = RoutingDecision(
            task_id=task.task_id,
            selected_agent=best.agent_name,
            score=best.total_score,
            confidence=confidence,
            reasons=list(best.reasons),
            rejected_candidates=[r.to_dict() for r in rejected_candidates],
            candidate_scores={b.agent_name: b.total_score for b in ranked},
            score_breakdowns={b.agent_name: b.to_dict() for b in ranked},
            ranked_candidates=[b.agent_name for b in ranked],
            is_low_confidence=is_low_conf,
            requires_human_review=requires_review,
            project_id=self.project_id
        )

        self._emit_telemetry(
            AgentEventType.SEO_AGENT_SELECTED,
            payload={
                "task_id": task.task_id,
                "selected_agent": best.agent_name,
                "score": best.total_score,
                "confidence": confidence,
                "reasons": best.reasons,
                "is_low_confidence": is_low_conf
            },
            correlation_id=corr_id
        )

        return decision

    def select_fallback(
        self,
        task: AgentTask,
        previous_decision: RoutingDecision,
        failed_agent: str,
        failure_reason: str,
        context_project_id: Optional[int] = None,
        correlation_id: str = "",
        max_attempts: int = 2
    ) -> Optional[RoutingDecision]:
        """
        Select next-ranked eligible agent after failure, bounded by max_attempts.
        Guarantees safety constraints are not bypassed during fallback.
        """
        corr_id = correlation_id or task.correlation_id or str(uuid.uuid4())
        next_attempt = previous_decision.fallback_attempt + 1

        if next_attempt > max_attempts:
            logger.warning(
                f"[AdaptiveAgentSelector] Max fallback attempts ({max_attempts}) exhausted "
                f"for task '{task.task_id}'."
            )
            self._emit_telemetry(
                AgentEventType.SEO_AGENT_SELECTION_FAILED,
                payload={
                    "task_id": task.task_id,
                    "reason": f"Fallback attempts exhausted ({next_attempt} > {max_attempts})",
                    "original_agent": previous_decision.selected_agent,
                    "failed_agent": failed_agent,
                    "failure_reason": failure_reason
                },
                correlation_id=corr_id
            )
            return None

        # Exclude failed agent and find next candidate in ranked list
        tried_agents = {failed_agent, previous_decision.selected_agent}
        remaining_ranked = [
            a for a in previous_decision.ranked_candidates
            if a not in tried_agents
        ]

        if not remaining_ranked:
            # Fallback to dynamically querying remaining eligible profiles
            available = [a for a in self.profiles.keys() if a not in tried_agents and a != "seo_supervisor"]
            if available:
                dyn_dec = self.select_agent(
                    task=task,
                    available_agents=available,
                    context_project_id=context_project_id,
                    correlation_id=corr_id
                )
                if dyn_dec and dyn_dec.score > 0.0 and dyn_dec.selected_agent not in tried_agents:
                    remaining_ranked = [dyn_dec.selected_agent]

        if not remaining_ranked:
            logger.warning(f"[AdaptiveAgentSelector] No alternative eligible agents for task '{task.task_id}'.")
            return None

        fallback_agent_name = remaining_ranked[0]
        fallback_profile = self.get_profile(fallback_agent_name)
        if not fallback_profile:
            return None

        # Fallback candidate must have genuine capability or task-type match for the task
        cand_breakdown = previous_decision.score_breakdowns.get(fallback_agent_name, {})
        has_cap = cand_breakdown.get("capability_score", 0.0) > 0.0
        has_type = cand_breakdown.get("task_type_score", 0.0) >= 1.0
        if not (has_cap or has_type):
            logger.info(
                f"[AdaptiveAgentSelector] Fallback candidate '{fallback_agent_name}' lacks capability or task type relevance for task '{task.task_id}'."
            )
            return None

        # Re-verify hard constraints for safety
        task_reqs = self._infer_task_requirements(task)

        # Domain Invariant: Fallback candidate must possess the primary specialized capability required by task
        primary_inferred = task_reqs.get("inferred_capabilities", set())
        if "root_cause_analysis" in primary_inferred and "root_cause_analysis" not in fallback_profile.capabilities:
            logger.info(
                f"[AdaptiveAgentSelector] Fallback agent '{fallback_agent_name}' lacks root_cause_analysis for task '{task.task_id}'."
            )
            return None
        if "seo_strategy" in primary_inferred and "seo_strategy" not in fallback_profile.capabilities:
            logger.info(
                f"[AdaptiveAgentSelector] Fallback agent '{fallback_agent_name}' lacks seo_strategy for task '{task.task_id}'."
            )
            return None
        if "action_planning" in primary_inferred and "action_planning" not in fallback_profile.capabilities:
            logger.info(
                f"[AdaptiveAgentSelector] Fallback agent '{fallback_agent_name}' lacks action_planning for task '{task.task_id}'."
            )
            return None
        if "outcome_verification" in primary_inferred and "outcome_verification" not in fallback_profile.capabilities:
            logger.info(
                f"[AdaptiveAgentSelector] Fallback agent '{fallback_agent_name}' lacks outcome_verification for task '{task.task_id}'."
            )
            return None

        eligible, rej = self.evaluate_hard_constraints(
            profile=fallback_profile,
            task=task,
            task_reqs=task_reqs,
            context_project_id=context_project_id
        )
        if not eligible:
            logger.warning(f"[AdaptiveAgentSelector] Fallback agent '{fallback_agent_name}' rejected: {rej}")
            return None

        fallback_score = previous_decision.candidate_scores.get(fallback_agent_name, 0.70)
        fallback_reasons = list(previous_decision.score_breakdowns.get(fallback_agent_name, {}).get("reasons", []))
        fallback_reasons.append(f"fallback_from: {failed_agent} (attempt {next_attempt})")

        fallback_decision = RoutingDecision(
            task_id=task.task_id,
            selected_agent=fallback_agent_name,
            score=fallback_score,
            confidence=max(0.3, previous_decision.confidence * 0.85),
            reasons=fallback_reasons,
            rejected_candidates=list(previous_decision.rejected_candidates),
            candidate_scores=dict(previous_decision.candidate_scores),
            score_breakdowns=dict(previous_decision.score_breakdowns),
            ranked_candidates=remaining_ranked,
            fallback_attempt=next_attempt,
            fallback_reason=failure_reason,
            is_low_confidence=previous_decision.is_low_confidence,
            requires_human_review=previous_decision.requires_human_review,
            project_id=self.project_id
        )

        self._emit_telemetry(
            AgentEventType.SEO_AGENT_FALLBACK,
            payload={
                "task_id": task.task_id,
                "original_agent": previous_decision.selected_agent,
                "failed_agent": failed_agent,
                "fallback_agent": fallback_agent_name,
                "attempt": next_attempt,
                "reason": failure_reason
            },
            correlation_id=corr_id
        )

        return fallback_decision
