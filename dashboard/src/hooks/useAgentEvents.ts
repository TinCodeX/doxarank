import { useState, useEffect, useRef, useCallback } from 'react';
import { AgentEventClient } from '../api/agentEvents';
import type {
  AgentEvent,
  AgentEventConnectionState,
} from '../types/agentEvent';

export interface UseAgentEventsOptions {
  autoConnect?: boolean;
  onEvent?: (event: AgentEvent) => void;
  onStatusChange?: (status: AgentEventConnectionState, error?: string | null) => void;
}

export interface UseAgentEventsResult {
  events: AgentEvent[];
  connectionState: AgentEventConnectionState;
  error: string | null;
  lastEvent: AgentEvent | null;
  connect: () => void;
  disconnect: () => void;
  clearEvents: () => void;
}

/**
 * React hook for consuming real-time AgentEvents for a given AgentRun.
 *
 * Guarantees:
 * 1. Monotonic ordering: Events are ordered strictly by sequence_number ascending.
 * 2. Deduplication: Events with identical event_id are ignored.
 * 3. Out-of-order insertion: Late-arriving events are placed in correct sequence slot.
 * 4. Lifecycle management: Automatically connects on mount / runId change and cleans up on unmount.
 */
export function useAgentEvents(
  runId: number | null | undefined,
  options: UseAgentEventsOptions = {}
): UseAgentEventsResult {
  const { autoConnect = true, onEvent, onStatusChange } = options;

  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [connectionState, setConnectionState] = useState<AgentEventConnectionState>('disconnected');
  const [error, setError] = useState<string | null>(null);
  const [lastEvent, setLastEvent] = useState<AgentEvent | null>(null);

  const clientRef = useRef<AgentEventClient | null>(null);
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const onEventRef = useRef(onEvent);
  const onStatusChangeRef = useRef(onStatusChange);

  // Keep callback refs updated to avoid re-subscription churn
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    onStatusChangeRef.current = onStatusChange;
  }, [onStatusChange]);

  // Instantiate client on first render
  if (!clientRef.current) {
    clientRef.current = new AgentEventClient();
  }

  const clearEvents = useCallback(() => {
    setEvents([]);
    setLastEvent(null);
    seenEventIdsRef.current.clear();
  }, []);

  const handleIncomingEvent = useCallback((newEvent: AgentEvent) => {
    // Deduplication check: ignore if event_id already processed
    if (seenEventIdsRef.current.has(newEvent.event_id)) {
      return;
    }
    seenEventIdsRef.current.add(newEvent.event_id);

    setLastEvent(newEvent);
    setEvents((prevEvents) => {
      // Check if already in list (defense-in-depth)
      if (prevEvents.some((e) => e.event_id === newEvent.event_id)) {
        return prevEvents;
      }
      // Insert and sort strictly by sequence_number ascending
      const merged = [...prevEvents, newEvent];
      merged.sort((a, b) => a.sequence_number - b.sequence_number);
      return merged;
    });

    if (onEventRef.current) {
      onEventRef.current(newEvent);
    }
  }, []);

  const handleStatusChange = useCallback((state: AgentEventConnectionState, err?: string | null) => {
    setConnectionState(state);
    setError(err || null);
    if (onStatusChangeRef.current) {
      onStatusChangeRef.current(state, err);
    }
  }, []);

  const connect = useCallback(() => {
    if (runId && clientRef.current) {
      clientRef.current.connect(runId);
    }
  }, [runId]);

  const disconnect = useCallback(() => {
    if (clientRef.current) {
      clientRef.current.disconnect();
    }
  }, []);

  // Subscribe to client events & manage connection lifecycle
  useEffect(() => {
    const client = clientRef.current;
    if (!client) return;

    const unsubEvent = client.subscribe(handleIncomingEvent);
    const unsubStatus = client.onStatusChange(handleStatusChange);

    if (runId && autoConnect) {
      clearEvents();
      client.connect(runId);
    } else {
      client.disconnect();
    }

    return () => {
      unsubEvent();
      unsubStatus();
      client.disconnect();
    };
  }, [runId, autoConnect, handleIncomingEvent, handleStatusChange, clearEvents]);

  return {
    events,
    connectionState,
    error,
    lastEvent,
    connect,
    disconnect,
    clearEvents,
  };
}
