export type ExternalSystemType = 'cms' | 'git' | 'webhook';

export type ExternalConnectionStatus = 'active' | 'inactive' | 'error' | 'test_staging';

export type ExternalOperationStatus =
  | 'pending'
  | 'authorized'
  | 'executing'
  | 'completed'
  | 'verified'
  | 'failed'
  | 'rate_limited'
  | 'rejected';

export interface ExternalConnection {
  id: number;
  project: number;
  project_name?: string;
  system_type: ExternalSystemType;
  provider: string;
  name: string;
  status: ExternalConnectionStatus;
  configuration: Record<string, any>;
  capabilities: string[];
  created_at?: string;
  updated_at?: string;
}

export interface ExternalOperationRecord {
  id: number;
  project: number;
  project_name?: string;
  connection?: number | null;
  connection_name?: string;
  action?: number | null;
  remediation_record?: number | null;
  agent_run?: number | null;
  task_id?: string;
  correlation_id: string;
  idempotency_key: string;
  system_type: string;
  provider: string;
  operation: string;
  required_capability: string;
  target: string;
  status: ExternalOperationStatus;
  risk_level: string;
  is_autonomous: boolean;
  request_summary?: Record<string, any>;
  before_state?: Record<string, any>;
  after_state?: Record<string, any>;
  response_summary?: Record<string, any>;
  status_code?: number | null;
  changed: boolean;
  error_category?: string;
  error_message?: string;
  retry_count: number;
  duration_ms: number;
  verification_status: 'pending' | 'verified' | 'failed' | 'not_required';
  verification_data?: Record<string, any>;
  created_at: string;
  updated_at: string;
}
