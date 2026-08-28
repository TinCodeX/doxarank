/**
 * Types for Autonomous AI SEO Agent Runs, Steps, and Tool Telemetry.
 */

export type AgentRunStatus =
  | 'pending'
  | 'running'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type AgentActionType =
  | 'plan'
  | 'tool_call'
  | 'observation'
  | 'decision'
  | 'final'
  | 'approval';

export type AgentStepStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'waiting';

export interface AgentToolCall {
  id: number;
  step: number;
  tool_name: string;
  tool_input: Record<string, any>;
  tool_output: Record<string, any>;
  error_message: string;
  duration_ms: number;
  is_mutating: boolean;
  created_at: string;
  completed_at: string | null;
}

export interface AgentStep {
  id: number;
  run: number;
  step_number: number;
  thought: string;
  action_type: AgentActionType;
  action_type_display: string;
  status: AgentStepStatus;
  status_display: string;
  tool_calls: AgentToolCall[];
  created_at: string;
  completed_at: string | null;
}

export interface PendingActionSummary {
  id: number;
  title: string;
  description: string;
  action_type: string;
  priority: string;
  target_url: string;
  target_keyword: string;
  status: string;
  proposed_change?: Record<string, any>;
  implementation_instructions?: string;
}

export interface AgentRun {
  id: number;
  project: number;
  project_name: string;
  project_website_url: string;
  user: number;
  goal: string;
  status: AgentRunStatus;
  status_display: string;
  plan: any[];
  context_snapshot: Record<string, any>;
  max_steps: number;
  total_steps: number;
  summary: string;
  steps: AgentStep[];
  pending_action: PendingActionSummary | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface CreateAgentRunPayload {
  project: number;
  goal: string;
}

export interface ResumeAgentRunPayload {
  decision: 'approved' | 'rejected';
}
