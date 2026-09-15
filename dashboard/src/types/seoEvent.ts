export type SEOEventType =
  | 'ranking_change'
  | 'page_status_change'
  | 'seo_audit_change'
  | 'gsc_change'
  | 'crawl_issue'
  | 'keyword_visibility_change'
  | 'content_change';

export type SEOEventSeverity = 'low' | 'medium' | 'high' | 'critical';

export type SEOEventStatus =
  | 'received'
  | 'accepted'
  | 'processed'
  | 'suppressed'
  | 'deduplicated'
  | 'rejected'
  | 'failed';

export interface SEOEvent {
  id: number;
  project: number;
  project_name: string;
  event_type: SEOEventType;
  source: string;
  severity: SEOEventSeverity;
  status: SEOEventStatus;
  payload: Record<string, any>;
  correlation_id: string;
  idempotency_key: string;
  occurred_at: string;
  received_at: string;
  processed_at: string | null;
  suppression_reason: string;
  agent_run: number | null;
  agent_run_status: string;
  continuous_operation: number | null;
  created_at: string;
  updated_at: string;
}

export interface SEOEventMetrics {
  project_id: number;
  event_type_filter: string | null;
  events_received: number;
  events_accepted: number;
  events_rejected: number;
  events_deduplicated: number;
  events_suppressed: number;
  events_triggered: number;
  event_trigger_rate: number;
  event_to_run_rate: number;
  average_event_trigger_delay: number;
  event_trigger_failures: number;
  event_storm_suppressions: number;
  cooldown_suppressions: number;
}

export interface SEOEventIngestPayload {
  project_id: number;
  event_type: SEOEventType;
  source: string;
  severity?: SEOEventSeverity;
  payload?: Record<string, any>;
  occurred_at?: string;
  idempotency_key?: string;
  continuous_operation_id?: number;
}
