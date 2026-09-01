export type ActionType =
  | 'update_title'
  | 'update_meta_description'
  | 'update_slug'
  | 'optimize_existing_content'
  | 'publish_new_content'
  | 'add_internal_links'
  | 'add_structured_data'
  | 'technical_seo_fix'
  | 'content_refresh'
  | 'optimize_title'
  | 'optimize_meta_description'
  | 'fix_missing_h1'
  | 'fix_canonical'
  | 'fix_image_alt'
  | 'fix_broken_link'
  | 'improve_content'
  | 'investigate_performance'
  | 'monitor'
  | 'no_action';

export type ActionStatus =
  | 'proposed'
  | 'pending_approval'
  | 'reviewed'
  | 'approved'
  | 'ready_to_execute'
  | 'executing'
  | 'completed'
  | 'rejected'
  | 'failed'
  | 'cancelled';

export type ActionPriority =
  | 'critical'
  | 'high'
  | 'medium'
  | 'low';

export interface SEOAction {
  id: number;
  project: number;
  project_name: string;
  project_website_url: string;
  recommendation: number | null;
  recommendation_title: string | null;
  brief: number | null;
  brief_title: string | null;
  draft: number | null;
  draft_title: string | null;
  investigation_id?: string;
  opportunity_type?: string;
  title: string;
  description: string;
  rationale?: string;
  evidence_snapshot?: Record<string, any>;
  action_type: ActionType;
  action_type_display: string;
  target_url: string;
  target_keyword: string;
  current_state: Record<string, any>;
  proposed_change: Record<string, any>;
  implementation_instructions: string;
  priority: ActionPriority;
  priority_display: string;
  risk_level: string;
  impact_estimate: string;
  effort_estimate: string;
  requires_human_approval: boolean;
  status: ActionStatus;
  status_display: string;
  assigned_to: string;
  approved_by?: number | null;
  approved_by_email?: string | null;
  approved_at?: string | null;
  rejected_by?: number | null;
  rejected_by_email?: string | null;
  rejected_at?: string | null;
  rejection_reason?: string;
  execution_started_at?: string | null;
  completed_at: string | null;
  failure_reason?: string;
  execution_metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface ActionPreviewDiff {
  action_id: number;
  action_type: string;
  target_url: string;
  target_keyword: string;
  risk_level: string;
  impact_estimate: string;
  effort_estimate: string;
  requires_human_approval: boolean;
  before_state: Record<string, any>;
  after_state: Record<string, any>;
  diff: Record<string, any>;
  summary: string;
}

export interface ActionPreviewResponse {
  action_id: number;
  preview: ActionPreviewDiff;
  status: ActionStatus;
  requires_human_approval: boolean;
}

export interface SEOActionGeneratePayload {
  project_id: number;
  recommendation_id?: number;
  content_draft_id?: number;
  content_brief_id?: number;
  action_type?: string;
}

export interface SEOActionUpdatePayload {
  title?: string;
  description?: string;
  action_type?: ActionType;
  target_url?: string;
  target_keyword?: string;
  current_state?: Record<string, any>;
  proposed_change?: Record<string, any>;
  implementation_instructions?: string;
  priority?: ActionPriority;
  status?: ActionStatus;
  assigned_to?: string;
}

export interface ActionStatusCounts {
  proposed: number;
  pending_approval?: number;
  reviewed: number;
  approved: number;
  completed: number;
  rejected: number;
  cancelled: number;
  total: number;
}
