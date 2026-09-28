import { apiFetch } from './client';
import type { CrawlJob, CrawlPage, LaunchCrawlPayload, LaunchCrawlResponse } from '../types/crawlJob';

/**
 * Fetch all crawl jobs owned by the authenticated user.
 * Optionally filter by project_id.
 * GET /api/seo/crawler/?project_id=<id>
 */
export async function getCrawlJobs(projectId?: number): Promise<CrawlJob[]> {
  const query = projectId ? `?project_id=${projectId}` : '';
  return apiFetch<CrawlJob[]>(`/api/seo/crawler/${query}`);
}

/**
 * Fetch a single crawl job by ID.
 * GET /api/seo/crawler/<id>/
 */
export async function getCrawlJob(id: number): Promise<CrawlJob> {
  return apiFetch<CrawlJob>(`/api/seo/crawler/${id}/`);
}

/**
 * Launch a new technical SEO crawl for a project.
 * POST /api/seo/crawler/launch/
 *
 * Returns 202 Accepted with the created CrawlJob.
 * Requires FeatureCode.TECHNICAL_CRAWLER (Starter/Agency plans only).
 */
export async function launchCrawl(payload: LaunchCrawlPayload): Promise<LaunchCrawlResponse> {
  return apiFetch<LaunchCrawlResponse>('/api/seo/crawler/launch/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Fetch crawled pages for a specific crawl job.
 * Supports optional filtering by is_broken or is_slow.
 * GET /api/seo/crawler-pages/?crawl_job_id=<id>&is_broken=true
 */
export async function getCrawlPages(
  crawlJobId: number,
  filters?: { is_broken?: boolean; is_slow?: boolean }
): Promise<CrawlPage[]> {
  const params = new URLSearchParams({ crawl_job_id: String(crawlJobId) });
  if (filters?.is_broken !== undefined) params.set('is_broken', String(filters.is_broken));
  if (filters?.is_slow !== undefined) params.set('is_slow', String(filters.is_slow));
  return apiFetch<CrawlPage[]>(`/api/seo/crawler-pages/?${params}`);
}
