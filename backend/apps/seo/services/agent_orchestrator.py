"""
DoxaRank Core Agent Orchestrator & ReAct Execution Engine.

Coordinates autonomous, bounded, multi-step agent execution for a specific Project.
Enforces multi-tenant isolation, step bounding (max_steps=15), loop detection,
error recovery, structured real-time AgentEvent emission, and human-in-the-loop approval gating.
"""

import logging
import json
from typing import Optional, Dict, Any, List, Union
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
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Autonomous ReAct Agent Orchestrator for DoxaRank.
    Takes high-level user goals, breaks them into iterative reasoning steps,
    executes tools through the ToolRegistry, records observations, emits structured
    real-time AgentEvents, and pauses for human approval on high-impact actions.
    """

    def __init__(
        self,
        project: Project,
        user: Any,
        provider: Optional[BaseAIProvider] = None,
        registry: Optional[ToolRegistry] = None,
        publisher: Optional[AgentEventPublisher] = None,
        max_steps: int = 15
    ):
        self.project = project
        self.user = user
        self.provider = provider or get_ai_provider()
        self.registry = registry or get_tool_registry()
        self.publisher = publisher or get_event_publisher()
        self.max_steps = max_steps
        self._sequence_counter = 0

    def _emit_event(
        self,
        run: AgentRun,
        event_type: Union[AgentEventType, str],
        payload: Optional[Dict[str, Any]] = None,
        step_number: Optional[int] = None
    ) -> Optional[AgentEvent]:
        """
        Construct and publish an AgentEvent with monotonically increasing run-scoped sequence numbering.
        Guarantees that event publication failures do not corrupt or fail the core agent execution state.
        """
        if self._sequence_counter == 0 and run.context_snapshot and '_event_seq' in run.context_snapshot:
            self._sequence_counter = int(run.context_snapshot['_event_seq'])

        self._sequence_counter += 1

        if run.context_snapshot is None:
            run.context_snapshot = {}
        run.context_snapshot['_event_seq'] = self._sequence_counter

        event = AgentEvent(
            event_type=event_type,
            run_id=run.id,
            project_id=self.project.id,
            step_number=step_number,
            sequence_number=self._sequence_counter,
            payload=payload or {}
        )

        if '_event_history' not in run.context_snapshot or not isinstance(run.context_snapshot['_event_history'], list):
            run.context_snapshot['_event_history'] = []
        run.context_snapshot['_event_history'].append(event.to_dict())

        try:
            self.publisher.publish(event)
        except Exception as exc:
            logger.warning(
                f"[AgentOrchestrator] Event publication failed for run #{run.id} "
                f"(event: {event.event_type}, seq: {event.sequence_number}): {exc}"
            )

        return event

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

        # Emit agent.started lifecycle event
        self._emit_event(
            run,
            AgentEventType.AGENT_STARTED,
            {
                "goal": goal,
                "project_id": self.project.id,
                "max_steps": self.max_steps
            }
        )
        run.save(update_fields=['context_snapshot', 'updated_at'])

        return self.execute_loop(run)

    def execute_loop(self, run: AgentRun) -> AgentRun:
        """
        Execute iterative ReAct loop until run reaches a terminal state
        or pauses for human approval.
        """
        # Ensure sequence counter is synced with run state
        if self._sequence_counter == 0 and run.context_snapshot and '_event_seq' in run.context_snapshot:
            self._sequence_counter = int(run.context_snapshot['_event_seq'])

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

        # Sync sequence counter
        if self._sequence_counter == 0 and run.context_snapshot and '_event_seq' in run.context_snapshot:
            self._sequence_counter = int(run.context_snapshot['_event_seq'])

        latest_step = run.steps.order_by('-step_number').first()
        step_num = latest_step.step_number if latest_step else run.total_steps
        decision = (approval_decision or "approved").lower()

        from apps.seo.services.action_executors import get_action_executor
        from apps.seo.services.seo_action_verifier import SEOActionVerifier

        if decision == "approved":
            logger.info(f"AgentRun #{run.id} approved by user. Executing action/plan and verifying result.")
            executor = get_action_executor()
            verifier = SEOActionVerifier(project=self.project, publisher=self.publisher)

            # Check if there is a pending SEOActionPlan
            proposed_plan = SEOActionPlan.objects.filter(
                project=self.project,
                status=ActionPlanStatus.PROPOSED
            ).order_by('-created_at').first()

            if proposed_plan:
                proposed_plan.status = ActionPlanStatus.APPROVED
                if self.user and getattr(self.user, 'is_authenticated', False) and self.user.id == self.project.owner_id:
                    proposed_plan.approved_by = self.user
                    proposed_plan.approved_at = timezone.now()
                proposed_plan.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

                for plan_action in proposed_plan.actions.filter(status__in=[ActionStatus.PROPOSED, ActionStatus.PENDING_APPROVAL]):
                    plan_action.status = ActionStatus.APPROVED
                    plan_action.approved_by = proposed_plan.approved_by
                    plan_action.approved_at = proposed_plan.approved_at
                    plan_action.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
                    try:
                        executor.execute(plan_action, user=self.user, run_id=run.id)
                    except Exception as e:
                        logger.error(f"Execution error for plan action #{plan_action.id}: {e}")

                verifier.verify_plan(proposed_plan, run_id=run.id)

            # Execute single proposed action if exists
            proposed_action = SEOAction.objects.filter(
                project=self.project,
                status=ActionStatus.PROPOSED
            ).order_by('-created_at').first()

            if proposed_action:
                proposed_action.status = ActionStatus.APPROVED
                if self.user and getattr(self.user, 'is_authenticated', False) and self.user.id == self.project.owner_id:
                    proposed_action.approved_by = self.user
                    proposed_action.approved_at = timezone.now()
                proposed_action.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
                try:
                    executor.execute(proposed_action, user=self.user, run_id=run.id)
                    verifier.verify_action(proposed_action, run_id=run.id)
                except Exception as e:
                    logger.error(f"Execution error for action #{proposed_action.id}: {e}")

            if latest_step:
                latest_step.status = AgentStepStatus.COMPLETED
                latest_step.thought += "\n[Human Approval]: SEO Action/Plan was reviewed, approved, executed, and verified."
                latest_step.save()

            # Emit approval.approved event
            self._emit_event(
                run,
                AgentEventType.APPROVAL_APPROVED,
                {
                    "action_id": proposed_action.id if proposed_action else None,
                    "plan_id": proposed_plan.id if proposed_plan else None,
                    "action_type": proposed_action.action_type if proposed_action else None
                },
                step_number=step_num
            )

            run.status = AgentRunStatus.RUNNING
            run.save()
            return self.execute_loop(run)
        else:
            logger.info(f"AgentRun #{run.id} rejected by user. Terminating run.")

            # Mark proposed plan as rejected if exists
            proposed_plan = SEOActionPlan.objects.filter(
                project=self.project,
                status=ActionPlanStatus.PROPOSED
            ).order_by('-created_at').first()
            if proposed_plan:
                proposed_plan.status = ActionPlanStatus.REJECTED
                if self.user and getattr(self.user, 'is_authenticated', False):
                    proposed_plan.rejected_by = self.user
                    proposed_plan.rejected_at = timezone.now()
                    proposed_plan.rejection_reason = "Rejected by user during agent execution."
                proposed_plan.save(update_fields=['status', 'rejected_by', 'rejected_at', 'rejection_reason', 'updated_at'])
                for plan_action in proposed_plan.actions.filter(status=ActionStatus.PROPOSED):
                    plan_action.status = ActionStatus.REJECTED
                    plan_action.rejected_by = proposed_plan.rejected_by
                    plan_action.rejected_at = proposed_plan.rejected_at
                    plan_action.rejection_reason = proposed_plan.rejection_reason
                    plan_action.save(update_fields=['status', 'rejected_by', 'rejected_at', 'rejection_reason', 'updated_at'])

            # Mark proposed action as rejected
            proposed_action = SEOAction.objects.filter(
                project=self.project,
                status=ActionStatus.PROPOSED
            ).order_by('-created_at').first()

            if proposed_action:
                proposed_action.status = ActionStatus.REJECTED
                if self.user and getattr(self.user, 'is_authenticated', False):
                    proposed_action.rejected_by = self.user
                    proposed_action.rejected_at = timezone.now()
                    proposed_action.rejection_reason = "Rejected by user during agent execution."
                proposed_action.save(update_fields=['status', 'rejected_by', 'rejected_at', 'rejection_reason', 'updated_at'])

            if latest_step:
                latest_step.status = AgentStepStatus.FAILED
                latest_step.thought += "\n[Human Rejection]: Proposed SEO Action was rejected by user."
                latest_step.save()

            run.status = AgentRunStatus.CANCELLED
            run.summary = f"Run terminated because human user rejected the proposed SEO Action."
            run.completed_at = timezone.now()

            # Emit approval.rejected and agent.cancelled events
            self._emit_event(
                run,
                AgentEventType.APPROVAL_REJECTED,
                {
                    "action_id": proposed_action.id if proposed_action else None,
                    "action_type": proposed_action.action_type if proposed_action else None
                },
                step_number=step_num
            )
            self._emit_event(
                run,
                AgentEventType.AGENT_CANCELLED,
                {
                    "summary": run.summary
                },
                step_number=step_num
            )

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

            self._emit_event(
                run,
                AgentEventType.AGENT_FAILED,
                {
                    "summary": run.summary,
                    "reason": "max_steps_exceeded",
                    "max_steps": run.max_steps
                },
                step_number=run.total_steps
            )
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

            self._emit_event(
                run,
                AgentEventType.AGENT_FAILED,
                {
                    "summary": run.summary,
                    "error": str(exc)
                },
                step_number=run.total_steps + 1
            )
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

            self._emit_event(
                run,
                AgentEventType.STEP_FAILED,
                {
                    "step_number": step_num,
                    "error": "malformed_ai_decision"
                },
                step_number=step_num
            )
            self._emit_event(
                run,
                AgentEventType.AGENT_FAILED,
                {
                    "summary": run.summary,
                    "error": "malformed_ai_decision"
                },
                step_number=step_num
            )
            run.save()
            return False

        # Handle Finish Action
        if decision["action"] == "finish":
            summary = decision.get("summary") or "Goal completed."
            reason = decision.get("reason") or "Goal successfully achieved."
            step_num = run.total_steps + 1

            self._emit_event(
                run,
                AgentEventType.STEP_STARTED,
                {
                    "step_number": step_num,
                    "action_type": "finish"
                },
                step_number=step_num
            )

            AgentStep.objects.create(
                run=run,
                step_number=step_num,
                thought=reason,
                action_type=AgentActionType.FINAL,
                status=AgentStepStatus.COMPLETED,
                completed_at=timezone.now()
            )

            self._emit_event(
                run,
                AgentEventType.STEP_COMPLETED,
                {
                    "step_number": step_num,
                    "action_type": "finish",
                    "reason": reason
                },
                step_number=step_num
            )

            run.total_steps += 1
            run.status = AgentRunStatus.COMPLETED
            run.summary = summary
            run.completed_at = timezone.now()

            self._emit_event(
                run,
                AgentEventType.AGENT_COMPLETED,
                {
                    "summary": summary,
                    "total_steps": run.total_steps
                },
                step_number=step_num
            )
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

            self._emit_event(
                run,
                AgentEventType.STEP_STARTED,
                {
                    "step_number": step_num,
                    "action_type": "tool",
                    "tool_name": tool_name
                },
                step_number=step_num
            )

            AgentStep.objects.create(
                run=run,
                step_number=step_num,
                thought=f"Detected repetitive tool loop on '{tool_name}'. Terminating run safely.",
                action_type=AgentActionType.DECISION,
                status=AgentStepStatus.FAILED,
                completed_at=timezone.now()
            )

            self._emit_event(
                run,
                AgentEventType.STEP_FAILED,
                {
                    "step_number": step_num,
                    "tool_name": tool_name,
                    "error": f"Repetitive tool failure loop on '{tool_name}'"
                },
                step_number=step_num
            )

            run.total_steps += 1
            run.status = AgentRunStatus.FAILED
            run.summary = f"Terminated due to repetitive tool loop on tool '{tool_name}'."
            run.completed_at = timezone.now()

            self._emit_event(
                run,
                AgentEventType.AGENT_FAILED,
                {
                    "summary": run.summary,
                    "error": "repetitive_tool_loop"
                },
                step_number=step_num
            )
            run.save()
            return False

        # Step Started Event & Record
        step_num = run.total_steps + 1
        self._emit_event(
            run,
            AgentEventType.STEP_STARTED,
            {
                "step_number": step_num,
                "action_type": "tool_call",
                "tool_name": tool_name
            },
            step_number=step_num
        )

        step = AgentStep.objects.create(
            run=run,
            step_number=step_num,
            thought=reason,
            action_type=AgentActionType.TOOL_CALL,
            status=AgentStepStatus.RUNNING
        )

        # Tool Started Event
        self._emit_event(
            run,
            AgentEventType.TOOL_STARTED,
            {
                "step_number": step_num,
                "tool_name": tool_name,
                "arguments": arguments
            },
            step_number=step_num
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

        # Tool Completed / Failed Event
        if exec_res["success"]:
            self._emit_event(
                run,
                AgentEventType.TOOL_COMPLETED,
                {
                    "step_number": step_num,
                    "tool_name": tool_name,
                    "duration_ms": exec_res.get("duration_ms", 0),
                    "success": True
                },
                step_number=step_num
            )
            self._emit_event(
                run,
                AgentEventType.STEP_COMPLETED,
                {
                    "step_number": step_num,
                    "tool_name": tool_name,
                    "success": True
                },
                step_number=step_num
            )
        else:
            self._emit_event(
                run,
                AgentEventType.TOOL_FAILED,
                {
                    "step_number": step_num,
                    "tool_name": tool_name,
                    "duration_ms": exec_res.get("duration_ms", 0),
                    "success": False,
                    "error_code": exec_res.get("error", {}).get("code", "EXECUTION_ERROR"),
                    "error_message": exec_res.get("error", {}).get("message", "")
                },
                step_number=step_num
            )
            self._emit_event(
                run,
                AgentEventType.STEP_FAILED,
                {
                    "step_number": step_num,
                    "tool_name": tool_name,
                    "error": exec_res.get("error", {}).get("message", "")
                },
                step_number=step_num
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

                action_data = exec_res.get("data") or {}
                self._emit_event(
                    run,
                    AgentEventType.APPROVAL_REQUIRED,
                    {
                        "action_id": action_data.get("id"),
                        "action_type": action_data.get("action_type"),
                        "requires_human_approval": True,
                        "title": action_data.get("title")
                    },
                    step_number=step_num
                )
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
