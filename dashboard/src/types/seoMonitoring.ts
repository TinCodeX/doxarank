export type MonitorType =
  | 'ranking'
  | 'page_status'
  | 'seo_audit'
  | 'keyword_visibility';

export type MonitorStatus =
  | 'healthy'
  | 'warning'
  | 'anomaly'
  | 'recovered';

export interface MonitoringState {
  id: number;
  project: number;
  project_name: string;
  monitor_type: MonitorType;
  metric_key: string;
  current_value: Record<string, any>;
  previous_value: Record<string, any>;
  baseline_value: Record<string, any>;
  status: MonitorStatus;
  consecutive_anomalies: number;
  snapshot_timestamp: string;
  last_checked_at: string;
  last_changed_at: string;
  last_event_at: string | null;
  last_event: number | null;
  last_event_type: string | null;
  last_event_status: string | null;
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface MonitoringSnapshot {
  id: number;
  project: number;
  project_name: string;
  monitor_type: MonitorType;
  metric_key: string;
  value: Record<string, any>;
  baseline_value: Record<string, any>;
  delta: Record<string, any>;
  status: MonitorStatus;
  is_anomaly: boolean;
  is_recovery: boolean;
  created_at: string;
}

export interface MonitoringMetrics {
  project_id: number;
  monitored_targets_count: number;
  active_anomalies_count: number;
  recoveries_detected_count: number;
  snapshots_captured_count: number;
  meaningful_changes_detected: number;
  insignificant_changes_ignored: number;
  events_generated_count: number;
  events_triggered_count: number;
  duplicate_detections_prevented: number;
  monitoring_event_generation_rate: number;
}

export interface MonitoringCycleResult {
  status: string;
  project_id: number;
  results: {
    project_id: number;
    snapshots_created: number;
    changes_detected: number;
    changes_ignored: number;
    events_generated: number;
    recoveries_detected: number;
    duplicates_prevented: number;
  };
}
