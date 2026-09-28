import { apiFetch } from './client';
import type {
  Recommendation,
  RecommendationStatus,
  RecommendationFilterParams,
  GenerateRecommendationsPayload,
} from '../types/recommendation';

/**
 * Fetch project recommendations with optional filtering.
 * (GET /api/seo/recommendations/?project_id=<id>&status=<status>&severity=<severity>&...)
 */
export async function getRecommendations(
  params?: RecommendationFilterParams
): Promise<Recommendation[]> {
  const queryParts: string[] = [];
  if (params?.project_id) queryParts.push(`project_id=${params.project_id}`);
  if (params?.status) queryParts.push(`status=${params.status}`);
  if (params?.severity) queryParts.push(`severity=${params.severity}`);
  if (params?.category) queryParts.push(`category=${params.category}`);
  if (params?.source_type) queryParts.push(`source_type=${params.source_type}`);

  const queryString = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';
  return apiFetch<Recommendation[]>(`/api/seo/recommendations/${queryString}`);
}

/**
 * Update the lifecycle status of a recommendation.
 * (PATCH /api/seo/recommendations/<id>/)
 */
export async function updateRecommendationStatus(
  id: number,
  status: RecommendationStatus
): Promise<Recommendation> {
  return apiFetch<Recommendation>(`/api/seo/recommendations/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

/**
 * Convenience method to acknowledge a recommendation.
 * (POST /api/seo/recommendations/<id>/acknowledge/)
 */
export async function acknowledgeRecommendation(id: number): Promise<Recommendation> {
  return apiFetch<Recommendation>(`/api/seo/recommendations/${id}/acknowledge/`, {
    method: 'POST',
  });
}

/**
 * Convenience method to mark a recommendation as resolved.
 * (POST /api/seo/recommendations/<id>/resolve/)
 */
export async function resolveRecommendation(id: number): Promise<Recommendation> {
  return apiFetch<Recommendation>(`/api/seo/recommendations/${id}/resolve/`, {
    method: 'POST',
  });
}

/**
 * Convenience method to dismiss a recommendation.
 * (POST /api/seo/recommendations/<id>/dismiss/)
 */
export async function dismissRecommendation(id: number): Promise<Recommendation> {
  return apiFetch<Recommendation>(`/api/seo/recommendations/${id}/dismiss/`, {
    method: 'POST',
  });
}

/**
 * Trigger recommendation generation for a project.
 * (POST /api/seo/recommendations/generate/)
 */
export async function generateRecommendations(
  payload: GenerateRecommendationsPayload
): Promise<Recommendation[]> {
  return apiFetch<Recommendation[]>('/api/seo/recommendations/generate/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
