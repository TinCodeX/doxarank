import { apiFetch } from './client';
import type {
  MonitoringState,
  MonitoringSnapshot,
  MonitoringMetrics,
  MonitoringCycleResult,
} from '../types/seoMonitoring';

/**
 * Fetch active monitoring states for a project with optional filters.
 */
export async function getMonitoringStates(
  projectId?: number,
  filters?: { monitor_type?: string; status?: string }
): Promise<MonitoringState[]> {
  const params = new URLSearchParams();
  if (projectId) params.append('project', projectId.toString());
  if (filters?.monitor_type) params.append('monitor_type', filters.monitor_type);
  if (filters?.status) params.append('status', filters.status);

  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<MonitoringState[]>(`/api/seo/ai/monitoring/${query}`);
}

/**
 * Fetch detailed monitoring state by ID.
 */
export async function getMonitoringState(id: number): Promise<MonitoringState> {
  return apiFetch<MonitoringState>(`/api/seo/ai/monitoring/${id}/`);
}

/**
 * Fetch monitoring observation snapshots for a project.
 */
export async function getMonitoringSnapshots(
  projectId?: number,
  filters?: { monitor_type?: string }
): Promise<MonitoringSnapshot[]> {
  const params = new URLSearchParams();
  if (projectId) params.append('project', projectId.toString());
  if (filters?.monitor_type) params.append('monitor_type', filters.monitor_type);

  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<MonitoringSnapshot[]>(`/api/seo/ai/monitoring/snapshots/${query}`);
}

/**
 * Fetch detected changes and recoveries (anomalies / recoveries).
 */
export async function getMonitoringChanges(
  projectId?: number
): Promise<MonitoringSnapshot[]> {
  const params = new URLSearchParams();
  if (projectId) params.append('project', projectId.toString());

  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<MonitoringSnapshot[]>(`/api/seo/ai/monitoring/changes/${query}`);
}

/**
 * Fetch runtime evaluation metrics for autonomous SEO monitoring.
 */
export async function getMonitoringMetrics(
  projectId: number
): Promise<MonitoringMetrics> {
  const params = new URLSearchParams({ project: projectId.toString() });
  return apiFetch<MonitoringMetrics>(`/api/seo/ai/monitoring/metrics/?${params.toString()}`);
}

/**
 * Trigger an on-demand autonomous monitoring cycle for a project.
 */
export async function triggerMonitoringCycle(
  projectId: number
): Promise<MonitoringCycleResult> {
  return apiFetch<MonitoringCycleResult>('/api/seo/ai/monitoring/trigger/', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId }),
  });
}
