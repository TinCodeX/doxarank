import { apiFetch } from './client';
import type {
  SEOInsight,
  SEOInsightAnalyzeSummary,
  SEOInsightSummaryCounts,
  SEOInsightFilterParams,
  InsightStatus
} from '../types/seoInsight';

/**
 * Fetch SEO insights with optional filtering by project, severity, status, type, and source.
 */
export async function getSEOInsights(params: SEOInsightFilterParams = {}): Promise<SEOInsight[]> {
  const searchParams = new URLSearchParams();
  if (params.project_id) searchParams.append('project_id', String(params.project_id));
  if (params.severity) searchParams.append('severity', params.severity);
  if (params.status) searchParams.append('status', params.status);
  if (params.insight_type) searchParams.append('insight_type', params.insight_type);
  if (params.source) searchParams.append('source', params.source);

  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return apiFetch<SEOInsight[]>(`/api/seo/insights/${query}`);
}

/**
 * Fetch a single SEO insight by ID.
 */
export async function getSEOInsight(id: number): Promise<SEOInsight> {
  return apiFetch<SEOInsight>(`/api/seo/insights/${id}/`);
}

/**
 * Trigger backend deterministic SEO intelligence analysis for a project.
 */
export async function analyzeSEO(projectId: number): Promise<SEOInsightAnalyzeSummary> {
  return apiFetch<SEOInsightAnalyzeSummary>('/api/seo/insights/analyze/', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId }),
  });
}

/**
 * Update the workflow status of an SEO insight (open, dismissed, resolved).
 */
export async function updateSEOInsightStatus(id: number, status: InsightStatus): Promise<SEOInsight> {
  return apiFetch<SEOInsight>(`/api/seo/insights/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

/**
 * Fetch aggregated insight counts by severity and status for a project.
 */
export async function getSEOInsightsSummary(projectId: number): Promise<SEOInsightSummaryCounts> {
  return apiFetch<SEOInsightSummaryCounts>(`/api/seo/insights/summary/?project_id=${projectId}`);
}

/**
 * Delete an SEO insight record.
 */
export async function deleteSEOInsight(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/insights/${id}/`, {
    method: 'DELETE',
  });
}
