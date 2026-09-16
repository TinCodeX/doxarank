export type RemediationRiskLevel = 'low' | 'medium' | 'high' | 'critical';

export type RemediationPolicyDecision =
  | 'autonomous_allowed'
  | 'human_approval_required'
  | 'blocked';

export type RemediationStatus =
  | 'proposed'
  | 'pending_approval'
  | 'reviewed'
  | 'approved'
  | 'ready_to_execute'
  | 'authorized'
  | 'executing'
  | 'completed'
  | 'verifying'
  | 'verified'
  | 'rejected'
  | 'failed'
  | 'blocked'
  | 'rolled_back'
  | 'cancelled';

export type RemediationErrorCategory =
  | 'tool_failure'
  | 'authorization_failure'
  | 'human_rejection'
  | 'execution_timeout'
  | 'verification_failure'
  | 'tenant_isolation_failure'
  | 'policy_block'
  | 'idempotency_conflict';

export interface RemediationRecord {
  id: number;
  project: number;
  project_name: string;
  action: number;
  action_title: string;
  action_type: string;
  target_url: string;
  event: number | null;
  agent_run: number | null;
  idempotency_key: string;
  risk_level: RemediationRiskLevel;
  policy_decision: RemediationPolicyDecision;
  policy_explanation: string;
  is_autonomous: boolean;
  status: RemediationStatus;
  rollback_data: Record<string, any>;
  verification_data: Record<string, any>;
  error_category: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectRemediationPolicy {
  id: number;
  project: number;
  project_name: string;
  is_autonomous_enabled: boolean;
  max_daily_autonomous_actions: number;
  min_confidence_threshold: number;
  allowed_autonomous_types: string[];
  created_at: string;
  updated_at: string;
}

export interface RemediationMetrics {
  project_id: number;
  total_remediations: number;
  remediation_attempts: number;
  remediation_successes: number;
  verification_successes: number;
  verification_failures: number;
  human_approved_count: number;
  human_rejected_count: number;
  autonomous_executed_count: number;
  policy_blocked_count: number;
  rollback_count: number;
  duplicates_prevented: number;
  remediation_attempt_rate: number;
  remediation_success_rate: number;
  verification_success_rate: number;
  verification_failure_rate: number;
  human_approval_rate: number;
  human_rejection_rate: number;
  autonomous_execution_rate: number;
  policy_block_rate: number;
  rollback_rate: number;
  duplicate_prevention_rate: number;
}
