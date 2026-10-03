import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types/project';
import type {
  SEOEvent,
  SEOEventMetrics,
  SEOEventSeverity,
} from '../types/seoEvent';
import {
  getSEOEvents,
  getSEOEventMetrics,
} from '../api/seoEvents';

interface EventActivityPanelProps {
  project: Project;
}

export const EventActivityPanel: React.FC<EventActivityPanelProps> = ({ project }) => {
  const [events, setEvents] = useState<SEOEvent[]>([]);
  const [metrics, setMetrics] = useState<SEOEventMetrics | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<SEOEvent | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage] = useState<string | null>(null);

  // Filters
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('');

  const pollIntervalRef = useRef<number | null>(null);

  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const [eventList, metricData] = await Promise.all([
        getSEOEvents(project.id, {
          event_type: typeFilter || undefined,
          status: statusFilter || undefined,
          severity: severityFilter || undefined,
        }),
        getSEOEventMetrics(project.id, typeFilter || undefined),
      ]);
      setEvents(eventList);
      setMetrics(metricData);
    } catch (err: any) {
      console.error('Error loading event activity:', err);
      setErrorMessage(err.message || 'Failed to load event activity.');
    } finally {
      setIsLoading(false);
    }
  }, [project.id, typeFilter, statusFilter, severityFilter]);

  useEffect(() => {
    loadData();
    pollIntervalRef.current = window.setInterval(loadData, 10000);
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [loadData]);

  const getSeverityBadgeClass = (severity: SEOEventSeverity) => {
    switch (severity) {
      case 'critical':
        return 'badge-critical';
      case 'high':
        return 'badge-high';
      case 'medium':
        return 'badge-medium';
      case 'low':
      default:
        return 'badge-low';
    }
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'processed':
        return 'badge-processed';
      case 'accepted':
        return 'badge-accepted';
      case 'suppressed':
        return 'badge-suppressed';
      case 'deduplicated':
        return 'badge-deduplicated';
      case 'rejected':
      case 'failed':
        return 'badge-rejected';
      default:
        return 'badge-received';
    }
  };

  return (
    <div className="event-activity-panel">
      {/* Header */}
      <div className="panel-header">
        <div>
          <h2 className="panel-title">
            <span className="pulse-dot" />
            Event-Driven Operations
          </h2>
          <p className="panel-subtitle">
            Autonomous agent workflow triggering upon domain events, rank drops, audit alerts, and crawl impediments.
          </p>
        </div>
        <div className="header-actions">
          <button
            className="btn btn-secondary"
            onClick={() => loadData()}
            disabled={isLoading}
          >
            {isLoading ? 'Refreshing...' : '↻ Refresh'}
          </button>
        </div>
      </div>

      {/* Messages */}
      {errorMessage && <div className="alert alert-danger">{errorMessage}</div>}
      {successMessage && <div className="alert alert-success">{successMessage}</div>}

      {/* Metrics Row */}
      {metrics && (
        <div className="metrics-strip">
          <div className="metric-card">
            <span className="metric-label">Events Ingested</span>
            <span className="metric-value">{metrics.events_received}</span>
            <span className="metric-sub">{metrics.events_accepted} accepted</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Triggered Runs</span>
            <span className="metric-value text-success">{metrics.events_triggered}</span>
            <span className="metric-sub">{metrics.event_trigger_rate}% trigger rate</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Suppressed (Storm / Cooldown)</span>
            <span className="metric-value text-amber">{metrics.events_suppressed}</span>
            <span className="metric-sub">{metrics.cooldown_suppressions} cooldown / {metrics.event_storm_suppressions} storm</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Deduplicated</span>
            <span className="metric-value text-purple">{metrics.events_deduplicated}</span>
            <span className="metric-sub">100% idempotent</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Avg Trigger Latency</span>
            <span className="metric-value">{metrics.average_event_trigger_delay}s</span>
            <span className="metric-sub">Event → Agent dispatch</span>
          </div>
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="filter-toolbar">
        <div className="filter-group">
          <label htmlFor="filter-type">Event Type:</label>
          <select
            id="filter-type"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">All Types</option>
            <option value="ranking_change">Ranking Change</option>
            <option value="page_status_change">Page Status Change</option>
            <option value="seo_audit_change">SEO Audit Change</option>
            <option value="gsc_change">GSC Performance Change</option>
            <option value="crawl_issue">Crawl Issue Detected</option>
            <option value="keyword_visibility_change">Keyword Visibility</option>
            <option value="content_change">Content Change</option>
          </select>
        </div>
        <div className="filter-group">
          <label htmlFor="filter-status">Status:</label>
          <select
            id="filter-status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="processed">Processed (Triggered)</option>
            <option value="accepted">Accepted (No Trigger)</option>
            <option value="suppressed">Suppressed</option>
            <option value="deduplicated">Deduplicated</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
        <div className="filter-group">
          <label htmlFor="filter-severity">Severity:</label>
          <select
            id="filter-severity"
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
          >
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
      </div>

      {/* Events Table */}
      <div className="table-responsive">
        <table className="events-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Event Type</th>
              <th>Source</th>
              <th>Severity</th>
              <th>Status</th>
              <th>Triggered Agent Run</th>
              <th>Policy / Suppression Reason</th>
              <th>Occurred At</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty-state">
                  No events found matching current criteria. Ingest or simulate an SEO event to observe real-time agent triggering.
                </td>
              </tr>
            ) : (
              events.map((ev) => (
                <tr
                  key={ev.id}
                  className={`event-row ${selectedEvent?.id === ev.id ? 'selected' : ''}`}
                  onClick={() => setSelectedEvent(ev)}
                >
                  <td className="font-mono text-muted">#{ev.id}</td>
                  <td>
                    <span className="event-type-tag">
                      {ev.event_type.replace(/_/g, ' ').toUpperCase()}
                    </span>
                  </td>
                  <td className="font-mono text-xs">{ev.source}</td>
                  <td>
                    <span className={`badge ${getSeverityBadgeClass(ev.severity)}`}>
                      {ev.severity.toUpperCase()}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${getStatusBadgeClass(ev.status)}`}>
                      {ev.status.toUpperCase()}
                    </span>
                  </td>
                  <td>
                    {ev.agent_run ? (
                      <span className="run-tag">
                        Run #{ev.agent_run} ({ev.agent_run_status || 'active'})
                      </span>
                    ) : (
                      <span className="text-muted text-xs">—</span>
                    )}
                  </td>
                  <td className="reason-cell">
                    {ev.suppression_reason || (ev.status === 'processed' ? 'Trigger policy satisfied' : 'Event accepted')}
                  </td>
                  <td className="text-xs text-muted">
                    {new Date(ev.occurred_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Detail Drawer if an event is selected */}
      {selectedEvent && (
        <div className="event-detail-drawer">
          <div className="drawer-header">
            <h4>Event #{selectedEvent.id} Details</h4>
            <button className="btn-close" onClick={() => setSelectedEvent(null)}>X</button>
          </div>
          <div className="drawer-body">
            <div className="detail-meta-grid">
              <div><strong>Correlation ID:</strong> <code>{selectedEvent.correlation_id}</code></div>
              <div><strong>Idempotency Key:</strong> <code>{selectedEvent.idempotency_key}</code></div>
              <div><strong>Occurred:</strong> {new Date(selectedEvent.occurred_at).toLocaleString()}</div>
              <div><strong>Ingested:</strong> {new Date(selectedEvent.received_at).toLocaleString()}</div>
            </div>
            <h5>Payload Snapshot:</h5>
            <pre className="payload-json">
              {JSON.stringify(selectedEvent.payload, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Scoped CSS styling */}
      <style>{`
        .event-activity-panel {
          margin-top: 1.5rem;
          background: #ffffff;
          border: 1px solid #e2e8f0;
          border-radius: 12px;
          padding: 1.5rem;
          color: #0f172a;
          box-shadow: 0 1px 3px 0 rgba(36, 20, 60, 0.06);
        }
        .panel-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.25rem;
          flex-wrap: wrap;
          gap: 1rem;
        }
        .panel-title {
          font-size: 1.25rem;
          font-weight: 800;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          margin: 0;
          color: #24143C;
        }
        .pulse-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #774da9;
          box-shadow: 0 0 8px rgba(119, 77, 169, 0.6);
          display: inline-block;
        }
        .panel-subtitle {
          font-size: 0.85rem;
          color: #64748b;
          margin-top: 0.25rem;
          margin-bottom: 0;
        }
        .header-actions {
          display: flex;
          gap: 0.75rem;
        }
        .btn {
          padding: 0.5rem 1rem;
          border-radius: 8px;
          font-size: 0.875rem;
          font-weight: 600;
          cursor: pointer;
          border: none;
          transition: all 0.2s;
        }
        .btn-primary {
          background: #774da9;
          color: #ffffff;
        }
        .btn-primary:hover {
          background: #673f97;
        }
        .btn-secondary {
          background: #ffffff;
          color: #334155;
          border: 1px solid #cbd5e1;
        }
        .btn-secondary:hover {
          background: #f8fafc;
          border-color: #94a3b8;
        }
        .metrics-strip {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 1rem;
          margin-bottom: 1.5rem;
        }
        .metric-card {
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          border-radius: 8px;
          padding: 1rem;
          display: flex;
          flex-direction: column;
        }
        .metric-label {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #64748b;
          font-weight: 600;
          margin-bottom: 0.25rem;
        }
        .metric-value {
          font-size: 1.5rem;
          font-weight: 800;
          color: #0f172a;
        }
        .metric-sub {
          font-size: 0.75rem;
          color: #64748b;
          margin-top: 0.25rem;
        }
        .text-success { color: #059669 !important; }
        .text-amber { color: #d97706 !important; }
        .text-purple { color: #774da9 !important; }
        .text-muted { color: #64748b; }
        .text-xs { font-size: 0.75rem; }
        .font-mono { font-family: monospace; }
        .filter-toolbar {
          display: flex;
          gap: 1rem;
          margin-bottom: 1rem;
          flex-wrap: wrap;
          background: #f8fafc;
          padding: 0.75rem 1rem;
          border-radius: 8px;
          border: 1px solid #e2e8f0;
        }
        .filter-group {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.8rem;
          color: #334155;
          font-weight: 500;
        }
        .filter-group select {
          background: #ffffff;
          border: 1px solid #cbd5e1;
          border-radius: 6px;
          color: #0f172a;
          padding: 0.35rem 0.6rem;
          font-size: 0.8rem;
          outline: none;
        }
        .table-responsive {
          overflow-x: auto;
        }
        .events-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.85rem;
        }
        .events-table th {
          text-align: left;
          padding: 0.75rem 1rem;
          background: #f8fafc;
          color: #334155;
          font-weight: 700;
          border-bottom: 1px solid #e2e8f0;
        }
        .events-table td {
          padding: 0.75rem 1rem;
          border-bottom: 1px solid #f1f5f9;
          color: #0f172a;
        }
        .event-row {
          cursor: pointer;
          transition: background 0.15s;
        }
        .event-row:hover {
          background: #f8fafc;
        }
        .event-row.selected {
          background: #f6f2fb;
          border-left: 3px solid #774da9;
        }
        .badge {
          display: inline-block;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
        }
        .badge-critical { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .badge-high { background: #fff7ed; color: #c2410c; border: 1px solid #ffedd5; }
        .badge-medium { background: #f6f2fb; color: #774da9; border: 1px solid #dac8ee; }
        .badge-low { background: #f1f5f9; color: #334155; border: 1px solid #e2e8f0; }
        .badge-processed { background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
        .badge-accepted { background: #f6f2fb; color: #593285; border: 1px solid #dac8ee; }
        .badge-suppressed { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
        .badge-deduplicated { background: #faf5ff; color: #6b21a8; border: 1px solid #e9d5ff; }
        .badge-rejected { background: #fdf2f8; color: #9d174d; border: 1px solid #fbcfe8; }
        .badge-received { background: #f3f4f6; color: #374151; border: 1px solid #e5e7eb; }
        .event-type-tag {
          font-size: 0.75rem;
          font-weight: 600;
          color: #774da9;
        }
        .run-tag {
          background: #f6f2fb;
          color: #774da9;
          border: 1px solid #dac8ee;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: 600;
        }
        .reason-cell {
          max-width: 250px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          color: #475569;
        }
        .empty-state {
          text-align: center;
          padding: 3rem 1rem;
          color: #64748b;
        }
        .event-detail-drawer {
          margin-top: 1rem;
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          border-radius: 8px;
          padding: 1rem;
        }
        .drawer-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.75rem;
        }
        .drawer-header h4 {
          margin: 0;
          color: #24143C;
          font-weight: 700;
        }
        .btn-close {
          background: none;
          border: none;
          color: #64748b;
          font-size: 1rem;
          font-weight: 700;
          cursor: pointer;
        }
        .detail-meta-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 0.5rem;
          font-size: 0.8rem;
          margin-bottom: 1rem;
          color: #334155;
        }
        .detail-meta-grid code {
          background: #ffffff;
          padding: 0.1rem 0.3rem;
          border-radius: 3px;
          color: #774da9;
          border: 1px solid #e2e8f0;
        }
        .payload-json {
          background: #0f172a;
          border: 1px solid #1e293b;
          border-radius: 6px;
          padding: 0.75rem;
          font-size: 0.75rem;
          color: #a5f3fc;
          overflow-x: auto;
        }
        .alert {
          padding: 0.75rem 1rem;
          border-radius: 6px;
          margin-bottom: 1rem;
          font-size: 0.85rem;
        }
        .alert-danger { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .alert-success { background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
      `}</style>
    </div>
  );
};
