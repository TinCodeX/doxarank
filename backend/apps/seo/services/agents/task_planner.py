"""
DoxaRank Dynamic Task Decomposition & Collaborative Planning (Phase 5.3).

Provides a structured, inspectable, bounded, and role-assigned task planning
abstraction for multi-agent SEO workflows. Decomposes high-level goals into
directed acyclic graphs (DAGs) of subtasks, evaluates dependency readiness,
assigns specialized agents, manages explicit state transitions, and performs
bounded adaptive replanning under strict human approval boundaries.
"""

import hashlib
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from django.utils import timezone

from .agent_handoff import KNOWN_AGENTS
from .shared_memory import (
    SharedWorkingMemory,
    ConflictStatus,
    redact_secrets,
)

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Lifecycle states for an individual AgentTask."""
    PENDING = "pending"        # Awaiting dependencies to be satisfied
    READY = "ready"            # All dependencies completed, eligible for execution
    RUNNING = "running"        # Currently being executed by assigned agent
    COMPLETED = "completed"    # Successfully executed with verified findings
    BLOCKED = "blocked"        # Cannot proceed because a dependency failed or was cancelled
    FAILED = "failed"          # Execution failed with error
    SKIPPED = "skipped"        # Deliberately bypassed during adaptive replanning
    CANCELLED = "cancelled"    # Aborted due to workflow termination or conflict


# Deterministic state transition validation matrix
VALID_TASK_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.SKIPPED, TaskStatus.CANCELLED},
    TaskStatus.READY: {TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.SKIPPED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.BLOCKED: {TaskStatus.READY, TaskStatus.PENDING, TaskStatus.CANCELLED, TaskStatus.SKIPPED},
    TaskStatus.FAILED: {TaskStatus.READY, TaskStatus.CANCELLED},  # Allows bounded retry
    TaskStatus.COMPLETED: set(),  # Terminal state
    TaskStatus.SKIPPED: set(),    # Terminal state
    TaskStatus.CANCELLED: set(),  # Terminal state
}


class TaskPriority(str, Enum):
    """Deterministic priority levels for scheduling ready tasks."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReplanReason(str, Enum):
    """Explicit domain triggers that justify adaptive replanning."""
    NEW_EVIDENCE = "new_evidence"
    TASK_FAILURE = "task_failure"
    CONFLICT_DETECTED = "conflict_detected"
    VERIFICATION_FAILURE = "verification_failure"
    MISSING_INFORMATION = "missing_information"
    DEPENDENCY_FAILURE = "dependency_failure"
    STRATEGY_CHANGE = "strategy_change"


class TaskPlanningError(Exception):
    """Base exception for task graph and planning errors."""
    pass


class CircularDependencyError(TaskPlanningError):
    """Raised when a task dependency cycle is detected."""
    pass


class InvalidTaskTransitionError(TaskPlanningError):
    """Raised when an illegal task lifecycle state transition is attempted."""
    pass


class PlanLimitExceededError(TaskPlanningError):
    """Raised when plan bounds (e.g. max_dependency_depth, max_tasks_per_plan) are exceeded."""
    pass


class PlanBudgetExceededError(TaskPlanningError):
    """Raised when planning budget limits (e.g. max_replans, max_planning_rounds) are exceeded."""
    pass


@dataclass
class PlanBudgetConfig:
    """
    Deterministic safety limits protecting against planning explosions
    and runaway replanning loops.
    """
    max_tasks_per_plan: int = 20
    max_planning_rounds: int = 3
    max_replans: int = 2
    max_dependency_depth: int = 8
    max_agent_executions: int = 25


@dataclass
class AgentTask:
    """
    A single typed, role-assigned, and dependency-bounded unit of work.
    """
    task_id: str
    objective: str
    description: str
    responsible_agent: str
    priority: str = TaskPriority.MEDIUM.value
    dependencies: List[str] = field(default_factory=list)  # List of prerequisite task_ids
    required_evidence: List[str] = field(default_factory=list)
    status: str = TaskStatus.PENDING.value
    created_by: str = "planner"
    correlation_id: str = ""
    reason: str = ""
    result_summary: Optional[str] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: timezone.now().isoformat())
    updated_at: str = field(default_factory=lambda: timezone.now().isoformat())
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Validate agent assignment against known agent registry
        if self.responsible_agent not in KNOWN_AGENTS and self.responsible_agent != "seo_supervisor":
            raise TaskPlanningError(
                f"Invalid agent '{self.responsible_agent}' assigned to task '{self.task_id}'. "
                f"Must be one of {KNOWN_AGENTS}"
            )
        # Redact secrets on ingest
        self.objective = redact_secrets(self.objective)
        self.description = redact_secrets(self.description)
        self.reason = redact_secrets(self.reason)
        if self.result_summary:
            self.result_summary = redact_secrets(self.result_summary)
        if self.metadata:
            self.metadata = redact_secrets(self.metadata)

    def transition_to(self, new_status: TaskStatus, error: Optional[str] = None, result_summary: Optional[str] = None) -> None:
        """Enforces validated task state progression."""
        curr_enum = TaskStatus(self.status)
        new_enum = TaskStatus(new_status)

        if new_enum != curr_enum and new_enum not in VALID_TASK_TRANSITIONS.get(curr_enum, set()):
            raise InvalidTaskTransitionError(
                f"Illegal transition for task '{self.task_id}': cannot move from '{curr_enum.value}' to '{new_enum.value}'"
            )

        self.status = new_enum.value
        self.updated_at = timezone.now().isoformat()
        if error:
            self.error = redact_secrets(str(error))
        if result_summary:
            self.result_summary = redact_secrets(str(result_summary))
        if new_enum == TaskStatus.COMPLETED:
            self.completed_at = timezone.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "description": self.description,
            "responsible_agent": self.responsible_agent,
            "priority": self.priority,
            "dependencies": list(self.dependencies),
            "required_evidence": list(self.required_evidence),
            "status": self.status,
            "created_by": self.created_by,
            "correlation_id": self.correlation_id,
            "reason": self.reason,
            "result_summary": self.result_summary,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTask":
        return cls(
            task_id=data.get("task_id", f"task-{uuid.uuid4().hex[:8]}"),
            objective=data.get("objective", ""),
            description=data.get("description", ""),
            responsible_agent=data.get("responsible_agent", "seo_researcher"),
            priority=data.get("priority", TaskPriority.MEDIUM.value),
            dependencies=data.get("dependencies", []),
            required_evidence=data.get("required_evidence", []),
            status=data.get("status", TaskStatus.PENDING.value),
            created_by=data.get("created_by", "planner"),
            correlation_id=data.get("correlation_id", ""),
            reason=data.get("reason", ""),
            result_summary=data.get("result_summary"),
            error=data.get("error"),
            created_at=data.get("created_at", timezone.now().isoformat()),
            updated_at=data.get("updated_at", timezone.now().isoformat()),
            completed_at=data.get("completed_at"),
            metadata=data.get("metadata", {})
        )


class TaskPlan:
    """
    A validated, bounded Directed Acyclic Graph (DAG) of AgentTasks representing
    an orchestrated multi-agent workflow.
    """

    def __init__(
        self,
        project_id: int,
        user_goal: Optional[str] = None,
        correlation_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        budget_config: Optional[PlanBudgetConfig] = None,
        goal: Optional[str] = None,
        budget: Optional[PlanBudgetConfig] = None
    ):
        if project_id <= 0:
            raise TaskPlanningError(f"TaskPlan requires a valid project_id > 0, got {project_id}")
        
        actual_corr_id = correlation_id or f"corr-plan-{uuid.uuid4().hex[:8]}"
        self.plan_id = plan_id or f"plan-{uuid.uuid4().hex[:8]}"
        self.project_id = project_id
        actual_goal = user_goal or goal or ""
        self.user_goal = redact_secrets(actual_goal)
        self.goal = self.user_goal
        self.correlation_id = actual_corr_id
        self.budget_config = budget_config or budget or PlanBudgetConfig()

        self._tasks: Dict[str, AgentTask] = {}  # task_id -> AgentTask
        self.planning_rounds: int = 1
        self.replans_count: int = 0
        self.replan_history: List[Dict[str, Any]] = []
        self.created_at: str = timezone.now().isoformat()
        self.updated_at: str = timezone.now().isoformat()

    def add_task(self, task: AgentTask) -> None:
        """Add an AgentTask to the plan with budget enforcement."""
        if len(self._tasks) >= self.budget_config.max_tasks_per_plan:
            logger.warning(f"[{self.plan_id}] Plan task budget limit reached ({self.budget_config.max_tasks_per_plan}).")
            raise PlanLimitExceededError(
                f"Task budget limit exceeded: maximum {self.budget_config.max_tasks_per_plan} tasks allowed per plan."
            )

        task.correlation_id = self.correlation_id
        self._tasks[task.task_id] = task
        self.updated_at = timezone.now().isoformat()

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        return self._tasks.get(task_id)

    @property
    def tasks(self) -> Dict[str, AgentTask]:
        return self._tasks

    def validate_graph(self) -> bool:
        """
        Validate the complete task graph:
        1. All dependencies refer to known tasks in this plan.
        2. No circular dependencies exist (Kahn's algorithm).
        3. All agents belong to the KNOWN_AGENTS allowlist.
        4. Dependency depth does not exceed max_dependency_depth.
        """
        # 1. Dependency existence check
        for task in self._tasks.values():
            for dep_id in task.dependencies:
                if dep_id not in self._tasks:
                    raise TaskPlanningError(
                        f"Task '{task.task_id}' depends on non-existent task '{dep_id}' in plan '{self.plan_id}'"
                    )

        # 2. Cycle detection via Kahn's algorithm
        in_degree: Dict[str, int] = {t_id: 0 for t_id in self._tasks}
        adjacency: Dict[str, List[str]] = {t_id: [] for t_id in self._tasks}

        for task in self._tasks.values():
            for dep_id in task.dependencies:
                adjacency[dep_id].append(task.task_id)
                in_degree[task.task_id] += 1

        queue = [t_id for t_id, deg in in_degree.items() if deg == 0]
        visited_count = 0

        while queue:
            node = queue.pop(0)
            visited_count += 1
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(self._tasks):
            cyclic_tasks = [t_id for t_id, deg in in_degree.items() if deg > 0]
            raise CircularDependencyError(
                f"Circular dependency detected in plan '{self.plan_id}' involving tasks: {cyclic_tasks}"
            )

        # 3. Agent allowlist validation
        for task in self._tasks.values():
            if task.responsible_agent not in KNOWN_AGENTS:
                raise TaskPlanningError(
                    f"Task '{task.task_id}' assigned to unknown agent '{task.responsible_agent}'"
                )

        # 4. Dependency depth check
        depths: Dict[str, int] = {}

        def get_depth(t_id: str, visited: Set[str]) -> int:
            if t_id in depths:
                return depths[t_id]
            task = self._tasks[t_id]
            if not task.dependencies:
                depths[t_id] = 1
                return 1
            visited.add(t_id)
            max_d = 1 + max(get_depth(d, visited.copy()) for d in task.dependencies)
            depths[t_id] = max_d
            return max_d

        for t_id in self._tasks:
            d = get_depth(t_id, set())
            if d > self.budget_config.max_dependency_depth:
                raise PlanLimitExceededError(
                    f"Task '{t_id}' exceeds maximum allowed depth {self.budget_config.max_dependency_depth} (depth={d})"
                )

        return True

    def get_ready_tasks(self) -> List[AgentTask]:
        """
        Returns all tasks currently eligible for execution:
        - Must have status == PENDING or READY
        - All declared dependencies must have status == COMPLETED
        """
        ready: List[AgentTask] = []
        for task in self._tasks.values():
            if task.status not in [TaskStatus.PENDING.value, TaskStatus.READY.value]:
                continue

            all_deps_satisfied = True
            for dep_id in task.dependencies:
                dep_task = self._tasks.get(dep_id)
                if not dep_task or dep_task.status != TaskStatus.COMPLETED.value:
                    all_deps_satisfied = False
                    break

            if all_deps_satisfied:
                if task.status == TaskStatus.PENDING.value:
                    task.transition_to(TaskStatus.READY)
                ready.append(task)

        # Sort ready tasks deterministically by priority
        priority_order = {
            TaskPriority.CRITICAL.value: 0,
            TaskPriority.HIGH.value: 1,
            TaskPriority.MEDIUM.value: 2,
            TaskPriority.LOW.value: 3
        }
        ready.sort(key=lambda t: (priority_order.get(t.priority, 2), t.created_at))
        return ready

    def handle_task_failure(self, failed_task_id: str, error_message: str = "") -> List[str]:
        """
        When a task fails, mark it FAILED and cascade BLOCKED status to all downstream
        dependent tasks to prevent phantom completions or corrupted state.
        Returns list of newly blocked task IDs.
        """
        failed_task = self._tasks.get(failed_task_id)
        if failed_task and failed_task.status != TaskStatus.FAILED.value:
            failed_task.transition_to(TaskStatus.FAILED, error=error_message)

        blocked_ids: List[str] = []
        queue = [failed_task_id]

        while queue:
            curr_id = queue.pop(0)
            for task in self._tasks.values():
                if curr_id in task.dependencies and task.status in [TaskStatus.PENDING.value, TaskStatus.READY.value]:
                    task.transition_to(
                        TaskStatus.BLOCKED,
                        error=f"Dependency '{curr_id}' failed: {error_message}"
                    )
                    blocked_ids.append(task.task_id)
                    queue.append(task.task_id)

        self.updated_at = timezone.now().isoformat()
        return blocked_ids

    def get_topological_sort(self) -> List[str]:
        """Return task IDs sorted in topological execution order."""
        self.validate_graph()
        in_degree: Dict[str, int] = {t_id: 0 for t_id in self._tasks}
        adjacency: Dict[str, List[str]] = {t_id: [] for t_id in self._tasks}

        for task in self._tasks.values():
            for dep_id in task.dependencies:
                adjacency[dep_id].append(task.task_id)
                in_degree[task.task_id] += 1

        queue = [t_id for t_id, deg in in_degree.items() if deg == 0]
        order: List[str] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return order

    def get_parallel_groups(self) -> List[List[str]]:
        """
        Partition tasks into sequential tiers where tasks within the same tier
        are independent and can conceptually run in parallel.
        """
        self.validate_graph()
        depths: Dict[str, int] = {}

        def get_depth(t_id: str) -> int:
            if t_id in depths:
                return depths[t_id]
            task = self._tasks[t_id]
            if not task.dependencies:
                depths[t_id] = 0
                return 0
            d = 1 + max(get_depth(dep_id) for dep_id in task.dependencies)
            depths[t_id] = d
            return d

        for t_id in self._tasks:
            get_depth(t_id)

        max_depth = max(depths.values()) if depths else 0
        groups: List[List[str]] = [[] for _ in range(max_depth + 1)]
        for t_id, d in depths.items():
            groups[d].append(t_id)
        return groups

    def summarize(self) -> Dict[str, Any]:
        """Generate high-level summary metrics of current plan execution state."""
        counts = {
            "total_tasks": len(self._tasks),
            "pending": sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING.value),
            "ready": sum(1 for t in self._tasks.values() if t.status == TaskStatus.READY.value),
            "running": sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING.value),
            "completed": sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED.value),
            "blocked": sum(1 for t in self._tasks.values() if t.status == TaskStatus.BLOCKED.value),
            "failed": sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED.value),
            "skipped": sum(1 for t in self._tasks.values() if t.status == TaskStatus.SKIPPED.value),
            "cancelled": sum(1 for t in self._tasks.values() if t.status == TaskStatus.CANCELLED.value),
        }
        completion_pct = round((counts["completed"] / max(counts["total_tasks"], 1)) * 100, 1)

        return {
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "correlation_id": self.correlation_id,
            "user_goal": self.user_goal,
            "goal": self.user_goal,
            "planning_rounds": self.planning_rounds,
            "replans_count": self.replans_count,
            "replan_count": self.replans_count,
            "completion_pct": completion_pct,
            "completion_rate": completion_pct,
            "completed_tasks": counts["completed"],
            "failed_tasks": counts["failed"],
            "blocked_tasks": counts["blocked"],
            "ready_tasks": counts["ready"],
            "running_tasks": counts["running"],
            "pending_tasks": counts["pending"],
            "skipped_tasks": counts["skipped"],
            "parallel_groups_count": len(self.get_parallel_groups()) if self._tasks else 0,
            **counts
        }

    def to_graph(self) -> Dict[str, Any]:
        """Export nodes and directed edges formatted for dashboard DAG rendering."""
        nodes = [
            {
                "id": t.task_id,
                "label": t.objective,
                "agent": t.responsible_agent,
                "status": t.status,
                "priority": t.priority,
                "dependencies": t.dependencies,
            }
            for t in self._tasks.values()
        ]
        edges = []
        for t in self._tasks.values():
            for dep_id in t.dependencies:
                edges.append({
                    "from": dep_id,
                    "to": t.task_id,
                })
        return {
            "plan_id": self.plan_id,
            "nodes": nodes,
            "edges": edges,
            "summary": self.summarize(),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Full serialization for storage and REST endpoints."""
        return {
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "user_goal": self.user_goal,
            "correlation_id": self.correlation_id,
            "planning_rounds": self.planning_rounds,
            "replans_count": self.replans_count,
            "replan_history": self.replan_history,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "summary": self.summarize(),
            "tasks": [t.to_dict() for t in self._tasks.values()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskPlan":
        """Deserialize from dictionary."""
        plan = cls(
            project_id=data.get("project_id", 0),
            user_goal=data.get("user_goal", ""),
            correlation_id=data.get("correlation_id", ""),
            plan_id=data.get("plan_id"),
        )
        plan.planning_rounds = data.get("planning_rounds", 1)
        plan.replans_count = data.get("replans_count", 0)
        plan.replan_history = data.get("replan_history", [])
        plan.created_at = data.get("created_at", timezone.now().isoformat())
        plan.updated_at = data.get("updated_at", timezone.now().isoformat())

        for t_data in data.get("tasks", []):
            task = AgentTask.from_dict(t_data)
            plan._tasks[task.task_id] = task

        return plan


class DynamicTaskPlanner:
    """
    Service responsible for translating high-level user goals into structured,
    inspectable, and bounded task plans (DAGs). Performs adaptive replanning
    when empirical evidence, conflicts, or failures warrant DAG modifications.
    """

    def __init__(
        self,
        budget_config: Optional[PlanBudgetConfig] = None,
        default_budget: Optional[PlanBudgetConfig] = None
    ):
        self.budget_config = budget_config or default_budget or PlanBudgetConfig()

    def decompose_goal(
        self,
        goal: str = "",
        project_id: int = 0,
        correlation_id: Optional[str] = None,
        target_url: Optional[str] = None,
        target_query: Optional[str] = None,
        shared_memory: Optional[SharedWorkingMemory] = None,
        **kwargs
    ) -> TaskPlan:
        """
        Dynamically decompose a user goal into a tailored task graph.
        Never generates unnecessary generic boilerplate; assigns each task
        to the appropriate specialized agent.
        """
        actual_corr_id = correlation_id or f"corr-plan-{uuid.uuid4().hex[:8]}"
        plan = TaskPlan(
            project_id=project_id,
            user_goal=goal,
            correlation_id=actual_corr_id,
            budget_config=self.budget_config
        )

        goal_lower = (goal or "").lower()
        url_label = target_url or "target domain"

        # 1. Investigation / Diagnostic Intent
        if any(w in goal_lower for w in ["drop", "decline", "fall", "why", "investigate", "audit", "diagnose"]):
            # Task 1: Performance evidence extraction
            t1 = AgentTask(
                task_id=f"task-res-{uuid.uuid4().hex[:6]}",
                objective=f"Extract Search Console and crawl performance evidence for {url_label}",
                description="Retrieve GSC queries, clicks, impressions, and site audit technical issues.",
                responsible_agent="seo_researcher",
                priority=TaskPriority.CRITICAL.value,
                required_evidence=["get_gsc_performance", "get_site_audit_summary"],
                reason="Empirical baseline required to establish drop magnitude and affected endpoints."
            )
            plan.add_task(t1)

            # Task 2: Ranking anomaly & query trend analysis (depends on T1)
            t2 = AgentTask(
                task_id=f"task-rank-{uuid.uuid4().hex[:6]}",
                objective=f"Analyze ranking shifts and keyword queries for {url_label}",
                description="Examine keyword ranking shifts and identify top degraded queries.",
                responsible_agent="seo_researcher",
                priority=TaskPriority.HIGH.value,
                dependencies=[t1.task_id],
                required_evidence=["get_ranking_history", "get_tracked_keywords"],
                reason="Identify specifically which queries dropped vs stable queries."
            )
            plan.add_task(t2)

            # Task 3: Technical crawl & HTTP anomaly check (depends on T1, can run parallel with T2)
            t3 = AgentTask(
                task_id=f"task-tech-{uuid.uuid4().hex[:6]}",
                objective=f"Inspect technical crawl health and HTTP response status on {url_label}",
                description="Verify status codes, robots.txt directives, canonicals, and DOM metadata.",
                responsible_agent="seo_researcher",
                priority=TaskPriority.HIGH.value,
                dependencies=[t1.task_id],
                required_evidence=["mcp__seo_local__check_url_status", "get_audit_issues"],
                reason="Rule out server errors, canonical misconfigurations, or blocking robots directives."
            )
            plan.add_task(t3)

            # Task 4: Root cause diagnostic synthesis (depends on T2 and T3)
            t4 = AgentTask(
                task_id=f"task-inv-{uuid.uuid4().hex[:6]}",
                objective="Synthesize diagnostic evidence and determine root cause hypotheses",
                description="Correlate ranking decline against technical and algorithmic factors.",
                responsible_agent="seo_investigator",
                priority=TaskPriority.CRITICAL.value,
                dependencies=[t2.task_id, t3.task_id],
                reason="Investigator synthesizes multi-source empirical evidence into validated inferences."
            )
            plan.add_task(t4)

            # Task 5: Strategic opportunity prioritization (depends on T4)
            t5 = AgentTask(
                task_id=f"task-strat-{uuid.uuid4().hex[:6]}",
                objective="Prioritize strategic remediation opportunities and calibrated win rates",
                description="Evaluate domain historical win rates to select highest impact solutions.",
                responsible_agent="seo_strategist",
                priority=TaskPriority.HIGH.value,
                dependencies=[t4.task_id],
                reason="Strategist ensures recommendations align with high-confidence historical win rates."
            )
            plan.add_task(t5)

            # If user explicitly asks for recommendations or actions, add Action Planning task
            if any(w in goal_lower for w in ["recommend", "action", "do", "fix", "plan", "solve"]):
                t6 = AgentTask(
                    task_id=f"task-plan-{uuid.uuid4().hex[:6]}",
                    objective="Stage structured action proposal with human-in-the-loop approval gate",
                    description="Draft reversible action items; strictly enforce human approval requirement.",
                    responsible_agent="seo_action_planner",
                    priority=TaskPriority.HIGH.value,
                    dependencies=[t5.task_id],
                    metadata={"requires_human_approval": True, "action_status": "proposed"},
                    reason="Draft implementation proposals under strict human approval boundary."
                )
                plan.add_task(t6)

        # 2. Pure Verification Intent
        elif any(w in goal_lower for w in ["verify", "verification", "check live", "confirm deployment"]):
            t1 = AgentTask(
                task_id=f"task-ver-{uuid.uuid4().hex[:6]}",
                objective=f"Perform live DOM verification and measurement on {url_label}",
                description="Empirically test live website state against expected outcomes.",
                responsible_agent="seo_verifier",
                priority=TaskPriority.CRITICAL.value,
                reason="Direct live verification of executed action items."
            )
            plan.add_task(t1)

        # 3. Pure Strategy / Prioritization Intent
        elif any(w in goal_lower for w in ["strategy", "prioritize", "win rate", "roi", "opportunity"]):
            t1 = AgentTask(
                task_id=f"task-res-{uuid.uuid4().hex[:6]}",
                objective=f"Gather baseline historical metrics and outcomes for {url_label}",
                description="Retrieve previous action outcomes and GSC performance.",
                responsible_agent="seo_researcher",
                priority=TaskPriority.HIGH.value,
                reason="Baseline data required for strategy calibration."
            )
            plan.add_task(t1)

            t2 = AgentTask(
                task_id=f"task-strat-{uuid.uuid4().hex[:6]}",
                objective="Calculate adaptive strategy signals and rank opportunities",
                description="Score opportunities by impact and calibrated win rate.",
                responsible_agent="seo_strategist",
                priority=TaskPriority.CRITICAL.value,
                dependencies=[t1.task_id],
                reason="Produce calibrated strategy prioritization."
            )
            plan.add_task(t2)

        # 4. Action Planning Intent
        elif any(w in goal_lower for w in ["create plan", "action plan", "propose actions", "plan steps"]):
            t1 = AgentTask(
                task_id=f"task-res-{uuid.uuid4().hex[:6]}",
                objective=f"Collect performance and crawl issues for {url_label}",
                description="Extract current audit issues and GSC query performance.",
                responsible_agent="seo_researcher",
                priority=TaskPriority.HIGH.value,
                reason="Provide factual scope for planning."
            )
            plan.add_task(t1)

            t2 = AgentTask(
                task_id=f"task-strat-{uuid.uuid4().hex[:6]}",
                objective="Filter and prioritize high-win-rate actions",
                description="Evaluate risk and win rates for candidate improvements.",
                responsible_agent="seo_strategist",
                priority=TaskPriority.HIGH.value,
                dependencies=[t1.task_id],
                reason="Filter out low-confidence or high-risk initiatives."
            )
            plan.add_task(t2)

            t3 = AgentTask(
                task_id=f"task-plan-{uuid.uuid4().hex[:6]}",
                objective="Generate staged action plan requiring human approval",
                description="Formulate concrete action items in PROPOSED status.",
                responsible_agent="seo_action_planner",
                priority=TaskPriority.CRITICAL.value,
                dependencies=[t2.task_id],
                metadata={"requires_human_approval": True, "action_status": "proposed"},
                reason="Staging executable steps behind approval boundary."
            )
            plan.add_task(t3)

        # 5. Default Comprehensive Full-Cycle Workflow
        else:
            t1 = AgentTask(
                task_id=f"task-res-{uuid.uuid4().hex[:6]}",
                objective=f"Collect empirical SEO signals for {url_label}",
                description="Extract performance, rankings, and audit diagnostics.",
                responsible_agent="seo_researcher",
                priority=TaskPriority.HIGH.value,
                reason="Foundational empirical evidence gathering."
            )
            t2 = AgentTask(
                task_id=f"task-inv-{uuid.uuid4().hex[:6]}",
                objective="Investigate root causes and formulate diagnostic inferences",
                description="Synthesize research data into diagnostic hypotheses.",
                responsible_agent="seo_investigator",
                priority=TaskPriority.HIGH.value,
                dependencies=[t1.task_id],
                reason="Root cause identification."
            )
            t3 = AgentTask(
                task_id=f"task-strat-{uuid.uuid4().hex[:6]}",
                objective="Prioritize remediation opportunities with win rate calibration",
                description="Align recommendations with historical domain performance.",
                responsible_agent="seo_strategist",
                priority=TaskPriority.HIGH.value,
                dependencies=[t2.task_id],
                reason="Strategic prioritization."
            )
            t4 = AgentTask(
                task_id=f"task-plan-{uuid.uuid4().hex[:6]}",
                objective="Draft proposed action plan with human approval gate",
                description="Create staged, reversible action proposals.",
                responsible_agent="seo_action_planner",
                priority=TaskPriority.HIGH.value,
                dependencies=[t3.task_id],
                metadata={"requires_human_approval": True, "action_status": "proposed"},
                reason="Governance-compliant action planning."
            )
            plan.add_task(t1)
            plan.add_task(t2)
            plan.add_task(t3)
            plan.add_task(t4)

        # Ensure root tasks with no dependencies start in READY status
        for t in plan.tasks.values():
            if not t.dependencies and t.status == TaskStatus.PENDING.value:
                t.status = TaskStatus.READY.value

        # Validate DAG structure immediately
        plan.validate_graph()
        return plan

    def replan(
        self,
        plan: TaskPlan,
        reason: ReplanReason,
        trigger_info: Any = None,
        shared_memory: Optional[SharedWorkingMemory] = None,
        explanation: Optional[str] = None,
        new_tasks: Optional[List[AgentTask]] = None
    ) -> TaskPlan:
        """
        Adaptively modify the task DAG in response to empirical findings,
        conflicts, or task failures, while strictly respecting budget boundaries.
        """
        # Enforce maximum replans safety limit
        if plan.replans_count >= self.budget_config.max_replans:
            reason_str = reason.value if hasattr(reason, "value") else str(reason)
            logger.warning(
                f"[{plan.plan_id}] Maximum replans limit reached ({self.budget_config.max_replans}). "
                f"Suppressing further replanning for trigger '{reason_str}'."
            )
            raise PlanBudgetExceededError(
                f"Maximum allowed replans ({self.budget_config.max_replans}) exceeded for plan {plan.plan_id}."
            )

        trigger_data = {}
        if isinstance(trigger_info, dict):
            trigger_data = dict(trigger_info)
        elif isinstance(trigger_info, str):
            trigger_data = {"topic": trigger_info, "explanation": trigger_info}
        if explanation:
            trigger_data["explanation"] = explanation

        plan.replans_count += 1
        plan.planning_rounds += 1
        reason_val = reason.value if hasattr(reason, "value") else str(reason)
        replan_record = {
            "round": plan.planning_rounds,
            "reason": reason_val,
            "trigger_info": redact_secrets(trigger_data),
            "timestamp": timezone.now().isoformat(),
        }

        if new_tasks:
            for nt in new_tasks:
                plan.add_task(nt)
            replan_record["added_tasks"] = [nt.task_id for nt in new_tasks]

        # 1. New Critical Evidence Trigger: e.g. Technical defect or indexing blocker
        if reason == ReplanReason.NEW_EVIDENCE:
            evidence_topic = trigger_data.get("topic", "critical technical anomaly")
            existing_inv_tasks = [t for t in plan.tasks.values() if t.responsible_agent == "seo_investigator" and t.status != TaskStatus.COMPLETED.value]
            target_dep = existing_inv_tasks[0].dependencies if existing_inv_tasks else []

            new_task = AgentTask(
                task_id=f"task-replan-ev-{uuid.uuid4().hex[:6]}",
                objective=f"Deep-dive technical investigation: {evidence_topic}",
                description=f"Targeted investigation triggered by new empirical evidence: {evidence_topic}",
                responsible_agent="seo_investigator",
                priority=TaskPriority.CRITICAL.value,
                dependencies=list(target_dep),
                created_by="replanner",
                reason=f"Adaptive replan: {evidence_topic} discovered during initial pass."
            )
            plan.add_task(new_task)
            replan_record["added_tasks"] = [new_task.task_id]

            # Re-wire downstream tasks to wait for this deep dive
            for t in plan.tasks.values():
                if t.responsible_agent in ["seo_strategist", "seo_action_planner"] and t.status != TaskStatus.COMPLETED.value:
                    if new_task.task_id not in t.dependencies:
                        t.dependencies.append(new_task.task_id)

        # 2. Multi-Agent Conflict Detected: Add resolution task
        elif reason == ReplanReason.CONFLICT_DETECTED:
            conflict_topic = trigger_data.get("topic", "discrepancy between findings")
            conflicting_agents = trigger_data.get("responsible_agents", ["seo_researcher", "seo_investigator"])

            resolve_task = AgentTask(
                task_id=f"task-replan-conf-{uuid.uuid4().hex[:6]}",
                objective=f"Resolve conflicting evidence regarding {conflict_topic}",
                description=f"Gather verifying empirical metrics to resolve discrepancy between {conflicting_agents}.",
                responsible_agent="seo_researcher",
                priority=TaskPriority.CRITICAL.value,
                created_by="replanner",
                reason=f"Multi-agent conflict detected on topic '{conflict_topic}'."
            )
            plan.add_task(resolve_task)
            replan_record["added_tasks"] = [resolve_task.task_id]

            # Inferences and strategy must await resolution
            for t in plan.tasks.values():
                if t.responsible_agent in ["seo_investigator", "seo_strategist"] and t.status != TaskStatus.COMPLETED.value:
                    if resolve_task.task_id not in t.dependencies and t.task_id != resolve_task.task_id:
                        t.dependencies.append(resolve_task.task_id)

        # 3. Verification Failure: Add remediation strategy task
        elif reason == ReplanReason.VERIFICATION_FAILURE:
            action_id = trigger_data.get("action_id", "unspecified_action")
            remedy_task = AgentTask(
                task_id=f"task-replan-remedy-{uuid.uuid4().hex[:6]}",
                objective=f"Formulate remediation strategy for failed verification on action {action_id}",
                description="Analyze root cause of verification failure and propose corrective action.",
                responsible_agent="seo_strategist",
                priority=TaskPriority.CRITICAL.value,
                created_by="replanner",
                reason=f"Action '{action_id}' failed empirical live verification."
            )
            plan.add_task(remedy_task)
            replan_record["added_tasks"] = [remedy_task.task_id]

        # 4. Task Failure: Downstream dependents are already marked BLOCKED by handle_task_failure
        elif reason == ReplanReason.TASK_FAILURE:
            failed_id = trigger_data.get("failed_task_id", "")
            replan_record["handled_failure"] = failed_id

        plan.replan_history.append(replan_record)
        plan.validate_graph()
        return plan


class TaskPlanRegistry:
    """
    Thread-safe in-memory cache and registry for active and completed TaskPlans.
    Keyed by correlation_id and optional run_id.
    """
    _instance: Optional["TaskPlanRegistry"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._plans_by_correlation: Dict[str, TaskPlan] = {}
        self._plans_by_run_id: Dict[int, TaskPlan] = {}
        self._registry_lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "TaskPlanRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, plan: TaskPlan, run_id: Optional[int] = None) -> None:
        with self._registry_lock:
            if plan.correlation_id:
                self._plans_by_correlation[str(plan.correlation_id)] = plan
            if run_id:
                self._plans_by_run_id[int(run_id)] = plan

    def get_by_correlation_id(self, correlation_id: str) -> Optional[TaskPlan]:
        with self._registry_lock:
            return self._plans_by_correlation.get(str(correlation_id))

    def get_by_run_id(self, run_id: int) -> Optional[TaskPlan]:
        with self._registry_lock:
            return self._plans_by_run_id.get(int(run_id))

    def clear(self) -> None:
        """Testing utility to clear the in-memory registry."""
        with self._registry_lock:
            self._plans_by_correlation.clear()
            self._plans_by_run_id.clear()
