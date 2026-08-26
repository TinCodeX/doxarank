export type RecommendationType =
  | 'meta_title'
  | 'meta_description'
  | 'content_update'
  | 'keyword_optimization'
  | 'internal_linking'
  | 'technical_seo'
  | 'ranking_recovery'
  | 'ctr_optimization'
  | 'page_two_opportunity'
  | 'general_seo';

export type RecommendationPriority = 'critical' | 'high' | 'medium' | 'low';

export type RecommendationStatus = 'pending_review' | 'reviewed' | 'applied' | 'dismissed';

export interface GeneratedContent {
  proposed_title?: string;
  proposed_meta_description?: string;
  action_checklist?: string[];
  content_suggestions?: string;
  [key: string]: any;
}

export interface SEORecommendation {
  id: number;
  project: number;
  project_name: string;
  insight: number;
  insight_title: string;
  insight_severity: string;
  insight_type: string;
  recommendation_type: RecommendationType;
  title: string;
  summary: string;
  explanation: string;
  priority: RecommendationPriority;
  recommended_action: string;
  expected_impact: string;
  affected_url: string;
  affected_keyword: string;
  generated_content: GeneratedContent;
  status: RecommendationStatus;
  created_at: string;
  updated_at: string;
}

export interface SEORecommendationSummaryCounts {
  critical: number;
  high: number;
  medium: number;
  low: number;
  pending_review: number;
  reviewed: number;
  applied: number;
  dismissed: number;
  total: number;
}

export interface SEORecommendationFilterParams {
  project_id?: number;
  insight_id?: number;
  status?: RecommendationStatus;
  priority?: RecommendationPriority;
  recommendation_type?: RecommendationType;
}

export interface RecommendationGeneratePayload {
  project_id: number;
  insight_ids?: number[];
}
