import type { SearchEngine, CountryCode, LanguageCode, DeviceType } from './keyword';

export type RankingResultStatus = 'found' | 'not_found' | 'error';
export type RankCheckJobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'partial_failure';
export type PositionChangeStatus = 'improved' | 'declined' | 'entered' | 'dropped' | 'unchanged' | 'new' | 'not_found';

export interface Ranking {
  id: number;
  keyword: number;
  keyword_name?: string;
  project_id?: number;
  project_name?: string;
  position: number | null;
  result_status?: RankingResultStatus;
  ranking_url: string | null;
  title?: string;
  search_engine: SearchEngine;
  search_domain?: string;
  country: CountryCode;
  language: LanguageCode;
  device: DeviceType;
  error_message?: string;
  recorded_at: string;
  created_at: string;
}

export interface CreateRankingPayload {
  keyword: number;
  position?: number | null;
  result_status?: RankingResultStatus;
  ranking_url?: string;
  title?: string;
  search_engine?: SearchEngine;
  search_domain?: string;
  country?: CountryCode;
  language?: LanguageCode;
  device?: DeviceType;
  error_message?: string;
  recorded_at?: string;
}

export interface UpdateRankingPayload {
  keyword?: number;
  position?: number | null;
  result_status?: RankingResultStatus;
  ranking_url?: string;
  title?: string;
  search_engine?: SearchEngine;
  search_domain?: string;
  country?: CountryCode;
  language?: LanguageCode;
  device?: DeviceType;
  error_message?: string;
  recorded_at?: string;
}

export interface KeywordRankingSummary {
  keyword_id: number;
  keyword: string;
  search_engine: SearchEngine;
  search_domain: string;
  country: CountryCode;
  language: LanguageCode;
  device: DeviceType;
  is_active: boolean;
  created_at: string;
  current_position: number | null;
  previous_position: number | null;
  change: number | null;
  change_status: PositionChangeStatus;
  ranking_url: string | null;
  title: string;
  last_checked_at: string | null;
  result_status: string;
}

export interface RankCheckJob {
  id: number;
  project: number;
  project_name?: string;
  status: RankCheckJobStatus;
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

export interface LaunchRankCheckPayload {
  keyword_id?: number;
  project_id?: number;
}

export interface LaunchRankCheckResponse {
  status: string;
  job_id?: number;
  task_id?: string;
  project_id?: number;
  keyword_id?: number;
  total_keywords?: number;
  message: string;
}
