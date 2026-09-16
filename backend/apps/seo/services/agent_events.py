"""
DoxaRank Transport-Independent Agent Event Architecture.

Provides strongly-typed event contracts, server-generated UUID identifiers,
monotonically increasing run-scoped sequence numbering, payload sanitization,
and publisher abstractions (In-Memory, Redis Pub/Sub, Django Channels) for decoupled real-time event streaming.
"""

import json
import logging
import re
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from django.utils import timezone

logger = logging.getLogger(__name__)


class AgentEventType(str, Enum):
    """
    Strongly typed, stable event types emitted across the autonomous agent lifecycle.
    Consumed by downstream transports (Redis, WebSockets, Channels, SSE, Observability).
    """
    # Agent session lifecycle
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_CANCELLED = "agent.cancelled"

    # Step reasoning lifecycle
    STEP_STARTED = "step.started"
    STEP_COMPLETED = "step.completed"
    STEP_FAILED = "step.failed"

    # Tool execution lifecycle
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    # Human-in-the-loop approval lifecycle
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"

    # SEO Intelligence & Correlation lifecycle
    SEO_INTELLIGENCE_STARTED = "seo.intelligence.started"
    SEO_EVIDENCE_COLLECTED = "seo.evidence.collected"
    SEO_OPPORTUNITY_DETECTED = "seo.opportunity.detected"
    SEO_INTELLIGENCE_COMPLETED = "seo.intelligence.completed"

    # SEO Investigation & Decision Loop lifecycle
    SEO_INVESTIGATION_STARTED = "seo.investigation.started"
    SEO_INVESTIGATION_EVIDENCE_COLLECTED = "seo.investigation.evidence_collected"
    SEO_INVESTIGATION_ROOT_CAUSE_IDENTIFIED = "seo.investigation.root_cause_identified"
    SEO_INVESTIGATION_RECOMMENDATION_GENERATED = "seo.investigation.recommendation_generated"
    SEO_INVESTIGATION_COMPLETED = "seo.investigation.completed"

    # SEO Action & Human-in-the-Loop Governance lifecycle
    SEO_ACTION_PLAN_CREATED = "seo.action.plan.created"
    SEO_ACTION_PROPOSED = "seo.action.proposed"
    SEO_ACTION_PENDING_APPROVAL = "seo.action.pending_approval"
    SEO_ACTION_APPROVAL_REQUESTED = "seo.action.approval.requested"
    SEO_ACTION_APPROVED = "seo.action.approved"
    SEO_ACTION_REJECTED = "seo.action.rejected"
    SEO_ACTION_EXECUTION_STARTED = "seo.action.execution_started"
    SEO_ACTION_COMPLETED = "seo.action.completed"
    SEO_ACTION_FAILED = "seo.action.failed"

    # SEO Action Real-World Verification lifecycle
    SEO_ACTION_VERIFICATION_STARTED = "seo.action.verification.started"
    SEO_ACTION_VERIFICATION_COMPLETED = "seo.action.verification.completed"
    SEO_ACTION_VERIFICATION_FAILED = "seo.action.verification.failed"

    # SEO Outcome Learning & Adaptive Intelligence lifecycle
    SEO_OUTCOME_MEASUREMENT_STARTED = "seo.outcome.measurement.started"
    SEO_OUTCOME_EVIDENCE_COLLECTED = "seo.outcome.evidence.collected"
    SEO_OUTCOME_CLASSIFIED = "seo.outcome.classified"
    SEO_LEARNING_SIGNAL_GENERATED = "seo.learning.signal.generated"
    SEO_OUTCOME_COMPLETED = "seo.outcome.completed"

    # SEO Adaptive Strategy & Historical Learning lifecycle
    SEO_STRATEGY_LEARNING_STARTED = "seo.strategy.learning.started"
    SEO_STRATEGY_EVIDENCE_COLLECTED = "seo.strategy.evidence.collected"
    SEO_STRATEGY_GENERATED = "seo.strategy.generated"
    SEO_STRATEGY_APPLIED = "seo.strategy.applied"
    SEO_STRATEGY_COMPLETED = "seo.strategy.completed"

    # Specialized SEO Agent Orchestration & Supervision lifecycle (Phase 4.7)
    SEO_AGENT_STARTED = "seo.agent.started"
    SEO_AGENT_COMPLETED = "seo.agent.completed"
    SEO_AGENT_FAILED = "seo.agent.failed"
    SEO_AGENT_HANDOFF = "seo.agent.handoff"
    SEO_AGENT_ROUTING_STARTED = "seo.agent.routing.started"
    SEO_AGENT_ROUTING_COMPLETED = "seo.agent.routing.completed"

    # Model Context Protocol (MCP) Interoperability lifecycle (Phase 4.8)
    MCP_SERVER_REGISTERED = "mcp.server.registered"
    MCP_TOOLS_DISCOVERED = "mcp.tools.discovered"
    MCP_TOOL_AUTHORIZATION_CHECKED = "mcp.tool.authorization.checked"
    MCP_TOOL_INVOCATION_STARTED = "mcp.tool.invocation.started"
    MCP_TOOL_INVOCATION_COMPLETED = "mcp.tool.invocation.completed"
    MCP_TOOL_INVOCATION_FAILED = "mcp.tool.invocation.failed"

    # Multi-Agent Collaboration & Structured Handoffs lifecycle (Phase 5.1)
    SEO_AGENT_HANDOFF_STARTED = "seo.agent.handoff.started"
    SEO_AGENT_HANDOFF_COMPLETED = "seo.agent.handoff.completed"
    SEO_AGENT_HANDOFF_REJECTED = "seo.agent.handoff.rejected"
    SEO_AGENT_COLLABORATION_STARTED = "seo.agent.collaboration.started"
    SEO_AGENT_COLLABORATION_COMPLETED = "seo.agent.collaboration.completed"
    SEO_AGENT_COLLABORATION_FAILED = "seo.agent.collaboration.failed"

    # Shared Working Memory & Adaptive Collaboration lifecycle (Phase 5.2)
    SEO_COLLABORATION_MEMORY_INITIALIZED = "seo.collaboration.memory.initialized"
    SEO_COLLABORATION_MEMORY_UPDATED = "seo.collaboration.memory.updated"
    SEO_COLLABORATION_MEMORY_PROJECTED = "seo.collaboration.memory.projected"
    SEO_COLLABORATION_MEMORY_CONFLICT_DETECTED = "seo.collaboration.memory.conflict.detected"
    SEO_COLLABORATION_MEMORY_CONFLICT_RESOLVED = "seo.collaboration.memory.conflict.resolved"
    SEO_COLLABORATION_AGENT_REVISIT = "seo.collaboration.agent.revisit"
    SEO_COLLABORATION_CONTEXT_BOUNDED = "seo.collaboration.context.bounded"

    # Dynamic Task Decomposition & Collaborative Planning lifecycle (Phase 5.3)
    SEO_TASK_PLAN_CREATED = "seo.agent.task.plan.created"
    SEO_TASK_CREATED = "seo.agent.task.created"
    SEO_TASK_READY = "seo.agent.task.ready"
    SEO_TASK_STARTED = "seo.agent.task.started"
    SEO_TASK_COMPLETED = "seo.agent.task.completed"
    SEO_TASK_FAILED = "seo.agent.task.failed"
    SEO_TASK_BLOCKED = "seo.agent.task.blocked"
    SEO_TASK_REPLANNED = "seo.agent.task.replanned"
    SEO_TASK_CANCELLED = "seo.agent.task.cancelled"
    SEO_TASK_DEPENDENCY_RESOLVED = "seo.agent.task.dependency.resolved"
    SEO_TASK_PLAN_LIMIT_REACHED = "seo.agent.task.plan.limit_reached"

    # Parallel Agent Execution & Bounded Batch Scheduling (Milestone 5.4)
    SEO_PARALLEL_BATCH_CREATED = "seo.agent.parallel.batch.created"
    SEO_PARALLEL_TASK_STARTED = "seo.agent.parallel.task.started"
    SEO_PARALLEL_TASK_COMPLETED = "seo.agent.parallel.task.completed"
    SEO_PARALLEL_TASK_FAILED = "seo.agent.parallel.task.failed"
    SEO_PARALLEL_BATCH_COMPLETED = "seo.agent.parallel.batch.completed"
    SEO_PARALLEL_BATCH_PARTIAL_FAILURE = "seo.agent.parallel.batch.partial_failure"
    SEO_PARALLEL_CONCURRENCY_LIMITED = "seo.agent.parallel.concurrency.limited"

    # Adaptive Agent Coordination & Dynamic Agent Selection (Milestone 5.5)
    SEO_AGENT_SELECTION_STARTED = "seo.agent.selection.started"
    SEO_AGENT_CANDIDATE_EVALUATED = "seo.agent.candidate.evaluated"
    SEO_AGENT_CANDIDATE_REJECTED = "seo.agent.candidate.rejected"
    SEO_AGENT_SELECTED = "seo.agent.selected"
    SEO_AGENT_FALLBACK = "seo.agent.fallback"
    SEO_AGENT_SELECTION_FAILED = "seo.agent.selection.failed"

    # Agent Learning & Optimization (Milestone 5.6)
    SEO_LEARNING_RECORD_CREATED = "seo.agent.learning.record_created"
    SEO_AGENT_PERFORMANCE_UPDATED = "seo.agent.learning.performance_updated"
    SEO_HISTORICAL_SIGNAL_APPLIED = "seo.agent.learning.signal_applied"
    SEO_HISTORICAL_SIGNAL_IGNORED = "seo.agent.learning.signal_ignored"
    SEO_ROUTING_OUTCOME_RECORDED = "seo.agent.learning.outcome_recorded"

    # Advanced Multi-Agent Reasoning & Consensus (Milestone 5.7)
    SEO_REASONING_CASE_STARTED = "seo.reasoning.case.started"
    SEO_REASONING_ROUND_STARTED = "seo.reasoning.round.started"
    SEO_REASONING_AGENT_ANALYSIS_COMPLETED = "seo.reasoning.agent.analysis.completed"
    SEO_REASONING_HYPOTHESIS_CREATED = "seo.reasoning.hypothesis.created"
    SEO_REASONING_CRITIQUE_CREATED = "seo.reasoning.critique.created"
    SEO_REASONING_DISAGREEMENT_DETECTED = "seo.reasoning.disagreement.detected"
    SEO_REASONING_CONSENSUS_REACHED = "seo.reasoning.consensus.reached"
    SEO_REASONING_CONSENSUS_FAILED = "seo.reasoning.consensus.failed"
    SEO_REASONING_ESCALATED = "seo.reasoning.escalated"
    SEO_REASONING_CASE_COMPLETED = "seo.reasoning.case.completed"

    # Continuous Agent Operations (Milestone 6.1)
    SEO_OPERATION_CREATED = "seo.operation.created"
    SEO_OPERATION_STARTED = "seo.operation.started"
    SEO_OPERATION_PAUSED = "seo.operation.paused"
    SEO_OPERATION_RESUMED = "seo.operation.resumed"
    SEO_OPERATION_RUN_SCHEDULED = "seo.operation.run.scheduled"
    SEO_OPERATION_RUN_STARTED = "seo.operation.run.started"
    SEO_OPERATION_RUN_COMPLETED = "seo.operation.run.completed"
    SEO_OPERATION_RUN_FAILED = "seo.operation.run.failed"
    SEO_OPERATION_COMPLETED = "seo.operation.completed"

    # Event-Driven Agents (Milestone 6.2)
    SEO_EVENT_RECEIVED = "seo.event.received"
    SEO_EVENT_ACCEPTED = "seo.event.accepted"
    SEO_EVENT_REJECTED = "seo.event.rejected"
    SEO_EVENT_DEDUPLICATED = "seo.event.deduplicated"
    SEO_EVENT_SUPPRESSED = "seo.event.suppressed"
    SEO_EVENT_TRIGGERED = "seo.event.triggered"
    SEO_EVENT_COOLDOWN = "seo.event.cooldown"
    SEO_EVENT_RUN_CREATED = "seo.event.run_created"
    SEO_EVENT_PROCESSING_FAILED = "seo.event.processing_failed"

    # Autonomous SEO Monitoring (Milestone 6.3)
    SEO_MONITORING_CYCLE_STARTED = "seo.monitoring.cycle.started"
    SEO_MONITORING_CYCLE_COMPLETED = "seo.monitoring.cycle.completed"
    SEO_MONITORING_CYCLE_FAILED = "seo.monitoring.cycle.failed"
    SEO_MONITORING_PROJECT_STARTED = "seo.monitoring.project.started"
    SEO_MONITORING_PROJECT_COMPLETED = "seo.monitoring.project.completed"
    SEO_MONITORING_PROJECT_FAILED = "seo.monitoring.project.failed"
    SEO_MONITORING_SNAPSHOT_CREATED = "seo.monitoring.snapshot.created"
    SEO_MONITORING_CHANGE_DETECTED = "seo.monitoring.change.detected"
    SEO_MONITORING_CHANGE_IGNORED = "seo.monitoring.change.ignored"
    SEO_MONITORING_EVENT_CREATED = "seo.monitoring.event.created"
    SEO_MONITORING_RECOVERY_DETECTED = "seo.monitoring.recovery.detected"
    SEO_MONITORING_DUPLICATE_PREVENTED = "seo.monitoring.duplicate_prevented"

    # Autonomous Remediation (Milestone 6.4)
    SEO_REMEDIATION_PROPOSED = "seo.remediation.proposed"
    SEO_REMEDIATION_AUTH_EVALUATED = "seo.remediation.auth.evaluated"
    SEO_REMEDIATION_AUTH_APPROVED = "seo.remediation.auth.approved"
    SEO_REMEDIATION_AUTH_REJECTED = "seo.remediation.auth.rejected"
    SEO_REMEDIATION_AUTONOMOUS_ALLOWED = "seo.remediation.autonomous.allowed"
    SEO_REMEDIATION_EXECUTION_STARTED = "seo.remediation.execution.started"
    SEO_REMEDIATION_EXECUTION_COMPLETED = "seo.remediation.execution.completed"
    SEO_REMEDIATION_EXECUTION_FAILED = "seo.remediation.execution.failed"
    SEO_REMEDIATION_VERIFICATION_STARTED = "seo.remediation.verification.started"
    SEO_REMEDIATION_VERIFICATION_PASSED = "seo.remediation.verification.passed"
    SEO_REMEDIATION_VERIFICATION_FAILED = "seo.remediation.verification.failed"
    SEO_REMEDIATION_ROLLBACK_STARTED = "seo.remediation.rollback.started"
    SEO_REMEDIATION_ROLLBACK_COMPLETED = "seo.remediation.rollback.completed"
    SEO_REMEDIATION_COMPLETED = "seo.remediation.completed"
    SEO_REMEDIATION_BLOCKED = "seo.remediation.blocked"
    SEO_REMEDIATION_DUPLICATE_PREVENTED = "seo.remediation.duplicate.prevented"





def sanitize_event_payload(data: Any) -> Any:
    """
    Recursively sanitize event payload dictionaries, lists, and strings to guarantee
    that no API keys, bearer tokens, passwords, or provider credentials are leaked.
    """
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(secret_term in k_lower for secret_term in ['password', 'secret', 'token', 'auth_token', 'api_key']):
                cleaned[k] = "***REDACTED***"
            else:
                cleaned[k] = sanitize_event_payload(v)
        return cleaned
    elif isinstance(data, list):
        return [sanitize_event_payload(item) for item in data]
    elif isinstance(data, str):
        # Mask OpenAI-style keys (sk-...)
        clean = re.sub(r'sk-[a-zA-Z0-9_-]{8,}', 'sk-***', data)
        # Mask Bearer tokens
        clean = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]{8,}', 'Bearer ***', clean, flags=re.IGNORECASE)
        # Mask generic key-value credential patterns
        clean = re.sub(r'(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,;]+', r'\1=***', clean)
        return clean
    return data


@dataclass
class AgentEvent:
    """
    Structured, transport-independent event representation for agent executions.
    """
    event_type: str
    run_id: int
    project_id: int
    step_number: Optional[int] = None
    sequence_number: int = 1
    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: timezone.now().isoformat())

    def __post_init__(self):
        # Guarantee server-side UUID4 format
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        elif not isinstance(self.event_id, str):
            self.event_id = str(self.event_id)

        # Normalize event_type if passed as enum
        if isinstance(self.event_type, AgentEventType):
            self.event_type = self.event_type.value
        else:
            self.event_type = str(self.event_type)

        # Normalize timestamp to ISO string
        if not self.timestamp:
            self.timestamp = timezone.now().isoformat()
        elif hasattr(self.timestamp, 'isoformat'):
            self.timestamp = self.timestamp.isoformat()

        # Sanitize payload dictionary
        self.payload = sanitize_event_payload(self.payload or {})

    def to_dict(self) -> Dict[str, Any]:
        """Convert AgentEvent into a clean serializable dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "step_number": self.step_number,
            "sequence_number": self.sequence_number,
            "timestamp": self.timestamp,
            "payload": self.payload
        }

    def to_json(self) -> str:
        """Serialize AgentEvent to standard JSON."""
        return json.dumps(self.to_dict(), default=str)


class AgentEventPublisher(ABC):
    """
    Abstract interface for publishing AgentEvents.
    Enables dependency inversion across in-memory test harnesses, Redis Pub/Sub,
    Django Channels WebSockets, or future SSE transports.
    """

    @abstractmethod
    def publish(self, event: AgentEvent) -> None:
        """Publish an AgentEvent to the underlying transport."""
        pass


class InMemoryEventPublisher(AgentEventPublisher):
    """
    In-memory publisher implementation for testing, validation, and local logging.
    Stores published events in order of arrival with thread-safe locking.
    """

    def __init__(self):
        self._events: List[AgentEvent] = []
        self._lock = threading.RLock()

    def publish(self, event: AgentEvent) -> None:
        """Store published event in memory."""
        with self._lock:
            self._events.append(event)
        logger.debug(f"[InMemoryEventPublisher] Published event #{event.sequence_number}: {event.event_type} (Run #{event.run_id})")

    def get_events(self, run_id: Optional[int] = None) -> List[AgentEvent]:
        """Retrieve all events or events filtered by run_id."""
        with self._lock:
            if run_id is not None:
                return [e for e in self._events if e.run_id == run_id]
            return list(self._events)

    @property
    def published_events(self) -> List[AgentEvent]:
        """Convenience property for testing harnesses."""
        return self.get_events()

    def get_event_types(self, run_id: Optional[int] = None) -> List[str]:
        """Retrieve list of event type strings."""
        with self._lock:
            return [e.event_type for e in self.get_events(run_id)]

    def get_events_by_type(self, event_type: Any) -> List[AgentEvent]:
        """Retrieve events matching a specific event type (Enum or string)."""
        target = event_type.value if hasattr(event_type, "value") else str(event_type)
        with self._lock:
            return [e for e in self._events if e.event_type == target]

    def clear(self) -> None:
        """Clear all stored events."""
        with self._lock:
            self._events.clear()


class RedisEventPublisher(AgentEventPublisher):
    """
    Production Redis Pub/Sub & Django Channels implementation of AgentEventPublisher.
    Publishes JSON-serialized AgentEvents to channel `agent:run:{run_id}`
    and dispatches to Django Channels group `agent_run_{run_id}`.
    Reuses project Redis configuration from Django settings (CELERY_BROKER_URL / REDIS_URL).
    """

    CHANNEL_PREFIX = "agent:run:"
    GROUP_PREFIX = "agent_run_"

    def __init__(
        self,
        redis_url: Optional[str] = None,
        redis_client: Optional[Any] = None,
        channel_layer: Optional[Any] = None
    ):
        self._redis_url = redis_url
        self._client = redis_client
        self._channel_layer = channel_layer

    @classmethod
    def get_channel_name(cls, run_id: int) -> str:
        """Return the standard Redis Pub/Sub channel name for an agent run."""
        return f"{cls.CHANNEL_PREFIX}{run_id}"

    @classmethod
    def get_group_name(cls, run_id: int) -> str:
        """Return the standard Django Channels group name for an agent run."""
        return f"{cls.GROUP_PREFIX}{run_id}"

    def _get_redis_url(self) -> str:
        """Resolve Redis URL from settings or fallback."""
        if self._redis_url:
            return self._redis_url
        from django.conf import settings
        return getattr(
            settings,
            'REDIS_URL',
            getattr(settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
        )

    @property
    def client(self) -> Any:
        """Lazy-initialize Redis client connection."""
        if self._client is None:
            import redis
            url = self._get_redis_url()
            self._client = redis.Redis.from_url(url, decode_responses=True)
        return self._client

    @property
    def channel_layer(self) -> Any:
        """Retrieve Django Channels channel layer."""
        if self._channel_layer is None:
            try:
                from channels.layers import get_channel_layer
                self._channel_layer = get_channel_layer()
            except Exception as exc:
                logger.debug(f"[RedisEventPublisher] Could not retrieve channel layer: {exc}")
                self._channel_layer = None
        return self._channel_layer

    def publish(self, event: AgentEvent) -> None:
        """
        Publish an AgentEvent as JSON to the agent run channel and Django Channels group.
        Catches and logs any transport exceptions to maintain non-fatal observability.
        """
        channel = self.get_channel_name(event.run_id)
        group = self.get_group_name(event.run_id)
        json_data = event.to_json()
        event_dict = event.to_dict()

        # 1. Publish to Redis Pub/Sub channel
        try:
            self.client.publish(channel, json_data)
            logger.debug(
                f"[RedisEventPublisher] Published event #{event.sequence_number} "
                f"({event.event_type}) to Redis channel '{channel}'"
            )
        except Exception as exc:
            logger.warning(
                f"[RedisEventPublisher] Failed to publish event #{event.sequence_number} "
                f"({event.event_type}) to Redis channel '{channel}': {exc}"
            )

        # 2. Dispatch to Django Channels group
        try:
            cl = self.channel_layer
            if cl is not None:
                from asgiref.sync import async_to_sync
                async_to_sync(cl.group_send)(
                    group,
                    {
                        "type": "agent_event",
                        "event": event_dict
                    }
                )
                logger.debug(
                    f"[RedisEventPublisher] Dispatched event #{event.sequence_number} "
                    f"({event.event_type}) to Channels group '{group}'"
                )
        except Exception as exc:
            logger.warning(
                f"[RedisEventPublisher] Failed to dispatch event #{event.sequence_number} "
                f"({event.event_type}) to Channels group '{group}': {exc}"
            )


# Module-level default publisher instance
_default_publisher: AgentEventPublisher = InMemoryEventPublisher()


def get_event_publisher() -> AgentEventPublisher:
    """Get the current global AgentEventPublisher instance."""
    return _default_publisher


def set_event_publisher(publisher: AgentEventPublisher) -> None:
    """Set the global AgentEventPublisher instance."""
    global _default_publisher
    _default_publisher = publisher


def reconstruct_agent_run_events(run) -> List[Dict[str, Any]]:
    """
    Deterministically reconstruct canonical AgentEvent sequence from PostgreSQL models
    (AgentRun, AgentStep, AgentToolCall) for historical runs without stored event history.
    """
    events = []
    seq = 1

    # 1. agent.started
    created_ts = run.created_at.isoformat() if hasattr(run, 'created_at') and run.created_at else timezone.now().isoformat()
    events.append({
        "event_id": f"rec-{run.id}-start",
        "event_type": AgentEventType.AGENT_STARTED.value,
        "run_id": run.id,
        "project_id": run.project_id,
        "step_number": None,
        "sequence_number": seq,
        "timestamp": created_ts,
        "payload": sanitize_event_payload({
            "goal": run.goal,
            "project_id": run.project_id,
            "max_steps": run.max_steps
        })
    })

    # 2. Steps & Tool Calls
    steps = run.steps.order_by('step_number').prefetch_related('tool_calls')
    for step in steps:
        step_num = step.step_number
        tool_calls = list(step.tool_calls.order_by('created_at'))
        tool_call = tool_calls[0] if tool_calls else None
        tool_name = tool_call.tool_name if tool_call else None

        # step.started
        seq += 1
        step_created_ts = step.created_at.isoformat() if step.created_at else timezone.now().isoformat()
        events.append({
            "event_id": f"rec-{run.id}-step-{step_num}-start",
            "event_type": AgentEventType.STEP_STARTED.value,
            "run_id": run.id,
            "project_id": run.project_id,
            "step_number": step_num,
            "sequence_number": seq,
            "timestamp": step_created_ts,
            "payload": sanitize_event_payload({
                "step_number": step_num,
                "action_type": step.action_type,
                "tool_name": tool_name
            })
        })

        if tool_call:
            # tool.started
            seq += 1
            tc_created_ts = tool_call.created_at.isoformat() if tool_call.created_at else timezone.now().isoformat()
            events.append({
                "event_id": f"rec-{run.id}-tc-{tool_call.id}-start",
                "event_type": AgentEventType.TOOL_STARTED.value,
                "run_id": run.id,
                "project_id": run.project_id,
                "step_number": step_num,
                "sequence_number": seq,
                "timestamp": tc_created_ts,
                "payload": sanitize_event_payload({
                    "step_number": step_num,
                    "tool_name": tool_call.tool_name,
                    "arguments": tool_call.tool_input
                })
            })

            # tool.completed / tool.failed
            seq += 1
            is_success = not bool(tool_call.error_message)
            tc_completed_ts = tool_call.completed_at.isoformat() if tool_call.completed_at else (
                tool_call.created_at.isoformat() if tool_call.created_at else timezone.now().isoformat()
            )
            events.append({
                "event_id": f"rec-{run.id}-tc-{tool_call.id}-finish",
                "event_type": AgentEventType.TOOL_COMPLETED.value if is_success else AgentEventType.TOOL_FAILED.value,
                "run_id": run.id,
                "project_id": run.project_id,
                "step_number": step_num,
                "sequence_number": seq,
                "timestamp": tc_completed_ts,
                "payload": sanitize_event_payload({
                    "step_number": step_num,
                    "tool_name": tool_call.tool_name,
                    "duration_ms": tool_call.duration_ms,
                    "success": is_success,
                    "error_message": tool_call.error_message if not is_success else ""
                })
            })

        # step.completed / step.failed
        seq += 1
        is_step_success = step.status != 'failed'
        step_completed_ts = step.completed_at.isoformat() if step.completed_at else (
            step.created_at.isoformat() if step.created_at else timezone.now().isoformat()
        )
        events.append({
            "event_id": f"rec-{run.id}-step-{step_num}-finish",
            "event_type": AgentEventType.STEP_COMPLETED.value if is_step_success else AgentEventType.STEP_FAILED.value,
            "run_id": run.id,
            "project_id": run.project_id,
            "step_number": step_num,
            "sequence_number": seq,
            "timestamp": step_completed_ts,
            "payload": sanitize_event_payload({
                "step_number": step_num,
                "tool_name": tool_name,
                "success": is_step_success
            })
        })

    # 3. Approval events
    if run.status == 'waiting_for_approval':
        seq += 1
        updated_ts = run.updated_at.isoformat() if hasattr(run, 'updated_at') and run.updated_at else timezone.now().isoformat()
        events.append({
            "event_id": f"rec-{run.id}-approval-req",
            "event_type": AgentEventType.APPROVAL_REQUIRED.value,
            "run_id": run.id,
            "project_id": run.project_id,
            "step_number": run.total_steps,
            "sequence_number": seq,
            "timestamp": updated_ts,
            "payload": sanitize_event_payload({
                "requires_human_approval": True,
                "run_id": run.id
            })
        })

    # 4. Terminal events
    completed_ts = run.completed_at.isoformat() if hasattr(run, 'completed_at') and run.completed_at else timezone.now().isoformat()
    if run.status == 'completed':
        seq += 1
        events.append({
            "event_id": f"rec-{run.id}-finish",
            "event_type": AgentEventType.AGENT_COMPLETED.value,
            "run_id": run.id,
            "project_id": run.project_id,
            "step_number": run.total_steps,
            "sequence_number": seq,
            "timestamp": completed_ts,
            "payload": sanitize_event_payload({
                "summary": run.summary,
                "total_steps": run.total_steps
            })
        })
    elif run.status == 'failed':
        seq += 1
        events.append({
            "event_id": f"rec-{run.id}-failed",
            "event_type": AgentEventType.AGENT_FAILED.value,
            "run_id": run.id,
            "project_id": run.project_id,
            "step_number": run.total_steps,
            "sequence_number": seq,
            "timestamp": completed_ts,
            "payload": sanitize_event_payload({
                "summary": run.summary,
                "error": "Execution failed"
            })
        })
    elif run.status == 'cancelled':
        seq += 1
        events.append({
            "event_id": f"rec-{run.id}-cancelled",
            "event_type": AgentEventType.AGENT_CANCELLED.value,
            "run_id": run.id,
            "project_id": run.project_id,
            "step_number": run.total_steps,
            "sequence_number": seq,
            "timestamp": completed_ts,
            "payload": sanitize_event_payload({
                "summary": run.summary
            })
        })

    return events


def get_agent_run_events(run, after_sequence: int = 0) -> List[Dict[str, Any]]:
    """
    Retrieve sanitized AgentEvents for an AgentRun filtered strictly after `after_sequence`.
    Prefers stored `_event_history` in `run.context_snapshot` if present,
    or reconstructs deterministically from database models.
    Guarantees ascending order by `sequence_number` and zero credential leakage.
    """
    snapshot = run.context_snapshot or {}
    stored_history = snapshot.get('_event_history')

    if stored_history and isinstance(stored_history, list) and len(stored_history) > 0:
        event_list = list(stored_history)
    else:
        event_list = reconstruct_agent_run_events(run)

    # Filter strictly where sequence_number > after_sequence
    filtered = [
        dict(e) for e in event_list
        if isinstance(e, dict) and int(e.get('sequence_number', 0)) > int(after_sequence)
    ]

    # Guarantee monotonic sort order
    filtered.sort(key=lambda x: int(x.get('sequence_number', 0)))

    # Ensure all payloads are safely sanitized
    for ev in filtered:
        if 'payload' in ev:
            ev['payload'] = sanitize_event_payload(ev['payload'])

    return filtered
