import { apiFetch } from './client';
import type {
  AgentRun,
  CreateAgentRunPayload,
  ResumeAgentRunPayload
} from '../types/agentRun';

/**
 * Fetch all Agent Runs for a project.
 */
export async function getAgentRuns(projectId?: number): Promise<AgentRun[]> {
  const query = projectId ? `?project=${projectId}` : '';
  return apiFetch<AgentRun[]>(`/api/seo/ai/agent/runs/${query}`);
}

/**
 * Fetch a single Agent Run by ID with full step telemetry.
 */
export async function getAgentRun(id: number): Promise<AgentRun> {
  return apiFetch<AgentRun>(`/api/seo/ai/agent/runs/${id}/`);
}

/**
 * Start a new Autonomous Agent Run.
 */
export async function createAgentRun(payload: CreateAgentRunPayload): Promise<AgentRun> {
  return apiFetch<AgentRun>('/api/seo/ai/agent/runs/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Resume an Agent Run paused at human approval checkpoint.
 */
export async function resumeAgentRun(
  id: number,
  payload: ResumeAgentRunPayload = { decision: 'approved' }
): Promise<AgentRun> {
  return apiFetch<AgentRun>(`/api/seo/ai/agent/runs/${id}/resume/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
