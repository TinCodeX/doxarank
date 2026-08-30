import { apiFetch, getStoredTokens } from './client';
import type {
  AgentEvent,
  AgentEventHandler,
  AgentEventConnectionState,
  AgentConnectionStatusHandler,
} from '../types/agentEvent';

/**
 * Fetch historical or missed AgentEvents for an AgentRun filtered strictly after a sequence cursor.
 * Used for client-side event replay, gap recovery, and reconnect synchronization.
 */
export async function fetchReplayEvents(
  runId: number,
  afterSequence: number = 0
): Promise<AgentEvent[]> {
  const query = afterSequence > 0 ? `?after_sequence=${afterSequence}` : '';
  return apiFetch<AgentEvent[]>(`/api/seo/ai/agent/runs/${runId}/events/${query}`);
}

/**
 * Derives the base WebSocket URL matching backend API configuration.
 */
function getWebSocketBaseUrl(): string {
  if (typeof window === 'undefined') return 'ws://127.0.0.1:8000';
  // If Vite dev server runs at localhost:5173, Django backend runs at 127.0.0.1:8000
  const isLocalDev = window.location.port === '5173' || window.location.hostname === 'localhost';
  if (isLocalDev) {
    return 'ws://127.0.0.1:8000';
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}`;
}

export interface AgentEventClientOptions {
  autoReconnect?: boolean;
  maxReconnectAttempts?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
}

/**
 * Reusable WebSocket client for real-time AgentEvent streaming.
 * Handles authenticated connections, sequence-aware event dispatch,
 * exponential backoff reconnection, and lifecycle cleanup.
 */
export class AgentEventClient {
  private socket: WebSocket | null = null;
  private currentRunId: number | null = null;
  private eventHandlers: Set<AgentEventHandler> = new Set();
  private statusHandlers: Set<AgentConnectionStatusHandler> = new Set();
  private connectionState: AgentEventConnectionState = 'disconnected';
  private reconnectAttempts = 0;
  private reconnectTimer: number | null = null;
  private isExplicitlyClosed = false;

  private readonly autoReconnect: boolean;
  private readonly maxReconnectAttempts: number;
  private readonly initialBackoffMs: number;
  private readonly maxBackoffMs: number;

  constructor(options: AgentEventClientOptions = {}) {
    this.autoReconnect = options.autoReconnect ?? true;
    this.maxReconnectAttempts = options.maxReconnectAttempts ?? 10;
    this.initialBackoffMs = options.initialBackoffMs ?? 1000;
    this.maxBackoffMs = options.maxBackoffMs ?? 30000;
  }

  /**
   * Connect to the WebSocket stream for a specific AgentRun.
   */
  public connect(runId: number): void {
    if (!runId || isNaN(runId)) {
      this.updateState('error', 'Invalid Agent Run ID provided.');
      return;
    }

    // Clean up any existing connection or pending reconnect timer
    this.clearReconnectTimer();
    if (this.socket) {
      this.isExplicitlyClosed = true;
      this.socket.close();
      this.socket = null;
    }

    this.currentRunId = runId;
    this.isExplicitlyClosed = false;

    const tokens = getStoredTokens();
    if (!tokens?.access) {
      this.updateState('error', 'Authentication required. No access token found.');
      return;
    }

    const wsBase = getWebSocketBaseUrl();
    const wsUrl = `${wsBase}/ws/seo/ai/agent/runs/${runId}/?token=${encodeURIComponent(tokens.access)}`;

    this.updateState(this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting');

    try {
      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        this.reconnectAttempts = 0;
        this.updateState('connected');
      };

      this.socket.onmessage = (messageEvent: MessageEvent) => {
        this.handleIncomingMessage(messageEvent.data);
      };

      this.socket.onerror = () => {
        // WebSocket onerror events do not contain diagnostic details for security reasons.
        // The subsequent onclose event will handle state transition & reconnect.
        if (this.connectionState !== 'error') {
          this.updateState('error', 'WebSocket connection encountered an error.');
        }
      };

      this.socket.onclose = (closeEvent: CloseEvent) => {
        this.handleSocketClose(closeEvent);
      };
    } catch (err: any) {
      this.updateState('error', err?.message || 'Failed to initialize WebSocket.');
      this.scheduleReconnect();
    }
  }

  /**
   * Explicitly disconnect from the WebSocket stream.
   */
  public disconnect(): void {
    this.isExplicitlyClosed = true;
    this.clearReconnectTimer();
    this.reconnectAttempts = 0;
    this.currentRunId = null;

    if (this.socket) {
      this.socket.close(1000, 'Client closed connection');
      this.socket = null;
    }
    this.updateState('disconnected');
  }

  /**
   * Subscribe a handler to receive validated AgentEvents.
   * Returns an unsubscribe function.
   */
  public subscribe(handler: AgentEventHandler): () => void {
    this.eventHandlers.add(handler);
    return () => this.unsubscribe(handler);
  }

  /**
   * Unsubscribe an event handler.
   */
  public unsubscribe(handler: AgentEventHandler): void {
    this.eventHandlers.delete(handler);
  }

  /**
   * Subscribe to connection state changes.
   */
  public onStatusChange(handler: AgentConnectionStatusHandler): () => void {
    this.statusHandlers.add(handler);
    handler(this.connectionState);
    return () => {
      this.statusHandlers.delete(handler);
    };
  }

  public getState(): AgentEventConnectionState {
    return this.connectionState;
  }

  public getCurrentRunId(): number | null {
    return this.currentRunId;
  }

  // --- Internal Handlers ---

  private handleIncomingMessage(raw: any): void {
    if (typeof raw !== 'string') return;

    try {
      const parsed = JSON.parse(raw);
      if (this.isValidAgentEvent(parsed)) {
        this.notifyEventHandlers(parsed);
      }
    } catch {
      // Malformed JSON is safely dropped without exposing internals or crashing.
    }
  }

  private isValidAgentEvent(data: any): data is AgentEvent {
    return (
      data &&
      typeof data === 'object' &&
      typeof data.event_id === 'string' &&
      typeof data.event_type === 'string' &&
      typeof data.sequence_number === 'number' &&
      (typeof data.run_id === 'number' || data.run_id === undefined)
    );
  }

  private notifyEventHandlers(event: AgentEvent): void {
    for (const handler of this.eventHandlers) {
      try {
        handler(event);
      } catch (err) {
        console.error('[AgentEventClient] Error in event subscriber callback:', err);
      }
    }
  }

  private handleSocketClose(closeEvent: CloseEvent): void {
    this.socket = null;

    if (this.isExplicitlyClosed) {
      this.updateState('disconnected');
      return;
    }

    // Handle terminal authentication / authorization rejection codes from backend
    if (closeEvent.code === 4001) {
      this.updateState('error', 'Authentication failed. WebSocket closed (4001).');
      return;
    }
    if (closeEvent.code === 4003) {
      this.updateState('error', 'Access denied. You do not own this agent run (4003).');
      return;
    }
    if (closeEvent.code === 4004) {
      this.updateState('error', 'Invalid agent run identifier (4004).');
      return;
    }

    if (this.autoReconnect && this.currentRunId !== null) {
      this.scheduleReconnect();
    } else {
      this.updateState('disconnected');
    }
  }

  private scheduleReconnect(): void {
    if (this.isExplicitlyClosed || this.currentRunId === null) return;

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.updateState('error', 'Max reconnection attempts reached.');
      return;
    }

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s... capped at maxBackoffMs
    const delay = Math.min(
      this.initialBackoffMs * Math.pow(2, this.reconnectAttempts),
      this.maxBackoffMs
    );
    this.reconnectAttempts += 1;

    this.updateState('reconnecting', `Reconnecting in ${Math.round(delay / 1000)}s...`);

    this.clearReconnectTimer();
    this.reconnectTimer = window.setTimeout(() => {
      if (!this.isExplicitlyClosed && this.currentRunId !== null) {
        this.connect(this.currentRunId);
      }
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private updateState(state: AgentEventConnectionState, error: string | null = null): void {
    this.connectionState = state;
    for (const handler of this.statusHandlers) {
      try {
        handler(state, error);
      } catch (err) {
        console.error('[AgentEventClient] Error in status handler:', err);
      }
    }
  }
}

// Global default singleton instance for simple consumer access
export const agentEventClient = new AgentEventClient();
