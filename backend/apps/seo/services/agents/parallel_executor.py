"""
DoxaRank Parallel Agent Execution & Bounded Batch Scheduling (Milestone 5.4).

Provides bounded, concurrent in-process execution of independent AgentTasks using
ThreadPoolExecutor. Guarantees DAG dependency preservation, task state safety,
failure isolation, runtime execution overlap measurement, and deterministic synchronization.
"""

import concurrent.futures
import copy
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from django.utils import timezone

from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher
)
from .base_agent import BaseSpecializedAgent, AgentResult, SharedContext
from .agent_handoff import AgentHandoffContext, AgentHandoffValidator, AgentHandoffValidationError
from .task_planner import AgentTask, TaskPlan, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class TaskExecutionTiming:
    """Precise timing record for an individual task in an execution batch."""
    task_id: str
    agent_name: str
    start_time: float
    end_time: float
    duration_ms: int = 0
    start_iso: str = field(default_factory=lambda: timezone.now().isoformat())
    end_iso: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "start_iso": self.start_iso,
            "end_iso": self.end_iso,
        }


@dataclass
class ParallelExecutionBatch:
    """
    Structured container for a bounded group of concurrently executing AgentTasks.
    Enables observability, failure isolation, and performance evaluation.
    """
    batch_id: str
    plan_id: str
    project_id: int
    task_ids: List[str] = field(default_factory=list)
    agent_names: List[str] = field(default_factory=list)
    status: str = "pending"  # "pending" | "running" | "completed" | "partial_failure" | "failed" | "cancelled"
    started_at: str = field(default_factory=lambda: timezone.now().isoformat())
    completed_at: Optional[str] = None
    successful_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)
    cancelled_tasks: List[str] = field(default_factory=list)
    max_concurrency: int = 3
    overlap_detected: bool = False
    overlap_duration_ms: int = 0
    duration_ms: int = 0
    task_timings: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "task_ids": list(self.task_ids),
            "tasks": list(self.task_ids),
            "agent_names": list(self.agent_names),
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "successful_tasks": list(self.successful_tasks),
            "failed_tasks": list(self.failed_tasks),
            "cancelled_tasks": list(self.cancelled_tasks),
            "max_concurrency": self.max_concurrency,
            "concurrency_limit": self.max_concurrency,
            "overlap_detected": self.overlap_detected,
            "overlap_duration_ms": self.overlap_duration_ms,
            "duration_ms": self.duration_ms,
            "task_timings": dict(self.task_timings),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParallelExecutionBatch":
        return cls(
            batch_id=data.get("batch_id", f"batch-{uuid.uuid4().hex[:8]}"),
            plan_id=data.get("plan_id", ""),
            project_id=data.get("project_id", 0),
            task_ids=data.get("task_ids", data.get("tasks", [])),
            agent_names=data.get("agent_names", []),
            status=data.get("status", "pending"),
            started_at=data.get("started_at", timezone.now().isoformat()),
            completed_at=data.get("completed_at"),
            successful_tasks=data.get("successful_tasks", []),
            failed_tasks=data.get("failed_tasks", []),
            cancelled_tasks=data.get("cancelled_tasks", []),
            max_concurrency=data.get("max_concurrency", data.get("concurrency_limit", 3)),
            overlap_detected=data.get("overlap_detected", False),
            overlap_duration_ms=data.get("overlap_duration_ms", 0),
            duration_ms=data.get("duration_ms", 0),
            task_timings=data.get("task_timings", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class BatchExecutionResult:
    """Results collected from a completed parallel execution batch."""
    batch: ParallelExecutionBatch
    task_results: Dict[str, AgentResult] = field(default_factory=dict)  # task_id -> AgentResult
    timings: Dict[str, TaskExecutionTiming] = field(default_factory=dict)  # task_id -> TaskExecutionTiming
    handoffs: Dict[str, AgentHandoffContext] = field(default_factory=dict)  # task_id -> AgentHandoffContext
    errors: Dict[str, str] = field(default_factory=dict)  # task_id -> error string


class ParallelBatchExecutor:
    """
    Executes a batch of independent AgentTasks concurrently within the bounds of max_parallel_tasks.
    Uses ThreadPoolExecutor to overlap I/O and CPU work while maintaining strict task isolation,
    tool authorization boundaries, and handoff validity.
    """

    def __init__(self, max_parallel_tasks: int = 3):
        self.max_parallel_tasks = max(1, int(max_parallel_tasks))

    def execute_batch(
        self,
        batch: ParallelExecutionBatch,
        tasks: List[AgentTask],
        agents: Dict[str, BaseSpecializedAgent],
        context: SharedContext,
        handoffs: Dict[str, AgentHandoffContext],
        publisher: Optional[AgentEventPublisher] = None,
        correlation_id: str = ""
    ) -> BatchExecutionResult:
        """
        Execute the given list of AgentTasks concurrently.
        Synchronizes at completion, detects runtime overlap, and returns all results.
        """
        pub = publisher or get_event_publisher()
        batch_start_mono = time.monotonic()
        batch.started_at = timezone.now().isoformat()
        batch.status = "running"

        result = BatchExecutionResult(batch=batch, handoffs=handoffs)
        num_workers = min(len(tasks), self.max_parallel_tasks)

        def _execute_single_task(
            task: AgentTask,
            handoff: AgentHandoffContext,
            task_context: Optional[SharedContext] = None
        ) -> Tuple[str, AgentResult, TaskExecutionTiming, Optional[str]]:
            """Thread worker executing a single specialized agent task."""
            agent_key = task.responsible_agent
            agent = agents.get(agent_key)
            if not agent:
                err = f"Agent '{agent_key}' not found for task '{task.task_id}'."
                failed_res = AgentResult(
                    agent=agent_key,
                    status="failed",
                    confidence=0.0,
                    errors=[err]
                )
                timing = TaskExecutionTiming(
                    task_id=task.task_id,
                    agent_name=agent_key,
                    start_time=time.monotonic(),
                    end_time=time.monotonic(),
                    duration_ms=0,
                    end_iso=timezone.now().isoformat()
                )
                return task.task_id, failed_res, timing, err

            # Create a thread-local scoped context view to avoid cross-thread collision on current_agent
            if task_context is None:
                if len(tasks) == 1:
                    task_context = context
                else:
                    task_context = copy.copy(context)
            task_context.current_agent = agent.name
            task_context.task_goal = task.objective

            start_mono = time.monotonic()
            start_iso = timezone.now().isoformat()

            try:
                if threading.current_thread() is not threading.main_thread():
                    from django.db import close_old_connections
                    close_old_connections()
                # Pre-execution validation
                AgentHandoffValidator.validate(handoff, expected_project_id=context.project_id)

                agent_result = agent.run(task_context, handoff=handoff)
                end_mono = time.monotonic()
                end_iso = timezone.now().isoformat()
                dur_ms = int((end_mono - start_mono) * 1000)

                # Synchronize any agent mutations on task_context back to shared context
                if task_context is not context:
                    if getattr(task_context, "created_plan_id", None):
                        context.created_plan_id = task_context.created_plan_id
                    if getattr(task_context, "action_plan_id", None):
                        context.action_plan_id = task_context.action_plan_id
                    if getattr(task_context, "action_proposals", None):
                        for ap in task_context.action_proposals:
                            if ap not in context.action_proposals:
                                context.action_proposals.append(ap)
                    if getattr(task_context, "investigation_findings", None):
                        for inv in task_context.investigation_findings:
                            if inv not in context.investigation_findings:
                                context.investigation_findings.append(inv)
                    if getattr(task_context, "strategy_signals", None):
                        context.strategy_signals.update(task_context.strategy_signals)

                timing = TaskExecutionTiming(
                    task_id=task.task_id,
                    agent_name=agent.name,
                    start_time=start_mono,
                    end_time=end_mono,
                    duration_ms=dur_ms,
                    start_iso=start_iso,
                    end_iso=end_iso
                )
                error_msg = None
                if agent_result.status == "failed":
                    error_msg = "; ".join(agent_result.errors) if agent_result.errors else "Agent execution failed."

                return task.task_id, agent_result, timing, error_msg

            except Exception as exc:
                end_mono = time.monotonic()
                end_iso = timezone.now().isoformat()
                dur_ms = int((end_mono - start_mono) * 1000)
                err = f"Task execution exception: {str(exc)}"
                logger.exception(f"[{task.task_id}] {err}")

                failed_res = AgentResult(
                    agent=agent.name,
                    status="failed",
                    confidence=0.0,
                    errors=[err],
                    duration_ms=dur_ms
                )
                timing = TaskExecutionTiming(
                    task_id=task.task_id,
                    agent_name=agent.name,
                    start_time=start_mono,
                    end_time=end_mono,
                    duration_ms=dur_ms,
                    start_iso=start_iso,
                    end_iso=end_iso
                )
                return task.task_id, failed_res, timing, err
            finally:
                if threading.current_thread() is not threading.main_thread():
                    try:
                        from django.db import close_old_connections
                        close_old_connections()
                    except Exception:
                        pass

        # If single task, execute synchronously on current thread to preserve caller transaction & eliminate overhead
        if len(tasks) == 1:
            task = tasks[0]
            try:
                tid, agent_result, timing, error_msg = _execute_single_task(task, handoffs[task.task_id], task_context=context)
                result.task_results[tid] = agent_result
                result.timings[tid] = timing
                if error_msg:
                    result.errors[tid] = error_msg
            except Exception as exc:
                err = f"Execution exception on task {task.task_id}: {exc}"
                logger.exception(err)
                result.errors[task.task_id] = err
                result.task_results[task.task_id] = AgentResult(
                    agent=task.responsible_agent,
                    status="failed",
                    confidence=0.0,
                    errors=[err]
                )
                result.timings[task.task_id] = TaskExecutionTiming(
                    task_id=task.task_id,
                    agent_name=task.responsible_agent,
                    start_time=batch_start_mono,
                    end_time=time.monotonic(),
                    duration_ms=int((time.monotonic() - batch_start_mono) * 1000)
                )
        elif num_workers == 1:
            for task in tasks:
                try:
                    tid, agent_result, timing, error_msg = _execute_single_task(task, handoffs[task.task_id], task_context=context)
                    result.task_results[tid] = agent_result
                    result.timings[tid] = timing
                    if error_msg:
                        result.errors[tid] = error_msg
                except Exception as exc:
                    err = f"Execution exception on task {task.task_id}: {exc}"
                    logger.exception(err)
                    result.errors[task.task_id] = err
                    result.task_results[task.task_id] = AgentResult(
                        agent=task.responsible_agent,
                        status="failed",
                        confidence=0.0,
                        errors=[err]
                    )
                    result.timings[task.task_id] = TaskExecutionTiming(
                        task_id=task.task_id,
                        agent_name=task.responsible_agent,
                        start_time=batch_start_mono,
                        end_time=time.monotonic(),
                        duration_ms=int((time.monotonic() - batch_start_mono) * 1000)
                    )
        else:
            # Concurrently execute tasks using bounded thread pool
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                future_to_task = {
                    executor.submit(_execute_single_task, task, handoffs[task.task_id]): task
                    for task in tasks
                }

                for future in concurrent.futures.as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        tid, agent_result, timing, error_msg = future.result()
                        result.task_results[tid] = agent_result
                        result.timings[tid] = timing
                        if error_msg:
                            result.errors[tid] = error_msg
                    except Exception as exc:
                        err = f"Thread pool unhandled exception on task {task.task_id}: {exc}"
                        logger.exception(err)
                        result.errors[task.task_id] = err
                        result.task_results[task.task_id] = AgentResult(
                            agent=task.responsible_agent,
                            status="failed",
                            confidence=0.0,
                            errors=[err]
                        )
                        result.timings[task.task_id] = TaskExecutionTiming(
                            task_id=task.task_id,
                            agent_name=task.responsible_agent,
                            start_time=batch_start_mono,
                            end_time=time.monotonic(),
                            duration_ms=int((time.monotonic() - batch_start_mono) * 1000)
                        )

        # Batch completion & timing synchronization
        batch_end_mono = time.monotonic()
        batch.completed_at = timezone.now().isoformat()
        batch.duration_ms = int((batch_end_mono - batch_start_mono) * 1000)

        # Determine task successes and failures
        for task in tasks:
            tid = task.task_id
            res = result.task_results.get(tid)
            if res and res.status == "completed" and tid not in result.errors:
                batch.successful_tasks.append(tid)
            else:
                batch.failed_tasks.append(tid)

        # Set final batch status
        if len(batch.failed_tasks) == 0:
            batch.status = "completed"
        elif len(batch.successful_tasks) > 0:
            batch.status = "partial_failure"
        else:
            batch.status = "failed"

        # Calculate empirical execution overlap
        # Two tasks overlap if max(start_A, start_B) < min(end_A, end_B)
        overlap_ms = 0
        overlap_found = False
        timing_list = list(result.timings.values())
        if len(timing_list) >= 2:
            for i in range(len(timing_list)):
                for j in range(i + 1, len(timing_list)):
                    t1 = timing_list[i]
                    t2 = timing_list[j]
                    latest_start = max(t1.start_time, t2.start_time)
                    earliest_end = min(t1.end_time, t2.end_time)
                    if latest_start < earliest_end:
                        overlap_found = True
                        dur = int((earliest_end - latest_start) * 1000)
                        if dur > overlap_ms:
                            overlap_ms = dur

        batch.overlap_detected = overlap_found
        batch.overlap_duration_ms = overlap_ms
        batch.task_timings = {t.task_id: t.to_dict() for t in timing_list}
        batch.metadata["timings"] = dict(batch.task_timings)

        return result
