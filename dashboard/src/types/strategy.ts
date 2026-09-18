/**
 * Long-Term SEO Strategy TypeScript Interfaces (Milestone 6.6)
 */

export type StrategicHorizon = 'short_term' | 'medium_term' | 'long_term';
export type StrategicPriority = 'critical' | 'high' | 'medium' | 'low';
export type ObjectiveStatus = 'draft' | 'active' | 'at_risk' | 'achieved' | 'paused' | 'cancelled' | 'expired';
export type TargetDirection = 'increasing' | 'decreasing';
export type InitiativeStatus = 'planned' | 'active' | 'at_risk' | 'completed' | 'paused' | 'cancelled';
export type StrategyStatus = 'draft' | 'proposed' | 'active' | 'superseded' | 'paused' | 'cancelled';
export type StrategyHealth = 'on_track' | 'at_risk' | 'off_track' | 'no_data';
export type ReviewDecision = 'keep' | 'adjust' | 'pause' | 'complete' | 'replace';
export type ReviewApprovalStatus = 'not_required' | 'pending_approval' | 'approved' | 'rejected';

export interface StrategicObjective {
  id: number;
  project: number;
  project_name?: string;
  name: string;
  description: string;
  metric: string;
  baseline: number;
  target: number;
  target_direction: TargetDirection;
  current_value: number;
  start_date: string;
  target_date: string;
  priority: StrategicPriority;
  horizon: StrategicHorizon;
  status: ObjectiveStatus;
  progress: number;
  evidence: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface StrategicInitiative {
  id: number;
  objective?: number | null;
  objective_name?: string;
  strategy: number;
  name: string;
  description: string;
  priority: StrategicPriority;
  status: InitiativeStatus;
  horizon: StrategicHorizon;
  start_date: string;
  target_date?: string | null;
  progress: number;
  risk_level: string;
  owner: string;
  target_action_types: string[];
  action_plan?: number | null;
  evidence: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface LongTermSEOStrategy {
  id: number;
  project: number;
  project_name?: string;
  title: string;
  version: number;
  status: StrategyStatus;
  health: StrategyHealth;
  effective_from: string;
  effective_until?: string | null;
  rationale: string;
  assumptions: string[];
  risks: Array<{ risk: string; severity: string }>;
  expected_outcomes: string[];
  evidence: Record<string, any>;
  adjustment_reason?: string;
  previous_version?: number | null;
  created_by_agent: string;
  approved_by?: number | null;
  approved_at?: string | null;
  initiatives?: StrategicInitiative[];
  created_at: string;
  updated_at: string;
}

export interface StrategyReviewRecord {
  id: number;
  strategy: number;
  strategy_version?: number;
  project: number;
  project_name?: string;
  review_cycle: number;
  status: string;
  evaluation_summary: {
    objectives?: Array<{ id: number; name: string; metric: string; progress: number; status: string }>;
    initiatives?: Array<{ id: number; name: string; progress: number; status: string; risk: string }>;
    strategy_health?: string;
    detected_risks?: string[];
    evaluated_at?: string;
    trigger_source?: string;
  };
  decision: ReviewDecision;
  proposed_changes: Record<string, any>;
  approval_status: ReviewApprovalStatus;
  fingerprint: string;
  reviewed_at: string;
  created_at: string;
  updated_at: string;
}

export interface StrategyMetrics {
  project_id: number;
  current_strategy_version: number;
  strategy_health: StrategyHealth;
  total_objectives: number;
  active_objectives: number;
  achieved_objectives: number;
  at_risk_objectives: number;
  average_objective_progress_pct: number;
  total_initiatives: number;
  active_initiatives: number;
  completed_initiatives: number;
  initiative_completion_rate_pct: number;
  total_strategy_versions: number;
  total_reviews_conducted: number;
  strategy_adjustment_rate_pct: number;
  evidence_backed_decisions_pct: number;
}
