"""
DoxaRank Specialized SEO Agents — Supervisor & Orchestrator (Phase 4.7)

Coordinates specialized SEO agents through deterministic routing, explicit handoffs,
and controlled shared context passing. The supervisor controls the workflow but never
directly performs website mutations.
"""

import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Type, Tuple
from apps.projects.models import Project
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher
)
from apps.seo.services.tool_registry import ToolRegistry, get_tool_registry

from .base_agent import BaseSpecializedAgent, SharedContext, AgentResult
from .seo_research_agent import SEOResearchAgent
from .seo_investigation_agent import SEOInvestigationAgent
from .seo_strategy_agent import SEOStrategyAgent
from .seo_action_agent import SEOActionPlanningAgent
from .seo_verification_agent import SEOVerificationAgent

logger = logging.getLogger(__name__)


# Standard deterministic routing table
ROUTING_WORKFLOWS: Dict[str, List[str]] = {
    "research": ["seo_researcher"],
    "investigate": ["seo_researcher", "seo_investigator", "seo_strategist"],
    "strategy": ["seo_researcher", "seo_strategist"],
    "plan": ["seo_researcher", "seo_investigator", "seo_strategist", "seo_action_planner"],
    "verify": ["seo_verifier"],
    "full_cycle": ["seo_researcher", "seo_investigator", "seo_strategist", "seo_action_planner"],
}


class SEOSupervisorAgent:
    """
    Supervisor coordinating the specialized agent team.
    Determines workflow routing, executes explicit agent handoffs, enforces
    tenant boundaries, and manages the shared context lifecycle.
    """

    name: str = "seo_supervisor"

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

        # Instantiate specialized agent registry
        self._agents: Dict[str, BaseSpecializedAgent] = {
            "seo_researcher": SEOResearchAgent(project=self.project, user=self.user, registry=self.registry, publisher=self.publisher),
            "seo_investigator": SEOInvestigationAgent(project=self.project, user=self.user, registry=self.registry, publisher=self.publisher),
            "seo_strategist": SEOStrategyAgent(project=self.project, user=self.user, registry=self.registry, publisher=self.publisher),
            "seo_action_planner": SEOActionPlanningAgent(project=self.project, user=self.user, registry=self.registry, publisher=self.publisher),
            "seo_verifier": SEOVerificationAgent(project=self.project, user=self.user, registry=self.registry, publisher=self.publisher),
        }

    def list_specialized_agents(self) -> List[Dict[str, Any]]:
        """Return descriptors and tool allowlists for all specialized agents."""
        return [
            {
                "name": agent.name,
                "purpose": agent.purpose,
                "allowed_tools": agent.allowed_tools,
                "tools_count": len(agent.allowed_tools)
            }
            for agent in self._agents.values()
        ]

    def _emit_supervisor_event(
        self,
        event_type: AgentEventType,
        payload: Dict[str, Any],
        correlation_id: str
    ) -> Optional[AgentEvent]:
        """Publish supervisor lifecycle telemetry."""
        payload["supervisor"] = self.name
        payload["project_id"] = self.project.id
        payload["correlation_id"] = correlation_id

        event = AgentEvent(
            event_type=event_type,
            run_id=None,
            project_id=self.project.id,
            sequence_number=1,
            payload=payload
        )
        try:
            self.publisher.publish(event)
        except Exception as exc:
            logger.warning(f"[{self.name}] Supervisor event publication failed: {exc}")
        return event

    def determine_workflow(self, task: str) -> Tuple[str, List[str]]:
        """
        Deterministic task routing engine.
        Maps task type or user goal to an ordered pipeline of specialized agents.
        """
        task_lower = (task or "").lower()

        if any(term in task_lower for term in ["strategy", "prioritize", "adaptive", "historical performance", "domain win rate"]):
            return "strategy", ROUTING_WORKFLOWS["strategy"]

        if any(term in task_lower for term in ["plan", "propose", "action plan", "create action"]):
            return "plan", ROUTING_WORKFLOWS["plan"]

        if any(term in task_lower for term in ["verify", "verification", "measure", "did this action work", "validate"]):
            return "verify", ROUTING_WORKFLOWS["verify"]

        if any(term in task_lower for term in ["investigate", "drop", "decline", "traffic loss", "ranking drop", "why did"]):
            return "investigate", ROUTING_WORKFLOWS["investigate"]

        if any(term in task_lower for term in ["research", "audit", "collect evidence"]):
            return "research", ROUTING_WORKFLOWS["research"]

        # Default to full autonomous cycle
        return "full_cycle", ROUTING_WORKFLOWS["full_cycle"]

    def orchestrate(
        self,
        task: str,
        target_url: Optional[str] = None,
        target_query: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> SharedContext:
        """
        Main orchestration entrypoint.
        Constructs SharedContext, routes workflow, executes sequential agent handoffs,
        and aggregates structured results.
        """
        # 1. Routing
        workflow_type, agent_pipeline = self.determine_workflow(task)
        corr_id = correlation_id or str(uuid.uuid4())

        context = SharedContext(
            project_id=self.project.id,
            project_name=self.project.name,
            website_url=self.project.website_url,
            user_id=getattr(self.user, 'id', None),
            task_type=workflow_type,
            task_goal=task,
            target_url=target_url,
            target_query=target_query,
            correlation_id=corr_id,
            status="running"
        )

        self._emit_supervisor_event(
            AgentEventType.SEO_AGENT_ROUTING_STARTED,
            payload={
                "task": task,
                "target_url": target_url,
                "target_query": target_query
            },
            correlation_id=corr_id
        )

        self._emit_supervisor_event(
            AgentEventType.SEO_AGENT_ROUTING_COMPLETED,
            payload={
                "selected_workflow": workflow_type,
                "agent_pipeline": agent_pipeline,
                "pipeline_length": len(agent_pipeline)
            },
            correlation_id=corr_id
        )

        logger.info(
            f"[{self.name}] Routed task '{task}' to workflow '{workflow_type}' "
            f"with pipeline: {agent_pipeline} (Correlation: {corr_id})"
        )

        # 2. Sequential Agent Handoff Pipeline
        previous_agent_name = "supervisor"
        for step_idx, agent_key in enumerate(agent_pipeline):
            agent = self._agents.get(agent_key)
            if not agent:
                err = f"Supervisor error: Agent '{agent_key}' not found in registry."
                context.errors.append(err)
                logger.error(err)
                break

            # Emit explicit handoff event
            self._emit_supervisor_event(
                AgentEventType.SEO_AGENT_HANDOFF,
                payload={
                    "source_agent": previous_agent_name,
                    "target_agent": agent.name,
                    "step_index": step_idx,
                    "total_steps": len(agent_pipeline)
                },
                correlation_id=corr_id
            )

            # Execute specialized agent
            result = agent.run(context)
            previous_agent_name = agent.name

            # Safe error handling: stop pipeline on fatal agent failure
            if result.status == "failed":
                logger.warning(
                    f"[{self.name}] Agent '{agent.name}' reported failure during step {step_idx}. "
                    f"Halting pipeline gracefully."
                )
                context.status = "failed"
                break

        if context.status != "failed":
            context.status = "completed"

        return context
