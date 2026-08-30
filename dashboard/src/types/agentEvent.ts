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
  | 'approval.rejected';

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
