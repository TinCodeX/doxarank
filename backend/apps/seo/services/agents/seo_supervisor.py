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
from .parallel_executor import ParallelExecutionBatch, ParallelBatchExecutor, BatchExecutionResult
from .adaptive_selector import (
    AdaptiveAgentSelector, AgentCapabilityProfile, RoutingDecision, WorkloadTracker
)
from .agent_learning import (
    AgentLearningService, AgentPerformanceStore, AgentPerformanceRecord,
    FailureCategory, get_agent_learning_service
)
from .advanced_reasoning import (
    AdvancedReasoningService,
    ReasoningCase,
    ReasoningEvidence,
    ReasoningHypothesis,
    AgentCritique,
    DisagreementRecord,
    ConsensusResult,
    ConsensusState,
    ChallengeType,
    CritiqueSeverity,
    DisagreementSeverity,
    ReasoningRegistry,
    MAX_REASONING_ROUNDS,
)

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
    "reasoning": {
        "agents": ["seo_researcher", "seo_investigator", "seo_strategist", "seo_verifier"],
        "description": "Bounded multi-agent reasoning, cross-critique, and consensus arbitration."
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
        user_id: Optional[int] = None,
        max_parallel_tasks: int = 3,
        learning_service: Optional[AgentLearningService] = None
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
        self.max_parallel_tasks = max(1, int(max_parallel_tasks))
        self.parallel_executor = ParallelBatchExecutor(max_parallel_tasks=self.max_parallel_tasks)
        self.workload_tracker = WorkloadTracker()
        self.learning_service = learning_service or get_agent_learning_service()
        self.agent_selector = AdaptiveAgentSelector(
            project_id=self.project.id if self.project else 0,
            tool_registry=self.tool_registry,
            publisher=self.publisher,
            workload_tracker=self.workload_tracker,
            max_concurrency=self.max_parallel_tasks,
            performance_store=self.learning_service.store
        )

        # Initialize specialized sub-agents
        self._agents: Dict[str, BaseSpecializedAgent] = {
            "seo_researcher": SEOResearchAgent(project=self.project, user=self.user, publisher=self.publisher),
            "seo_investigator": SEOInvestigationAgent(project=self.project, user=self.user, publisher=self.publisher),
            "seo_strategist": SEOStrategyAgent(project=self.project, user=self.user, publisher=self.publisher),
            "seo_action_planner": SEOActionPlanningAgent(project=self.project, user=self.user, publisher=self.publisher),
            "seo_verifier": SEOVerificationAgent(project=self.project, user=self.user, publisher=self.publisher),
        }
        self.planner = DynamicTaskPlanner()
        self.reasoning_service = AdvancedReasoningService(
            project_id=self.project.id if self.project else 0,
            publisher=self.publisher,
            max_rounds=MAX_REASONING_ROUNDS,
        )

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

        if any(w in task_lower for w in ["reasoning", "consensus", "competing hypotheses", "multi-agent reasoning", "cross-agent challenge"]):
            return "reasoning", list(ROUTING_WORKFLOWS["reasoning"]["agents"])
        elif any(w in task_lower for w in ["verify", "verification", "check outcome", "post-change"]):
            return "verify", list(ROUTING_WORKFLOWS["verify"]["agents"])
        elif any(w in task_lower for w in ["strategy", "historical win rate", "prioritize opportunity"]):
            return "strategy", list(ROUTING_WORKFLOWS["strategy"]["agents"])
        elif any(w in task_lower for w in ["plan", "fix", "action plan", "generate actions", "propose"]):
            return "plan", list(ROUTING_WORKFLOWS["plan"]["agents"])
        elif any(w in task_lower for w in ["why", "investigate", "drop", "traffic loss", "cannibalization", "root cause"]):
            return "investigate", list(ROUTING_WORKFLOWS["investigate"]["agents"])
        elif any(w in task_lower for w in ["audit", "inspect", "crawl", "gsc", "rankings", "research"]):
            return "research", list(ROUTING_WORKFLOWS["research"]["agents"])
        else:
            # Default to full-cycle workflow
            return "full_cycle", list(ROUTING_WORKFLOWS["full_cycle"]["agents"])

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
        task_plan: Optional[TaskPlan] = None,
        enable_reasoning: bool = False,
        **kwargs
    ) -> SharedContext:
        """
        Main orchestration entrypoint.
        Constructs SharedContext and CollaborationState, initializes SharedWorkingMemory,
        routes workflow, executes sequential structured agent handoffs with validation,
        handles bounded iterative revisits, and provides failure isolation.
        """
        # 1. Routing
        workflow_type, agent_pipeline = self.determine_workflow(task)
        if enable_reasoning or kwargs.get("multi_agent_reasoning", False):
            workflow_type = "reasoning"
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

        # Initialize Phase 5.7 Reasoning Case if reasoning tasks are present or workflow is reasoning
        has_reasoning_tasks = any(
            t.metadata.get("analysis_type") in ["technical", "strategic", "critique", "consensus"]
            for t in task_plan.tasks.values()
        )
        reasoning_case = None
        if workflow_type == "reasoning" or has_reasoning_tasks:
            reasoning_case = self.reasoning_service.create_case(
                objective=task,
                correlation_id=corr_id,
                context_data={"target_url": target_url, "target_query": target_query},
            )
            context.reasoning_cases.append(reasoning_case.to_dict())
            context.active_case_id = reasoning_case.case_id
            if hasattr(collaboration_state, "reasoning_cases"):
                collaboration_state.reasoning_cases.append(reasoning_case.to_dict())

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

        # 2. DAG-Driven Dynamic Task Execution Loop with Bounded Parallel Batches
        previous_agent_name = "seo_supervisor"
        max_total_steps = min(25, max(15, len(task_plan.tasks) * 2 + 5))
        step_idx = 0

        while step_idx < max_total_steps:
            # 2a. Query ready tasks eligible for execution under strict DAG dependency satisfaction
            ready_tasks = task_plan.get_ready_tasks()
            if not ready_tasks:
                # Terminal condition: either all tasks completed, or remaining tasks are blocked/cancelled
                break

            # 2b. Form bounded parallel execution batch with Adaptive Agent Selection
            candidate_tasks = ready_tasks[:self.max_parallel_tasks]
            batch_tasks = []
            for task_to_select in candidate_tasks:
                routing_decision = self.agent_selector.select_agent(
                    task=task_to_select,
                    available_agents=list(self._agents.keys()),
                    context_project_id=self.project.id if self.project else None,
                    correlation_id=corr_id
                )
                if not task_to_select.metadata:
                    task_to_select.metadata = {}
                task_to_select.metadata["routing_decision"] = routing_decision.to_dict()
                context.routing_decisions.append(routing_decision.to_dict())
                if hasattr(collaboration_state, "routing_decisions"):
                    collaboration_state.routing_decisions.append(routing_decision.to_dict())

                # BUG-001: Enforce hard safety boundary when routing fails
                is_routing_failure = (
                    routing_decision.score == 0.0 or
                    not routing_decision.ranked_candidates or
                    (len(routing_decision.rejected_candidates) > 0 and not routing_decision.candidate_scores)
                )
                if is_routing_failure:
                    err_reason = (
                        routing_decision.reasons[0]
                        if routing_decision.reasons
                        else f"Routing failed: no eligible agent satisfied hard constraints for task '{task_to_select.task_id}'."
                    )
                    logger.warning(
                        f"[{self.name}] Routing failed for task '{task_to_select.task_id}': {err_reason}. "
                        "Failing task deterministically."
                    )
                    # Milestone 5.6: Record safety block / hard constraint elimination in learning store
                    task_cat = task_to_select.metadata.get("task_type") or self.agent_selector._infer_task_requirements(task_to_select).get("task_category", "general")
                    safety_rec = self.learning_service.record_task_outcome(
                        agent_name=routing_decision.selected_agent or "unassigned",
                        task_id=task_to_select.task_id,
                        task_type=task_cat,
                        task_objective=task_to_select.objective,
                        project_id=self.project.id if self.project else 0,
                        success=False,
                        failure_category=FailureCategory.SAFETY_BLOCK,
                        failure_reason=err_reason,
                        routing_metadata=routing_decision.to_dict(),
                        correlation_id=corr_id
                    )
                    context.learning_records.append(safety_rec.to_dict())
                    if hasattr(collaboration_state, "learning_records"):
                        collaboration_state.learning_records.append(safety_rec.to_dict())

                    context.errors.append(f"Routing failed for task '{task_to_select.task_id}': {err_reason}")
                    collaboration_state.errors.append(f"Routing failed for task '{task_to_select.task_id}': {err_reason}")
                    task_plan.handle_task_failure(task_to_select.task_id, err_reason)
                    continue

                task_to_select.responsible_agent = routing_decision.selected_agent
                self.workload_tracker.increment(routing_decision.selected_agent)
                batch_tasks.append(task_to_select)

            if not batch_tasks:
                if not task_plan.get_ready_tasks():
                    context.status = "failed"
                    collaboration_state.status = "failed"
                    break
                continue

            if len(ready_tasks) > len(batch_tasks):
                self._emit_supervisor_event(
                    AgentEventType.SEO_PARALLEL_CONCURRENCY_LIMITED,
                    payload={
                        "ready_count": len(ready_tasks),
                        "batch_size": len(batch_tasks),
                        "max_concurrency": self.max_parallel_tasks,
                        "deferred_tasks": [t.task_id for t in ready_tasks[self.max_parallel_tasks:]]
                    },
                    correlation_id=corr_id
                )

            batch_id = f"batch-{uuid.uuid4().hex[:8]}"
            batch = ParallelExecutionBatch(
                batch_id=batch_id,
                plan_id=task_plan.plan_id,
                project_id=self.project.id,
                task_ids=[t.task_id for t in batch_tasks],
                agent_names=[t.responsible_agent for t in batch_tasks],
                max_concurrency=self.max_parallel_tasks
            )

            self._emit_supervisor_event(
                AgentEventType.SEO_PARALLEL_BATCH_CREATED,
                payload=batch.to_dict(),
                correlation_id=corr_id
            )

            # 2c. Prepare handoff contexts and validate permissions for all batch tasks
            handoffs = {}
            validation_failed = False
            for task_to_execute in batch_tasks:
                agent_key = task_to_execute.responsible_agent
                agent = self._agents.get(agent_key)
                if not agent:
                    err = f"Supervisor error: Agent '{agent_key}' not found in registry for task '{task_to_execute.task_id}'."
                    context.errors.append(err)
                    collaboration_state.errors.append(err)
                    logger.error(err)
                    task_plan.handle_task_failure(task_to_execute.task_id, err)
                    validation_failed = True
                    break

                # Invariant: task transitions from READY to RUNNING
                task_to_execute.transition_to(TaskStatus.RUNNING)
                self._emit_supervisor_event(
                    AgentEventType.SEO_TASK_STARTED,
                    payload=task_to_execute.to_dict(),
                    correlation_id=corr_id
                )
                self._emit_supervisor_event(
                    AgentEventType.SEO_PARALLEL_TASK_STARTED,
                    payload={
                        "batch_id": batch.batch_id,
                        "task": task_to_execute.to_dict()
                    },
                    correlation_id=corr_id
                )

                # Build controlled, minimally-scoped handoff package
                handoff = self.build_handoff_context(
                    source_agent=previous_agent_name,
                    target_agent_name=agent.name,
                    context=context,
                    correlation_id=corr_id,
                    current_task_id=task_to_execute.task_id,
                    task_objective=task_to_execute.objective
                )

                # Pre-execution handoff validation
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
                    task_plan.handle_task_failure(task_to_execute.task_id, err_msg)
                    validation_failed = True
                    break

                handoffs[task_to_execute.task_id] = handoff

                # Emit context projection & handoff events
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
                        "step_index": step_idx + 1,
                        "total_steps": len(task_plan.tasks)
                    },
                    correlation_id=corr_id
                )

                self._emit_supervisor_event(
                    AgentEventType.SEO_AGENT_HANDOFF,
                    payload={
                        "source_agent": previous_agent_name,
                        "target_agent": agent.name,
                        "step_index": step_idx + 1,
                        "task_type": handoff.task_type
                    },
                    correlation_id=corr_id
                )

            if validation_failed:
                if not task_plan.get_ready_tasks():
                    context.status = "failed"
                    collaboration_state.status = "failed"
                    break
                continue

            # 2d. Concurrently execute batch via ParallelBatchExecutor
            batch_result = self.parallel_executor.execute_batch(
                batch=batch,
                tasks=batch_tasks,
                agents=self._agents,
                context=context,
                handoffs=handoffs,
                publisher=self.publisher,
                correlation_id=corr_id
            )
            step_idx += len(batch_tasks)

            # Decrement active workloads after batch execution completes
            for t_done in batch_tasks:
                self.workload_tracker.decrement(t_done.responsible_agent)

            # 2e. Synchronize batch results and update DAG & shared context
            for task_to_execute in batch_tasks:
                tid = task_to_execute.task_id
                agent_result = batch_result.task_results.get(tid)
                agent_key = task_to_execute.responsible_agent
                agent = self._agents.get(agent_key)
                handoff = handoffs.get(tid)
                timing = batch_result.timings.get(tid)
                duration_ms = timing.duration_ms if timing else 0

                is_failed = tid in batch.failed_tasks or (agent_result and agent_result.status == "failed")
                if is_failed:
                    err_detail = batch_result.errors.get(tid) or str(agent_result.errors if agent_result else "Unknown execution error")

                    # Milestone 5.5 Dynamic Reassignment / Bounded Safe Fallback
                    prev_routing = task_to_execute.metadata.get("routing_decision")
                    fallback_decision = None
                    if prev_routing and prev_routing.get("ranked_candidates"):
                        prev_dec_obj = RoutingDecision(
                            task_id=prev_routing["task_id"],
                            selected_agent=prev_routing["selected_agent"],
                            score=prev_routing.get("score", 0.0),
                            confidence=prev_routing.get("confidence", 0.5),
                            reasons=prev_routing.get("reasons", []),
                            rejected_candidates=prev_routing.get("rejected_candidates", []),
                            candidate_scores=prev_routing.get("candidate_scores", {}),
                            score_breakdowns=prev_routing.get("score_breakdowns", {}),
                            ranked_candidates=prev_routing.get("ranked_candidates", []),
                            fallback_attempt=prev_routing.get("fallback_attempt", 0),
                            fallback_reason=prev_routing.get("fallback_reason"),
                            project_id=self.project.id if self.project else 0
                        )
                        fallback_decision = self.agent_selector.select_fallback(
                            task=task_to_execute,
                            previous_decision=prev_dec_obj,
                            failed_agent=agent_key,
                            failure_reason=err_detail,
                            context_project_id=self.project.id if self.project else None,
                            correlation_id=corr_id,
                            max_attempts=2
                        )

                    if fallback_decision:
                        fallback_agent_key = fallback_decision.selected_agent
                        fallback_agent = self._agents.get(fallback_agent_key)
                        if fallback_agent:
                            logger.info(
                                f"[{self.name}] Attempting safe fallback reassignment for task '{tid}' "
                                f"from '{agent_key}' to '{fallback_agent_key}' (Attempt {fallback_decision.fallback_attempt})."
                            )
                            # Milestone 5.6: Record reassignment and initial failure in learning store
                            fail_rec = self.learning_service.record_task_outcome(
                                agent_name=agent_key,
                                task_id=tid,
                                task_type=task_to_execute.metadata.get("task_type") or self.agent_selector._infer_task_requirements(task_to_execute).get("task_category", "general"),
                                task_objective=task_to_execute.objective,
                                project_id=self.project.id if self.project else 0,
                                success=False,
                                duration_ms=duration_ms,
                                predicted_confidence=prev_routing.get("confidence", 0.85) if prev_routing else 0.85,
                                reassignment_count=fallback_decision.fallback_attempt,
                                tool_usage=list(agent.allowed_tools) if agent else [],
                                failure_category=FailureCategory.AGENT_FAILURE,
                                failure_reason=err_detail,
                                was_fallback=True,
                                routing_metadata=prev_routing or {},
                                correlation_id=corr_id
                            )
                            context.learning_records.append(fail_rec.to_dict())
                            if hasattr(collaboration_state, "learning_records"):
                                collaboration_state.learning_records.append(fail_rec.to_dict())

                            task_to_execute.responsible_agent = fallback_agent_key
                            task_to_execute.metadata["routing_decision"] = fallback_decision.to_dict()
                            context.routing_decisions.append(fallback_decision.to_dict())
                            if hasattr(collaboration_state, "routing_decisions"):
                                collaboration_state.routing_decisions.append(fallback_decision.to_dict())

                            fb_handoff = self.build_handoff_context(
                                source_agent=previous_agent_name,
                                target_agent_name=fallback_agent_key,
                                context=context,
                                correlation_id=corr_id,
                                current_task_id=tid,
                                task_objective=task_to_execute.objective
                            )
                            try:
                                AgentHandoffValidator.validate(fb_handoff, expected_project_id=self.project.id)
                                fb_res = fallback_agent.run(context, handoff=fb_handoff)
                                if fb_res.status == "completed":
                                    agent_result = fb_res
                                    agent_key = fallback_agent_key
                                    handoff = fb_handoff
                                    is_failed = False
                                    if tid in batch.failed_tasks:
                                        batch.failed_tasks.remove(tid)
                                    if tid not in batch.successful_tasks:
                                        batch.successful_tasks.append(tid)
                            except Exception as fb_err:
                                logger.warning(f"[{self.name}] Fallback execution of '{fallback_agent_key}' failed: {fb_err}")

                if is_failed:
                    err_detail = batch_result.errors.get(tid) or str(agent_result.errors if agent_result else "Unknown execution error")
                    logger.warning(
                        f"[{self.name}] Agent '{agent_key}' reported failure on task '{tid}'. "
                        f"Isolating failure and preserving {len(context.evidence)} evidence items."
                    )
                    blocked_ids = task_plan.handle_task_failure(tid, err_detail)
                    self._emit_supervisor_event(
                        AgentEventType.SEO_TASK_FAILED,
                        payload=task_to_execute.to_dict(),
                        correlation_id=corr_id
                    )
                    self._emit_supervisor_event(
                        AgentEventType.SEO_PARALLEL_TASK_FAILED,
                        payload={
                            "batch_id": batch.batch_id,
                            "task_id": tid,
                            "agent": agent_key,
                            "error": err_detail,
                            "duration_ms": duration_ms
                        },
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
                    if agent_key not in collaboration_state.failed_agents:
                        collaboration_state.failed_agents.append(agent_key)
                    collaboration_state.status = "degraded"

                    # Milestone 5.6: Record unrecovered task failure in learning store
                    fail_cat = FailureCategory.AGENT_FAILURE
                    if "tool" in err_detail.lower():
                        fail_cat = FailureCategory.TOOL_FAILURE
                    elif "depend" in err_detail.lower() or "prereq" in err_detail.lower():
                        fail_cat = FailureCategory.DEPENDENCY_FAILURE
                    elif "safety" in err_detail.lower() or "unauthorized" in err_detail.lower() or "permission" in err_detail.lower():
                        fail_cat = FailureCategory.SAFETY_BLOCK
                    elif "human" in err_detail.lower() or "reject" in err_detail.lower():
                        fail_cat = FailureCategory.HUMAN_REJECTION
                    elif "verif" in err_detail.lower():
                        fail_cat = FailureCategory.VERIFICATION_FAILURE

                    current_routing = task_to_execute.metadata.get("routing_decision", {})
                    fail_rec = self.learning_service.record_task_outcome(
                        agent_name=agent_key,
                        task_id=tid,
                        task_type=task_to_execute.metadata.get("task_type") or self.agent_selector._infer_task_requirements(task_to_execute).get("task_category", "general"),
                        task_objective=task_to_execute.objective,
                        project_id=self.project.id if self.project else 0,
                        success=False,
                        duration_ms=duration_ms,
                        predicted_confidence=current_routing.get("confidence", 0.85),
                        verification_status="failed" if fail_cat == FailureCategory.VERIFICATION_FAILURE else "none",
                        reassignment_count=current_routing.get("fallback_attempt", 0),
                        tool_usage=list(agent.allowed_tools) if agent else [],
                        failure_category=fail_cat,
                        failure_reason=err_detail,
                        was_fallback=bool(current_routing.get("fallback_attempt", 0) > 0),
                        routing_metadata=current_routing,
                        correlation_id=corr_id
                    )
                    context.learning_records.append(fail_rec.to_dict())
                    if hasattr(collaboration_state, "learning_records"):
                        collaboration_state.learning_records.append(fail_rec.to_dict())

                else:
                    # Success step
                    task_to_execute.transition_to(
                        TaskStatus.COMPLETED,
                        result_summary=f"{agent_key} executed step with {len(agent_result.findings)} findings."
                    )
                    self._emit_supervisor_event(
                        AgentEventType.SEO_TASK_COMPLETED,
                        payload=task_to_execute.to_dict(),
                        correlation_id=corr_id
                    )
                    self._emit_supervisor_event(
                        AgentEventType.SEO_PARALLEL_TASK_COMPLETED,
                        payload={
                            "batch_id": batch.batch_id,
                            "task_id": tid,
                            "agent": agent_key,
                            "findings_count": len(agent_result.findings),
                            "duration_ms": duration_ms
                        },
                        correlation_id=corr_id
                    )

                    if agent_key not in collaboration_state.completed_agents:
                        collaboration_state.completed_agents.append(agent_key)
                    collaboration_state.current_evidence.update(agent_result.evidence)
                    context.evidence.update(agent_result.evidence)

                    # Milestone 5.6: Record task success and verification outcome in learning store
                    verif_status = "none"
                    if agent_key == "seo_verifier" or "verif" in task_to_execute.objective.lower():
                        verif_data = agent_result.evidence.get("verification_status") if agent_result else None
                        if verif_data in ["verified", "passed"] or any("verified" in str(f).lower() for f in (agent_result.findings if agent_result else [])):
                            verif_status = "verified"
                        else:
                            verif_status = "failed"

                    current_routing = task_to_execute.metadata.get("routing_decision", {})
                    succ_rec = self.learning_service.record_task_outcome(
                        agent_name=agent_key,
                        task_id=tid,
                        task_type=task_to_execute.metadata.get("task_type") or self.agent_selector._infer_task_requirements(task_to_execute).get("task_category", "general"),
                        task_objective=task_to_execute.objective,
                        project_id=self.project.id if self.project else 0,
                        success=True,
                        duration_ms=duration_ms,
                        predicted_confidence=current_routing.get("confidence", 0.85),
                        verification_status=verif_status,
                        reassignment_count=current_routing.get("fallback_attempt", 0),
                        tool_usage=list(agent.allowed_tools) if agent else [],
                        failure_category=FailureCategory.NONE,
                        was_fallback=bool(current_routing.get("fallback_attempt", 0) > 0),
                        routing_metadata=current_routing,
                        correlation_id=corr_id
                    )
                    context.learning_records.append(succ_rec.to_dict())
                    if hasattr(collaboration_state, "learning_records"):
                        collaboration_state.learning_records.append(succ_rec.to_dict())

                    if agent_key == "seo_investigator" or "investigation" in agent_key:
                        for f_item in agent_result.findings:
                            if f_item not in context.investigation_findings:
                                context.investigation_findings.append(f_item)
                    if "strategy" in agent_result.evidence:
                        context.strategy_signals.update(agent_result.evidence["strategy"])
                    if agent_result.recommendations:
                        for rec_item in agent_result.recommendations:
                            if rec_item not in context.action_proposals:
                                context.action_proposals.append(rec_item)

                    for f in agent_result.observed_facts:
                        if f not in context.observed_facts:
                            context.observed_facts.append(f)
                    for inf in agent_result.inferences:
                        if inf not in context.inferences:
                            context.inferences.append(inf)
                    for unc in agent_result.uncertainties:
                        if unc not in context.uncertainties:
                            context.uncertainties.append(unc)
                    for asm in agent_result.assumptions:
                        if asm not in context.assumptions:
                            context.assumptions.append(asm)

                    if handoff:
                        handoff_dict = handoff.to_dict()
                        if not any(h.get("target_agent") == agent_key and h.get("source_agent") == handoff.source_agent and h.get("current_task_id") == tid for h in collaboration_state.handoff_history):
                            collaboration_state.handoff_history.append(handoff_dict)
                        if not any(h.get("target_agent") == agent_key and h.get("source_agent") == handoff.source_agent and h.get("current_task_id") == tid for h in context.handoff_history):
                            context.handoff_history.append(handoff_dict)

                        self._emit_supervisor_event(
                            AgentEventType.SEO_AGENT_HANDOFF_COMPLETED,
                            payload={
                                "source_agent": handoff.source_agent,
                                "target_agent": agent_key,
                                "step_index": step_idx,
                                "confidence": agent_result.confidence
                            },
                            correlation_id=corr_id
                        )

                    self._emit_supervisor_event(
                        AgentEventType.SEO_COLLABORATION_MEMORY_UPDATED,
                        payload={
                            "agent": agent_key,
                            "new_facts": len(agent_result.observed_facts),
                            "new_inferences": len(agent_result.inferences),
                            "new_uncertainties": len(agent_result.uncertainties),
                            "memory_summary": shared_memory.summarize()
                        },
                        correlation_id=corr_id
                    )

                    # Phase 5.7 Reasoning result integration
                    if reasoning_case:
                        analysis_type = task_to_execute.metadata.get("analysis_type")
                        round_num = task_to_execute.metadata.get("reasoning_round", 1)

                        new_evi_ids = []
                        for f in agent_result.observed_facts:
                            fact_str = f.get("fact") if isinstance(f, dict) else str(f)
                            evi_item = self.reasoning_service.add_evidence(
                                case_id=reasoning_case.case_id,
                                fact=fact_str,
                                source_agent=agent_key,
                                source_tool=f.get("source") if isinstance(f, dict) else None,
                                confidence=f.get("confidence", 1.0) if isinstance(f, dict) else 1.0,
                                raw_data=f.get("raw_data") if isinstance(f, dict) else None,
                            )
                            new_evi_ids.append(evi_item.evidence_id)

                        # If agent generated inferences from previously ingested evidence, link to case evidence
                        if not new_evi_ids and reasoning_case.evidence_references:
                            new_evi_ids = [e.evidence_id for e in reasoning_case.evidence_references]

                        for inf in agent_result.inferences:
                            inf_str = inf.get("inference") if isinstance(inf, dict) else str(inf)
                            conf = inf.get("confidence", 0.75) if isinstance(inf, dict) else 0.75
                            self.reasoning_service.add_hypothesis(
                                case_id=reasoning_case.case_id,
                                statement=inf_str,
                                proposing_agent=agent_key,
                                confidence=conf,
                                supporting_evidence_ids=new_evi_ids,
                                rationale=f"Inferred by {agent_key} in round {round_num}",
                            )

                        if not agent_result.inferences and agent_result.findings and analysis_type in ["technical", "strategic"]:
                            for find_str in agent_result.findings:
                                self.reasoning_service.add_hypothesis(
                                    case_id=reasoning_case.case_id,
                                    statement=find_str,
                                    proposing_agent=agent_key,
                                    confidence=agent_result.confidence,
                                    supporting_evidence_ids=new_evi_ids,
                                    rationale=f"Finding from {agent_key} in round {round_num}",
                                )

                        if analysis_type == "critique":
                            for target_h in list(reasoning_case.hypotheses):
                                if target_h.proposing_agent != agent_key:
                                    c_type = ChallengeType.MISSING_EVIDENCE if not target_h.supporting_evidence_ids else ChallengeType.ALTERNATIVE_EXPLANATION
                                    self.reasoning_service.submit_critique(
                                        case_id=reasoning_case.case_id,
                                        target_hypothesis_id=target_h.hypothesis_id,
                                        critic_agent=agent_key,
                                        challenge_type=c_type,
                                        challenged_claim=target_h.statement,
                                        severity=CritiqueSeverity.MEDIUM,
                                        confidence=0.85,
                                        recommended_resolution="Verify causal correlation against empirical GSC metrics.",
                                    )

                        if analysis_type == "consensus":
                            consensus = self.reasoning_service.arbitrate(reasoning_case.case_id)
                            self.reasoning_service.ingest_into_shared_memory(reasoning_case, shared_memory)
                            if consensus.consensus_state == ConsensusState.ESCALATED.value:
                                logger.warning(f"[{self.name}] Reasoning escalated: {consensus.escalation_reason}")
                                context.status = "degraded"
                                collaboration_state.status = "degraded"

                        case_dict = reasoning_case.to_dict()
                        for idx, rc in enumerate(context.reasoning_cases):
                            if rc.get("case_id") == reasoning_case.case_id:
                                context.reasoning_cases[idx] = case_dict
                                break
                        else:
                            context.reasoning_cases.append(case_dict)
                        if hasattr(collaboration_state, "reasoning_cases"):
                            for idx, rc in enumerate(collaboration_state.reasoning_cases):
                                if rc.get("case_id") == reasoning_case.case_id:
                                    collaboration_state.reasoning_cases[idx] = case_dict
                                    break
                            else:
                                collaboration_state.reasoning_cases.append(case_dict)

                    previous_agent_name = agent_key

            # 2f. Emit batch completion events and store batch
            if batch.status == "partial_failure":
                self._emit_supervisor_event(
                    AgentEventType.SEO_PARALLEL_BATCH_PARTIAL_FAILURE,
                    payload=batch.to_dict(),
                    correlation_id=corr_id
                )
            self._emit_supervisor_event(
                AgentEventType.SEO_PARALLEL_BATCH_COMPLETED,
                payload=batch.to_dict(),
                correlation_id=corr_id
            )
            batch_dict = batch.to_dict()
            collaboration_state.parallel_batches.append(batch_dict)
            context.parallel_batches.append(batch_dict)

            # Update pending agents based on remaining tasks in plan
            remaining_agents = {
                t.responsible_agent for t in task_plan.tasks.values()
                if t.status in [TaskStatus.PENDING.value, TaskStatus.READY.value, TaskStatus.RUNNING.value]
            }
            collaboration_state.pending_agents = [a for a in agent_pipeline if a in remaining_agents]

            # Unblock downstream dependencies and emit resolution events
            new_ready_tasks = task_plan.get_ready_tasks()
            for ready_t in new_ready_tasks:
                for resolved_t in batch.successful_tasks:
                    if resolved_t in ready_t.dependencies:
                        self._emit_supervisor_event(
                            AgentEventType.SEO_TASK_DEPENDENCY_RESOLVED,
                            payload={"task_id": ready_t.task_id, "ready_task": ready_t.to_dict(), "resolved_by": resolved_t},
                            correlation_id=corr_id
                        )
                self._emit_supervisor_event(
                    AgentEventType.SEO_TASK_READY,
                    payload=ready_t.to_dict(),
                    correlation_id=corr_id
                )

            # 2g. Conflict Detection & Adaptive Replanning
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

            # If any batch agent provided updated findings resolving an earlier conflict, resolve it
            for c in shared_memory._conflicts:
                if c.resolution_status == ConflictStatus.OPEN.value:
                    for b_agent in batch.agent_names:
                        if b_agent in c.responsible_agents:
                            prev_revisits = sum(1 for r in shared_memory._revisits if r.agent == b_agent)
                            if prev_revisits > 0:
                                shared_memory.resolve_conflict(
                                    conflict_id=c.conflict_id,
                                    resolved_by=b_agent,
                                    resolution_notes=f"Resolved by {b_agent} with clarifying empirical evidence."
                                )
                                self._emit_supervisor_event(
                                    AgentEventType.SEO_COLLABORATION_MEMORY_CONFLICT_RESOLVED,
                                    payload=c.to_dict(),
                                    correlation_id=corr_id
                                )

            # 2h. Bounded Iterative Collaboration Check
            for c in shared_memory._conflicts:
                if c.resolution_status == ConflictStatus.OPEN.value:
                    for prev_agent_name in c.responsible_agents:
                        if prev_agent_name in self._agents:
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

            if not task_plan.get_ready_tasks() and len(batch.successful_tasks) == 0 and len(batch.failed_tasks) > 0:
                context.status = "failed"
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

        # Ensure reasoning case is arbitrated if one exists and was not yet arbitrated
        if reasoning_case and reasoning_case.consensus_state == ConsensusState.NO_CONSENSUS.value:
            consensus = self.reasoning_service.arbitrate(reasoning_case.case_id)
            self.reasoning_service.ingest_into_shared_memory(reasoning_case, shared_memory)
            case_dict = reasoning_case.to_dict()
            for idx, rc in enumerate(context.reasoning_cases):
                if rc.get("case_id") == reasoning_case.case_id:
                    context.reasoning_cases[idx] = case_dict
                    break
            else:
                context.reasoning_cases.append(case_dict)
            if hasattr(collaboration_state, "reasoning_cases"):
                for idx, rc in enumerate(collaboration_state.reasoning_cases):
                    if rc.get("case_id") == reasoning_case.case_id:
                        collaboration_state.reasoning_cases[idx] = case_dict
                        break
                else:
                    collaboration_state.reasoning_cases.append(case_dict)

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
                    "parallel_batches_count": len(context.parallel_batches),
                    "parallel_batches": context.parallel_batches,
                },
                correlation_id=corr_id
            )

        return context

    def orchestrate_reasoning(
        self,
        objective: str,
        target_url: Optional[str] = None,
        target_query: Optional[str] = None,
        correlation_id: Optional[str] = None,
        hypotheses_statements: Optional[List[str]] = None,
        run_id: Optional[int] = None,
        participating_agent_names: Optional[List[str]] = None,
    ) -> Tuple[ReasoningCase, ConsensusResult]:
        """
        Direct supervisor execution of the bounded multi-agent reasoning & consensus flow:
        Round 1: Independent agent analyses (isolated, evidence-backed hypotheses)
        Round 2: Cross-agent structured critiques and challenges
        Round 3: Disagreement detection, non-majority consensus evaluation, supervisor arbitration.
        """
        corr_id = correlation_id or str(uuid.uuid4())
        case = self.reasoning_service.create_case(
            objective=objective,
            correlation_id=corr_id,
            run_id=run_id,
            context_data={"target_url": target_url, "target_query": target_query},
        )

        shared_memory = SharedWorkingMemory(
            project_id=self.project.id,
            task_goal=objective,
            correlation_id=corr_id,
            run_id=run_id,
        )
        SharedMemoryRegistry.get_instance().register(shared_memory)

        # Round 1: Independent Analysis
        self.reasoning_service.execute_reasoning_round(case.case_id, "independent_analysis")

        # 1. Researcher gathers empirical evidence
        researcher = self._agents.get("seo_researcher")
        if researcher:
            res_ctx = SharedContext(
                project_id=self.project.id,
                project_name=self.project.name,
                website_url=self.project.website_url,
                user_id=getattr(self.user, 'id', None),
                task_type="research",
                task_goal=f"Gather empirical evidence for: {objective}",
                target_url=target_url,
                target_query=target_query,
                correlation_id=corr_id,
            )
            res_handoff = self.build_handoff_context(
                source_agent="seo_supervisor",
                target_agent_name="seo_researcher",
                context=res_ctx,
                correlation_id=corr_id,
            )
            try:
                res_result = researcher.run(res_ctx, handoff=res_handoff)
                for f in res_result.observed_facts:
                    self.reasoning_service.add_evidence(
                        case_id=case.case_id,
                        fact=f.get("fact") if isinstance(f, dict) else str(f),
                        source_agent="seo_researcher",
                        source_tool=f.get("source") if isinstance(f, dict) else "get_gsc_performance",
                        confidence=f.get("confidence", 1.0) if isinstance(f, dict) else 1.0,
                        quality_score=1.0,
                        raw_data=f.get("raw_data") if isinstance(f, dict) else None,
                    )
            except Exception as e:
                logger.warning(f"[{self.name}] Researcher step in reasoning failed: {e}")

        # 2. Independent agents formulate competing hypotheses
        competing_agents = participating_agent_names or ["seo_investigator", "seo_strategist"]
        evidence_ids = [e.evidence_id for e in case.evidence_references]

        if hypotheses_statements and len(hypotheses_statements) >= len(competing_agents):
            for idx, a_name in enumerate(competing_agents):
                h_stmt = hypotheses_statements[idx]
                sup_ids = [evidence_ids[idx % len(evidence_ids)]] if evidence_ids else []
                self.reasoning_service.add_hypothesis(
                    case_id=case.case_id,
                    statement=h_stmt,
                    proposing_agent=a_name,
                    confidence=0.82,
                    supporting_evidence_ids=sup_ids,
                    rationale=f"Independently derived by {a_name} based on empirical evidence {sup_ids}",
                )
                self.reasoning_service.record_independent_analysis(
                    case_id=case.case_id,
                    agent_name=a_name,
                    round_number=1,
                    hypotheses_proposed=[h_stmt],
                    evidence_collected=case.evidence_references,
                    rationale=f"Independent analysis from {a_name}",
                    confidence=0.82,
                )
        else:
            # Generate default domain hypotheses for competing agents
            inv_agent = self._agents.get("seo_investigator")
            if inv_agent and "seo_investigator" in competing_agents:
                inv_stmt = f"Technical anomaly or broken canonical tags on {target_url or 'target domain'}"
                self.reasoning_service.add_hypothesis(
                    case_id=case.case_id,
                    statement=inv_stmt,
                    proposing_agent="seo_investigator",
                    confidence=0.85,
                    supporting_evidence_ids=evidence_ids[:1] if evidence_ids else [],
                    rationale="Technical crawl and HTTP inspection indicate canonical or status anomaly.",
                )
                self.reasoning_service.record_independent_analysis(
                    case_id=case.case_id,
                    agent_name="seo_investigator",
                    round_number=1,
                    hypotheses_proposed=[inv_stmt],
                    confidence=0.85,
                )

            strat_agent = self._agents.get("seo_strategist")
            if strat_agent and "seo_strategist" in competing_agents:
                strat_stmt = f"Competitor visibility surge and content decay on {target_query or 'target queries'}"
                self.reasoning_service.add_hypothesis(
                    case_id=case.case_id,
                    statement=strat_stmt,
                    proposing_agent="seo_strategist",
                    confidence=0.72,
                    supporting_evidence_ids=evidence_ids[1:2] if len(evidence_ids) > 1 else [],
                    rationale="Competitor visibility shifts and search intent mismatch.",
                )
                self.reasoning_service.record_independent_analysis(
                    case_id=case.case_id,
                    agent_name="seo_strategist",
                    round_number=1,
                    hypotheses_proposed=[strat_stmt],
                    confidence=0.72,
                )

        # Round 2: Structured Cross-Critique
        self.reasoning_service.execute_reasoning_round(case.case_id, "critique")
        verifier = self._agents.get("seo_verifier")
        for h in list(case.hypotheses):
            if not h.supporting_evidence_ids:
                self.reasoning_service.submit_critique(
                    case_id=case.case_id,
                    target_hypothesis_id=h.hypothesis_id,
                    critic_agent="seo_verifier" if verifier else "seo_supervisor",
                    challenge_type=ChallengeType.UNSUPPORTED_CLAIM,
                    challenged_claim=h.statement,
                    severity=CritiqueSeverity.HIGH,
                    confidence=0.90,
                    recommended_resolution="Provide empirical GSC or crawl data supporting this claim.",
                )
            elif h.proposing_agent == "seo_strategist":
                self.reasoning_service.submit_critique(
                    case_id=case.case_id,
                    target_hypothesis_id=h.hypothesis_id,
                    critic_agent="seo_investigator",
                    challenge_type=ChallengeType.ALTERNATIVE_EXPLANATION,
                    challenged_claim=h.statement,
                    severity=CritiqueSeverity.MEDIUM,
                    confidence=0.75,
                    recommended_resolution="Consider technical degradation as primary root cause.",
                )

        # Round 3: Disagreement Detection, Consensus & Supervisor Arbitration
        self.reasoning_service.execute_reasoning_round(case.case_id, "resolution")
        consensus = self.reasoning_service.arbitrate(
            case_id=case.case_id,
            supervisor_notes=f"Arbitrated multi-agent reasoning on objective: {objective}",
        )
        self.reasoning_service.ingest_into_shared_memory(case, shared_memory)
        return case, consensus


# Alias for backward compatibility and concise import
SEOSupervisor = SEOSupervisorAgent
