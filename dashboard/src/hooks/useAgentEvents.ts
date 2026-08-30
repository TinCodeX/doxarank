import { useState, useEffect, useRef, useCallback } from 'react';
import { AgentEventClient, fetchReplayEvents } from '../api/agentEvents';
import type {
  AgentEvent,
  AgentEventConnectionState,
} from '../types/agentEvent';

export interface UseAgentEventsOptions {
  autoConnect?: boolean;
  enableReplayRecovery?: boolean;
  onEvent?: (event: AgentEvent) => void;
  onStatusChange?: (status: AgentEventConnectionState, error?: string | null) => void;
}

export interface UseAgentEventsResult {
  events: AgentEvent[];
  connectionState: AgentEventConnectionState;
  error: string | null;
  lastEvent: AgentEvent | null;
  highestSequence: number;
  connect: () => void;
  disconnect: () => void;
  clearEvents: () => void;
  recoverMissingEvents: () => Promise<void>;
}

/**
 * React hook for consuming real-time AgentEvents with gap detection,
 * automatic reconnect recovery, and deterministic sequence ordering.
 *
 * Guarantees:
 * 1. Monotonic ordering: Events are ordered strictly by sequence_number ascending.
 * 2. Deduplication: Events with identical event_id are ignored.
 * 3. Out-of-order & gap recovery: Gaps in sequence numbers trigger automatic replay sync.
 * 4. Reconnect resilience: Automatically syncs missed events generated during disconnections.
 * 5. Lifecycle management: Connects on mount/runId change and cleans up timers on unmount.
 */
export function useAgentEvents(
  runId: number | null | undefined,
  options: UseAgentEventsOptions = {}
): UseAgentEventsResult {
  const {
    autoConnect = true,
    enableReplayRecovery = true,
    onEvent,
    onStatusChange,
  } = options;

  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [connectionState, setConnectionState] = useState<AgentEventConnectionState>('disconnected');
  const [error, setError] = useState<string | null>(null);
  const [lastEvent, setLastEvent] = useState<AgentEvent | null>(null);

  const clientRef = useRef<AgentEventClient | null>(null);
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const highestSequenceRef = useRef<number>(0);
  const isRecoveringRef = useRef<boolean>(false);
  const prevRunIdRef = useRef<number | null | undefined>(null);

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
    highestSequenceRef.current = 0;
  }, []);

  /**
   * Recovers missing events from REST Replay API starting from highestSequenceRef.
   * Handles in-flight race conditions with live WebSocket deliveries.
   */
  const recoverMissingEvents = useCallback(async () => {
    if (!runId || !enableReplayRecovery || isRecoveringRef.current) {
      return;
    }

    isRecoveringRef.current = true;
    const previousState = clientRef.current?.getState() || 'connected';
    if (previousState === 'connected') {
      setConnectionState('recovering');
      if (onStatusChangeRef.current) {
        onStatusChangeRef.current('recovering', null);
      }
    }

    try {
      const cursor = highestSequenceRef.current;
      const replayed = await fetchReplayEvents(runId, cursor);

      if (replayed && replayed.length > 0) {
        setEvents((prevEvents) => {
          const freshReplayed: AgentEvent[] = [];
          for (const ev of replayed) {
            if (!seenEventIdsRef.current.has(ev.event_id)) {
              seenEventIdsRef.current.add(ev.event_id);
              freshReplayed.push(ev);
              if (onEventRef.current) {
                onEventRef.current(ev);
              }
            }
          }

          if (freshReplayed.length === 0) return prevEvents;

          const merged = [...prevEvents, ...freshReplayed];
          merged.sort((a, b) => a.sequence_number - b.sequence_number);

          // Update highest sequence ref
          for (const ev of merged) {
            if (ev.sequence_number > highestSequenceRef.current) {
              highestSequenceRef.current = ev.sequence_number;
            }
          }

          if (merged.length > 0) {
            setLastEvent(merged[merged.length - 1]);
          }

          return merged;
        });
      }
    } catch (err: any) {
      console.warn('[useAgentEvents] Replay event recovery failed:', err?.message || err);
    } finally {
      isRecoveringRef.current = false;
      const currentState = clientRef.current?.getState() || 'connected';
      setConnectionState(currentState);
      if (onStatusChangeRef.current) {
        onStatusChangeRef.current(currentState, null);
      }
    }
  }, [runId, enableReplayRecovery]);

  /**
   * Handles incoming live WebSocket message event with deduplication,
   * monotonic sequence sorting, and gap detection.
   */
  const handleIncomingEvent = useCallback((newEvent: AgentEvent) => {
    // Gap Detection: if incoming sequence jumps beyond expected next sequence
    const expectedNext = highestSequenceRef.current + 1;
    const hasGap = highestSequenceRef.current > 0 && newEvent.sequence_number > expectedNext;

    // Deduplication check: ignore if event_id was already processed
    if (seenEventIdsRef.current.has(newEvent.event_id)) {
      return;
    }
    seenEventIdsRef.current.add(newEvent.event_id);

    if (newEvent.sequence_number > highestSequenceRef.current) {
      highestSequenceRef.current = newEvent.sequence_number;
    }

    setLastEvent(newEvent);
    setEvents((prevEvents) => {
      if (prevEvents.some((e) => e.event_id === newEvent.event_id)) {
        return prevEvents;
      }
      const merged = [...prevEvents, newEvent];
      merged.sort((a, b) => a.sequence_number - b.sequence_number);
      return merged;
    });

    if (onEventRef.current) {
      onEventRef.current(newEvent);
    }

    // Trigger recovery if a gap was detected
    if (hasGap && enableReplayRecovery) {
      recoverMissingEvents();
    }
  }, [enableReplayRecovery, recoverMissingEvents]);

  const handleStatusChange = useCallback((state: AgentEventConnectionState, err?: string | null) => {
    if (!isRecoveringRef.current) {
      setConnectionState(state);
      setError(err || null);
      if (onStatusChangeRef.current) {
        onStatusChangeRef.current(state, err);
      }
    }

    // When connection is restored (or established), sync missed events
    if (state === 'connected' && runId && enableReplayRecovery) {
      recoverMissingEvents();
    }
  }, [runId, enableReplayRecovery, recoverMissingEvents]);

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

  // Handle run selection change and lifecycle management
  useEffect(() => {
    const client = clientRef.current;
    if (!client) return;

    const isRunChanged = prevRunIdRef.current !== runId;
    prevRunIdRef.current = runId;

    if (isRunChanged) {
      clearEvents();
    }

    const unsubEvent = client.subscribe(handleIncomingEvent);
    const unsubStatus = client.onStatusChange(handleStatusChange);

    if (runId && autoConnect) {
      client.connect(runId);
      // Immediately hydrate historical events for this run
      recoverMissingEvents();
    } else {
      client.disconnect();
    }

    return () => {
      unsubEvent();
      unsubStatus();
      client.disconnect();
    };
  }, [runId, autoConnect, handleIncomingEvent, handleStatusChange, clearEvents, recoverMissingEvents]);

  return {
    events,
    connectionState,
    error,
    lastEvent,
    highestSequence: highestSequenceRef.current,
    connect,
    disconnect,
    clearEvents,
    recoverMissingEvents,
  };
}
