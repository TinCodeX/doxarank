import { apiFetch } from './client';
import type {
  ExternalConnection,
  ExternalOperationRecord,
} from '../types/externalIntegration';

/**
 * Fetch project-scoped external connections (CMS, Git, Webhook).
 */
export async function getExternalConnections(
  projectId?: number,
  systemType?: string
): Promise<ExternalConnection[]> {
  const params = new URLSearchParams();
  if (projectId) params.append('project_id', projectId.toString());
  if (systemType) params.append('system_type', systemType);

  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<ExternalConnection[]>(`/api/seo/ai/integrations/${query}`);
}

/**
 * Fetch operations history for a specific external connection.
 */
export async function getConnectionOperations(
  connectionId: number
): Promise<ExternalOperationRecord[]> {
  return apiFetch<ExternalOperationRecord[]>(`/api/seo/ai/integrations/${connectionId}/operations/`);
}

/**
 * Fetch external operations correlated with an orchestration run.
 */
export async function getRunExternalIntegrations(
  runId: string | number
): Promise<{ run_id: number; project_id: number; operations_count: number; operations: ExternalOperationRecord[] }> {
  return apiFetch(`/api/seo/ai/orchestrate/${runId}/integrations/`);
}
