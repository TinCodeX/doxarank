export type BriefContentType =
  | 'blog_post'
  | 'landing_page'
  | 'page_optimization'
  | 'technical_implementation';

export type BriefSearchIntent =
  | 'informational'
  | 'transactional'
  | 'commercial'
  | 'navigational';

export type BriefStatus =
  | 'draft'
  | 'in_progress'
  | 'completed'
  | 'archived';

export interface OutlineItem {
  heading: string;
  level: 'H1' | 'H2' | 'H3';
  key_points: string[];
}

export interface InternalLinkSuggestion {
  target_url: string;
  anchor_text: string;
  context: string;
}

export interface ExternalLinkSuggestion {
  source: string;
  anchor_text: string;
  context: string;
}

export interface FAQQuestion {
  question: string;
  answer_guidance: string;
}

export interface SEOContentBrief {
  id: number;
  project: number;
  project_name: string;
  recommendation: number | null;
  recommendation_title?: string;
  recommendation_priority?: string;
  title: string;
  target_keyword: string;
  secondary_keywords: string[];
  search_intent: BriefSearchIntent;
  search_intent_display: string;
  target_url: string;
  content_type: BriefContentType;
  content_type_display: string;
  recommended_title: string;
  meta_description: string;
  suggested_slug: string;
  content_angle: string;
  audience: string;
  outline: OutlineItem[];
  key_points: string[];
  internal_link_suggestions: InternalLinkSuggestion[];
  external_link_suggestions: ExternalLinkSuggestion[];
  faq_questions: FAQQuestion[];
  entities_topics: string[];
  content_length_target: number | null;
  generated_content: Record<string, any>;
  status: BriefStatus;
  status_display: string;
  created_at: string;
  updated_at: string;
}

export interface GenerateContentBriefPayload {
  project_id: number;
  recommendation_id: number;
  content_type?: BriefContentType;
}

export interface UpdateContentBriefPayload {
  title?: string;
  target_keyword?: string;
  secondary_keywords?: string[];
  search_intent?: BriefSearchIntent;
  target_url?: string;
  content_type?: BriefContentType;
  recommended_title?: string;
  meta_description?: string;
  suggested_slug?: string;
  content_angle?: string;
  audience?: string;
  outline?: OutlineItem[];
  key_points?: string[];
  internal_link_suggestions?: InternalLinkSuggestion[];
  external_link_suggestions?: ExternalLinkSuggestion[];
  faq_questions?: FAQQuestion[];
  entities_topics?: string[];
  content_length_target?: number;
  status?: BriefStatus;
}
