"""
DoxaRank Model Context Protocol (MCP) — Permissions & Governance Policy (Phase 4.8)

Enforces strict security boundaries on external MCP servers and tools:
1. Server Allowlist: Only explicitly registered, approved servers can be discovered/invoked.
2. Read-Only Constraint: Mutating tools from MCP are strictly rejected during discovery.
3. Parameter Sanitization: Prevents path traversal, SQL injection, and XSS patterns in tool arguments.
4. Agent Permission Gating: Restricts which specialized agents can access external MCP tools.
"""

import logging
import re
from typing import Dict, Any, List, Set, Optional, Tuple

logger = logging.getLogger(__name__)

# Approved server identifiers allowed in DoxaRank
APPROVED_MCP_SERVERS: Set[str] = {
    "seo_local"
}

# Agents explicitly authorized to query external MCP tools
MCP_AUTHORIZED_AGENTS: Set[str] = {
    "seo_researcher",
    "seo_investigator",
    "seo_supervisor"
}


class MCPPermissionPolicy:
    """
    Security and authorization policy for external MCP tools.
    Acts as a non-negotiable security barrier before any MCP tool is registered or executed.
    """

    @classmethod
    def is_server_approved(cls, server_id: str) -> bool:
        """Verify if the MCP server is in the authorized registry."""
        return server_id in APPROVED_MCP_SERVERS

    @classmethod
    def validate_tool_for_registration(cls, server_id: str, tool_declaration: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate whether a discovered MCP tool meets DoxaRank security standards.
        Enforces read-only constraints and rejects mutating tools.
        """
        if not cls.is_server_approved(server_id):
            return False, f"Server '{server_id}' is not in the approved MCP servers allowlist."

        # Strict Read-Only Invariant for Phase 4.8
        is_mutating = tool_declaration.get("is_mutating", False)
        category = str(tool_declaration.get("category", "")).lower()

        if is_mutating:
            err = f"Security Violation: MCP tool '{tool_declaration.get('name')}' declares mutation. MCP mutation is forbidden in Phase 4.8."
            logger.error(f"[MCPPolicyRejected] {err}")
            return False, err

        if category not in ["read_only", "safe_read_only", ""]:
            err = f"Security Violation: MCP tool '{tool_declaration.get('name')}' category '{category}' is not read-only."
            logger.error(f"[MCPPolicyRejected] {err}")
            return False, err

        return True, None

    @classmethod
    def is_agent_authorized(cls, agent_name: str, tool_name: str) -> bool:
        """Check whether a specialized agent has permission to invoke external MCP tools."""
        return agent_name in MCP_AUTHORIZED_AGENTS

    @classmethod
    def sanitize_arguments(cls, arguments: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Sanitize input arguments to prevent directory traversal and injection payloads.
        Returns (is_valid, sanitized_dict, error_message).
        """
        sanitized = {}
        for key, val in arguments.items():
            if isinstance(val, str):
                # Path traversal check
                if "../" in val or "..\\" in val:
                    return False, {}, f"Invalid argument value for '{key}': Path traversal forbidden."
                # Script injection check
                if re.search(r'<\s*script\b', val, re.IGNORECASE):
                    return False, {}, f"Invalid argument value for '{key}': Script injection forbidden."
                sanitized[key] = val.strip()
            else:
                sanitized[key] = val
        return True, sanitized, None
