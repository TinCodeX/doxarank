import { apiFetch } from './client';

export interface SystemComponentHealth {
  status: 'healthy' | 'degraded' | 'unavailable';
  latency_ms?: number;
  mode?: string;
  registered_jobs?: number;
  registered_tools?: number;
  error?: string;
  note?: string;
}

export interface PlatformHealthResponse {
  status: 'healthy' | 'degraded' | 'unavailable';
  timestamp: string;
  components: {
    database: SystemComponentHealth;
    redis: SystemComponentHealth;
    celery: SystemComponentHealth;
    scheduler: SystemComponentHealth;
    agent_runtime: SystemComponentHealth;
    external_subsystem: {
      status: 'healthy' | 'degraded' | 'unavailable';
      total_dependencies: number;
      tripped_breakers: string[];
      probing_breakers: string[];
    };
  };
}

export interface PlatformMetricsResponse {
  total_runs: number;
  active_runs: number;
  queued_tasks: number;
  completed_runs: number;
  failed_runs: number;
  recovered_runs: number;
  success_rate_pct: number;
  failure_rate_pct: number;
  recovery_rate_pct: number;
  total_tool_calls: number;
  tool_failure_rate_pct: number;
  avg_tool_latency_ms: number;
  average_run_duration_sec: number;
  p95_run_duration_sec: number;
  open_circuit_breakers: number;
  circuit_breakers: Record<string, string>;
  active_alerts_count: number;
  timestamp: string;
}

export interface CircuitBreakerItem {
  id: number;
  service_name: string;
  state: 'closed' | 'open' | 'half_open';
  failure_count: number;
  failure_threshold: number;
  cooldown_seconds: number;
  last_failure_at: string | null;
  last_state_change_at: string;
  opened_reason: string;
  trip_count: number;
  metadata: Record<string, any>;
}

export interface PlatformAlertItem {
  id: number;
  alert_type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  project: number | null;
  project_name?: string;
  message: string;
  details: Record<string, any>;
  is_resolved: boolean;
  resolved_at: string | null;
  created_at: string;
}

export interface OperatorAuditLogItem {
  id: number;
  user: number | null;
  user_email?: string;
  project: number | null;
  project_name?: string;
  action: string;
  target_type: string;
  target_id: string;
  rationale: string;
  details: Record<string, any>;
  ip_address: string;
  timestamp: string;
}

export interface RunInspectionStep {
  step_number: number;
  action_type: string;
  status: string;
  thought: string;
  tool_calls: Array<{
    id: number;
    tool_name: string;
    duration_ms: number;
    is_mutating: boolean;
    error: string | null;
    input: any;
    output: any;
  }>;
  created_at: string;
  completed_at: string | null;
}

export interface RunInspectionPayload {
  run: {
    id: number;
    project_id: number;
    project_name: string;
    goal: string;
    status: string;
    worker_id: string | null;
    correlation_id: string | null;
    retry_count: number;
    max_retries: number;
    recovery_status: string;
    lease_expires_at: string | null;
    last_heartbeat_at: string | null;
    total_steps: number;
    summary: string;
    created_at: string;
    completed_at: string | null;
  };
  steps: RunInspectionStep[];
  external_operations: Array<{
    id: number;
    operation_type: string;
    status: string;
    verification_status: string;
    is_mutating: boolean;
    created_at: string;
  }>;
  actions: Array<{
    id: number;
    title: string;
    action_type: string;
    status: string;
    verification_status: string;
    is_mutating: boolean;
  }>;
  correlation_chain: {
    request_id: string;
    run_id: number;
    steps_count: number;
    tools_count: number;
    external_ops_count: number;
  };
}

export interface OperatorActionPayload {
  action: 'pause_continuous_ops' | 'resume_continuous_ops' | 'retry_run' | 'reset_circuit_breaker' | 'trip_circuit_breaker' | 'reconcile_external_op' | 'compact_data';
  target_id?: string;
  project_id?: number;
  rationale?: string;
}

// API functions
export const getPlatformHealth = async (): Promise<PlatformHealthResponse> => {
  return apiFetch<PlatformHealthResponse>('/api/seo/ai/platform/health/');
};

export const getPlatformReadiness = async (): Promise<{ ready: boolean; database: string; agent_runtime: string }> => {
  return apiFetch<{ ready: boolean; database: string; agent_runtime: string }>('/api/seo/ai/platform/readiness/');
};

export const getPlatformMetrics = async (projectId?: number): Promise<PlatformMetricsResponse> => {
  const query = projectId ? `?project_id=${projectId}` : '';
  return apiFetch<PlatformMetricsResponse>(`/api/seo/ai/platform/metrics/${query}`);
};

export const getPlatformAlerts = async (isResolved?: boolean): Promise<PlatformAlertItem[]> => {
  const query = isResolved !== undefined ? `?is_resolved=${isResolved}` : '';
  return apiFetch<PlatformAlertItem[]>(`/api/seo/ai/platform/alerts/${query}`);
};

export const resolvePlatformAlert = async (alertId: number): Promise<PlatformAlertItem> => {
  return apiFetch<PlatformAlertItem>('/api/seo/ai/platform/alerts/', {
    method: 'PATCH',
    body: JSON.stringify({ alert_id: alertId }),
  });
};

export const getCircuitBreakers = async (): Promise<CircuitBreakerItem[]> => {
  return apiFetch<CircuitBreakerItem[]>('/api/seo/ai/platform/circuit-breakers/');
};

export const operateCircuitBreaker = async (
  serviceName: string,
  action: 'reset' | 'trip',
  rationale: string = ''
): Promise<CircuitBreakerItem> => {
  return apiFetch<CircuitBreakerItem>(`/api/seo/ai/platform/circuit-breakers/${serviceName}/`, {
    method: 'POST',
    body: JSON.stringify({ action, rationale }),
  });
};

export const executeOperatorAction = async (payload: OperatorActionPayload): Promise<any> => {
  return apiFetch<any>('/api/seo/ai/platform/operator/actions/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const inspectPlatformRun = async (runId: number): Promise<RunInspectionPayload> => {
  return apiFetch<RunInspectionPayload>(`/api/seo/ai/platform/runs/${runId}/inspect/`);
};

export const recoverPlatformRun = async (runId: number): Promise<any> => {
  return apiFetch<any>(`/api/seo/ai/platform/runs/${runId}/recover/`, {
    method: 'POST',
  });
};

export const getOperatorAuditLogs = async (): Promise<OperatorAuditLogItem[]> => {
  return apiFetch<OperatorAuditLogItem[]>('/api/seo/ai/platform/audit-log/');
};
