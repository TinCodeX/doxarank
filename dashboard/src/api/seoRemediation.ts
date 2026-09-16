import { apiFetch } from './client';
import type {
  RemediationRecord,
  ProjectRemediationPolicy,
  RemediationMetrics,
} from '../types/seoRemediation';

/**
 * Fetch remediation history records for a project with optional status/risk filters.
 */
export async function getRemediationRecords(
  projectId?: number,
  filters?: { status?: string; risk_level?: string; is_autonomous?: boolean }
): Promise<RemediationRecord[]> {
  const params = new URLSearchParams();
  if (projectId) params.append('project', projectId.toString());
  if (filters?.status) params.append('status', filters.status);
  if (filters?.risk_level) params.append('risk_level', filters.risk_level);
  if (filters?.is_autonomous !== undefined) {
    params.append('is_autonomous', filters.is_autonomous ? 'true' : 'false');
  }

  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<RemediationRecord[]>(`/api/seo/ai/remediation/${query}`);
}

/**
 * Fetch detailed remediation record by ID.
 */
export async function getRemediationRecord(id: number): Promise<RemediationRecord> {
  return apiFetch<RemediationRecord>(`/api/seo/ai/remediation/${id}/`);
}

/**
 * Fetch runtime evaluation metrics for autonomous remediation.
 */
export async function getRemediationMetrics(projectId: number): Promise<RemediationMetrics> {
  const params = new URLSearchParams();
  params.append('project', projectId.toString());
  return apiFetch<RemediationMetrics>(`/api/seo/ai/remediation/metrics/?${params.toString()}`);
}

/**
 * Fetch project remediation policy settings.
 */
export async function getRemediationPolicy(projectId: number): Promise<ProjectRemediationPolicy> {
  const params = new URLSearchParams();
  params.append('project', projectId.toString());
  return apiFetch<ProjectRemediationPolicy>(`/api/seo/ai/remediation/policy/?${params.toString()}`);
}
