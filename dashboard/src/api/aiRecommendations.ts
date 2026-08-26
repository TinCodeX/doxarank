import { apiFetch } from './client';
import type {
  SEORecommendation,
  SEORecommendationSummaryCounts,
  SEORecommendationFilterParams,
  RecommendationGeneratePayload,
  RecommendationStatus
} from '../types/aiRecommendation';

/**
 * Fetch AI SEO recommendations with optional filtering.
 */
export async function getSEORecommendations(
  params: SEORecommendationFilterParams = {}
): Promise<SEORecommendation[]> {
  const searchParams = new URLSearchParams();
  if (params.project_id) searchParams.append('project_id', String(params.project_id));
  if (params.insight_id) searchParams.append('insight_id', String(params.insight_id));
  if (params.status) searchParams.append('status', params.status);
  if (params.priority) searchParams.append('priority', params.priority);
  if (params.recommendation_type) searchParams.append('recommendation_type', params.recommendation_type);

  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return apiFetch<SEORecommendation[]>(`/api/seo/ai/recommendations/${query}`);
}

/**
 * Fetch a single AI SEO recommendation by ID.
 */
export async function getSEORecommendation(id: number): Promise<SEORecommendation> {
  return apiFetch<SEORecommendation>(`/api/seo/ai/recommendations/${id}/`);
}

/**
 * Trigger AI recommendation generation for a project or specific insights.
 */
export async function generateSEORecommendations(
  payload: RecommendationGeneratePayload
): Promise<SEORecommendation[]> {
  return apiFetch<SEORecommendation[]>('/api/seo/ai/recommendations/generate/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update the workflow status of an AI SEO recommendation.
 */
export async function updateSEORecommendationStatus(
  id: number,
  status: RecommendationStatus
): Promise<SEORecommendation> {
  return apiFetch<SEORecommendation>(`/api/seo/ai/recommendations/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

/**
 * Fetch aggregated AI recommendation counts by priority and status.
 */
export async function getSEORecommendationsSummary(
  projectId: number
): Promise<SEORecommendationSummaryCounts> {
  return apiFetch<SEORecommendationSummaryCounts>(
    `/api/seo/ai/recommendations/summary/?project_id=${projectId}`
  );
}

/**
 * Delete an AI recommendation record.
 */
export async function deleteSEORecommendation(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/ai/recommendations/${id}/`, {
    method: 'DELETE',
  });
}
