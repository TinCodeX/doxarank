import type { BriefContentType, BriefSearchIntent } from './seoContentBrief';

export type DraftStatus =
  | 'draft'
  | 'generating'
  | 'generated'
  | 'reviewed'
  | 'approved'
  | 'published'
  | 'archived';

export interface DraftSection {
  heading: string;
  level: string; // 'H1' | 'H2' | 'H3'
  content: string;
  key_points?: string[];
}

export interface DraftFAQItem {
  question: string;
  answer: string;
}

export interface DraftLinkItem {
  target_url: string;
  anchor_text: string;
  context?: string;
}

export interface DraftCitationItem {
  source: string;
  anchor_text: string;
  context?: string;
}

export interface DraftKeywordUsage {
  total_words: number;
  target_keyword: {
    phrase: string;
    occurrences: number;
    density_percent: number;
    in_title: boolean;
  };
  secondary_keywords: Record<string, number>;
  secondary_coverage_percent: number;
  secondary_covered_count: number;
  secondary_total_count: number;
}

export interface SEOContentDraft {
  id: number;
  project: number;
  project_name: string;
  brief: number;
  brief_title: string;
  recommendation: number | null;
  insight: number | null;
  title: string;
  target_keyword: string;
  secondary_keywords: string[];
  search_intent: BriefSearchIntent;
  search_intent_display: string;
  target_url: string;
  content_type: BriefContentType;
  content_type_display: string;
  introduction: string;
  content_body: string;
  outline_structure: DraftSection[];
  word_count: number;
  keyword_usage: DraftKeywordUsage;
  internal_links: DraftLinkItem[];
  external_links: DraftCitationItem[];
  faq_section: DraftFAQItem[];
  meta_title: string;
  meta_description: string;
  suggested_slug: string;
  schema_json_ld: Record<string, any>;
  generated_content: Record<string, any>;
  generation_metadata: Record<string, any>;
  status: DraftStatus;
  status_display: string;
  created_at: string;
  updated_at: string;
}

export interface GenerateDraftRequest {
  project_id: number;
  content_brief_id: number;
  regenerate?: boolean;
}

export interface UpdateDraftRequest {
  title?: string;
  meta_title?: string;
  meta_description?: string;
  suggested_slug?: string;
  introduction?: string;
  content_body?: string;
  outline_structure?: DraftSection[];
  faq_section?: DraftFAQItem[];
  internal_links?: DraftLinkItem[];
  external_links?: DraftCitationItem[];
  schema_json_ld?: Record<string, any>;
  status?: DraftStatus;
}
