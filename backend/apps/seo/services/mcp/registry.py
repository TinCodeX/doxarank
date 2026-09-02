"""
DoxaRank Model Context Protocol (MCP) — Registry Service (Phase 4.8)

Coordinates MCP server registration, tool discovery, adapter conversion,
and mounting into DoxaRank's central ToolRegistry.
"""

import logging
from typing import Dict, Any, List, Optional

from apps.seo.services.tool_registry import ToolRegistry
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher, get_event_publisher
)
from .server import LocalSEOExternalServer
from .client import MCPClient
from .adapter import MCPToolAdapter
from .permissions import MCPPermissionPolicy

logger = logging.getLogger(__name__)


class MCPRegistryService:
    """
    Central registry managing external MCP servers, tool discovery, and tool integration.
    """

    def __init__(
        self,
        tool_registry: Optional[Any] = None,
        publisher: Optional[AgentEventPublisher] = None
    ):
        if tool_registry is None:
            from apps.seo.services.tool_registry import get_tool_registry
            self.tool_registry = get_tool_registry()
        else:
            self.tool_registry = tool_registry
        self.publisher = publisher or get_event_publisher()
        self._servers: Dict[str, Dict[str, Any]] = {}
        self._clients: Dict[str, MCPClient] = {}
        self._discovered_tools: Dict[str, List[Dict[str, Any]]] = {}

    def register_server(
        self,
        server_instance: Any,
        server_id: str,
        server_name: str,
        version: str = "1.0.0",
        description: str = ""
    ) -> bool:
        """
        Register an approved MCP server into the subsystem.
        """
        if not MCPPermissionPolicy.is_server_approved(server_id):
            logger.warning(f"[MCPRegistry] Registration rejected: Server '{server_id}' is not in approved allowlist.")
            return False

        client = MCPClient(server=server_instance, server_id=server_id)
        self._servers[server_id] = {
            "server_id": server_id,
            "server_name": server_name,
            "version": version,
            "description": description,
            "status": "connected"
        }
        self._clients[server_id] = client

        try:
            self.publisher.publish(AgentEvent(
                event_type=AgentEventType.MCP_SERVER_REGISTERED,
                run_id=None,
                project_id=None,
                sequence_number=1,
                payload={
                    "server_id": server_id,
                    "server_name": server_name,
                    "version": version
                }
            ))
        except Exception:
            pass

        logger.info(f"[MCPRegistry] Registered MCP server '{server_id}' ({server_name}).")
        return True

    def discover_and_mount_tools(self, server_id: Optional[str] = None) -> List[str]:
        """
        Discover tools from registered servers, adapt them into AgentToolDefinitions,
        and mount them directly into DoxaRank's ToolRegistry.
        Returns list of newly registered tool names.
        """
        servers_to_scan = [server_id] if server_id else list(self._servers.keys())
        mounted_tools = []

        for sid in servers_to_scan:
            client = self._clients.get(sid)
            if not client:
                continue

            tools = client.discover_tools()
            self._discovered_tools[sid] = tools

            try:
                self.publisher.publish(AgentEvent(
                    event_type=AgentEventType.MCP_TOOLS_DISCOVERED,
                    run_id=None,
                    project_id=None,
                    sequence_number=1,
                    payload={
                        "server_id": sid,
                        "tools_count": len(tools),
                        "tools": [t.get("name") for t in tools]
                    }
                ))
            except Exception:
                pass

            for tool_decl in tools:
                adapted = MCPToolAdapter.adapt(
                    server_id=sid,
                    tool_declaration=tool_decl,
                    client=client,
                    publisher=self.publisher
                )
                if adapted:
                    self.tool_registry.register(adapted)
                    mounted_tools.append(adapted.name)
                    logger.info(f"[MCPRegistry] Mounted tool '{adapted.name}' into central ToolRegistry.")

        return mounted_tools

    def list_servers(self) -> List[Dict[str, Any]]:
        """List registered MCP servers with status and capabilities."""
        server_list = []
        for sid, info in self._servers.items():
            discovered = self._discovered_tools.get(sid, [])
            server_list.append({
                **info,
                "tools_count": len(discovered),
                "tools": [t.get("name") for t in discovered]
            })
        return server_list

    def list_mcp_tools(self) -> List[Dict[str, Any]]:
        """List all discovered MCP tools across all servers."""
        all_tools = []
        for sid, tools in self._discovered_tools.items():
            for t in tools:
                all_tools.append({
                    "server_id": sid,
                    "registered_name": f"mcp__{sid}__{t.get('name')}",
                    "raw_name": t.get("name"),
                    "description": t.get("description"),
                    "category": t.get("category", "read_only"),
                    "is_mutating": t.get("is_mutating", False),
                    "input_schema": t.get("inputSchema")
                })
        return all_tools


# Global singleton instance
_mcp_registry_instance: Optional[MCPRegistryService] = None


def get_mcp_registry(tool_registry: Optional[ToolRegistry] = None) -> MCPRegistryService:
    """Retrieve or initialize the global MCPRegistryService singleton."""
    global _mcp_registry_instance
    if _mcp_registry_instance is None:
        _mcp_registry_instance = MCPRegistryService(tool_registry=tool_registry)
        # Bootstrap default local server
        default_server = LocalSEOExternalServer()
        _mcp_registry_instance.register_server(
            server_instance=default_server,
            server_id=default_server.server_id,
            server_name=default_server.server_name,
            version=default_server.version,
            description=default_server.description
        )
        _mcp_registry_instance.discover_and_mount_tools()
    return _mcp_registry_instance
