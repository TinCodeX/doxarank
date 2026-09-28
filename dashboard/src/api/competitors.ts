import { apiFetch } from './client';
import type {
  Competitor,
  CreateCompetitorPayload,
  UpdateCompetitorPayload,
  CompetitorSnapshot,
  CompetitorSnapshotJob,
  LatestCompetitorSnapshot,
  LaunchCompetitorSnapshotResponse,
} from '../types/competitor';

/**
 * Fetch competitors for a project.
 * (GET /api/seo/competitors/?project_id=<id>)
 */
export async function getCompetitors(projectId?: number): Promise<Competitor[]> {
  const query = projectId ? `?project_id=${projectId}` : '';
  return apiFetch<Competitor[]>(`/api/seo/competitors/${query}`);
}

/**
 * Create a new tracked competitor.
 * (POST /api/seo/competitors/)
 */
export async function createCompetitor(payload: CreateCompetitorPayload): Promise<Competitor> {
  return apiFetch<Competitor>('/api/seo/competitors/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update an existing competitor.
 * (PATCH /api/seo/competitors/<id>/)
 */
export async function updateCompetitor(
  id: number,
  payload: UpdateCompetitorPayload
): Promise<Competitor> {
  return apiFetch<Competitor>(`/api/seo/competitors/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Delete a competitor.
 * (DELETE /api/seo/competitors/<id>/)
 */
export async function deleteCompetitor(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/competitors/${id}/`, {
    method: 'DELETE',
  });
}

/**
 * Trigger an asynchronous competitor SERP snapshot batch.
 * (POST /api/seo/competitor-snapshots/check/)
 */
export async function triggerCompetitorSnapshot(
  projectId: number
): Promise<LaunchCompetitorSnapshotResponse> {
  return apiFetch<LaunchCompetitorSnapshotResponse>('/api/seo/competitor-snapshots/check/', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId }),
  });
}

/**
 * Fetch historical competitor snapshots.
 * (GET /api/seo/competitor-snapshots/?project_id=<id>&competitor_id=<id>&keyword_id=<id>)
 */
export async function getCompetitorSnapshots(
  projectId?: number,
  competitorId?: number,
  keywordId?: number
): Promise<CompetitorSnapshot[]> {
  const params = new URLSearchParams();
  if (projectId) params.append('project_id', String(projectId));
  if (competitorId) params.append('competitor_id', String(competitorId));
  if (keywordId) params.append('keyword_id', String(keywordId));
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<CompetitorSnapshot[]>(`/api/seo/competitor-snapshots/${query}`);
}

/**
 * Fetch latest snapshot observation matrix for each (competitor, keyword) pair.
 * (GET /api/seo/competitor-snapshots/latest/?project_id=<id>)
 */
export async function getLatestCompetitorSnapshots(
  projectId: number
): Promise<LatestCompetitorSnapshot[]> {
  return apiFetch<LatestCompetitorSnapshot[]>(
    `/api/seo/competitor-snapshots/latest/?project_id=${projectId}`
  );
}

/**
 * Fetch competitor snapshot batch jobs.
 * (GET /api/seo/competitor-snapshot-jobs/?project_id=<id>)
 */
export async function getCompetitorSnapshotJobs(
  projectId?: number
): Promise<CompetitorSnapshotJob[]> {
  const query = projectId ? `?project_id=${projectId}` : '';
  return apiFetch<CompetitorSnapshotJob[]>(`/api/seo/competitor-snapshot-jobs/${query}`);
}

/**
 * Fetch a single competitor snapshot job by ID.
 * (GET /api/seo/competitor-snapshot-jobs/<id>/)
 */
export async function getCompetitorSnapshotJob(
  jobId: number
): Promise<CompetitorSnapshotJob> {
  return apiFetch<CompetitorSnapshotJob>(`/api/seo/competitor-snapshot-jobs/${jobId}/`);
}
