import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types/project';
import type {
  SEOEvent,
  SEOEventMetrics,
  SEOEventType,
  SEOEventSeverity,
} from '../types/seoEvent';
import {
  getSEOEvents,
  getSEOEventMetrics,
  ingestSEOEvent,
} from '../api/seoEvents';

interface EventActivityPanelProps {
  project: Project;
}

export const EventActivityPanel: React.FC<EventActivityPanelProps> = ({ project }) => {
  const [events, setEvents] = useState<SEOEvent[]>([]);
  const [metrics, setMetrics] = useState<SEOEventMetrics | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<SEOEvent | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Filters
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('');

  // Simulation Form state
  const [isSimModalOpen, setIsSimModalOpen] = useState<boolean>(false);
  const [simEventType, setSimEventType] = useState<SEOEventType>('ranking_change');
  const [simSeverity, setSimSeverity] = useState<SEOEventSeverity>('high');
  const [simSource, setSimSource] = useState<string>('rank_tracker_engine');
  const [simKeyword, setSimKeyword] = useState<string>('best ai seo software');
  const [simRankDrop, setSimRankDrop] = useState<number>(4);
  const [simUrl, setSimUrl] = useState<string>(project.website_url || 'https://example.com/landing');

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

  const handleSimulateEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsSimulating(true);
      setErrorMessage(null);
      setSuccessMessage(null);

      let payload: Record<string, any> = {};
      if (simEventType === 'ranking_change') {
        payload = {
          keyword: simKeyword,
          rank_drop: Number(simRankDrop),
          previous_rank: 3,
          new_rank: 3 + Number(simRankDrop),
          url: simUrl,
        };
      } else if (simEventType === 'page_status_change') {
        payload = {
          status_code: 500,
          url: simUrl,
          is_error: true,
          error_message: 'Internal Server Error detected on product page',
        };
      } else if (simEventType === 'seo_audit_change') {
        payload = {
          critical_issues_count: 3,
          score_drop: 8,
          url: simUrl,
        };
      } else {
        payload = {
          notes: 'Simulated automated SEO notification',
          url: simUrl,
        };
      }

      const created = await ingestSEOEvent({
        project_id: project.id,
        event_type: simEventType,
        source: simSource,
        severity: simSeverity,
        payload,
      });

      setSuccessMessage(`Event #${created.id} ingested successfully! Status: ${created.status.toUpperCase()}`);
      setIsSimModalOpen(false);
      await loadData();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to ingest simulated event.');
    } finally {
      setIsSimulating(false);
    }
  };

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
            Event-Driven Agent Operations (Milestone 6.2)
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
          <button
            className="btn btn-primary"
            onClick={() => setIsSimModalOpen(true)}
          >
            + Simulate SEO Event
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
            <button className="btn-close" onClick={() => setSelectedEvent(null)}>✕</button>
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

      {/* Simulation Modal */}
      {isSimModalOpen && (
        <div className="modal-backdrop">
          <div className="modal-dialog">
            <div className="modal-header">
              <h3>Simulate Incoming SEO Event</h3>
              <button className="btn-close" onClick={() => setIsSimModalOpen(false)}>✕</button>
            </div>
            <form onSubmit={handleSimulateEvent}>
              <div className="modal-body">
                <div className="form-group">
                  <label htmlFor="sim-event-type">Event Type:</label>
                  <select
                    id="sim-event-type"
                    value={simEventType}
                    onChange={(e) => setSimEventType(e.target.value as SEOEventType)}
                  >
                    <option value="ranking_change">Ranking Change (e.g. Rank Drop)</option>
                    <option value="page_status_change">Page Status Change (e.g. 500 Error)</option>
                    <option value="seo_audit_change">SEO Audit Change (e.g. Critical Issues)</option>
                    <option value="crawl_issue">Crawl Issue Detected</option>
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="sim-severity">Severity:</label>
                  <select
                    id="sim-severity"
                    value={simSeverity}
                    onChange={(e) => setSimSeverity(e.target.value as SEOEventSeverity)}
                  >
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="sim-source">Source:</label>
                  <input
                    id="sim-source"
                    type="text"
                    value={simSource}
                    onChange={(e) => setSimSource(e.target.value)}
                    required
                  />
                </div>

                {simEventType === 'ranking_change' && (
                  <>
                    <div className="form-group">
                      <label htmlFor="sim-keyword">Tracked Keyword:</label>
                      <input
                        id="sim-keyword"
                        type="text"
                        value={simKeyword}
                        onChange={(e) => setSimKeyword(e.target.value)}
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="sim-rank-drop">Rank Drop (Positions):</label>
                      <input
                        id="sim-rank-drop"
                        type="number"
                        min="1"
                        max="100"
                        value={simRankDrop}
                        onChange={(e) => setSimRankDrop(Number(e.target.value))}
                        required
                      />
                      <small className="help-text">Drop &ge; 3 triggers autonomous agent investigation.</small>
                    </div>
                  </>
                )}

                <div className="form-group">
                  <label htmlFor="sim-url">Target URL:</label>
                  <input
                    id="sim-url"
                    type="url"
                    value={simUrl}
                    onChange={(e) => setSimUrl(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsSimModalOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isSimulating}
                >
                  {isSimulating ? 'Ingesting...' : 'Ingest & Trigger'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Scoped CSS styling */}
      <style>{`
        .event-activity-panel {
          margin-top: 2rem;
          background: #0f172a;
          border: 1px solid #1e293b;
          border-radius: 12px;
          padding: 1.5rem;
          color: #f8fafc;
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
          font-weight: 700;
          display: flex;
          align-items: center;
          gap: 0.5rem;
          margin: 0;
          color: #f1f5f9;
        }
        .pulse-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #3b82f6;
          box-shadow: 0 0 8px #3b82f6;
          display: inline-block;
        }
        .panel-subtitle {
          font-size: 0.85rem;
          color: #94a3b8;
          margin-top: 0.25rem;
          margin-bottom: 0;
        }
        .header-actions {
          display: flex;
          gap: 0.75rem;
        }
        .btn {
          padding: 0.5rem 1rem;
          border-radius: 6px;
          font-size: 0.875rem;
          font-weight: 500;
          cursor: pointer;
          border: none;
          transition: all 0.2s;
        }
        .btn-primary {
          background: #2563eb;
          color: #ffffff;
        }
        .btn-primary:hover {
          background: #1d4ed8;
        }
        .btn-secondary {
          background: #1e293b;
          color: #cbd5e1;
          border: 1px solid #334155;
        }
        .btn-secondary:hover {
          background: #334155;
        }
        .metrics-strip {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 1rem;
          margin-bottom: 1.5rem;
        }
        .metric-card {
          background: #1e293b;
          border: 1px solid #334155;
          border-radius: 8px;
          padding: 1rem;
          display: flex;
          flex-direction: column;
        }
        .metric-label {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #94a3b8;
          margin-bottom: 0.25rem;
        }
        .metric-value {
          font-size: 1.5rem;
          font-weight: 700;
          color: #f8fafc;
        }
        .metric-sub {
          font-size: 0.7rem;
          color: #64748b;
          margin-top: 0.25rem;
        }
        .text-success { color: #10b981 !important; }
        .text-amber { color: #f59e0b !important; }
        .text-purple { color: #a855f7 !important; }
        .text-muted { color: #64748b; }
        .text-xs { font-size: 0.75rem; }
        .font-mono { font-family: monospace; }
        .filter-toolbar {
          display: flex;
          gap: 1rem;
          margin-bottom: 1rem;
          flex-wrap: wrap;
          background: #131d33;
          padding: 0.75rem 1rem;
          border-radius: 8px;
        }
        .filter-group {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.8rem;
          color: #94a3b8;
        }
        .filter-group select {
          background: #0f172a;
          border: 1px solid #334155;
          border-radius: 4px;
          color: #f8fafc;
          padding: 0.25rem 0.5rem;
          font-size: 0.8rem;
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
          background: #1e293b;
          color: #94a3b8;
          font-weight: 600;
          border-bottom: 1px solid #334155;
        }
        .events-table td {
          padding: 0.75rem 1rem;
          border-bottom: 1px solid #1e293b;
        }
        .event-row {
          cursor: pointer;
          transition: background 0.15s;
        }
        .event-row:hover {
          background: #1e293b;
        }
        .event-row.selected {
          background: #1e3a8a33;
          border-left: 3px solid #3b82f6;
        }
        .badge {
          display: inline-block;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
        }
        .badge-critical { background: #991b1b; color: #fecaca; }
        .badge-high { background: #c2410c; color: #ffedd5; }
        .badge-medium { background: #1d4ed8; color: #dbeafe; }
        .badge-low { background: #334155; color: #cbd5e1; }
        .badge-processed { background: #065f46; color: #a7f3d0; }
        .badge-accepted { background: #1e40af; color: #bfdbfe; }
        .badge-suppressed { background: #92400e; color: #fef3c7; }
        .badge-deduplicated { background: #6b21a8; color: #f3e8ff; }
        .badge-rejected { background: #831843; color: #fce7f3; }
        .badge-received { background: #374151; color: #e5e7eb; }
        .event-type-tag {
          font-size: 0.75rem;
          font-weight: 600;
          color: #38bdf8;
        }
        .run-tag {
          background: #0284c722;
          color: #38bdf8;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: 500;
        }
        .reason-cell {
          max-width: 250px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          color: #cbd5e1;
        }
        .empty-state {
          text-align: center;
          padding: 3rem 1rem;
          color: #64748b;
        }
        .event-detail-drawer {
          margin-top: 1rem;
          background: #131d33;
          border: 1px solid #1e293b;
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
          color: #f1f5f9;
        }
        .btn-close {
          background: none;
          border: none;
          color: #94a3b8;
          font-size: 1rem;
          cursor: pointer;
        }
        .detail-meta-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 0.5rem;
          font-size: 0.8rem;
          margin-bottom: 1rem;
          color: #94a3b8;
        }
        .detail-meta-grid code {
          background: #0f172a;
          padding: 0.1rem 0.3rem;
          border-radius: 3px;
          color: #38bdf8;
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
        .modal-backdrop {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.75);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 9999;
        }
        .modal-dialog {
          background: #1e293b;
          border: 1px solid #334155;
          border-radius: 12px;
          width: 100%;
          max-width: 500px;
          padding: 1.5rem;
          box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
        }
        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.25rem;
        }
        .modal-header h3 {
          margin: 0;
          font-size: 1.15rem;
          color: #f8fafc;
        }
        .form-group {
          margin-bottom: 1rem;
        }
        .form-group label {
          display: block;
          font-size: 0.8rem;
          font-weight: 500;
          color: #cbd5e1;
          margin-bottom: 0.35rem;
        }
        .form-group input, .form-group select {
          width: 100%;
          background: #0f172a;
          border: 1px solid #334155;
          border-radius: 6px;
          padding: 0.5rem 0.75rem;
          color: #f8fafc;
          font-size: 0.85rem;
        }
        .form-group input:focus, .form-group select:focus {
          outline: none;
          border-color: #3b82f6;
        }
        .help-text {
          font-size: 0.75rem;
          color: #94a3b8;
          margin-top: 0.25rem;
          display: block;
        }
        .modal-footer {
          display: flex;
          justify-content: flex-end;
          gap: 0.75rem;
          margin-top: 1.5rem;
        }
        .alert {
          padding: 0.75rem 1rem;
          border-radius: 6px;
          margin-bottom: 1rem;
          font-size: 0.85rem;
        }
        .alert-danger { background: #7f1d1d; color: #fecaca; }
        .alert-success { background: #064e3b; color: #a7f3d0; }
      `}</style>
    </div>
  );
};
