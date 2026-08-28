"""
DoxaRank Core Agent Orchestrator & ReAct Execution Engine.

Coordinates autonomous, bounded, multi-step agent execution for a specific Project.
Enforces multi-tenant isolation, step bounding (max_steps=15), loop detection,
error recovery, and human-in-the-loop approval gating.
"""

import logging
import json
from typing import Optional, Dict, Any, List
from django.utils import timezone

from apps.projects.models import Project
from apps.seo.models import (
    AgentRun, AgentStep, AgentToolCall,
    AgentRunStatus, AgentActionType, AgentStepStatus,
    Keyword, SEOInsight, SEORecommendation,
    SEOContentBrief, SEOContentDraft, SEOAction,
    InsightStatus, ActionStatus
)
from apps.seo.services.tool_registry import (
    ToolRegistry, get_tool_registry
)
from apps.seo.services.ai_providers import (
    BaseAIProvider, get_ai_provider
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Autonomous ReAct Agent Orchestrator for DoxaRank.
    Takes high-level user goals, breaks them into iterative reasoning steps,
    executes tools through the ToolRegistry, records observations, and pauses
    for human approval on high-impact actions.
    """

    def __init__(
        self,
        project: Project,
        user: Any,
        provider: Optional[BaseAIProvider] = None,
        registry: Optional[ToolRegistry] = None,
        max_steps: int = 15
    ):
        self.project = project
        self.user = user
        self.provider = provider or get_ai_provider()
        self.registry = registry or get_tool_registry()
        self.max_steps = max_steps

    def start_run(
        self,
        goal: str,
        context_snapshot: Optional[Dict[str, Any]] = None,
        plan: Optional[List[Any]] = None
    ) -> AgentRun:
        """
        Create a new AgentRun session and begin the execution loop.
        """
        snapshot = context_snapshot or self._capture_project_baseline()
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal=goal,
            status=AgentRunStatus.RUNNING,
            plan=plan or [],
            context_snapshot=snapshot,
            max_steps=self.max_steps,
            total_steps=0
        )

        logger.info(f"Started AgentRun #{run.id} for project #{self.project.id} with goal: '{goal[:60]}'")
        return self.execute_loop(run)

    def execute_loop(self, run: AgentRun) -> AgentRun:
        """
        Execute iterative ReAct loop until run reaches a terminal state
        or pauses for human approval.
        """
        while run.status == AgentRunStatus.RUNNING:
            should_continue = self.step(run)
            run.refresh_from_db()
            if not should_continue:
                break

        return run

    def resume_run(self, run: AgentRun, approval_decision: Optional[str] = None) -> AgentRun:
        """
        Resume an AgentRun paused in 'waiting_for_approval' state after human review.
        If approved, executes the proposed action through the safe action executor before resuming the loop.
        If rejected, marks the proposed action as rejected and terminates the run.
        """
        if run.status != AgentRunStatus.WAITING_FOR_APPROVAL:
            raise ValueError(f"AgentRun #{run.id} is not waiting for approval (current status: {run.status}).")

        latest_step = run.steps.order_by('-step_number').first()
        decision = (approval_decision or "approved").lower()

        from apps.seo.services.action_executors import get_action_executor

        if decision == "approved":
            logger.info(f"AgentRun #{run.id} approved by user. Executing action and resuming loop.")
            
            # Execute the proposed action safely
            proposed_action = SEOAction.objects.filter(
                project=self.project,
                status=ActionStatus.PROPOSED
            ).order_by('-created_at').first()

            if proposed_action:
                proposed_action.status = ActionStatus.APPROVED
                proposed_action.save(update_fields=['status', 'updated_at'])
                executor = get_action_executor()
                executor.execute(proposed_action)

            if latest_step:
                latest_step.status = AgentStepStatus.COMPLETED
                latest_step.thought += "\n[Human Approval]: SEO Action was reviewed, approved, and executed by safe action executor."
                latest_step.save()

            run.status = AgentRunStatus.RUNNING
            run.save()
            return self.execute_loop(run)
        else:
            logger.info(f"AgentRun #{run.id} rejected by user. Terminating run.")
            
            # Mark proposed action as rejected
            proposed_action = SEOAction.objects.filter(
                project=self.project,
                status=ActionStatus.PROPOSED
            ).order_by('-created_at').first()

            if proposed_action:
                proposed_action.status = ActionStatus.REJECTED
                proposed_action.save(update_fields=['status', 'updated_at'])

            if latest_step:
                latest_step.status = AgentStepStatus.FAILED
                latest_step.thought += "\n[Human Rejection]: Proposed SEO Action was rejected by user."
                latest_step.save()

            run.status = AgentRunStatus.CANCELLED
            run.summary = f"Run terminated because human user rejected the proposed SEO Action."
            run.completed_at = timezone.now()
            run.save()
            return run

    def step(self, run: AgentRun) -> bool:
        """
        Execute a single reasoning and tool-execution step within the run.
        Returns True if the loop should continue, or False if the loop must stop.
        """
        # Guardrail 1: Step Limit Bounding
        if run.total_steps >= run.max_steps:
            logger.warning(f"AgentRun #{run.id} reached maximum step limit ({run.max_steps}).")
            run.status = AgentRunStatus.FAILED
            run.summary = f"Agent reached maximum execution step limit ({run.max_steps}) without finishing."
            run.completed_at = timezone.now()
            run.save()
            return False

        # Build context for AI reasoning
        ai_context = self._build_ai_context(run)

        # Consult AI Provider for next action
        try:
            decision = self.provider.decide_agent_action(ai_context)
        except Exception as exc:
            logger.exception(f"AI Provider error during decision on AgentRun #{run.id}: {exc}")
            run.status = AgentRunStatus.FAILED
            run.summary = f"AI Provider decision error: {exc}"
            run.completed_at = timezone.now()
            run.save()
            return False

        # Validate decision structure
        if not isinstance(decision, dict) or decision.get("action") not in ["tool", "finish"]:
            logger.error(f"Malformed decision from AI Provider: {decision}")
            step_num = run.total_steps + 1
            AgentStep.objects.create(
                run=run,
                step_number=step_num,
                thought=f"Malformed decision received from AI: {decision}",
                action_type=AgentActionType.DECISION,
                status=AgentStepStatus.FAILED,
                completed_at=timezone.now()
            )
            run.total_steps += 1
            run.status = AgentRunStatus.FAILED
            run.summary = "Agent terminated due to malformed AI decision output."
            run.completed_at = timezone.now()
            run.save()
            return False

        # Handle Finish Action
        if decision["action"] == "finish":
            summary = decision.get("summary") or "Goal completed."
            reason = decision.get("reason") or "Goal successfully achieved."
            step_num = run.total_steps + 1

            AgentStep.objects.create(
                run=run,
                step_number=step_num,
                thought=reason,
                action_type=AgentActionType.FINAL,
                status=AgentStepStatus.COMPLETED,
                completed_at=timezone.now()
            )

            run.total_steps += 1
            run.status = AgentRunStatus.COMPLETED
            run.summary = summary
            run.completed_at = timezone.now()
            run.save()
            logger.info(f"AgentRun #{run.id} finished successfully in {run.total_steps} steps.")
            return False

        # Handle Tool Call Action
        tool_name = decision.get("tool_name", "")
        arguments = decision.get("arguments") or {}
        reason = decision.get("reason") or f"Invoke tool '{tool_name}'"

        # Guardrail 2: Loop / Repeated Tool Detection
        if self._detect_repeated_tool_loop(run, tool_name, arguments):
            logger.warning(f"Detected repetitive tool failure loop on '{tool_name}' for AgentRun #{run.id}.")
            step_num = run.total_steps + 1
            AgentStep.objects.create(
                run=run,
                step_number=step_num,
                thought=f"Detected repetitive tool loop on '{tool_name}'. Terminating run safely.",
                action_type=AgentActionType.DECISION,
                status=AgentStepStatus.FAILED,
                completed_at=timezone.now()
            )
            run.total_steps += 1
            run.status = AgentRunStatus.FAILED
            run.summary = f"Terminated due to repetitive tool loop on tool '{tool_name}'."
            run.completed_at = timezone.now()
            run.save()
            return False

        # Create AgentStep record
        step_num = run.total_steps + 1
        step = AgentStep.objects.create(
            run=run,
            step_number=step_num,
            thought=reason,
            action_type=AgentActionType.TOOL_CALL,
            status=AgentStepStatus.RUNNING
        )

        # Execute tool via registry
        exec_res = self.registry.execute(tool_name, self.project, arguments)

        # Record AgentToolCall telemetry
        AgentToolCall.objects.create(
            step=step,
            tool_name=tool_name,
            tool_input=arguments,
            tool_output=exec_res.get("data") or {},
            error_message=exec_res.get("error", {}).get("message", "") if not exec_res["success"] else "",
            duration_ms=exec_res.get("duration_ms", 0),
            is_mutating=exec_res.get("is_mutating", False),
            completed_at=timezone.now()
        )

        step.status = AgentStepStatus.COMPLETED if exec_res["success"] else AgentStepStatus.FAILED
        step.completed_at = timezone.now()
        step.save()

        run.total_steps += 1
        run.save()

        # Guardrail 3: Human Approval Checkpoint
        if exec_res.get("requires_approval") or tool_name == "propose_seo_action":
            if exec_res["success"]:
                logger.info(f"AgentRun #{run.id} generated action proposal. Pausing for human approval.")
                step.action_type = AgentActionType.APPROVAL
                step.status = AgentStepStatus.WAITING
                step.save()

                run.status = AgentRunStatus.WAITING_FOR_APPROVAL
                run.save()
                return False  # Pause execution loop

        return True  # Continue loop

    def _build_ai_context(self, run: AgentRun) -> Dict[str, Any]:
        """
        Assemble grounded context for the AI decision step without leaking private tokens.
        """
        steps = run.steps.all().order_by('step_number')
        history = []
        for s in steps:
            tc = s.tool_calls.first()
            history.append({
                "step_number": s.step_number,
                "thought": s.thought,
                "action_type": s.action_type,
                "status": s.status,
                "tool_name": tc.tool_name if tc else None,
                "tool_input": tc.tool_input if tc else None,
                "tool_output": tc.tool_output if tc else None,
                "error": tc.error_message if tc and tc.error_message else None
            })

        # Discover most recent entities for this project to assist deterministic mock or prompt grounding
        latest_insight = SEOInsight.objects.filter(project=self.project).order_by('-created_at').first()
        latest_rec = SEORecommendation.objects.filter(project=self.project).order_by('-created_at').first()
        latest_brief = SEOContentBrief.objects.filter(project=self.project).order_by('-created_at').first()
        latest_draft = SEOContentDraft.objects.filter(project=self.project).order_by('-created_at').first()

        return {
            "project_id": self.project.id,
            "project_name": self.project.name,
            "website_url": self.project.website_url,
            "goal": run.goal,
            "current_step_number": run.total_steps + 1,
            "max_steps": run.max_steps,
            "history": history,
            "available_tools": self.registry.get_schemas(),
            "target_insight_id": latest_insight.id if latest_insight else None,
            "target_recommendation_id": latest_rec.id if latest_rec else None,
            "target_brief_id": latest_brief.id if latest_brief else None,
            "target_draft_id": latest_draft.id if latest_draft else None,
        }

    def _detect_repeated_tool_loop(self, run: AgentRun, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """
        Detect if the same tool with identical arguments was invoked in the immediately preceding step and failed.
        """
        recent_steps = run.steps.order_by('-step_number')[:2]
        if len(recent_steps) >= 1:
            last_tc = recent_steps[0].tool_calls.first()
            if (
                last_tc and
                last_tc.tool_name == tool_name and
                last_tc.tool_input == arguments and
                recent_steps[0].status == AgentStepStatus.FAILED
            ):
                return True
        return False

    def _capture_project_baseline(self) -> Dict[str, Any]:
        """Capture initial quantitative baseline of the project state."""
        return {
            "captured_at": timezone.now().isoformat(),
            "total_keywords": Keyword.objects.filter(project=self.project).count(),
            "open_insights": SEOInsight.objects.filter(project=self.project, status=InsightStatus.OPEN).count(),
            "total_recommendations": SEORecommendation.objects.filter(project=self.project).count(),
            "total_actions": SEOAction.objects.filter(project=self.project).count(),
        }
