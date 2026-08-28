export type ActionType =
  | 'update_title'
  | 'update_meta_description'
  | 'update_slug'
  | 'optimize_existing_content'
  | 'publish_new_content'
  | 'add_internal_links'
  | 'add_structured_data'
  | 'technical_seo_fix'
  | 'content_refresh';

export type ActionStatus =
  | 'proposed'
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
  title: string;
  description: string;
  action_type: ActionType;
  action_type_display: string;
  target_url: string;
  target_keyword: string;
  current_state: Record<string, any>;
  proposed_change: Record<string, any>;
  implementation_instructions: string;
  priority: ActionPriority;
  priority_display: string;
  status: ActionStatus;
  status_display: string;
  assigned_to: string;
  execution_metadata: Record<string, any>;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
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
  reviewed: number;
  approved: number;
  completed: number;
  rejected: number;
  cancelled: number;
  total: number;
}
