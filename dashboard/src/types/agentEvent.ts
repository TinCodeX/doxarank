/**
 * Types and schema contracts for Real-Time Agent Events in DoxaRank.
 * Authoritative contract matching backend AgentEvent in apps/seo/services/agent_events.py.
 */

export type AgentEventType =
  // Agent session lifecycle
  | 'agent.started'
  | 'agent.completed'
  | 'agent.failed'
  | 'agent.cancelled'
  // Step reasoning lifecycle
  | 'step.started'
  | 'step.completed'
  | 'step.failed'
  // Tool execution lifecycle
  | 'tool.started'
  | 'tool.completed'
  | 'tool.failed'
  // Human-in-the-loop approval lifecycle
  | 'approval.required'
  | 'approval.approved'
  | 'approval.rejected'
  // SEO Intelligence lifecycle
  | 'seo.intelligence.started'
  | 'seo.evidence.collected'
  | 'seo.opportunity.detected'
  | 'seo.intelligence.completed'
  // SEO Investigation lifecycle
  | 'seo.investigation.started'
  | 'seo.investigation.evidence_collected'
  | 'seo.investigation.root_cause_identified'
  | 'seo.investigation.recommendation_generated'
  | 'seo.investigation.completed'
  // SEO Action & Mutation Gating lifecycle
  | 'seo.action.plan.created'
  | 'seo.action.proposed'
  | 'seo.action.pending_approval'
  | 'seo.action.approval.requested'
  | 'seo.action.approved'
  | 'seo.action.rejected'
  | 'seo.action.execution_started'
  | 'seo.action.completed'
  | 'seo.action.failed'
  // SEO Action Real-World Verification lifecycle
  | 'seo.action.verification.started'
  | 'seo.action.verification.completed'
  | 'seo.action.verification.failed'
  // Multi-Agent Collaboration & Structured Handoffs lifecycle (Phase 5.1)
  | 'seo.agent.handoff.started'
  | 'seo.agent.handoff.completed'
  | 'seo.agent.handoff.rejected'
  | 'seo.agent.collaboration.started'
  | 'seo.agent.collaboration.completed'
  | 'seo.agent.collaboration.failed'
  // Shared Working Memory & Adaptive Collaboration lifecycle (Phase 5.2)
  | 'seo.collaboration.memory.initialized'
  | 'seo.collaboration.memory.updated'
  | 'seo.collaboration.memory.projected'
  | 'seo.collaboration.memory.conflict.detected'
  | 'seo.collaboration.memory.conflict.resolved'
  | 'seo.collaboration.agent.revisit'
  | 'seo.collaboration.context.bounded'
  // Dynamic Task Decomposition & Collaborative Planning lifecycle (Phase 5.3)
  | 'seo.agent.task.plan.created'
  | 'seo.agent.task.created'
  | 'seo.agent.task.ready'
  | 'seo.agent.task.started'
  | 'seo.agent.task.completed'
  | 'seo.agent.task.failed'
  | 'seo.agent.task.blocked'
  | 'seo.agent.task.replanned'
  | 'seo.agent.task.cancelled'
  | 'seo.agent.task.dependency.resolved'
  | 'seo.agent.task.plan.limit_reached';

export interface AgentEvent {
  event_id: string;
  event_type: AgentEventType | string;
  run_id: number;
  project_id?: number;
  step_number?: number | null;
  sequence_number: number;
  timestamp: string;
  payload: Record<string, any>;
}

export type AgentEventConnectionState =
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'recovering'
  | 'disconnected'
  | 'error';

export type AgentEventHandler = (event: AgentEvent) => void;
export type AgentConnectionStatusHandler = (
  state: AgentEventConnectionState,
  error?: string | null
) => void;
