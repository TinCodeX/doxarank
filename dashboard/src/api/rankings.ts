import { apiFetch } from './client';
import type { Ranking, CreateRankingPayload, UpdateRankingPayload } from '../types/ranking';

/**
 * Fetch ranking observations.
 * Supports optional keyword_id filtering: /api/seo/rankings/?keyword_id=<id>
 */
export async function getRankings(keywordId?: number): Promise<Ranking[]> {
  const query = keywordId ? `?keyword_id=${keywordId}` : '';
  return apiFetch<Ranking[]>(`/api/seo/rankings/${query}`);
}

/**
 * Fetch a single ranking observation by ID.
 * (GET /api/seo/rankings/<id>/)
 */
export async function getRanking(id: number): Promise<Ranking> {
  return apiFetch<Ranking>(`/api/seo/rankings/${id}/`);
}

/**
 * Create a new keyword ranking observation.
 * (POST /api/seo/rankings/)
 */
export async function createRanking(payload: CreateRankingPayload): Promise<Ranking> {
  return apiFetch<Ranking>('/api/seo/rankings/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update an existing keyword ranking observation.
 * (PATCH /api/seo/rankings/<id>/)
 */
export async function updateRanking(
  id: number,
  payload: UpdateRankingPayload
): Promise<Ranking> {
  return apiFetch<Ranking>(`/api/seo/rankings/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Delete a keyword ranking observation.
 * (DELETE /api/seo/rankings/<id>/)
 */
export async function deleteRanking(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/rankings/${id}/`, {
    method: 'DELETE',
  });
}
