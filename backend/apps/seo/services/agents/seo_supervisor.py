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
from .shared_memory import (
    SharedWorkingMemory,
    SharedMemoryRegistry,
    ConflictStatus,
    AgentRevisitReason,
    RevisitRecord,
)
from .task_planner import (
    AgentTask,
    TaskPlan,
    TaskStatus,
    TaskPriority,
    ReplanReason,
    DynamicTaskPlanner,
    TaskPlanRegistry,
    PlanBudgetConfig,
)
from .seo_research_agent import SEOResearchAgent
from .seo_investigation_agent import SEOInvestigationAgent
from .seo_strategy_agent import SEOStrategyAgent
from .seo_action_agent import SEOActionPlanningAgent
from .seo_verification_agent import SEOVerificationAgent

logger = logging.getLogger(__name__)


# Workflow routing definitions for specialized agent pipelines
ROUTING_WORKFLOWS: Dict[str, Dict[str, Any]] = {
    "research": {
        "agents": ["seo_researcher"],
        "description": "Gather raw Search Console, ranking, and audit evidence."
    },
    "investigate": {
        "agents": ["seo_researcher", "seo_investigator", "seo_strategist"],
        "description": "Research + root cause investigation and diagnosis."
    },
    "strategy": {
        "agents": ["seo_researcher", "seo_strategist"],
        "description": "Evaluate domain historical win rates and strategic priority."
    },
    "plan": {
        "agents": ["seo_researcher", "seo_investigator", "seo_strategist", "seo_action_planner"],
        "description": "End-to-end planning with human approval governance."
    },
    "verify": {
        "agents": ["seo_verifier"],
        "description": "Empirical live verification and GSC outcome measurement."
    },
    "full_cycle": {
        "agents": ["seo_researcher", "seo_investigator", "seo_strategist", "seo_action_planner"],
        "description": "Autonomous full-cycle SEO intelligence and action planning."
    }
}


class SEOSupervisorAgent:
    """
    Supervisor agent coordinating specialized SEO agents.
    Enforces deterministic routing, role-specific handoffs, pre-acceptance validation,
    failure isolation, and maintains shared working memory across the multi-agent team.
    """
    name = "seo_supervisor"

    def __init__(
        self,
        project: Optional[Project] = None,
        user=None,
        publisher: Optional[AgentEventPublisher] = None,
        tool_registry: Optional[ToolRegistry] = None,
        project_id: Optional[int] = None,
        user_id: Optional[int] = None
    ):
        if project is None and project_id is not None:
            project = Project.objects.get(id=project_id)
        if user is None and user_id is not None:
            from django.contrib.auth import get_user_model
            user = get_user_model().objects.get(id=user_id)

        self.project = project
        self.user = user
        self.publisher = publisher or get_event_publisher()
        self.tool_registry = tool_registry or get_tool_registry()

        # Initialize specialized sub-agents
        self._agents: Dict[str, BaseSpecializedAgent] = {
            "seo_researcher": SEOResearchAgent(project=self.project, user=self.user, publisher=self.publisher),
            "seo_investigator": SEOInvestigationAgent(project=self.project, user=self.user, publisher=self.publisher),
            "seo_strategist": SEOStrategyAgent(project=self.project, user=self.user, publisher=self.publisher),
            "seo_action_planner": SEOActionPlanningAgent(project=self.project, user=self.user, publisher=self.publisher),
            "seo_verifier": SEOVerificationAgent(project=self.project, user=self.user, publisher=self.publisher),
        }
        self.planner = DynamicTaskPlanner()

    def list_specialized_agents(self) -> List[Dict[str, Any]]:
        """List all available specialized agents, their descriptions, and permitted tools."""
        return [
            {
                "name": agent.name,
                "purpose": agent.purpose,
                "allowed_tools": list(agent.allowed_tools),
                "tools_count": len(agent.allowed_tools),
            }
            for agent in self._agents.values()
        ]

    def determine_workflow(self, task: str) -> Tuple[str, List[str]]:
        """
        Deterministically map user intent to an agent pipeline.
        Never hallucinates pipeline stages.
        """
        task_lower = (task or "").lower()

        if any(w in task_lower for w in ["verify", "verification", "check outcome", "post-change"]):
            return "verify", ROUTING_WORKFLOWS["verify"]["agents"]
        elif any(w in task_lower for w in ["strategy", "historical win rate", "prioritize opportunity"]):
            return "strategy", ROUTING_WORKFLOWS["strategy"]["agents"]
        elif any(w in task_lower for w in ["plan", "fix", "action plan", "generate actions", "propose"]):
            return "plan", ROUTING_WORKFLOWS["plan"]["agents"]
        elif any(w in task_lower for w in ["why", "investigate", "drop", "traffic loss", "cannibalization", "root cause"]):
            return "investigate", ROUTING_WORKFLOWS["investigate"]["agents"]
        elif any(w in task_lower for w in ["audit", "inspect", "crawl", "gsc", "rankings", "research"]):
            return "research", ROUTING_WORKFLOWS["research"]["agents"]
        else:
            # Default to full-cycle workflow
            return "full_cycle", ROUTING_WORKFLOWS["full_cycle"]["agents"]

    def _emit_supervisor_event(
        self,
        event_type: AgentEventType,
        payload: Dict[str, Any],
        correlation_id: str
    ) -> None:
        """Emit a lifecycle or supervisor event through the event publisher."""
        full_payload = dict(payload or {})
        full_payload["agent"] = self.name
        full_payload["correlation_id"] = correlation_id
        full_payload["project_id"] = self.project.id

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
            logger.warning(f"[{self.name}] Supervisor event publication failed ({event_type}): {exc}")

    def build_handoff_context(
        self,
        source_agent: str,
        target_agent_name: str,
        context: SharedContext,
        correlation_id: str,
        current_task_id: Optional[str] = None,
        task_objective: Optional[str] = None
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

        # Phase 5.2 Adaptive Working Memory Projection
        memory_snapshot_id = None
        relevant_memory_ids: List[str] = []
        active_uncertainties = list(context.uncertainties)
        open_conflicts: List[Dict[str, Any]] = []
        pending_questions: List[str] = []

        if getattr(context, "shared_memory", None):
            mem: SharedWorkingMemory = context.shared_memory
            memory_snapshot_id = f"snap-{mem.correlation_id[:8]}"
            all_items = list(mem._facts.values()) + list(mem._inferences.values())
            relevant_memory_ids = [m.memory_id for m in all_items[:15]]
            active_uncertainties = [u.content for u in mem._uncertainties.values()]
            open_conflicts = [c.to_dict() for c in mem._conflicts if c.resolution_status == ConflictStatus.OPEN.value]
            projected = mem.get_context_for_agent(target_agent_name)
            pending_questions = projected.get("pending_research_questions", [])

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
            ],
            memory_snapshot_id=memory_snapshot_id,
            relevant_memory_ids=relevant_memory_ids,
            active_uncertainties=active_uncertainties,
            open_conflicts=open_conflicts,
            pending_questions=pending_questions,
            current_task_id=current_task_id,
            task_objective=task_objective,
        )

    def orchestrate(
        self,
        task: str,
        target_url: Optional[str] = None,
        target_query: Optional[str] = None,
        correlation_id: Optional[str] = None,
        task_plan: Optional[TaskPlan] = None
    ) -> SharedContext:
        """
        Main orchestration entrypoint.
        Constructs SharedContext and CollaborationState, initializes SharedWorkingMemory,
        routes workflow, executes sequential structured agent handoffs with validation,
        handles bounded iterative revisits, and provides failure isolation.
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

        # Initialize Phase 5.2 Shared Working Memory
        shared_memory = SharedWorkingMemory(
            project_id=self.project.id,
            task_goal=task,
            correlation_id=corr_id
        )
        context.shared_memory = shared_memory
        SharedMemoryRegistry.get_instance().register(shared_memory)

        # Initialize Phase 5.3 Dynamic Task Plan
        if task_plan is None:
            task_plan = self.planner.decompose_goal(
                goal=task,
                project_id=self.project.id,
                correlation_id=corr_id,
                target_url=target_url,
                target_query=target_query,
                shared_memory=shared_memory
            )
        else:
            task_plan.project_id = self.project.id
            if not task_plan.correlation_id:
                task_plan.correlation_id = corr_id
        context.task_plan = task_plan
        TaskPlanRegistry.get_instance().register(task_plan)

        # Synchronize agent_pipeline with task_plan to ensure all planned agents execute
        for tid in task_plan.get_topological_sort():
            task_node = task_plan.get_task(tid)
            if task_node and task_node.responsible_agent in self._agents and task_node.responsible_agent not in agent_pipeline:
                agent_pipeline.append(task_node.responsible_agent)
                if task_node.responsible_agent not in collaboration_state.pending_agents:
                    collaboration_state.pending_agents.append(task_node.responsible_agent)

        self._emit_supervisor_event(
            AgentEventType.SEO_TASK_PLAN_CREATED,
            payload={
                "plan_id": task_plan.plan_id,
                "total_tasks": len(task_plan.tasks),
                "summary": task_plan.summarize(),
            },
            correlation_id=corr_id
        )

        for t in task_plan.tasks.values():
            self._emit_supervisor_event(
                AgentEventType.SEO_TASK_CREATED,
                payload=t.to_dict(),
                correlation_id=corr_id
            )

        self._emit_supervisor_event(
            AgentEventType.SEO_COLLABORATION_MEMORY_INITIALIZED,
            payload={
                "project_id": self.project.id,
                "task_goal": task,
                "correlation_id": corr_id
            },
            correlation_id=corr_id
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

        logger.info(
            f"[{self.name}] Routed task '{task}' to workflow '{workflow_type}' "
            f"with pipeline: {agent_pipeline} (Correlation: {corr_id})"
        )

        # 2. DAG-Driven Dynamic Task Execution Loop with Bounded Iteration
        previous_agent_name = "seo_supervisor"
        max_total_steps = min(25, max(15, len(task_plan.tasks) * 2 + 5))
        step_idx = 0

        while step_idx < max_total_steps:
            # 2a. Query ready tasks eligible for execution under strict DAG dependency satisfaction
            ready_tasks = task_plan.get_ready_tasks()
            if not ready_tasks:
                # Terminal condition: either all tasks completed, or remaining tasks are blocked/cancelled
                break

            # 2b. Select highest-priority ready task (get_ready_tasks is sorted by priority and created_at)
            task_to_execute = ready_tasks[0]
            agent_key = task_to_execute.responsible_agent
            agent = self._agents.get(agent_key)
            if not agent:
                err = f"Supervisor error: Agent '{agent_key}' not found in registry for task '{task_to_execute.task_id}'."
                context.errors.append(err)
                collaboration_state.errors.append(err)
                logger.error(err)
                task_plan.handle_task_failure(task_to_execute.task_id, err)
                break

            step_idx += 1

            # 2c. Invariant: task must transition from READY to RUNNING
            task_to_execute.transition_to(TaskStatus.RUNNING)
            self._emit_supervisor_event(
                AgentEventType.SEO_TASK_STARTED,
                payload=task_to_execute.to_dict(),
                correlation_id=corr_id
            )

            primary_task = task_to_execute
            matching_task = primary_task
            matching_tasks = [task_to_execute]

            # 2d. Build controlled, minimally-scoped handoff package for this specific task
            handoff = self.build_handoff_context(
                source_agent=previous_agent_name,
                target_agent_name=agent.name,
                context=context,
                correlation_id=corr_id,
                current_task_id=task_to_execute.task_id,
                task_objective=task_to_execute.objective
            )

            # 2e. Pre-execution handoff validation
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
                task_plan.handle_task_failure(task_to_execute.task_id, err_msg)
                break

            # 2f. Emit context projection & handoff events
            self._emit_supervisor_event(
                AgentEventType.SEO_COLLABORATION_MEMORY_PROJECTED,
                payload={
                    "target_agent": agent.name,
                    "projected_keys": list(handoff.relevant_evidence.keys()),
                    "facts_count": len(handoff.observed_facts),
                    "inferences_count": len(handoff.inferences),
                },
                correlation_id=corr_id
            )

            self._emit_supervisor_event(
                AgentEventType.SEO_AGENT_HANDOFF_STARTED,
                payload={
                    "source_agent": previous_agent_name,
                    "target_agent": agent.name,
                    "step_index": step_idx,
                    "total_steps": len(task_plan.tasks)
                },
                correlation_id=corr_id
            )

            self._emit_supervisor_event(
                AgentEventType.SEO_AGENT_HANDOFF,
                payload={
                    "source_agent": previous_agent_name,
                    "target_agent": agent.name,
                    "step_index": step_idx,
                    "task_type": handoff.task_type
                },
                correlation_id=corr_id
            )

            collaboration_state.current_agent = agent.name

            # 2g. Execute specialized agent with handoff for this specific task
            result = agent.run(context, handoff=handoff)
            previous_agent_name = agent.name

            # 2h. Failure isolation: preserve completed evidence on failure
            if result.status == "failed":
                logger.warning(
                    f"[{self.name}] Agent '{agent.name}' reported failure during step {step_idx} on task '{task_to_execute.task_id}'. "
                    f"Isolating failure and preserving {len(context.evidence)} evidence items."
                )
                blocked_ids = task_plan.handle_task_failure(task_to_execute.task_id, str(result.errors or context.errors))
                self._emit_supervisor_event(
                    AgentEventType.SEO_TASK_FAILED,
                    payload=task_to_execute.to_dict(),
                    correlation_id=corr_id
                )
                for b_id in blocked_ids:
                    b_task = task_plan.get_task(b_id)
                    if b_task:
                        self._emit_supervisor_event(
                            AgentEventType.SEO_TASK_BLOCKED,
                            payload=b_task.to_dict(),
                            correlation_id=corr_id
                        )
                if agent.name not in collaboration_state.failed_agents:
                    collaboration_state.failed_agents.append(agent.name)
                collaboration_state.status = "degraded"
                if not task_plan.get_ready_tasks():
                    context.status = "failed"
                    break
                continue

            # 2i. Success step: advance collaboration state and task status
            task_to_execute.transition_to(
                TaskStatus.COMPLETED,
                result_summary=f"{agent.name} executed step with {len(result.findings)} findings."
            )
            self._emit_supervisor_event(
                AgentEventType.SEO_TASK_COMPLETED,
                payload=task_to_execute.to_dict(),
                correlation_id=corr_id
            )

            if agent.name not in collaboration_state.completed_agents:
                collaboration_state.completed_agents.append(agent.name)
            collaboration_state.current_evidence.update(result.evidence)

            # Update pending agents based on remaining tasks in plan
            remaining_agents = {
                t.responsible_agent for t in task_plan.tasks.values()
                if t.status in [TaskStatus.PENDING.value, TaskStatus.READY.value, TaskStatus.RUNNING.value]
            }
            collaboration_state.pending_agents = [a for a in agent_pipeline if a in remaining_agents]

            # Unblock downstream dependencies and emit resolution events
            new_ready_tasks = task_plan.get_ready_tasks()
            for ready_t in new_ready_tasks:
                if task_to_execute.task_id in ready_t.dependencies:
                    self._emit_supervisor_event(
                        AgentEventType.SEO_TASK_DEPENDENCY_RESOLVED,
                        payload={"task_id": ready_t.task_id, "ready_task": ready_t.to_dict(), "resolved_by": task_to_execute.task_id},
                        correlation_id=corr_id
                    )
                self._emit_supervisor_event(
                    AgentEventType.SEO_TASK_READY,
                    payload=ready_t.to_dict(),
                    correlation_id=corr_id
                )

            handoff_dict = handoff.to_dict()
            if not any(h.get("target_agent") == agent.name and h.get("source_agent") == handoff.source_agent and h.get("current_task_id") == task_to_execute.task_id for h in collaboration_state.handoff_history):
                collaboration_state.handoff_history.append(handoff_dict)
            if not any(h.get("target_agent") == agent.name and h.get("source_agent") == handoff.source_agent and h.get("current_task_id") == task_to_execute.task_id for h in context.handoff_history):
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

            # Emit memory updated event
            self._emit_supervisor_event(
                AgentEventType.SEO_COLLABORATION_MEMORY_UPDATED,
                payload={
                    "agent": agent.name,
                    "new_facts": len(result.observed_facts),
                    "new_inferences": len(result.inferences),
                    "new_uncertainties": len(result.uncertainties),
                    "memory_summary": shared_memory.summarize()
                },
                correlation_id=corr_id
            )

            # 2j. Conflict Detection & Adaptive Replanning
            new_conflicts = shared_memory.detect_conflicts()
            for conflict in new_conflicts:
                self._emit_supervisor_event(
                    AgentEventType.SEO_COLLABORATION_MEMORY_CONFLICT_DETECTED,
                    payload=conflict.to_dict(),
                    correlation_id=corr_id
                )

            # Adaptive Replanning on Conflict
            if new_conflicts and task_plan.replans_count < task_plan.budget_config.max_replans:
                c = new_conflicts[0]
                task_plan = self.planner.replan(
                    plan=task_plan,
                    reason=ReplanReason.CONFLICT_DETECTED,
                    trigger_info={"topic": c.topic, "responsible_agents": c.responsible_agents},
                    shared_memory=shared_memory
                )
                context.task_plan = task_plan
                self._emit_supervisor_event(
                    AgentEventType.SEO_TASK_REPLANNED,
                    payload={"reason": ReplanReason.CONFLICT_DETECTED.value, "summary": task_plan.summarize()},
                    correlation_id=corr_id
                )

            # If agent provided updated findings resolving an earlier conflict, resolve it
            for c in shared_memory._conflicts:
                if c.resolution_status == ConflictStatus.OPEN.value and agent.name in c.responsible_agents:
                    prev_revisits = sum(1 for r in shared_memory._revisits if r.agent == agent.name)
                    if prev_revisits > 0:
                        shared_memory.resolve_conflict(
                            conflict_id=c.conflict_id,
                            resolved_by=agent.name,
                            resolution_notes=f"Resolved by {agent.name} with clarifying empirical evidence."
                        )
                        self._emit_supervisor_event(
                            AgentEventType.SEO_COLLABORATION_MEMORY_CONFLICT_RESOLVED,
                            payload=c.to_dict(),
                            correlation_id=corr_id
                        )

            # 2k. Bounded Iterative Collaboration Check (Phase 5.2 backward compatibility)
            for c in shared_memory._conflicts:
                if c.resolution_status == ConflictStatus.OPEN.value:
                    for prev_agent_name in c.responsible_agents:
                        if prev_agent_name != agent.name and prev_agent_name in self._agents:
                            prev_revisits = sum(1 for r in shared_memory._revisits if r.agent == prev_agent_name)
                            if prev_revisits < 2 and len(shared_memory._revisits) < 4:
                                shared_memory.record_revisit(
                                    agent=prev_agent_name,
                                    reason=AgentRevisitReason.UNRESOLVED_CONFLICT.value,
                                    step_index=step_idx
                                )
                                self._emit_supervisor_event(
                                    AgentEventType.SEO_COLLABORATION_AGENT_REVISIT,
                                    payload={
                                        "agent": prev_agent_name,
                                        "reason": AgentRevisitReason.UNRESOLVED_CONFLICT.value,
                                        "conflict_id": c.conflict_id,
                                        "revisit_count": prev_revisits + 1
                                    },
                                    correlation_id=corr_id
                                )
                                break
                    break

        # Finalize Collaboration, Memory & Task Plan State
        if shared_memory.budget_exceeded_events > 0:
            self._emit_supervisor_event(
                AgentEventType.SEO_COLLABORATION_CONTEXT_BOUNDED,
                payload={"budget_exceeded_events": shared_memory.budget_exceeded_events},
                correlation_id=corr_id
            )

        if task_plan.replans_count >= task_plan.budget_config.max_replans:
            self._emit_supervisor_event(
                AgentEventType.SEO_TASK_PLAN_LIMIT_REACHED,
                payload={"plan_id": task_plan.plan_id, "summary": task_plan.summarize()},
                correlation_id=corr_id
            )

        collaboration_state.revisit_history = [r.to_dict() for r in shared_memory._revisits]
        collaboration_state.open_conflicts_count = len([c for c in shared_memory._conflicts if c.resolution_status == ConflictStatus.OPEN.value])
        collaboration_state.memory_summary = shared_memory.summarize()
        collaboration_state.task_plan_summary = task_plan.summarize()

        if context.status != "failed":
            context.status = "completed"
            collaboration_state.status = "completed"
            self._emit_supervisor_event(
                AgentEventType.SEO_AGENT_COLLABORATION_COMPLETED,
                payload={
                    "completed_agents": collaboration_state.completed_agents,
                    "total_handoffs": len(context.handoff_history),
                    "memory_summary": collaboration_state.memory_summary,
                    "task_plan_summary": collaboration_state.task_plan_summary,
                },
                correlation_id=corr_id
            )

        return context


# Alias for backward compatibility and concise import
SEOSupervisor = SEOSupervisorAgent
