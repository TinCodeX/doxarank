export type CompetitorJobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'partial_failure';
export type CompetitorResultStatus = 'found' | 'not_found' | 'error';

export interface Competitor {
  id: number;
  project: number;
  project_name?: string;
  name: string;
  domain: string;
  website_url?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateCompetitorPayload {
  project: number;
  name: string;
  domain: string;
  website_url?: string;
  is_active?: boolean;
}

export interface UpdateCompetitorPayload {
  name?: string;
  domain?: string;
  website_url?: string;
  is_active?: boolean;
}

export interface CompetitorSnapshot {
  id: number;
  competitor: number;
  competitor_name?: string;
  competitor_domain?: string;
  project: number;
  project_name?: string;
  keyword: number;
  keyword_name?: string;
  snapshot_job: number | null;
  position: number | null;
  ranking_url: string;
  title: string;
  result_status: CompetitorResultStatus;
  search_engine: string;
  search_domain: string;
  country: string;
  language: string;
  device: string;
  error_message?: string;
  recorded_at: string;
}

export interface CompetitorSnapshotJob {
  id: number;
  project: number;
  project_name?: string;
  status: CompetitorJobStatus;
  total_keywords: number;
  completed_keywords: number;
  failed_keywords: number;
  trigger: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface LatestCompetitorSnapshot {
  competitor_id: number;
  competitor_name: string;
  competitor_domain: string;
  keyword_id: number;
  keyword: string;
  position: number | null;
  ranking_url: string;
  title: string;
  result_status: string;
  recorded_at: string | null;
  search_domain: string;
}

export interface LaunchCompetitorSnapshotResponse {
  status: string;
  job_id?: number;
  task_id?: string;
  project_id?: number;
  message: string;
}
