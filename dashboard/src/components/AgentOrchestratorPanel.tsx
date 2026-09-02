import React, { useState, useEffect, useRef, useCallback } from 'react';
import type { Project } from '../types/project';
import type { AgentRun, AgentStep } from '../types/agentRun';
import type { AgentEvent, AgentEventConnectionState } from '../types/agentEvent';
import {
  getAgentRuns,
  getAgentRun,
  createAgentRun,
  resumeAgentRun,
} from '../api/agentRuns';
import { useAgentEvents } from '../hooks/useAgentEvents';

interface AgentOrchestratorPanelProps {
  project: Project;
  onActionCreated?: () => void;
}

const SAMPLE_GOALS = [
  'Analyze Google Search Console queries to identify high-impact Page 2 opportunities and propose metadata optimizations.',
  'Compare Google Search Console search performance over the last 28 days vs previous period and detect traffic declines.',
  'Inspect Google Search Console queries with high impressions but low CTR and draft meta tag optimizations.',
  'Analyze ranking drops for tracked keywords and synthesize an organic recovery plan.',
  'Inspect site audit diagnostic issues and propose technical fixes for the developer team.',
];

export const AgentOrchestratorPanel: React.FC<AgentOrchestratorPanelProps> = ({
  project,
  onActionCreated,
}) => {
  const [goal, setGoal] = useState<string>('');
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [activeRun, setActiveRun] = useState<AgentRun | null>(null);
  const [isLoadingRuns, setIsLoadingRuns] = useState<boolean>(false);
  const [isStartingRun, setIsStartingRun] = useState<boolean>(false);
  const [isResuming, setIsResuming] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [expandedStepId, setExpandedStepId] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<'steps' | 'events'>('steps');

  const pollingRef = useRef<number | null>(null);

  // Real-time WebSocket event handler for active run
  const handleLiveAgentEvent = useCallback((event: AgentEvent) => {
    // Reactive sync: Fetch authoritative state from PostgreSQL when lifecycle boundaries fire
    if (activeRun && event.run_id === activeRun.id) {
      if (event.event_type === 'approval.required') {
        // Immediate UI reaction to approval checkpoint
        getAgentRun(event.run_id).then((freshRun) => {
          setActiveRun(freshRun);
          setRuns((prev) => prev.map((r) => (r.id === freshRun.id ? freshRun : r)));
        }).catch((err) => console.error('[AgentOrchestrator] Error syncing approval state:', err));
      } else if (
        event.event_type === 'step.completed' ||
        event.event_type === 'step.started' ||
        event.event_type === 'tool.completed' ||
        event.event_type === 'agent.completed' ||
        event.event_type === 'agent.failed' ||
        event.event_type === 'agent.cancelled'
      ) {
        getAgentRun(event.run_id).then((freshRun) => {
          setActiveRun(freshRun);
          setRuns((prev) => prev.map((r) => (r.id === freshRun.id ? freshRun : r)));
          if (event.event_type === 'agent.completed') {
            setSuccessMessage('Agent run finished successfully!');
          }
        }).catch((err) => console.error('[AgentOrchestrator] Error syncing run state:', err));
      }
    }
  }, [activeRun]);

  // Real-time WebSocket hook connection with gap recovery
  const {
    events: liveEvents,
    connectionState,
    highestSequence,
    connect: reconnectWs,
    recoverMissingEvents,
  } = useAgentEvents(activeRun?.id, {
    enableReplayRecovery: true,
    onEvent: handleLiveAgentEvent,
  });

  // Fetch runs on project change
  useEffect(() => {
    fetchProjectRuns();
    return () => {
      stopPolling();
    };
  }, [project.id]);

  // Fallback Polling: Adjust interval based on WebSocket connection state
  useEffect(() => {
    const isRunActive = activeRun && (activeRun.status === 'running' || activeRun.status === 'pending');
    if (isRunActive) {
      // If WebSocket is actively connected or recovering, run polling at a relaxed heartbeat (10s)
      // If WebSocket is offline/reconnecting/error, run polling at rapid fallback frequency (1.5s)
      const isLiveOrRecovering = connectionState === 'connected' || connectionState === 'recovering';
      const pollInterval = isLiveOrRecovering ? 10000 : 1500;
      startPolling(activeRun.id, pollInterval);
    } else {
      stopPolling();
    }
    return () => {
      stopPolling();
    };
  }, [activeRun?.status, activeRun?.id, connectionState]);

  const startPolling = (runId: number, intervalMs = 1500) => {
    stopPolling();
    pollingRef.current = window.setInterval(async () => {
      try {
        const updated = await getAgentRun(runId);
        setActiveRun(updated);
        setRuns((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
        if (updated.status !== 'running' && updated.status !== 'pending') {
          stopPolling();
          if (updated.status === 'completed') {
            setSuccessMessage('Agent run finished successfully!');
          }
        }
      } catch (err) {
        console.error('Polling agent run failed:', err);
        stopPolling();
      }
    }, intervalMs);
  };

  const stopPolling = () => {
    if (pollingRef.current !== null) {
      window.clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  const fetchProjectRuns = async () => {
    setIsLoadingRuns(true);
    setErrorMessage(null);
    try {
      const data = await getAgentRuns(project.id);
      setRuns(data);
      if (data.length > 0) {
        setActiveRun(data[0]);
      } else {
        setActiveRun(null);
      }
    } catch (err: any) {
      setErrorMessage(err?.data?.detail || 'Failed to load agent runs.');
    } finally {
      setIsLoadingRuns(false);
    }
  };

  const handleStartRun = async () => {
    if (!goal.trim()) {
      setErrorMessage('Please specify an SEO goal for the agent.');
      return;
    }

    setIsStartingRun(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const newRun = await createAgentRun({
        project: project.id,
        goal: goal.trim(),
      });
      setRuns((prev) => [newRun, ...prev]);
      setActiveRun(newRun);
      setGoal('');
      if (newRun.status === 'running' || newRun.status === 'pending') {
        startPolling(newRun.id, connectionState === 'connected' ? 10000 : 1500);
      }
    } catch (err: any) {
      setErrorMessage(err?.data?.detail || 'Failed to start agent run.');
    } finally {
      setIsStartingRun(false);
    }
  };

  const handleResumeRun = async (decision: 'approved' | 'rejected') => {
    if (!activeRun) return;

    setIsResuming(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const resumed = await resumeAgentRun(activeRun.id, { decision });
      setActiveRun(resumed);
      setRuns((prev) => prev.map((r) => (r.id === resumed.id ? resumed : r)));
      if (decision === 'approved') {
        setSuccessMessage('Action approved! Agent resumed execution.');
        if (resumed.status === 'running' || resumed.status === 'pending') {
          startPolling(resumed.id, connectionState === 'connected' ? 10000 : 1500);
        }
        if (onActionCreated) onActionCreated();
      } else {
        setSuccessMessage('Action proposal rejected. Agent run cancelled.');
      }
    } catch (err: any) {
      setErrorMessage(err?.data?.detail || `Failed to ${decision} agent action.`);
    } finally {
      setIsResuming(false);
    }
  };

  const toggleStepExpand = (stepId: number) => {
    setExpandedStepId((prev) => (prev === stepId ? null : stepId));
  };

  // WebSocket Connection Indicator helper
  const getConnectionBadge = (state: AgentEventConnectionState) => {
    switch (state) {
      case 'connected':
        return (
          <span style={badgeWsLiveStyle} title="Connected to real-time agent event stream">
            <span style={pulseGreenDotStyle} /> Live Stream
          </span>
        );
      case 'recovering':
        return (
          <span style={badgeWsRecoveringStyle} title="Recovering missed events from server...">
            ↻ Recovering Events...
          </span>
        );
      case 'connecting':
        return (
          <span style={badgeWsConnectingStyle} title="Connecting to agent WebSocket stream...">
            <span style={pulseBlueDotStyle} /> Connecting...
          </span>
        );
      case 'reconnecting':
        return (
          <span style={badgeWsReconnectingStyle} title="Reconnecting with exponential backoff...">
            ⚠️ Reconnecting...
          </span>
        );
      case 'error':
      case 'disconnected':
      default:
        return (
          <span
            style={badgeWsOfflineStyle}
            title="WebSocket disconnected. Polling fallback is active. Click to reconnect."
            onClick={() => reconnectWs()}
          >
            ○ Offline (Polling Active)
          </span>
        );
    }
  };

  // Status Styling Helpers
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending':
        return (
          <span style={badgePendingStyle}>
            <span style={pulseDotStyle} /> Queued in Celery
          </span>
        );
      case 'running':
        return (
          <span style={badgeRunningStyle}>
            <span style={pulseDotStyle} /> Running ({activeRun?.total_steps || 0}/{activeRun?.max_steps || 15})
          </span>
        );
      case 'waiting_for_approval':
        return (
          <span style={badgeWaitingStyle}>
            ⚠️ Paused — Human Approval Required
          </span>
        );
      case 'completed':
        return <span style={badgeCompletedStyle}>✓ Completed</span>;
      case 'failed':
        return <span style={badgeFailedStyle}>✕ Failed</span>;
      case 'cancelled':
        return <span style={badgeCancelledStyle}>⊘ Cancelled</span>;
      default:
        return <span style={badgePendingStyle}>⏳ {status}</span>;
    }
  };

  const getEventTypeTagStyle = (eventType: string) => {
    if (eventType.startsWith('agent.')) {
      return { backgroundColor: '#e0e7ff', color: '#3730a3' };
    }
    if (eventType.startsWith('tool.')) {
      return { backgroundColor: '#f3e8ff', color: '#6b21a8' };
    }
    if (eventType.startsWith('approval.')) {
      return { backgroundColor: '#fef3c7', color: '#92400e' };
    }
    return { backgroundColor: '#f1f5f9', color: '#475569' };
  };

  return (
    <section
      id="ai-agent-orchestrator-section"
      style={panelContainerStyle}
    >
      {/* Header Bar */}
      <div style={headerContainerStyle}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={featureTagStyle}>
              Autonomous ReAct Engine
            </span>
            <span style={{ fontSize: '13px', color: '#64748b' }}>
              Project: <strong>{project.name}</strong>
            </span>
          </div>
          <h3 style={titleStyle}>
            🤖 AI SEO Agent Orchestrator
          </h3>
          <p style={subtitleStyle}>
            Define high-level objectives. The agent decomposes goals, invokes governed SEO tools, evaluates observations, and requests approval for publishing actions.
          </p>
        </div>

        {/* Run Selector Dropdown & Live Indicator */}
        {runs.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            {activeRun && getConnectionBadge(connectionState)}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label htmlFor="agent-run-select" style={{ fontSize: '13px', color: '#475569', fontWeight: 600 }}>
                Runs:
              </label>
              <select
                id="agent-run-select"
                value={activeRun?.id || ''}
                onChange={(e) => {
                  const selected = runs.find((r) => String(r.id) === e.target.value);
                  if (selected) setActiveRun(selected);
                }}
                style={selectDropdownStyle}
              >
                {runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    Run #{r.id} ({r.status}) — {r.goal.slice(0, 35)}...
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>

      {/* Alert Messages */}
      {errorMessage && (
        <div style={errorAlertStyle}>
          <span>⚠️ {errorMessage}</span>
          <button onClick={() => setErrorMessage(null)} style={closeAlertBtnStyle}>×</button>
        </div>
      )}
      {successMessage && (
        <div style={successAlertStyle}>
          <span>✓ {successMessage}</span>
          <button onClick={() => setSuccessMessage(null)} style={closeAlertBtnStyle}>×</button>
        </div>
      )}

      {/* Specialized SEO Agent Architecture (Phase 4.7) */}
      <div
        id="specialized-agent-orchestrator-banner"
        style={{
          padding: '16px 20px',
          borderRadius: '12px',
          backgroundColor: '#f8fafc',
          border: '1px solid #e2e8f0',
          marginBottom: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '18px' }}>🤖</span>
            <strong style={{ fontSize: '14px', color: '#0f172a' }}>Specialized SEO Agent Team (Phase 4.7)</strong>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: '12px',
                backgroundColor: '#dbeafe',
                color: '#1d4ed8'
              }}
            >
              5 SPECIALIZED AGENTS + SUPERVISOR
            </span>
          </div>
          <span style={{ fontSize: '12px', color: '#64748b' }}>
            Deterministic routing, explicit handoffs, and strictly governed tool permissions
          </span>
        </div>

        {/* Specialized Agents Badges */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
          <div style={{ backgroundColor: '#ffffff', padding: '10px 12px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#0f172a', marginBottom: '2px' }}>🔍 Research Agent</div>
            <div style={{ fontSize: '11px', color: '#64748b' }}>GSC, Rankings, Audit (11 Read-Only Tools)</div>
          </div>
          <div style={{ backgroundColor: '#ffffff', padding: '10px 12px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#0f172a', marginBottom: '2px' }}>🩺 Investigation Agent</div>
            <div style={{ fontSize: '11px', color: '#64748b' }}>Root Cause & Certainty (10 Tools)</div>
          </div>
          <div style={{ backgroundColor: '#ffffff', padding: '10px 12px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#0f172a', marginBottom: '2px' }}>🧠 Strategy Agent</div>
            <div style={{ fontSize: '11px', color: '#64748b' }}>Bayesian Lift & 4-Tier Reasoning (3 Tools)</div>
          </div>
          <div style={{ backgroundColor: '#ffffff', padding: '10px 12px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#0f172a', marginBottom: '2px' }}>⚡ Action Planning Agent</div>
            <div style={{ fontSize: '11px', color: '#64748b' }}>Human-Gated Proposals (5 Tools)</div>
          </div>
          <div style={{ backgroundColor: '#ffffff', padding: '10px 12px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#0f172a', marginBottom: '2px' }}>🎯 Verification & Outcome</div>
            <div style={{ fontSize: '11px', color: '#64748b' }}>Live Proof & GSC Lift (3 Tools)</div>
          </div>
        </div>

        {/* Quick Multi-Agent Workflow Triggers */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap', paddingTop: '8px', borderTop: '1px solid #f1f5f9' }}>
          <span style={{ fontSize: '11px', fontWeight: 700, color: '#475569' }}>Routing Pipelines:</span>
          <button
            type="button"
            onClick={() => setGoal('Execute full autonomous cycle: Research performance data, investigate anomalies, evaluate historical strategy, and synthesize an action plan.')}
            style={{ ...suggestionPillStyle, backgroundColor: '#eff6ff', borderColor: '#bfdbfe', color: '#1e40af' }}
          >
            🔄 Full Autonomous Cycle
          </button>
          <button
            type="button"
            onClick={() => setGoal('Investigate why page rankings and organic impressions declined over the past 28 days.')}
            style={{ ...suggestionPillStyle, backgroundColor: '#fef2f2', borderColor: '#fecaca', color: '#991b1b' }}
          >
            📉 Investigate Ranking Drop
          </button>
          <button
            type="button"
            onClick={() => setGoal('Evaluate adaptive strategy and domain win rates to prioritize highest-impact SEO interventions.')}
            style={{ ...suggestionPillStyle, backgroundColor: '#f0fdf4', borderColor: '#bbf7d0', color: '#166534' }}
          >
            🧠 Prioritize Strategy
          </button>
          <button
            type="button"
            onClick={() => setGoal('Verify live website DOM changes and measure search outcome lift for completed actions.')}
            style={{ ...suggestionPillStyle, backgroundColor: '#faf5ff', borderColor: '#e9d5ff', color: '#6b21a8' }}
          >
            🎯 Verify & Measure
          </button>
        </div>
      </div>

      {/* Model Context Protocol (MCP) Interoperability Section (Phase 4.8) */}
      <div
        id="mcp-tools-banner"
        style={{
          padding: '14px 18px',
          borderRadius: '12px',
          backgroundColor: '#f1f5f9',
          border: '1px solid #cbd5e1',
          marginBottom: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px'
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '16px' }}>🔌</span>
            <strong style={{ fontSize: '13px', color: '#0f172a' }}>External Tool Interoperability — Model Context Protocol (MCP)</strong>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: '12px',
                backgroundColor: '#dcfce7',
                color: '#15803d'
              }}
            >
              ● seo-local-diagnostics (JSON-RPC 2.0 CONNECTED)
            </span>
          </div>
          <span style={{ fontSize: '11px', color: '#64748b' }}>
            Protocol-standard external diagnostic tools adapted into DoxaRank ToolRegistry
          </span>
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ backgroundColor: '#ffffff', padding: '6px 12px', borderRadius: '6px', border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#1e293b' }}>✓ check_url_status</span>
            <span style={{ fontSize: '10px', fontWeight: 700, padding: '1px 5px', borderRadius: '4px', backgroundColor: '#f1f5f9', color: '#475569' }}>READ ONLY</span>
          </div>
          <div style={{ backgroundColor: '#ffffff', padding: '6px 12px', borderRadius: '6px', border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#1e293b' }}>✓ get_page_metadata</span>
            <span style={{ fontSize: '10px', fontWeight: 700, padding: '1px 5px', borderRadius: '4px', backgroundColor: '#f1f5f9', color: '#475569' }}>READ ONLY</span>
          </div>
          <div style={{ backgroundColor: '#ffffff', padding: '6px 12px', borderRadius: '6px', border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#1e293b' }}>✓ get_external_page_signals</span>
            <span style={{ fontSize: '10px', fontWeight: 700, padding: '1px 5px', borderRadius: '4px', backgroundColor: '#f1f5f9', color: '#475569' }}>READ ONLY</span>
          </div>
          <button
            type="button"
            onClick={() => setGoal('Inspect URL with external MCP diagnostic tools: check live HTTP status latency, OpenGraph head tags, and DOM text-to-HTML ratio.')}
            style={{ ...suggestionPillStyle, backgroundColor: '#ffffff', borderColor: '#cbd5e1', color: '#334155', marginLeft: 'auto' }}
          >
            ⚡ Test MCP Diagnostics Mission
          </button>
        </div>
      </div>

      {/* Goal Input & Trigger Box */}
      <div style={goalCardStyle}>
        <label htmlFor="agent-goal-input" style={goalLabelStyle}>
          Agent Mission / Goal
        </label>
        <textarea
          id="agent-goal-input"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="e.g. Inspect tracked rankings for page-two keywords, analyze anomalies, synthesize an article brief, and propose an action."
          rows={3}
          style={goalTextareaStyle}
          disabled={isStartingRun}
        />

        {/* Suggestion Pills */}
        <div style={{ marginTop: '10px', display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>Suggested missions:</span>
          {SAMPLE_GOALS.map((sample, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => setGoal(sample)}
              style={suggestionPillStyle}
              title="Click to populate goal"
            >
              💡 {sample.slice(0, 48)}...
            </button>
          ))}
        </div>

        <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '12px' }}>
          <button
            id="run-agent-btn"
            onClick={handleStartRun}
            disabled={isStartingRun || !goal.trim()}
            style={{
              ...primaryRunBtnStyle,
              opacity: isStartingRun || !goal.trim() ? 0.6 : 1,
              cursor: isStartingRun || !goal.trim() ? 'not-allowed' : 'pointer',
            }}
          >
            {isStartingRun ? '⚡ Launching Agent Loop...' : '🚀 Run Autonomous Agent'}
          </button>
        </div>
      </div>

      {/* Active Run Execution Lifecycle View */}
      {isLoadingRuns ? (
        <div style={emptyRunsCardStyle}>
          <p style={{ color: '#64748b', fontSize: '14px' }}>Loading agent execution runs...</p>
        </div>
      ) : activeRun ? (
        <div style={executionCardStyle}>
          {/* Run Header */}
          <div style={runHeaderStyle}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <h4 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                  Execution Run #{activeRun.id}
                </h4>
                {getStatusBadge(activeRun.status)}
              </div>
              <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#64748b' }}>
                <strong>Goal:</strong> "{activeRun.goal}"
              </p>
            </div>

            <div style={{ textAlign: 'right' }}>
              <span style={{ fontSize: '12px', color: '#64748b' }}>
                Started: {new Date(activeRun.created_at).toLocaleTimeString()}
              </span>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#334155', marginTop: '2px' }}>
                Steps: {activeRun.total_steps} / {activeRun.max_steps}
              </div>
            </div>
          </div>

          {/* Progress Bar */}
          <div style={progressTrackStyle}>
            <div
              style={{
                ...progressBarStyle,
                width: `${Math.min(100, ((activeRun.total_steps || 1) / (activeRun.max_steps || 15)) * 100)}%`,
                backgroundColor:
                  activeRun.status === 'completed'
                    ? '#10b981'
                    : activeRun.status === 'waiting_for_approval'
                    ? '#f59e0b'
                    : activeRun.status === 'failed' || activeRun.status === 'cancelled'
                    ? '#ef4444'
                    : '#3b82f6',
              }}
            />
          </div>

          {/* HUMAN APPROVAL REQUIRED CALLOUT */}
          {activeRun.status === 'waiting_for_approval' && activeRun.pending_action && (
            <div style={approvalGateCardStyle} id="agent-approval-gate-card">
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
                <span style={{ fontSize: '28px' }}>⚠️</span>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#92400e' }}>
                      Human Review & Approval Required
                    </h4>
                    <span style={actionTypeBadgeStyle}>
                      {activeRun.pending_action.action_type}
                    </span>
                  </div>
                  <p style={{ margin: '6px 0 10px 0', fontSize: '13px', color: '#78350f', lineHeight: 1.4 }}>
                    The agent has generated a proposed SEO action and paused execution. <strong>This action has NOT been executed</strong> on your website. Review the proposal below to proceed.
                  </p>

                  <div style={proposalDetailBoxStyle}>
                    <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b' }}>
                      {activeRun.pending_action.title}
                    </div>
                    <div style={{ fontSize: '13px', color: '#475569', marginTop: '4px' }}>
                      {activeRun.pending_action.description}
                    </div>
                    <div style={{ marginTop: '8px', fontSize: '12px', color: '#64748b', display: 'flex', gap: '16px' }}>
                      {activeRun.pending_action.target_keyword && (
                        <span>🎯 Keyword: <strong>{activeRun.pending_action.target_keyword}</strong></span>
                      )}
                      {activeRun.pending_action.target_url && (
                        <span>🔗 URL: <strong>{activeRun.pending_action.target_url}</strong></span>
                      )}
                    </div>
                  </div>

                  {/* Approve / Reject Controls */}
                  <div style={{ marginTop: '16px', display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <button
                      id="agent-approve-btn"
                      onClick={() => handleResumeRun('approved')}
                      disabled={isResuming}
                      style={approveBtnStyle}
                    >
                      {isResuming ? 'Processing Approval...' : '✓ Approve & Resume Run'}
                    </button>
                    <button
                      id="agent-reject-btn"
                      onClick={() => handleResumeRun('rejected')}
                      disabled={isResuming}
                      style={rejectBtnStyle}
                    >
                      {isResuming ? 'Processing...' : '✕ Reject Proposal'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Final Executive Summary Box */}
          {activeRun.summary && (
            <div style={summaryBoxStyle}>
              <div style={{ fontSize: '13px', fontWeight: 800, color: '#047857', textTransform: 'uppercase', marginBottom: '4px' }}>
                Executive Conclusion
              </div>
              <p style={{ margin: 0, fontSize: '14px', color: '#064e3b', lineHeight: 1.5 }}>
                {activeRun.summary}
              </p>
            </div>
          )}

          {/* Telemetry Stream View Toggle */}
          <div style={{ marginTop: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  onClick={() => setViewMode('steps')}
                  style={{
                    ...tabBtnStyle,
                    backgroundColor: viewMode === 'steps' ? '#4338ca' : '#f1f5f9',
                    color: viewMode === 'steps' ? '#ffffff' : '#475569',
                  }}
                >
                  ⚡ ReAct Steps ({activeRun.steps?.length || 0})
                </button>
                <button
                  onClick={() => setViewMode('events')}
                  style={{
                    ...tabBtnStyle,
                    backgroundColor: viewMode === 'events' ? '#4338ca' : '#f1f5f9',
                    color: viewMode === 'events' ? '#ffffff' : '#475569',
                  }}
                >
                  📡 Event Log ({liveEvents.length} Events)
                </button>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {highestSequence > 0 && (
                  <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 600 }}>
                    Seq Cursor: #{highestSequence}
                  </span>
                )}
                <button
                  onClick={() => recoverMissingEvents()}
                  style={syncBtnStyle}
                  title="Sync any missed events from backend"
                >
                  ↻ Sync Events
                </button>
              </div>
            </div>

            {/* View Mode: ReAct Steps Timeline */}
            {viewMode === 'steps' && (
              activeRun.steps && activeRun.steps.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {activeRun.steps.map((step: AgentStep) => {
                    const toolCall = step.tool_calls?.[0];
                    const isExpanded = expandedStepId === step.id;
                    const isStepWaiting = step.status === 'waiting';
                    const isStepFailed = step.status === 'failed';
                    const isStepCompleted = step.status === 'completed';

                    return (
                      <div
                        key={step.id}
                        id={`agent-step-${step.step_number}`}
                        style={{
                          ...stepItemStyle,
                          borderColor: isStepWaiting ? '#fcd34d' : isStepFailed ? '#fca5a5' : '#e2e8f0',
                          backgroundColor: isStepWaiting ? '#fffbeb' : isStepFailed ? '#fef2f2' : '#ffffff',
                        }}
                      >
                        {/* Step Header Line */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                            <span
                              style={{
                                ...stepNumberBadgeStyle,
                                backgroundColor: isStepWaiting ? '#f59e0b' : isStepFailed ? '#ef4444' : isStepCompleted ? '#10b981' : '#3b82f6',
                              }}
                            >
                              {step.step_number}
                            </span>
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                <span style={actionTypeTagStyle}>{step.action_type_display}</span>
                                {toolCall && (
                                  <code style={toolNameCodeStyle}>
                                    🔧 {toolCall.tool_name}
                                  </code>
                                )}
                                {toolCall?.duration_ms !== undefined && (
                                  <span style={{ fontSize: '11px', color: '#64748b' }}>
                                    ⏱️ {toolCall.duration_ms}ms
                                  </span>
                                )}
                              </div>
                              <p style={stepThoughtStyle}>
                                {step.thought}
                              </p>
                            </div>
                          </div>

                          {toolCall && (
                            <button
                              onClick={() => toggleStepExpand(step.id)}
                              style={toggleDetailBtnStyle}
                            >
                              {isExpanded ? 'Hide Data ▲' : 'View Observation ▼'}
                            </button>
                          )}
                        </div>

                        {/* Expandable Tool Call Observation Details */}
                        {isExpanded && toolCall && (
                          <div style={toolDetailBoxStyle}>
                            <div style={{ marginBottom: '8px' }}>
                              <strong style={{ fontSize: '12px', color: '#475569' }}>Arguments Passed:</strong>
                              <pre style={codeBlockStyle}>{JSON.stringify(toolCall.tool_input, null, 2)}</pre>
                            </div>
                            {toolCall.error_message ? (
                              <div>
                                <strong style={{ fontSize: '12px', color: '#dc2626' }}>Error Details:</strong>
                                <pre style={{ ...codeBlockStyle, color: '#dc2626', backgroundColor: '#fef2f2' }}>
                                  {toolCall.error_message}
                                </pre>
                              </div>
                            ) : (
                              <div>
                                {/* Rich Findings Display for GSC Intelligence Tools */}
                                {Array.isArray(toolCall.tool_output?.findings) && toolCall.tool_output.findings.length > 0 && (
                                  <div style={{ marginBottom: '12px', padding: '12px', backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                                    <div style={{ fontSize: '13px', fontWeight: 700, color: '#0f172a', marginBottom: '8px' }}>
                                      🎯 Discovered GSC Intelligence Opportunities ({toolCall.tool_output.findings.length})
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                      {toolCall.tool_output.findings.slice(0, 5).map((f: any, fIdx: number) => (
                                        <div key={fIdx} style={{ padding: '8px 10px', backgroundColor: '#ffffff', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginBottom: '4px' }}>
                                            <span style={{ fontSize: '12px', fontWeight: 600, color: '#1e293b' }}>{f.title || f.finding_type}</span>
                                            <span style={{
                                              fontSize: '10px',
                                              fontWeight: 700,
                                              textTransform: 'uppercase',
                                              padding: '2px 6px',
                                              borderRadius: '4px',
                                              backgroundColor: f.severity === 'critical' ? '#fee2e2' : f.severity === 'warning' ? '#fef3c7' : '#e0f2fe',
                                              color: f.severity === 'critical' ? '#991b1b' : f.severity === 'warning' ? '#92400e' : '#0369a1'
                                            }}>
                                              {f.severity || 'info'}
                                            </span>
                                          </div>
                                          <p style={{ margin: '0 0 4px 0', fontSize: '12px', color: '#475569' }}>{f.insight}</p>
                                          {f.recommendation && (
                                            <p style={{ margin: 0, fontSize: '11px', color: '#166534', backgroundColor: '#f0fdf4', padding: '4px 6px', borderRadius: '4px' }}>
                                              💡 <strong>Recommendation:</strong> {f.recommendation}
                                            </p>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {/* Period-over-Period Deltas Display */}
                                {toolCall.tool_output?.summary_deltas && (
                                  <div style={{ marginBottom: '12px', padding: '10px 12px', backgroundColor: '#f0fdf4', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
                                    <div style={{ fontSize: '12px', fontWeight: 700, color: '#166534', marginBottom: '6px' }}>
                                      📊 Period-over-Period Performance Deltas
                                    </div>
                                    <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', fontSize: '12px', color: '#1e293b' }}>
                                      <span><strong>Clicks:</strong> {toolCall.tool_output.summary_deltas.clicks_delta > 0 ? '+' : ''}{toolCall.tool_output.summary_deltas.clicks_delta} ({toolCall.tool_output.summary_deltas.clicks_change_percent}%)</span>
                                      <span><strong>Impressions:</strong> {toolCall.tool_output.summary_deltas.impressions_delta > 0 ? '+' : ''}{toolCall.tool_output.summary_deltas.impressions_delta} ({toolCall.tool_output.summary_deltas.impressions_change_percent}%)</span>
                                      <span><strong>CTR:</strong> {toolCall.tool_output.summary_deltas.ctr_delta_percent > 0 ? '+' : ''}{toolCall.tool_output.summary_deltas.ctr_delta_percent}%</span>
                                    </div>
                                  </div>
                                )}

                                <strong style={{ fontSize: '12px', color: '#475569' }}>Tool Observation / Output:</strong>
                                <pre style={codeBlockStyle}>{JSON.stringify(toolCall.tool_output, null, 2)}</pre>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={emptyStepsStyle}>
                  <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
                    No execution steps recorded yet. Click "Run Autonomous Agent" to start.
                  </p>
                </div>
              )
            )}

            {/* View Mode: Real-Time Event Log */}
            {viewMode === 'events' && (
              liveEvents.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {liveEvents.map((ev) => {
                    const tagStyle = getEventTypeTagStyle(ev.event_type);
                    return (
                      <div key={ev.event_id} style={eventRowStyle}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                          <span style={sequenceBadgeStyle}>#{ev.sequence_number}</span>
                          <span style={{ ...eventTagStyle, ...tagStyle }}>{ev.event_type}</span>
                          {ev.step_number !== null && ev.step_number !== undefined && (
                            <span style={stepSmallTagStyle}>Step {ev.step_number}</span>
                          )}
                          {ev.payload?.tool_name && (
                            <code style={toolNameCodeStyle}>🔧 {ev.payload.tool_name}</code>
                          )}
                          {ev.payload?.duration_ms !== undefined && (
                            <span style={{ fontSize: '11px', color: '#64748b' }}>
                              ⏱️ {ev.payload.duration_ms}ms
                            </span>
                          )}
                          {ev.payload?.requires_human_approval && (
                            <span style={approvalBadgeStyle}>⚠️ Approval Checkpoint</span>
                          )}
                        </div>
                        <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                          {new Date(ev.timestamp).toLocaleTimeString()}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={emptyStepsStyle}>
                  <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
                    No real-time events logged for this run yet.
                  </p>
                </div>
              )
            )}
          </div>
        </div>
      ) : (
        <div style={emptyRunsCardStyle}>
          <span style={{ fontSize: '36px', marginBottom: '8px' }}>🚀</span>
          <h4 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 600, color: '#0f172a' }}>
            No Agent Runs Executed Yet
          </h4>
          <p style={{ margin: 0, fontSize: '13px', color: '#64748b', maxWidth: '460px', textAlign: 'center' }}>
            Enter an SEO mission above to allow DoxaRank's Autonomous ReAct Agent to discover keyword opportunities, inspect audits, and propose actionable publishing fixes.
          </p>
        </div>
      )}
    </section>
  );
};

// Styles
const panelContainerStyle: React.CSSProperties = {
  marginTop: '40px',
  backgroundColor: '#ffffff',
  borderRadius: '16px',
  border: '1px solid #e2e8f0',
  padding: '28px',
  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
};

const headerContainerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  flexWrap: 'wrap',
  gap: '16px',
  borderBottom: '1px solid #f1f5f9',
  paddingBottom: '18px',
  marginBottom: '20px',
};

const featureTagStyle: React.CSSProperties = {
  fontSize: '11px',
  textTransform: 'uppercase',
  fontWeight: 800,
  letterSpacing: '0.05em',
  color: '#4338ca',
  backgroundColor: '#e0e7ff',
  padding: '3px 8px',
  borderRadius: '4px',
};

const titleStyle: React.CSSProperties = {
  margin: '8px 0 4px 0',
  fontSize: '22px',
  fontWeight: 800,
  color: '#0f172a',
  letterSpacing: '-0.02em',
};

const subtitleStyle: React.CSSProperties = {
  margin: 0,
  fontSize: '13px',
  color: '#64748b',
  maxWidth: '680px',
  lineHeight: 1.4,
};

const selectDropdownStyle: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: '8px',
  border: '1px solid #cbd5e1',
  backgroundColor: '#ffffff',
  fontSize: '13px',
  color: '#1e293b',
  fontWeight: 600,
};

const goalCardStyle: React.CSSProperties = {
  backgroundColor: '#f8fafc',
  border: '1px solid #e2e8f0',
  borderRadius: '12px',
  padding: '20px',
  marginBottom: '24px',
};

const goalLabelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '14px',
  fontWeight: 700,
  color: '#1e293b',
  marginBottom: '8px',
};

const goalTextareaStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '12px',
  fontSize: '14px',
  borderRadius: '8px',
  border: '1px solid #cbd5e1',
  fontFamily: 'inherit',
  resize: 'vertical',
  lineHeight: 1.4,
  outline: 'none',
};

const suggestionPillStyle: React.CSSProperties = {
  padding: '4px 10px',
  borderRadius: '16px',
  backgroundColor: '#eff6ff',
  color: '#2563eb',
  border: '1px solid #bfdbfe',
  fontSize: '11px',
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'all 0.15s ease',
};

const primaryRunBtnStyle: React.CSSProperties = {
  padding: '10px 20px',
  borderRadius: '8px',
  backgroundColor: '#4338ca',
  color: '#ffffff',
  fontWeight: 700,
  fontSize: '14px',
  border: 'none',
  boxShadow: '0 2px 4px rgba(67, 56, 202, 0.25)',
};

const executionCardStyle: React.CSSProperties = {
  border: '1px solid #e2e8f0',
  borderRadius: '12px',
  padding: '20px',
  backgroundColor: '#ffffff',
};

const runHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  flexWrap: 'wrap',
  gap: '12px',
  marginBottom: '14px',
};

const progressTrackStyle: React.CSSProperties = {
  height: '6px',
  width: '100%',
  backgroundColor: '#e2e8f0',
  borderRadius: '3px',
  overflow: 'hidden',
  marginBottom: '20px',
};

const progressBarStyle: React.CSSProperties = {
  height: '100%',
  transition: 'width 0.3s ease',
};

const approvalGateCardStyle: React.CSSProperties = {
  backgroundColor: '#fffbeb',
  border: '2px solid #f59e0b',
  borderRadius: '12px',
  padding: '18px',
  marginBottom: '20px',
  boxShadow: '0 4px 6px -1px rgba(245, 158, 11, 0.15)',
};

const actionTypeBadgeStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  backgroundColor: '#fef3c7',
  color: '#b45309',
  padding: '2px 8px',
  borderRadius: '4px',
  textTransform: 'uppercase',
};

const proposalDetailBoxStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  border: '1px solid #fde68a',
  borderRadius: '8px',
  padding: '12px',
  marginTop: '8px',
};

const approveBtnStyle: React.CSSProperties = {
  padding: '8px 18px',
  borderRadius: '8px',
  backgroundColor: '#059669',
  color: '#ffffff',
  fontWeight: 700,
  fontSize: '13px',
  border: 'none',
  cursor: 'pointer',
  boxShadow: '0 2px 4px rgba(5, 150, 105, 0.2)',
};

const rejectBtnStyle: React.CSSProperties = {
  padding: '8px 16px',
  borderRadius: '8px',
  backgroundColor: '#ffffff',
  color: '#dc2626',
  fontWeight: 700,
  fontSize: '13px',
  border: '1px solid #f87171',
  cursor: 'pointer',
};

const summaryBoxStyle: React.CSSProperties = {
  backgroundColor: '#ecfdf5',
  border: '1px solid #a7f3d0',
  borderRadius: '8px',
  padding: '14px',
  marginBottom: '20px',
};

const tabBtnStyle: React.CSSProperties = {
  padding: '6px 14px',
  borderRadius: '6px',
  fontSize: '12px',
  fontWeight: 700,
  border: 'none',
  cursor: 'pointer',
  transition: 'all 0.15s ease',
};

const syncBtnStyle: React.CSSProperties = {
  padding: '4px 10px',
  borderRadius: '6px',
  fontSize: '11px',
  fontWeight: 600,
  backgroundColor: '#f1f5f9',
  color: '#475569',
  border: '1px solid #cbd5e1',
  cursor: 'pointer',
};

const stepItemStyle: React.CSSProperties = {
  border: '1px solid #e2e8f0',
  borderRadius: '8px',
  padding: '14px',
  transition: 'all 0.15s ease',
};

const stepNumberBadgeStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '24px',
  height: '24px',
  borderRadius: '50%',
  color: '#ffffff',
  fontSize: '12px',
  fontWeight: 800,
  flexShrink: 0,
};

const actionTypeTagStyle: React.CSSProperties = {
  fontSize: '11px',
  textTransform: 'uppercase',
  fontWeight: 700,
  backgroundColor: '#f1f5f9',
  color: '#475569',
  padding: '2px 6px',
  borderRadius: '4px',
};

const toolNameCodeStyle: React.CSSProperties = {
  fontSize: '12px',
  fontFamily: 'monospace',
  color: '#1e293b',
  backgroundColor: '#f1f5f9',
  padding: '2px 6px',
  borderRadius: '4px',
};

const stepThoughtStyle: React.CSSProperties = {
  margin: '4px 0 0 0',
  fontSize: '13px',
  color: '#334155',
  lineHeight: 1.4,
};

const toggleDetailBtnStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 600,
  color: '#64748b',
  backgroundColor: 'transparent',
  border: 'none',
  cursor: 'pointer',
  padding: '4px 8px',
};

const toolDetailBoxStyle: React.CSSProperties = {
  marginTop: '12px',
  paddingTop: '12px',
  borderTop: '1px dashed #cbd5e1',
};

const codeBlockStyle: React.CSSProperties = {
  margin: '4px 0 0 0',
  padding: '8px 12px',
  backgroundColor: '#f8fafc',
  border: '1px solid #e2e8f0',
  borderRadius: '6px',
  fontSize: '11px',
  fontFamily: 'monospace',
  overflowX: 'auto',
  maxHeight: '180px',
};

const eventRowStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '10px 14px',
  borderRadius: '8px',
  border: '1px solid #e2e8f0',
  backgroundColor: '#f8fafc',
};

const sequenceBadgeStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 800,
  fontFamily: 'monospace',
  backgroundColor: '#e2e8f0',
  color: '#334155',
  padding: '2px 6px',
  borderRadius: '4px',
};

const eventTagStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  padding: '2px 8px',
  borderRadius: '4px',
};

const stepSmallTagStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 600,
  backgroundColor: '#f1f5f9',
  color: '#475569',
  padding: '2px 6px',
  borderRadius: '4px',
};

const approvalBadgeStyle: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  backgroundColor: '#fef3c7',
  color: '#92400e',
  padding: '2px 8px',
  borderRadius: '4px',
};

const emptyRunsCardStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '48px 24px',
  border: '1px dashed #cbd5e1',
  borderRadius: '12px',
  backgroundColor: '#f8fafc',
};

const emptyStepsStyle: React.CSSProperties = {
  padding: '18px',
  border: '1px dashed #cbd5e1',
  borderRadius: '8px',
  backgroundColor: '#f8fafc',
  textAlign: 'center',
};

// WebSocket Live Badges
const badgeWsLiveStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
  fontSize: '12px',
  fontWeight: 700,
  padding: '3px 10px',
  borderRadius: '12px',
  backgroundColor: '#ecfdf5',
  color: '#059669',
  border: '1px solid #a7f3d0',
};

const pulseGreenDotStyle: React.CSSProperties = {
  width: '8px',
  height: '8px',
  borderRadius: '50%',
  backgroundColor: '#10b981',
};

const badgeWsRecoveringStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
  fontSize: '12px',
  fontWeight: 700,
  padding: '3px 10px',
  borderRadius: '12px',
  backgroundColor: '#f5f3ff',
  color: '#6d28d9',
  border: '1px solid #ddd6fe',
};

const badgeWsConnectingStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
  fontSize: '12px',
  fontWeight: 700,
  padding: '3px 10px',
  borderRadius: '12px',
  backgroundColor: '#eff6ff',
  color: '#2563eb',
  border: '1px solid #bfdbfe',
};

const pulseBlueDotStyle: React.CSSProperties = {
  width: '8px',
  height: '8px',
  borderRadius: '50%',
  backgroundColor: '#3b82f6',
};

const badgeWsReconnectingStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
  fontSize: '12px',
  fontWeight: 700,
  padding: '3px 10px',
  borderRadius: '12px',
  backgroundColor: '#fffbeb',
  color: '#b45309',
  border: '1px solid #fcd34d',
};

const badgeWsOfflineStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
  fontSize: '12px',
  fontWeight: 600,
  padding: '3px 10px',
  borderRadius: '12px',
  backgroundColor: '#f8fafc',
  color: '#64748b',
  border: '1px solid #e2e8f0',
  cursor: 'pointer',
};

// Status Badges
const badgeRunningStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
  fontSize: '12px',
  fontWeight: 700,
  padding: '3px 10px',
  borderRadius: '12px',
  backgroundColor: '#eff6ff',
  color: '#1d4ed8',
  border: '1px solid #bfdbfe',
};

const pulseDotStyle: React.CSSProperties = {
  width: '8px',
  height: '8px',
  borderRadius: '50%',
  backgroundColor: '#3b82f6',
};

const badgeWaitingStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 800,
  padding: '3px 10px',
  borderRadius: '12px',
  backgroundColor: '#fef3c7',
  color: '#92400e',
  border: '1px solid #fcd34d',
};

const badgeCompletedStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 700,
  padding: '3px 10px',
  borderRadius: '12px',
  backgroundColor: '#ecfdf5',
  color: '#047857',
  border: '1px solid #a7f3d0',
};

const badgeFailedStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 700,
  padding: '3px 10px',
  borderRadius: '12px',
  backgroundColor: '#fef2f2',
  color: '#b91c1c',
  border: '1px solid #fca5a5',
};

const badgeCancelledStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 700,
  padding: '3px 10px',
  borderRadius: '12px',
  backgroundColor: '#f1f5f9',
  color: '#475569',
  border: '1px solid #cbd5e1',
};

const badgePendingStyle: React.CSSProperties = {
  fontSize: '12px',
  fontWeight: 700,
  padding: '3px 10px',
  borderRadius: '12px',
  backgroundColor: '#f8fafc',
  color: '#64748b',
  border: '1px solid #e2e8f0',
};

const errorAlertStyle: React.CSSProperties = {
  backgroundColor: '#fef2f2',
  border: '1px solid #f87171',
  borderRadius: '8px',
  padding: '10px 14px',
  color: '#991b1b',
  fontSize: '13px',
  marginBottom: '16px',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const successAlertStyle: React.CSSProperties = {
  backgroundColor: '#f0fdf4',
  border: '1px solid #86efac',
  borderRadius: '8px',
  padding: '10px 14px',
  color: '#166534',
  fontSize: '13px',
  marginBottom: '16px',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
};

const closeAlertBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'inherit',
  cursor: 'pointer',
  fontSize: '16px',
  fontWeight: 'bold',
};
