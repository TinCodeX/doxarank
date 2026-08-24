import { apiFetch } from './client';
import type {
  SearchConsoleConnection,
  CreateSearchConsoleConnectionPayload,
  UpdateSearchConsoleConnectionPayload,
} from '../types/searchConsole';

/**
 * Fetch Search Console connection(s).
 * Supports optional project_id filtering: /api/seo/search-console/?project_id=<id>
 */
export async function getSearchConsoleConnections(
  projectId?: number
): Promise<SearchConsoleConnection[]> {
  const query = projectId ? `?project_id=${projectId}` : '';
  return apiFetch<SearchConsoleConnection[]>(`/api/seo/search-console/${query}`);
}

/**
 * Convenience helper to fetch the single Search Console connection for a project.
 */
export async function getSearchConsoleConnection(
  projectId: number
): Promise<SearchConsoleConnection | null> {
  const list = await getSearchConsoleConnections(projectId);
  return list.length > 0 ? list[0] : null;
}

/**
 * Fetch a single Search Console connection record by ID.
 * (GET /api/seo/search-console/<id>/)
 */
export async function getSearchConsoleConnectionById(
  id: number
): Promise<SearchConsoleConnection> {
  return apiFetch<SearchConsoleConnection>(`/api/seo/search-console/${id}/`);
}

/**
 * Create a new Search Console connection for a project.
 * (POST /api/seo/search-console/)
 */
export async function createSearchConsoleConnection(
  payload: CreateSearchConsoleConnectionPayload
): Promise<SearchConsoleConnection> {
  return apiFetch<SearchConsoleConnection>('/api/seo/search-console/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update an existing Search Console connection.
 * (PATCH /api/seo/search-console/<id>/)
 */
export async function updateSearchConsoleConnection(
  id: number,
  payload: UpdateSearchConsoleConnectionPayload
): Promise<SearchConsoleConnection> {
  return apiFetch<SearchConsoleConnection>(`/api/seo/search-console/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Delete / disconnect a Search Console connection.
 * (DELETE /api/seo/search-console/<id>/)
 */
export async function deleteSearchConsoleConnection(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/search-console/${id}/`, {
    method: 'DELETE',
  });
}
