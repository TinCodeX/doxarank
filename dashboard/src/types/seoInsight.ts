export type InsightSeverity = 'critical' | 'warning' | 'opportunity' | 'info';

export type InsightStatus = 'open' | 'dismissed' | 'resolved';

export type InsightSource = 'ranking' | 'search_console' | 'site_audit' | 'combined';

export type InsightType =
  | 'ranking_drop'
  | 'ranking_improvement'
  | 'page_two_keyword'
  | 'high_impressions_low_ctr'
  | 'declining_clicks'
  | 'declining_impressions'
  | 'low_ctr'
  | 'high_position_opportunity'
  | 'technical_seo_issue'
  | 'keyword_cannibalization'
  | 'content_opportunity';

export interface SEOInsight {
  id: number;
  project: number;
  project_name: string;
  fingerprint: string;
  insight_type: InsightType;
  severity: InsightSeverity;
  title: string;
  description: string;
  recommendation: string;
  status: InsightStatus;
  source: InsightSource;
  related_keyword: number | null;
  related_keyword_name: string | null;
  related_url: string;
  metadata: Record<string, any>;
  detected_at: string;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SEOInsightAnalyzeSummary {
  created: number;
  updated: number;
  resolved: number;
  total_open: number;
}

export interface SEOInsightSummaryCounts {
  critical: number;
  warning: number;
  opportunity: number;
  info: number;
  open_total: number;
  resolved_total: number;
  dismissed_total: number;
  total: number;
}

export interface SEOInsightFilterParams {
  project_id?: number;
  severity?: InsightSeverity;
  status?: InsightStatus;
  insight_type?: InsightType;
  source?: InsightSource;
}
