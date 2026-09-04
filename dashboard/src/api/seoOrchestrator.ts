/**
 * Specialized SEO Agent Orchestration API client (Phase 4.7).
 */

import { apiFetch } from './client';

export interface SpecializedAgentInfo {
  name: string;
  purpose: string;
  allowed_tools: string[];
  tools_count: number;
}

export interface OrchestrationWorkflow {
  workflow: string;
  description: string;
}

export interface SpecializedAgentsResponse {
  agents: SpecializedAgentInfo[];
  workflows: OrchestrationWorkflow[];
}

export interface OrchestratedAgentResult {
  agent: string;
  status: string;
  confidence: number;
  evidence: Record<string, any>;
  findings: string[];
  recommendations: Array<Record<string, any>>;
  next_step?: string | null;
  errors: string[];
  duration_ms: number;
  metadata: Record<string, any>;
}

export interface AgentHandoffItem {
  project_id?: number;
  source_agent: string;
  target_agent: string;
  user_goal: string;
  task_type: string;
  correlation_id: string;
  relevant_evidence?: Record<string, any>;
  observed_facts?: Array<Record<string, any>>;
  inferences?: Array<Record<string, any>>;
  uncertainties?: string[];
  assumptions?: string[];
  allowed_tools?: string[];
  approval_state?: string;
  timestamp?: string;
}

export interface CollaborationStateInfo {
  project_id: number;
  task_goal: string;
  task_type: string;
  correlation_id: string;
  status: string;
  current_agent?: string | null;
  completed_agents: string[];
  pending_agents: string[];
  failed_agents: string[];
  handoff_history: AgentHandoffItem[];
  current_evidence: Record<string, any>;
  unresolved_questions: string[];
  errors: string[];
}

export interface OrchestrationResponse {
  project_id: number;
  project_name: string;
  website_url: string;
  user_id?: number | null;
  task_type: string;
  task_goal: string;
  target_url?: string | null;
  target_query?: string | null;
  correlation_id: string;
  evidence: Record<string, any>;
  investigation_findings: Array<Record<string, any>>;
  strategy_signals: Record<string, any>;
  action_proposals: Array<Record<string, any>>;
  created_plan_id?: number | null;
  action_plan_id?: number | null;
  verification_results: Record<string, any>;
  outcome_measurements: Record<string, any>;
  agent_results_history: OrchestratedAgentResult[];
  observed_facts?: Array<Record<string, any>>;
  inferences?: Array<Record<string, any>>;
  uncertainties?: string[];
  assumptions?: string[];
  handoff_history?: AgentHandoffItem[];
  collaboration_state?: CollaborationStateInfo;
  current_agent?: string | null;
  status: string;
  errors: string[];
}


/**
 * List all available specialized agents, their descriptions, and permitted tools.
 */
export async function getSpecializedAgents(projectId?: number): Promise<SpecializedAgentsResponse> {
  const url = projectId
    ? `/api/seo/ai/orchestrate/agents/?project_id=${projectId}`
    : `/api/seo/ai/orchestrate/agents/`;
  return apiFetch<SpecializedAgentsResponse>(url);
}

/**
 * Execute an orchestrated multi-agent workflow.
 */
export async function orchestrateTask(
  projectId: number,
  task: string,
  options?: { target_url?: string; target_query?: string }
): Promise<OrchestrationResponse> {
  return apiFetch<OrchestrationResponse>('/api/seo/ai/orchestrate/', {
    method: 'POST',
    body: JSON.stringify({
      project_id: projectId,
      task,
      target_url: options?.target_url,
      target_query: options?.target_query,
    }),
  });
}
