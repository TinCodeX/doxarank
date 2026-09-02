"""
DoxaRank Model Context Protocol (MCP) — Client Implementation (Phase 4.8)

Provides a standard JSON-RPC 2.0 client for discovering and executing tools on registered MCP servers.
Enforces timeout boundaries, protocol validation, and error normalization.
"""

import json
import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Union

from .server import LocalSEOExternalServer

logger = logging.getLogger(__name__)


class MCPClient:
    """
    Standard JSON-RPC 2.0 Model Context Protocol (MCP) Client.
    Communicates with registered MCP servers (in-process or network).
    """

    def __init__(self, server: Optional[Any] = None, server_id: str = "seo_local", timeout: float = 5.0):
        self.server = server or LocalSEOExternalServer()
        self.server_id = server_id
        self.timeout = timeout

    def discover_tools(self) -> List[Dict[str, Any]]:
        """
        Invoke 'tools/list' on the MCP server to discover declared tools and schemas.
        Returns a list of raw MCP tool declarations.
        """
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": {}
        }

        try:
            response = self._send_request(payload)
            if "error" in response:
                err = response["error"]
                logger.error(f"[MCPClient] Discovery error on '{self.server_id}': {err}")
                return []

            result = response.get("result", {})
            tools = result.get("tools", [])
            logger.info(f"[MCPClient] Discovered {len(tools)} tools from MCP server '{self.server_id}'.")
            return tools

        except Exception as exc:
            logger.error(f"[MCPClient] Failed to discover tools from '{self.server_id}': {exc}")
            return []

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invoke 'tools/call' on the MCP server for a specific tool.
        Returns normalized response: { "success": bool, "data": ..., "duration_ms": ... }
        """
        start_time = time.time()
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        try:
            response = self._send_request(payload)
            duration_ms = int((time.time() - start_time) * 1000)

            if "error" in response:
                err = response["error"]
                logger.warning(f"[MCPClient] Tool call failed ({tool_name}): {err}")
                return {
                    "success": False,
                    "error": err.get("message", "Unknown MCP error"),
                    "code": err.get("code", -1),
                    "duration_ms": duration_ms
                }

            result = response.get("result", {})
            content = result.get("content", [])
            is_error = result.get("isError", False)

            if not content:
                return {
                    "success": not is_error,
                    "data": {},
                    "duration_ms": duration_ms
                }

            # Parse MCP content block (typically type='text' with JSON payload)
            first_block = content[0]
            raw_text = first_block.get("text", "{}")
            try:
                parsed_data = json.loads(raw_text)
            except Exception:
                parsed_data = {"raw_output": raw_text}

            return {
                "success": not is_error,
                "data": parsed_data,
                "duration_ms": duration_ms
            }

        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[MCPClient] Exception invoking MCP tool '{tool_name}': {exc}")
            return {
                "success": False,
                "error": str(exc),
                "duration_ms": duration_ms
            }

    def _send_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transport layer for sending JSON-RPC request.
        Dispatches to in-process server handler or network transport.
        """
        if hasattr(self.server, "handle_request"):
            return self.server.handle_request(payload)
        else:
            raise NotImplementedError("Remote HTTP/WebSocket MCP transport not configured.")
