/**
 * TypeScript type definitions for the Technical SEO Crawler feature.
 * Mirrors backend CrawlJob and CrawlPage Django models.
 */

export type CrawlJobStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface CrawlJob {
  id: number;
  project: number;
  project_name: string;
  project_website_url: string;
  status: CrawlJobStatus;
  max_pages: number;
  max_depth: number;
  respect_robots_txt: boolean;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  pages_crawled: number;
  pages_discovered: number;
  broken_links_count: number;
  missing_titles_count: number;
  missing_descriptions_count: number;
  duplicate_titles_count: number;
  missing_h1_count: number;
  redirect_chains_count: number;
  slow_pages_count: number;
  celery_task_id: string | null;
  error_message: string | null;
  crawl_metadata: Record<string, unknown>;
  duration_seconds: number | null;
  pages_count: number;
}

export interface CrawlPageIssue {
  type: string;
  severity: 'critical' | 'warning' | 'notice';
  message: string;
}

export interface CrawlPage {
  id: number;
  crawl_job: number;
  url: string;
  final_url: string | null;
  status_code: number;
  response_time_ms: number;
  depth: number;
  title: string | null;
  meta_description: string | null;
  h1_count: number;
  word_count: number;
  canonical_url: string | null;
  has_redirect: boolean;
  redirect_chain: string[];
  internal_links_count: number;
  external_links_count: number;
  images_count: number;
  images_missing_alt_count: number;
  is_broken: boolean;
  is_slow: boolean;
  issues: CrawlPageIssue[];
  created_at: string;
}

export interface LaunchCrawlPayload {
  project_id: number;
  max_pages?: number;
  max_depth?: number;
  respect_robots_txt?: boolean;
}

export interface LaunchCrawlResponse {
  crawl_job: CrawlJob;
}
