"""
DoxaRank Specialized SEO Agents — Base Contracts, Shared Context & Guardrails (Phase 4.7)

Defines the universal contracts, typed result containers, shared context management,
and tool authorization boundaries for all specialized SEO agents.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Union
from abc import ABC, abstractmethod

from apps.projects.models import Project
from apps.seo.services.tool_registry import ToolRegistry, get_tool_registry
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher
)

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """
    Standardized, provider-neutral result contract for all specialized SEO agents.
    Every specialized agent must return this exact contract.
    """
    agent: str
    status: str  # "completed" | "failed" | "skipped" | "waiting_for_approval"
    confidence: float  # 0.0 to 1.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    findings: List[str] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    next_step: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence,
            "findings": self.findings,
            "recommendations": self.recommendations,
            "next_step": self.next_step,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata
        }


@dataclass
class SharedContext:
    """
    Controlled shared context passed between specialized agents during an orchestrated run.
    Maintains strict tenant isolation and explicit, auditable data propagation.
    """
    project_id: int
    project_name: str
    website_url: str
    user_id: Optional[int] = None
    task_type: str = "general"
    task_goal: str = ""
    target_url: Optional[str] = None
    target_query: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Domain Data Accumulation
    evidence: Dict[str, Any] = field(default_factory=dict)
    investigation_findings: List[Dict[str, Any]] = field(default_factory=list)
    strategy_signals: Dict[str, Any] = field(default_factory=dict)
    action_proposals: List[Dict[str, Any]] = field(default_factory=list)
    created_plan_id: Optional[int] = None
    verification_results: Dict[str, Any] = field(default_factory=dict)
    outcome_measurements: Dict[str, Any] = field(default_factory=dict)

    # Telemetry and Execution State
    agent_results_history: List[Dict[str, Any]] = field(default_factory=list)
    current_agent: Optional[str] = None
    status: str = "initialized"  # "initialized" | "running" | "completed" | "failed"
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "website_url": self.website_url,
            "user_id": self.user_id,
            "task_type": self.task_type,
            "task_goal": self.task_goal,
            "target_url": self.target_url,
            "target_query": self.target_query,
            "correlation_id": self.correlation_id,
            "evidence": self.evidence,
            "investigation_findings": self.investigation_findings,
            "strategy_signals": self.strategy_signals,
            "action_proposals": self.action_proposals,
            "created_plan_id": self.created_plan_id,
            "verification_results": self.verification_results,
            "outcome_measurements": self.outcome_measurements,
            "agent_results_history": self.agent_results_history,
            "current_agent": self.current_agent,
            "status": self.status,
            "errors": self.errors
        }


class BaseSpecializedAgent(ABC):
    """
    Abstract base class for all specialized SEO agents.
    Enforces:
    1. Explicit agent identification and bounded responsibility.
    2. Strict tool allowlist gating (PermissionError if agent calls unauthorized tool).
    3. Structured event emission across lifecycle boundaries.
    4. Deterministic error isolation and timing measurement.
    """

    name: str = "base_agent"
    purpose: str = "Base specialized agent"
    allowed_tools: List[str] = []

    def __init__(
        self,
        project: Project,
        user: Optional[Any] = None,
        registry: Optional[ToolRegistry] = None,
        publisher: Optional[AgentEventPublisher] = None
    ):
        self.project = project
        self.user = user
        self.registry = registry or get_tool_registry()
        self.publisher = publisher or get_event_publisher()

    def execute_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a registered tool subject to this agent's strict permission allowlist.
        Raises PermissionError if the tool is not explicitly permitted for this agent.
        """
        if tool_name not in self.allowed_tools:
            err_msg = f"Agent '{self.name}' is NOT authorized to execute tool '{tool_name}'. Allowed tools: {self.allowed_tools}"
            logger.error(f"[ToolPermissionDenied] {err_msg}")
            raise PermissionError(err_msg)

        logger.info(f"[{self.name}] Executing authorized tool '{tool_name}' for project #{self.project.id}")
        return self.registry.execute(tool_name=tool_name, project=self.project, arguments=arguments or {})

    def _emit_event(
        self,
        event_type: Union[AgentEventType, str],
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> Optional[AgentEvent]:
        """Publish structured agent telemetry event."""
        full_payload = payload or {}
        full_payload["agent"] = self.name
        full_payload["project_id"] = self.project.id
        if correlation_id:
            full_payload["correlation_id"] = correlation_id

        event = AgentEvent(
            event_type=event_type,
            run_id=None,
            project_id=self.project.id,
            sequence_number=1,
            payload=full_payload
        )
        try:
            self.publisher.publish(event)
        except Exception as exc:
            logger.warning(f"[{self.name}] Event publication failed ({event_type}): {exc}")
        return event

    def run(self, context: SharedContext) -> AgentResult:
        """
        Public template method executing the specialized agent with lifecycle events,
        timing, and error handling.
        """
        start_time = time.time()
        context.current_agent = self.name

        self._emit_event(
            AgentEventType.SEO_AGENT_STARTED,
            payload={
                "task_type": context.task_type,
                "task_goal": context.task_goal,
                "target_url": context.target_url,
                "target_query": context.target_query
            },
            correlation_id=context.correlation_id
        )

        try:
            result = self._execute(context)
            duration_ms = int((time.time() - start_time) * 1000)
            result.duration_ms = duration_ms

            context.agent_results_history.append(result.to_dict())

            self._emit_event(
                AgentEventType.SEO_AGENT_COMPLETED,
                payload={
                    "status": result.status,
                    "confidence": result.confidence,
                    "findings_count": len(result.findings),
                    "recommendations_count": len(result.recommendations),
                    "next_step": result.next_step,
                    "duration_ms": duration_ms
                },
                correlation_id=context.correlation_id
            )
            return result

        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            error_str = f"Agent '{self.name}' failed: {str(exc)}"
            logger.exception(f"[{self.name}] {error_str}")

            context.errors.append(error_str)
            failed_result = AgentResult(
                agent=self.name,
                status="failed",
                confidence=0.0,
                errors=[error_str],
                duration_ms=duration_ms
            )
            context.agent_results_history.append(failed_result.to_dict())

            self._emit_event(
                AgentEventType.SEO_AGENT_FAILED,
                payload={
                    "error": str(exc),
                    "duration_ms": duration_ms
                },
                correlation_id=context.correlation_id
            )
            return failed_result

    @abstractmethod
    def _execute(self, context: SharedContext) -> AgentResult:
        """Domain-specific execution logic implemented by specialized agents."""
        raise NotImplementedError
