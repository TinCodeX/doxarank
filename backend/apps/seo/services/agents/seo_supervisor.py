"""
DoxaRank Specialized SEO Agents — Supervisor & Orchestrator (Phase 4.7)

Coordinates specialized SEO agents through deterministic routing, explicit handoffs,
and controlled shared context passing. The supervisor controls the workflow but never
directly performs website mutations.
"""

import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Type, Tuple, Union

from apps.projects.models import Project
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher
)
from apps.seo.services.tool_registry import ToolRegistry, get_tool_registry
from .base_agent import BaseSpecializedAgent, SharedContext, AgentResult

from .agent_handoff import (
    AgentHandoffContext,
    CollaborationState,
    AgentHandoffValidator,
    AgentHandoffValidationError,
    KNOWN_AGENTS
)
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
        event_type: Union[AgentEventType, str],
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

    def build_handoff_context(
        self,
        source_agent: str,
        target_agent_name: str,
        context: SharedContext,
        correlation_id: str
    ) -> AgentHandoffContext:
        """
        Build a controlled, minimally-scoped context package for the target agent.
        Does NOT blindly copy the entire previous context.
        """
        target_agent = self._agents.get(target_agent_name)
        target_tools = list(target_agent.allowed_tools) if target_agent else []

        scoped_evidence: Dict[str, Any] = {}
        if target_agent_name == "seo_researcher":
            if context.target_url:
                scoped_evidence["target_url"] = context.target_url
        elif target_agent_name == "seo_investigator":
            for k in ["gsc_performance", "top_queries", "audit_summary", "mcp_url_status"]:
                if k in context.evidence:
                    scoped_evidence[k] = context.evidence[k]
        elif target_agent_name == "seo_strategist":
            scoped_evidence["investigation_findings"] = list(context.investigation_findings)
            if "historical_strategy" in context.evidence:
                scoped_evidence["historical_strategy"] = context.evidence["historical_strategy"]
        elif target_agent_name == "seo_action_planner":
            scoped_evidence["investigation_findings"] = list(context.investigation_findings)
            scoped_evidence["strategy_signals"] = dict(context.strategy_signals)
        elif target_agent_name == "seo_verifier":
            if context.created_plan_id:
                scoped_evidence["created_plan_id"] = context.created_plan_id
            scoped_evidence["action_proposals"] = list(context.action_proposals)

        approval_state = "none"
        risk_info: Dict[str, Any] = {}
        if target_agent_name == "seo_action_planner":
            approval_state = "pending_human_approval"
            risk_info = {"requires_human_approval": True, "risk_boundary": "strict"}

        return AgentHandoffContext(
            project_id=self.project.id,
            source_agent=source_agent,
            target_agent=target_agent_name,
            user_goal=context.task_goal,
            task_type=context.task_type,
            correlation_id=correlation_id,
            relevant_evidence=scoped_evidence,
            observed_facts=list(context.observed_facts),
            inferences=list(context.inferences),
            uncertainties=list(context.uncertainties),
            assumptions=list(context.assumptions),
            allowed_tools=target_tools,
            approval_state=approval_state,
            risk_information=risk_info,
            previous_agent_steps=[
                {"agent": item["agent"], "status": item["status"], "confidence": item.get("confidence", 0.0)}
                for item in context.agent_results_history
            ]
        )

    def orchestrate(
        self,
        task: str,
        target_url: Optional[str] = None,
        target_query: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> SharedContext:
        """
        Main orchestration entrypoint.
        Constructs SharedContext and CollaborationState, routes workflow, executes
        sequential structured agent handoffs with validation, and provides failure isolation.
        """
        # 1. Routing
        workflow_type, agent_pipeline = self.determine_workflow(task)
        corr_id = correlation_id or str(uuid.uuid4())

        collaboration_state = CollaborationState(
            project_id=self.project.id,
            task_goal=task,
            task_type=workflow_type,
            correlation_id=corr_id,
            status="running",
            pending_agents=list(agent_pipeline)
        )

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
            collaboration_state=collaboration_state,
            status="running"
        )

        self._emit_supervisor_event(
            AgentEventType.SEO_AGENT_COLLABORATION_STARTED,
            payload={
                "task": task,
                "workflow": workflow_type,
                "agent_pipeline": agent_pipeline,
                "pipeline_length": len(agent_pipeline)
            },
            correlation_id=corr_id
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

        # 2. Sequential Structured Agent Handoff Pipeline
        previous_agent_name = "seo_supervisor"
        for step_idx, agent_key in enumerate(agent_pipeline):
            agent = self._agents.get(agent_key)
            if not agent:
                err = f"Supervisor error: Agent '{agent_key}' not found in registry."
                context.errors.append(err)
                collaboration_state.errors.append(err)
                logger.error(err)
                break

            # 2a. Build controlled, minimally-scoped handoff package
            handoff = self.build_handoff_context(
                source_agent=previous_agent_name,
                target_agent_name=agent.name,
                context=context,
                correlation_id=corr_id
            )

            # 2b. Pre-execution handoff validation
            try:
                AgentHandoffValidator.validate(handoff, expected_project_id=self.project.id)
            except AgentHandoffValidationError as val_err:
                err_msg = f"Handoff validation failed for '{agent.name}': {val_err}"
                logger.error(f"[{self.name}] {err_msg}")
                self._emit_supervisor_event(
                    AgentEventType.SEO_AGENT_HANDOFF_REJECTED,
                    payload={
                        "source_agent": previous_agent_name,
                        "target_agent": agent.name,
                        "error": str(val_err)
                    },
                    correlation_id=corr_id
                )
                context.errors.append(err_msg)
                collaboration_state.errors.append(err_msg)
                collaboration_state.status = "failed"
                context.status = "failed"
                break

            # 2c. Emit explicit handoff events
            self._emit_supervisor_event(
                AgentEventType.SEO_AGENT_HANDOFF_STARTED,
                payload={
                    "source_agent": previous_agent_name,
                    "target_agent": agent.name,
                    "step_index": step_idx,
                    "total_steps": len(agent_pipeline)
                },
                correlation_id=corr_id
            )

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

            collaboration_state.current_agent = agent.name

            # 2d. Execute specialized agent with handoff
            result = agent.run(context, handoff=handoff)
            previous_agent_name = agent.name

            # 2e. Failure isolation: preserve completed evidence on failure
            if result.status == "failed":
                logger.warning(
                    f"[{self.name}] Agent '{agent.name}' reported failure during step {step_idx}. "
                    f"Isolating failure and preserving {len(context.evidence)} evidence items."
                )
                if agent.name in collaboration_state.pending_agents:
                    collaboration_state.pending_agents.remove(agent.name)
                collaboration_state.failed_agents.append(agent.name)
                collaboration_state.status = "degraded"
                context.status = "failed"

                self._emit_supervisor_event(
                    AgentEventType.SEO_AGENT_COLLABORATION_FAILED,
                    payload={
                        "failed_agent": agent.name,
                        "step_index": step_idx,
                        "preserved_evidence_keys": list(context.evidence.keys()),
                        "error": result.errors[0] if result.errors else "Unknown agent failure"
                    },
                    correlation_id=corr_id
                )
                break

            # Success step: advance collaboration state
            if agent.name in collaboration_state.pending_agents:
                collaboration_state.pending_agents.remove(agent.name)
            collaboration_state.completed_agents.append(agent.name)
            collaboration_state.current_evidence.update(result.evidence)
            handoff_dict = handoff.to_dict()
            if not any(h.get("target_agent") == agent.name and h.get("source_agent") == handoff.source_agent for h in collaboration_state.handoff_history):
                collaboration_state.handoff_history.append(handoff_dict)
            if not any(h.get("target_agent") == agent.name and h.get("source_agent") == handoff.source_agent for h in context.handoff_history):
                context.handoff_history.append(handoff_dict)

            self._emit_supervisor_event(
                AgentEventType.SEO_AGENT_HANDOFF_COMPLETED,
                payload={
                    "source_agent": handoff.source_agent,
                    "target_agent": agent.name,
                    "step_index": step_idx,
                    "confidence": result.confidence
                },
                correlation_id=corr_id
            )

        if context.status != "failed":
            context.status = "completed"
            collaboration_state.status = "completed"
            self._emit_supervisor_event(
                AgentEventType.SEO_AGENT_COLLABORATION_COMPLETED,
                payload={
                    "completed_agents": collaboration_state.completed_agents,
                    "total_handoffs": len(context.handoff_history)
                },
                correlation_id=corr_id
            )

        return context
