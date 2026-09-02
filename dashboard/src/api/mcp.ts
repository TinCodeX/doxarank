/**
 * Model Context Protocol (MCP) API client (Phase 4.8).
 */

import { apiFetch } from './client';

export interface MCPServerInfo {
  server_id: string;
  server_name: string;
  version: string;
  description: string;
  status: string;
  tools_count: number;
  tools: string[];
}

export interface MCPToolInfo {
  server_id: string;
  registered_name: string;
  raw_name: string;
  description: string;
  category: string;
  is_mutating: boolean;
  input_schema: Record<string, any>;
}

export interface MCPServersResponse {
  servers: MCPServerInfo[];
  count: number;
}

export interface MCPToolsResponse {
  tools: MCPToolInfo[];
  count: number;
}

/**
 * List all registered Model Context Protocol (MCP) servers and their health status.
 */
export async function getMCPServers(): Promise<MCPServersResponse> {
  return apiFetch<MCPServersResponse>('/api/seo/ai/mcp/servers/');
}

/**
 * List all discovered external MCP tools adapted into DoxaRank's tool ecosystem.
 */
export async function getMCPTools(): Promise<MCPToolsResponse> {
  return apiFetch<MCPToolsResponse>('/api/seo/ai/mcp/tools/');
}
