"""
DoxaRank Transport-Independent Agent Event Architecture.

Provides strongly-typed event contracts, server-generated UUID identifiers,
monotonically increasing run-scoped sequence numbering, payload sanitization,
and publisher abstractions (In-Memory, Redis Pub/Sub, Django Channels) for decoupled real-time event streaming.
"""

import json
import logging
import re
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
    Stores published events in order of arrival.
    """

    def __init__(self):
        self._events: List[AgentEvent] = []

    def publish(self, event: AgentEvent) -> None:
        """Store published event in memory."""
        self._events.append(event)
        logger.debug(f"[InMemoryEventPublisher] Published event #{event.sequence_number}: {event.event_type} (Run #{event.run_id})")

    def get_events(self, run_id: Optional[int] = None) -> List[AgentEvent]:
        """Retrieve all events or events filtered by run_id."""
        if run_id is not None:
            return [e for e in self._events if e.run_id == run_id]
        return list(self._events)

    def get_event_types(self, run_id: Optional[int] = None) -> List[str]:
        """Retrieve list of event type strings."""
        return [e.event_type for e in self.get_events(run_id)]

    def clear(self) -> None:
        """Clear all stored events."""
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
