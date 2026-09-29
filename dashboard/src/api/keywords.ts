import { apiFetch } from './client';
import type { Keyword, CreateKeywordPayload, UpdateKeywordPayload } from '../types/keyword';

/**
 * Fetch keywords belonging to authenticated user's projects.
 * Supports optional project_id filtering: /api/seo/keywords/?project_id=<id>
 */
export async function getKeywords(projectId?: number): Promise<Keyword[]> {
  const query = projectId ? `?project_id=${projectId}` : '';
  return apiFetch<Keyword[]>(`/api/seo/keywords/${query}`);
}

/**
 * Fetch a single keyword by ID.
 * (GET /api/seo/keywords/<id>/)
 */
export async function getKeyword(id: number): Promise<Keyword> {
  return apiFetch<Keyword>(`/api/seo/keywords/${id}/`);
}

/**
 * Create a new keyword for a project.
 * (POST /api/seo/keywords/)
 */
export async function createKeyword(payload: CreateKeywordPayload): Promise<Keyword> {
  return apiFetch<Keyword>('/api/seo/keywords/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update an existing keyword.
 * (PATCH /api/seo/keywords/<id>/)
 */
export async function updateKeyword(
  id: number,
  payload: UpdateKeywordPayload
): Promise<Keyword> {
  return apiFetch<Keyword>(`/api/seo/keywords/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Delete a keyword.
 * (DELETE /api/seo/keywords/<id>/)
 */
export async function deleteKeyword(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/keywords/${id}/`, {
    method: 'DELETE',
  });
}

/**
 * Fetch keyword intelligence metrics for a single keyword.
 * (GET /api/seo/keywords/<id>/intelligence/)
 */
export async function getKeywordIntelligence(keywordId: number): Promise<import('../types/keyword').KeywordIntelligence> {
  return apiFetch<import('../types/keyword').KeywordIntelligence>(`/api/seo/keywords/${keywordId}/intelligence/`);
}

/**
 * Request fresh keyword intelligence for a single keyword.
 * (POST /api/seo/keywords/<id>/intelligence/refresh/)
 */
export async function refreshKeywordIntelligence(
  keywordId: number,
  force: boolean = false
): Promise<import('../types/keyword').KeywordIntelligence> {
  return apiFetch<import('../types/keyword').KeywordIntelligence>(`/api/seo/keywords/${keywordId}/intelligence/refresh/`, {
    method: 'POST',
    body: JSON.stringify({ force }),
  });
}

/**
 * Bulk refresh keyword intelligence for all active keywords of a project.
 * (POST /api/seo/keyword-intelligence/refresh/)
 */
export async function bulkRefreshKeywordIntelligence(
  projectId: number,
  force: boolean = false
): Promise<{ status: string; total_keywords: number; queued_keywords_count: number }> {
  return apiFetch('/api/seo/keyword-intelligence/refresh/', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, force }),
  });
}

/**
 * Fetch snapshot history for a keyword intelligence record.
 * (GET /api/seo/keyword-intelligence/<id>/history/)
 */
export async function getKeywordIntelligenceHistory(
  intelId: number
): Promise<import('../types/keyword').KeywordIntelligenceSnapshot[]> {
  return apiFetch<import('../types/keyword').KeywordIntelligenceSnapshot[]>(`/api/seo/keyword-intelligence/${intelId}/history/`);
}

