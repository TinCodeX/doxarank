"""
DoxaRank Model Context Protocol (MCP) — Tool Adapter (Phase 4.8)

Converts discovered MCP tool declarations into controlled DoxaRank AgentToolDefinition instances.
Enforces parameter validation, sanitization, telemetry emission, and result normalization.
"""

import logging
import time
from typing import Dict, Any, Callable, Optional

from apps.projects.models import Project
from apps.seo.services.tool_registry import AgentToolDefinition, ToolCategory
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher
)
from .client import MCPClient
from .permissions import MCPPermissionPolicy

logger = logging.getLogger(__name__)


class MCPToolAdapter:
    """
    Adapter converting external MCP tool specifications into native DoxaRank AgentToolDefinition objects.
    """

    @classmethod
    def adapt(
        cls,
        server_id: str,
        tool_declaration: Dict[str, Any],
        client: MCPClient,
        publisher: Optional[AgentEventPublisher] = None
    ) -> Optional[AgentToolDefinition]:
        """
        Validate and adapt an MCP tool into an AgentToolDefinition.
        Returns None if tool validation fails.
        """
        raw_name = tool_declaration.get("name", "")
        # Validate against strict security policy
        is_valid, err_msg = MCPPermissionPolicy.validate_tool_for_registration(server_id, tool_declaration)
        if not is_valid:
            logger.warning(f"[MCPToolAdapter] Skipping tool '{raw_name}' from '{server_id}': {err_msg}")
            return None

        # Build standardized namespaced tool name
        adapted_name = f"mcp__{server_id}__{raw_name}"
        description = f"[MCP: {server_id}] {tool_declaration.get('description', '')}"
        parameters_schema = tool_declaration.get("inputSchema", {"type": "object", "properties": {}})
        event_publisher = publisher or get_event_publisher()

        def execution_handler(project: Project, arguments: Dict[str, Any]) -> Dict[str, Any]:
            """
            Handler executing the adapted tool through the MCP client with security,
            telemetry, and result normalization.
            """
            start_time = time.time()

            # 1. Sanitize arguments
            is_valid_args, clean_args, arg_err = MCPPermissionPolicy.sanitize_arguments(arguments)
            if not is_valid_args:
                return {
                    "source": "mcp",
                    "server": server_id,
                    "tool": raw_name,
                    "status": "failed",
                    "error": arg_err,
                    "duration_ms": 0
                }

            # 2. Emit authorization and started events
            try:
                event_publisher.publish(AgentEvent(
                    event_type=AgentEventType.MCP_TOOL_AUTHORIZATION_CHECKED,
                    run_id=None,
                    project_id=project.id,
                    sequence_number=1,
                    payload={
                        "server": server_id,
                        "tool": raw_name,
                        "status": "authorized"
                    }
                ))
                event_publisher.publish(AgentEvent(
                    event_type=AgentEventType.MCP_TOOL_INVOCATION_STARTED,
                    run_id=None,
                    project_id=project.id,
                    sequence_number=1,
                    payload={
                        "server": server_id,
                        "tool": raw_name,
                        "arguments": clean_args
                    }
                ))
            except Exception as exc:
                logger.warning(f"[MCPToolAdapter] Event emission failed: {exc}")

            # 3. Invoke external tool through client
            client_res = client.call_tool(raw_name, clean_args)
            duration_ms = int((time.time() - start_time) * 1000)

            # 4. Normalize result
            if client_res.get("success"):
                norm_result = {
                    "source": "mcp",
                    "server": server_id,
                    "tool": raw_name,
                    "status": "success",
                    "data": client_res.get("data", {}),
                    "duration_ms": duration_ms
                }
                try:
                    event_publisher.publish(AgentEvent(
                        event_type=AgentEventType.MCP_TOOL_INVOCATION_COMPLETED,
                        run_id=None,
                        project_id=project.id,
                        sequence_number=1,
                        payload={
                            "server": server_id,
                            "tool": raw_name,
                            "status": "success",
                            "duration_ms": duration_ms
                        }
                    ))
                except Exception:
                    pass
                return norm_result
            else:
                norm_result = {
                    "source": "mcp",
                    "server": server_id,
                    "tool": raw_name,
                    "status": "failed",
                    "error": client_res.get("error", "Unknown MCP execution failure"),
                    "duration_ms": duration_ms
                }
                try:
                    event_publisher.publish(AgentEvent(
                        event_type=AgentEventType.MCP_TOOL_INVOCATION_FAILED,
                        run_id=None,
                        project_id=project.id,
                        sequence_number=1,
                        payload={
                            "server": server_id,
                            "tool": raw_name,
                            "error": norm_result["error"],
                            "duration_ms": duration_ms
                        }
                    ))
                except Exception:
                    pass
                return norm_result

        return AgentToolDefinition(
            name=adapted_name,
            description=description,
            category=ToolCategory.READ_ONLY,
            parameters_schema=parameters_schema,
            requires_approval=False,
            is_mutating=False,
            handler=execution_handler
        )
