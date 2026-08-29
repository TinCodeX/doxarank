"""
Django Channels WebSocket Consumers for DoxaRank Real-Time Agent Experience.

Provides secure, multi-tenant, authenticated WebSocket streaming of AgentEvents
originating from the autonomous agent orchestrator via Redis / Channels layer.
"""

import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from apps.seo.models import AgentRun
from apps.seo.services.agent_events import RedisEventPublisher

logger = logging.getLogger(__name__)


class AgentEventConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer that streams real-time AgentEvents for a specific AgentRun.

    Security & Tenant Isolation Guarantees:
    - Enforces authentication: Rejects unauthenticated/anonymous users immediately with code 4001.
    - Validates ownership server-side: AgentRun -> Project -> owner == authenticated user.
    - Rejects cross-tenant access and nonexistent runs with code 4003 without leaking information.
    - Joins the run-specific Channels group `agent_run_{run_id}`.
    - Preserves existing event structure, monotonic sequence numbers, and sanitization.
    """

    async def connect(self):
        self.user = self.scope.get("user")
        self.run_id_param = self.scope.get("url_route", {}).get("kwargs", {}).get("run_id")

        # 1. Authentication Enforcement
        if not self.user or not self.user.is_authenticated or self.user.is_anonymous:
            logger.warning("[AgentEventConsumer] Connection rejected: Unauthenticated user.")
            await self.close(code=4001)
            return

        # 2. Parameter Validation
        try:
            self.run_id = int(self.run_id_param)
        except (TypeError, ValueError):
            logger.warning(f"[AgentEventConsumer] Connection rejected: Invalid run_id '{self.run_id_param}'.")
            await self.close(code=4004)
            return

        # 3. Multi-Tenant Authorization Check (AgentRun -> Project -> owner == user)
        has_access = await self._verify_run_access(self.user.id, self.run_id)
        if not has_access:
            logger.warning(
                f"[AgentEventConsumer] Access denied: User #{self.user.id} attempted unauthorized access to AgentRun #{self.run_id}."
            )
            await self.close(code=4003)
            return

        # 4. Join Channels Group & Accept Connection
        self.group_name = RedisEventPublisher.get_group_name(self.run_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info(
            f"[AgentEventConsumer] User #{self.user.id} subscribed to AgentRun #{self.run_id} (group '{self.group_name}')."
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name") and self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(
                f"[AgentEventConsumer] User disconnected from group '{self.group_name}' (close code: {close_code})."
            )

    async def agent_event(self, event_message):
        """
        Handler for messages dispatched to the Channels group by RedisEventPublisher.
        Transmits sanitized AgentEvent payload to the connected WebSocket client.
        """
        payload = event_message.get("event")
        if payload is None:
            payload = event_message.get("data") or event_message
        await self.send_json(payload)

    @database_sync_to_async
    def _verify_run_access(self, user_id: int, run_id: int) -> bool:
        """
        Query database to confirm that AgentRun exists and belongs to a project owned by user_id.
        Prevents cross-tenant information leakage by returning False for both missing and unowned runs.
        """
        try:
            run = AgentRun.objects.select_related("project").get(id=run_id)
            return run.project.owner_id == user_id
        except (AgentRun.DoesNotExist, ValueError):
            return False
