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
  revisit_history?: Array<Record<string, any>>;
  open_conflicts_count?: number;
  memory_summary?: SharedMemorySummary;
  task_plan_summary?: TaskPlanSummary;
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
  shared_memory?: {
    summary?: SharedMemorySummary;
    facts?: Array<Record<string, any>>;
    inferences?: Array<Record<string, any>>;
    uncertainties?: Array<Record<string, any>>;
    decisions?: CollaborationDecisionItem[];
    conflicts?: MemoryConflictItem[];
    [key: string]: any;
  };
  task_plan?: {
    summary?: TaskPlanSummary;
    tasks?: Record<string, AgentTaskItem>;
    [key: string]: any;
  };
  current_agent?: string | null;
  status: string;
  errors: string[];
}

export interface SharedMemorySummary {
  project_id: number;
  correlation_id: string;
  task_goal: string;
  facts_count: number;
  inferences_count: number;
  uncertainties_count: number;
  assumptions_count: number;
  recommendations_count: number;
  decisions_count: number;
  open_conflicts_count: number;
  resolved_conflicts_count: number;
  pending_work_count: number;
  completed_work_count: number;
  revisits_count: number;
  entries_created: number;
  entries_deduplicated: number;
  context_efficiency: number;
}

export interface MemoryConflictItem {
  conflict_id: string;
  topic: string;
  claim_a: { agent: string; content: string; confidence?: number };
  claim_b: { agent: string; content: string; confidence?: number };
  responsible_agents: string[];
  resolution_status: 'open' | 'resolved' | 'escalated';
  resolution_notes?: string | null;
  resolved_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CollaborationDecisionItem {
  decision_id: string;
  title: string;
  reason: string;
  decision_owner: string;
  status: 'proposed' | 'accepted' | 'rejected' | 'superseded';
  timestamp: string;
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

/**
 * Retrieve complete structured collaboration working memory for a run.
 */
export async function getCollaborationMemory(runId: string | number): Promise<Record<string, any>> {
  return apiFetch<Record<string, any>>(`/api/seo/ai/orchestrate/${runId}/memory/`);
}

/**
 * Retrieve high-level summary of collaboration working memory for a run.
 */
export async function getCollaborationMemorySummary(runId: string | number): Promise<SharedMemorySummary> {
  return apiFetch<SharedMemorySummary>(`/api/seo/ai/orchestrate/${runId}/memory/summary/`);
}

/**
 * Retrieve detected multi-agent conflicts and resolution records for a run.
 */
export async function getCollaborationConflicts(runId: string | number): Promise<{
  correlation_id: string;
  project_id: number;
  conflicts: MemoryConflictItem[];
  open_count: number;
  resolved_count: number;
}> {
  return apiFetch(`/api/seo/ai/orchestrate/${runId}/conflicts/`);
}

export interface AgentTaskItem {
  task_id: string;
  objective: string;
  description: string;
  responsible_agent: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  dependencies: string[];
  required_evidence: string[];
  status: 'pending' | 'ready' | 'running' | 'completed' | 'blocked' | 'failed' | 'skipped' | 'cancelled';
  created_by: string;
  correlation_id: string;
  reason?: string | null;
  result_summary?: string | null;
  error?: string | null;
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
  completed_at?: string | null;
}

export interface TaskPlanSummary {
  project_id: number;
  correlation_id: string;
  goal: string;
  total_tasks: number;
  pending_tasks: number;
  ready_tasks: number;
  running_tasks: number;
  completed_tasks: number;
  blocked_tasks: number;
  failed_tasks: number;
  skipped_tasks: number;
  completion_rate: number;
  planning_rounds: number;
  replan_count: number;
  parallel_groups_count: number;
}

export interface TaskGraphNode {
  id: string;
  label: string;
  agent: string;
  status: string;
  priority: string;
  parallel_tier: number;
}

export interface TaskGraphEdge {
  from: string;
  to: string;
}

export interface TaskGraphResponse {
  correlation_id: string;
  project_id: number;
  goal: string;
  nodes: TaskGraphNode[];
  edges: TaskGraphEdge[];
  summary: TaskPlanSummary;
}

/**
 * Retrieve complete structured task plan (DAG of AgentTasks) for a run.
 */
export async function getCollaborationTasks(runId: string | number): Promise<Record<string, any>> {
  return apiFetch<Record<string, any>>(`/api/seo/ai/orchestrate/${runId}/tasks/`);
}

/**
 * Retrieve high-level summary of task plan for a run.
 */
export async function getCollaborationTasksSummary(runId: string | number): Promise<TaskPlanSummary> {
  return apiFetch<TaskPlanSummary>(`/api/seo/ai/orchestrate/${runId}/tasks/summary/`);
}

/**
 * Retrieve visualization DAG node/edge format of task plan for a run.
 */
export async function getCollaborationTasksGraph(runId: string | number): Promise<TaskGraphResponse> {
  return apiFetch<TaskGraphResponse>(`/api/seo/ai/orchestrate/${runId}/tasks/graph/`);
}
