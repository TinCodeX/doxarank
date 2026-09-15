/**
 * TypeScript definitions for Milestone 6.1: Continuous Agent Operations.
 */

export type ContinuousOperationStatus =
  | 'inactive'
  | 'active'
  | 'running'
  | 'paused'
  | 'waiting'
  | 'failed'
  | 'completed';

export type ContinuousOperationScheduleType =
  | 'interval_minutes'
  | 'interval_hours'
  | 'daily';

export interface ContinuousOperationMetrics {
  duplicate_prevention_count?: number;
  approval_wait_count?: number;
  total_duration_ms?: number;
  average_run_duration_ms?: number;
  [key: string]: any;
}

export interface ContinuousOperation {
  id: number;
  project: number;
  project_name: string;
  user: number;
  goal: string;
  status: ContinuousOperationStatus;
  status_display: string;
  schedule_type: ContinuousOperationScheduleType;
  schedule_type_display: string;
  interval_value: number;
  schedule_config: Record<string, any>;
  current_run: number | null;
  current_run_status?: string | null;
  last_run: number | null;
  last_successful_run: number | null;
  next_run_at: string | null;
  last_run_at: string | null;
  consecutive_failures: number;
  max_consecutive_failures: number;
  failed_run_id: number | null;
  failure_category: string;
  failure_reason: string;
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  metrics: ContinuousOperationMetrics;
  created_at: string;
  updated_at: string;
  paused_at: string | null;
  resumed_at: string | null;
}

export interface ContinuousOperationCreatePayload {
  project: number;
  goal: string;
  schedule_type?: ContinuousOperationScheduleType;
  interval_value?: number;
  schedule_config?: Record<string, any>;
  auto_activate?: boolean;
}

export interface OperationalMetricsReport {
  project_id: number;
  operation_id?: number | null;
  active_operations: number;
  paused_operations: number;
  failed_operations: number;
  scheduled_runs: number;
  completed_runs: number;
  failed_runs: number;
  operation_success_rate: number;
  average_run_duration: number;
  scheduling_delay: number;
  duplicate_run_prevention_count: number;
  consecutive_failures: number;
  human_approval_waits: number;
}
