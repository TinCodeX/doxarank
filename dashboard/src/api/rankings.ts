import { apiFetch } from './client';
import type {
  Ranking,
  CreateRankingPayload,
  UpdateRankingPayload,
  KeywordRankingSummary,
  RankCheckJob,
  LaunchRankCheckPayload,
  LaunchRankCheckResponse,
} from '../types/ranking';

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

/**
 * Trigger an asynchronous ranking check (single keyword or project batch).
 * (POST /api/seo/rankings/check/)
 */
export async function triggerRankCheck(
  payload: LaunchRankCheckPayload
): Promise<LaunchRankCheckResponse> {
  return apiFetch<LaunchRankCheckResponse>('/api/seo/rankings/check/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Fetch project keyword ranking summary with current/previous/delta metrics.
 * (GET /api/seo/rankings/summary/?project_id=<id>)
 */
export async function getRankingSummary(
  projectId: number
): Promise<KeywordRankingSummary[]> {
  return apiFetch<KeywordRankingSummary[]>(`/api/seo/rankings/summary/?project_id=${projectId}`);
}

/**
 * Fetch historical ranking snapshots for a tracked keyword.
 * (GET /api/seo/rankings/history/?keyword_id=<id>)
 */
export async function getRankingHistory(
  keywordId: number
): Promise<Ranking[]> {
  return apiFetch<Ranking[]>(`/api/seo/rankings/history/?keyword_id=${keywordId}`);
}

/**
 * Fetch recent rank check jobs for a project.
 * (GET /api/seo/rankings/jobs/?project_id=<id>)
 */
export async function getRankCheckJobs(
  projectId?: number
): Promise<RankCheckJob[]> {
  const query = projectId ? `?project_id=${projectId}` : '';
  return apiFetch<RankCheckJob[]>(`/api/seo/rankings/jobs/${query}`);
}

/**
 * Fetch a single rank check job by ID.
 * (GET /api/seo/rankings/jobs/<jobId>/)
 */
export async function getRankCheckJob(
  jobId: number
): Promise<RankCheckJob> {
  return apiFetch<RankCheckJob>(`/api/seo/rankings/jobs/${jobId}/`);
}
