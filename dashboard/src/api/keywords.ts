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
