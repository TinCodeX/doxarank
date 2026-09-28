export type RecommendationSourceType = 'crawler' | 'rank_tracker' | 'competitor_snapshot' | 'seo_tool' | 'system';

export type RecommendationCategory =
  | 'technical_seo'
  | 'on_page_seo'
  | 'performance'
  | 'indexing'
  | 'rankings'
  | 'content'
  | 'competitors';

export type RecommendationSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export type RecommendationStatus = 'open' | 'acknowledged' | 'resolved' | 'dismissed';

export interface Recommendation {
  id: number;
  project: number;
  project_name?: string;
  project_website_url?: string;
  source_type: RecommendationSourceType;
  source_id?: string;
  category: RecommendationCategory;
  severity: RecommendationSeverity;
  title: string;
  description: string;
  recommended_action: string;
  affected_url?: string;
  affected_keyword?: string;
  status: RecommendationStatus;
  priority: number;
  fingerprint: string;
  metadata?: Record<string, any>;
  created_at: string;
  updated_at: string;
  resolved_at?: string | null;
}

export interface GenerateRecommendationsPayload {
  project_id: number;
  async?: boolean;
}

export interface RecommendationFilterParams {
  project_id?: number;
  status?: RecommendationStatus;
  severity?: RecommendationSeverity;
  category?: RecommendationCategory;
  source_type?: RecommendationSourceType;
}
