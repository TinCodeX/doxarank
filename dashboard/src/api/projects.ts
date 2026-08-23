import { apiFetch } from './client';
import type { Project, CreateProjectPayload, UpdateProjectPayload } from '../types/project';

/**
 * Fetch all projects belonging to the authenticated user.
 * (GET /api/projects/)
 */
export async function getProjects(): Promise<Project[]> {
  return apiFetch<Project[]>('/api/projects/');
}

/**
 * Fetch a single project by ID.
 * (GET /api/projects/<id>/)
 */
export async function getProject(id: number): Promise<Project> {
  return apiFetch<Project>(`/api/projects/${id}/`);
}

/**
 * Create a new project for the authenticated user.
 * Note: owner_id is NOT sent here; the backend extracts it from the JWT.
 * (POST /api/projects/)
 */
export async function createProject(payload: CreateProjectPayload): Promise<Project> {
  return apiFetch<Project>('/api/projects/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update an existing project owned by the authenticated user.
 * (PATCH /api/projects/<id>/)
 */
export async function updateProject(
  id: number,
  payload: UpdateProjectPayload
): Promise<Project> {
  return apiFetch<Project>(`/api/projects/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Delete a project owned by the authenticated user.
 * (DELETE /api/projects/<id>/)
 */
export async function deleteProject(id: number): Promise<void> {
  return apiFetch<void>(`/api/projects/${id}/`, {
    method: 'DELETE',
  });
}
