import { apiFetch } from './client';
import type {
  ContinuousOperation,
  ContinuousOperationCreatePayload,
  OperationalMetricsReport,
} from '../types/continuousOperation';
import type { AgentRun } from '../types/agentRun';

/**
 * Fetch all continuous operations for a project.
 */
export async function getContinuousOperations(projectId?: number): Promise<ContinuousOperation[]> {
  const query = projectId ? `?project=${projectId}` : '';
  return apiFetch<ContinuousOperation[]>(`/api/seo/ai/operations/${query}`);
}

/**
 * Fetch single continuous operation details.
 */
export async function getContinuousOperation(id: number): Promise<ContinuousOperation> {
  return apiFetch<ContinuousOperation>(`/api/seo/ai/operations/${id}/`);
}

/**
 * Create a new continuous operation session.
 */
export async function createContinuousOperation(
  payload: ContinuousOperationCreatePayload
): Promise<ContinuousOperation> {
  return apiFetch<ContinuousOperation>('/api/seo/ai/operations/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Pause an active continuous operation.
 */
export async function pauseContinuousOperation(id: number): Promise<ContinuousOperation> {
  return apiFetch<ContinuousOperation>(`/api/seo/ai/operations/${id}/pause/`, {
    method: 'POST',
  });
}

/**
 * Resume a paused continuous operation.
 */
export async function resumeContinuousOperation(id: number): Promise<ContinuousOperation> {
  return apiFetch<ContinuousOperation>(`/api/seo/ai/operations/${id}/resume/`, {
    method: 'POST',
  });
}

/**
 * Manually trigger an immediate scheduled run for an operation.
 */
export async function triggerContinuousOperationRun(id: number): Promise<AgentRun> {
  return apiFetch<AgentRun>(`/api/seo/ai/operations/${id}/trigger/`, {
    method: 'POST',
  });
}

/**
 * Fetch all AgentRun sessions launched under a continuous operation.
 */
export async function getContinuousOperationRuns(id: number): Promise<AgentRun[]> {
  return apiFetch<AgentRun[]>(`/api/seo/ai/operations/${id}/runs/`);
}

/**
 * Fetch runtime operational metrics for a specific operation.
 */
export async function getContinuousOperationMetrics(id: number): Promise<OperationalMetricsReport> {
  return apiFetch<OperationalMetricsReport>(`/api/seo/ai/operations/${id}/metrics/`);
}

/**
 * Fetch aggregated continuous operational metrics for a project.
 */
export async function getProjectOperationalMetrics(projectId: number): Promise<OperationalMetricsReport> {
  return apiFetch<OperationalMetricsReport>(`/api/seo/ai/operations/metrics/?project=${projectId}`);
}
