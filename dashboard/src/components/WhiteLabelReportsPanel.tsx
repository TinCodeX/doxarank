import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { Project } from '../types/project';
import type { SEOReport } from '../types/report';
import { getReports, generateReport, downloadReportFile } from '../api/reports';

interface WhiteLabelReportsPanelProps {
  project: Project;
  hasReportsEntitlement: boolean;
  onUpgrade?: () => void;
}

export const WhiteLabelReportsPanel: React.FC<WhiteLabelReportsPanelProps> = ({
  project,
  hasReportsEntitlement,
  onUpgrade,
}) => {
  const [reports, setReports] = useState<SEOReport[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  // Form inputs
  const [clientName, setClientName] = useState<string>('');
  const [reportTitle, setReportTitle] = useState<string>('SEO Performance & Technical Audit Report');
  const [showGenerateModal, setShowGenerateModal] = useState<boolean>(false);

  // Status banners
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const pollIntervalRef = useRef<any>(null);

  const loadReports = useCallback(async () => {
    if (!project || !hasReportsEntitlement) return;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await getReports(project.id);
      setReports(data);
    } catch (err: any) {
      setErrorMsg(err?.data?.detail || err?.message || 'Failed to load reports.');
    } finally {
      setIsLoading(false);
    }
  }, [project, hasReportsEntitlement]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  // Polling effect while any report is PENDING or RUNNING
  const hasActiveReports = reports.some(
    (r) => r.status === 'PENDING' || r.status === 'RUNNING'
  );

  useEffect(() => {
    if (hasActiveReports && project && hasReportsEntitlement) {
      pollIntervalRef.current = setInterval(async () => {
        try {
          const data = await getReports(project.id);
          setReports(data);
          const stillActive = data.some((r) => r.status === 'PENDING' || r.status === 'RUNNING');
          if (!stillActive && pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
          }
        } catch {
          // ignore transient poll error
        }
      }, 3000);
    }

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [hasActiveReports, project, hasReportsEntitlement]);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!project || isGenerating) return;

    setIsGenerating(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      const newReport = await generateReport({
        project_id: project.id,
        client_name: clientName.trim(),
        title: reportTitle.trim() || 'SEO Performance & Technical Audit Report',
        async: true,
      });

      setReports((prev) => [newReport, ...prev.filter((r) => r.id !== newReport.id)]);
      setSuccessMsg(`Report generation initiated for "${project.name}". PDF compilation running in background.`);
      setShowGenerateModal(false);
      setClientName('');
    } catch (err: any) {
      setErrorMsg(err?.data?.detail || err?.message || 'Failed to initiate report generation.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDownload = async (report: SEOReport) => {
    if (report.status !== 'COMPLETED') return;
    setDownloadingId(report.id);
    setErrorMsg(null);
    try {
      const filename = `seo_report_${project.name.toLowerCase().replace(/[^a-z0-9]/g, '_')}_${report.id}.pdf`;
      await downloadReportFile(report.id, filename);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to download PDF report.');
    } finally {
      setDownloadingId(null);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (!bytes || bytes === 0) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span
            style={{
              padding: '3px 8px',
              borderRadius: '6px',
              backgroundColor: '#ecfdf5',
              color: '#065f46',
              border: '1px solid #a7f3d0',
              fontSize: '11px',
              fontWeight: 600,
            }}
          >
            ✓ Ready
          </span>
        );
      case 'RUNNING':
        return (
          <span
            style={{
              padding: '3px 8px',
              borderRadius: '6px',
              backgroundColor: '#eff6ff',
              color: '#1e40af',
              border: '1px solid #bfdbfe',
              fontSize: '11px',
              fontWeight: 600,
            }}
          >
            ⚙ Generating...
          </span>
        );
      case 'PENDING':
        return (
          <span
            style={{
              padding: '3px 8px',
              borderRadius: '6px',
              backgroundColor: '#fffbeb',
              color: '#92400e',
              border: '1px solid #fde68a',
              fontSize: '11px',
              fontWeight: 600,
            }}
          >
            ⏳ Queued
          </span>
        );
      case 'FAILED':
        return (
          <span
            style={{
              padding: '3px 8px',
              borderRadius: '6px',
              backgroundColor: '#fef2f2',
              color: '#991b1b',
              border: '1px solid #fecaca',
              fontSize: '11px',
              fontWeight: 600,
            }}
          >
            ✕ Failed
          </span>
        );
      default:
        return <span>{status}</span>;
    }
  };

  return (
    <section
      id="white-label-reports-section"
      style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        padding: '24px',
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
        border: '1px solid #e2e8f0',
        marginBottom: '32px',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '20px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', margin: 0 }}>
              White-Label PDF Reports
            </h2>
            <span
              style={{
                fontSize: '12px',
                fontWeight: 600,
                padding: '3px 8px',
                borderRadius: '6px',
                backgroundColor: '#ede9fe',
                color: '#6d28d9',
                border: '1px solid #ddd6fe',
              }}
            >
              Agency Plan
            </span>
          </div>
          <p style={{ fontSize: '14px', color: '#64748b', margin: '6px 0 0 0' }}>
            Generate executive, unbranded SEO reports with technical findings, Google Ethiopia rank tracking, competitor benchmarks, and action plans.
          </p>
        </div>

        {hasReportsEntitlement && (
          <button
            id="generate-report-modal-btn"
            onClick={() => setShowGenerateModal(true)}
            style={{
              padding: '9px 18px',
              backgroundColor: '#7c3aed',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              fontWeight: 600,
              fontSize: '13px',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            📄 Generate New Report
          </button>
        )}
      </div>

      {/* Paywall Notice for Free & Starter users */}
      {!hasReportsEntitlement && (
        <div
          id="reports-paywall-notice"
          style={{
            padding: '28px',
            backgroundColor: '#faf5ff',
            borderRadius: '10px',
            border: '1px solid #e9d5ff',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '32px', marginBottom: '8px' }}>🔒</div>
          <h3 style={{ fontSize: '17px', fontWeight: 700, color: '#581c87', margin: '0 0 8px 0' }}>
            White-Label PDF Reports is an Agency Feature
          </h3>
          <p
            style={{
              fontSize: '14px',
              color: '#6b21a8',
              margin: '0 0 18px 0',
              maxWidth: '560px',
              marginLeft: 'auto',
              marginRight: 'auto',
              lineHeight: 1.5,
            }}
          >
            Upgrade to the Agency Plan (ETB 6,000/mo) to generate professional, unbranded SEO audit and ranking PDF reports customized with your client or agency branding.
          </p>
          <button
            id="upgrade-to-agency-btn"
            onClick={() => {
              if (onUpgrade) {
                onUpgrade();
              } else {
                window.location.href = '/subscription';
              }
            }}
            style={{
              padding: '9px 20px',
              backgroundColor: '#7c3aed',
              color: '#ffffff',
              border: 'none',
              borderRadius: '8px',
              fontWeight: 600,
              fontSize: '13px',
              cursor: 'pointer',
            }}
          >
            Upgrade to Agency Plan
          </button>
        </div>
      )}

      {hasReportsEntitlement && (
        <>
          {/* Status alerts */}
          {errorMsg && (
            <div
              style={{
                padding: '12px 16px',
                backgroundColor: '#fef2f2',
                borderRadius: '8px',
                border: '1px solid #fecaca',
                color: '#991b1b',
                fontSize: '13px',
                marginBottom: '16px',
              }}
            >
              ⚠ {errorMsg}
            </div>
          )}

          {successMsg && (
            <div
              style={{
                padding: '12px 16px',
                backgroundColor: '#f0fdf4',
                borderRadius: '8px',
                border: '1px solid #bbf7d0',
                color: '#166534',
                fontSize: '13px',
                marginBottom: '16px',
              }}
            >
              ✓ {successMsg}
            </div>
          )}

          {/* Reports Table */}
          {isLoading && reports.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '36px', color: '#64748b', fontSize: '14px' }}>
              Loading generated reports...
            </div>
          ) : reports.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '36px',
                backgroundColor: '#f8fafc',
                borderRadius: '8px',
                border: '1px dashed #cbd5e1',
                color: '#64748b',
              }}
            >
              <p style={{ margin: '0 0 10px 0', fontSize: '15px', fontWeight: 600, color: '#334155' }}>
                No reports generated yet for {project.name}
              </p>
              <p style={{ margin: '0 0 16px 0', fontSize: '13px' }}>
                Click "Generate New Report" to compile a client-ready white-label SEO audit.
              </p>
              <button
                onClick={() => setShowGenerateModal(true)}
                style={{
                  padding: '7px 15px',
                  backgroundColor: '#7c3aed',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '6px',
                  fontWeight: 600,
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
              >
                + Create First Report
              </button>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #e2e8f0', textAlign: 'left', backgroundColor: '#f8fafc' }}>
                    <th style={{ padding: '10px 12px', color: '#475569', fontWeight: 600 }}>Report Title</th>
                    <th style={{ padding: '10px 12px', color: '#475569', fontWeight: 600 }}>Client Label</th>
                    <th style={{ padding: '10px 12px', color: '#475569', fontWeight: 600 }}>Generated Date</th>
                    <th style={{ padding: '10px 12px', color: '#475569', fontWeight: 600 }}>Status</th>
                    <th style={{ padding: '10px 12px', color: '#475569', fontWeight: 600 }}>File Size</th>
                    <th style={{ padding: '10px 12px', color: '#475569', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((rep) => (
                    <tr
                      key={rep.id}
                      style={{
                        borderBottom: '1px solid #f1f5f9',
                        transition: 'background-color 0.15s ease',
                      }}
                    >
                      <td style={{ padding: '12px', fontWeight: 600, color: '#0f172a' }}>
                        {rep.title}
                        {rep.error_message && (
                          <div style={{ fontSize: '11px', color: '#dc2626', fontWeight: 400, marginTop: '2px' }}>
                            {rep.error_message}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: '12px', color: '#334155' }}>
                        {rep.client_name || <span style={{ color: '#94a3b8' }}>—</span>}
                      </td>
                      <td style={{ padding: '12px', color: '#64748b' }}>
                        {new Date(rep.created_at).toLocaleString()}
                      </td>
                      <td style={{ padding: '12px' }}>
                        {getStatusBadge(rep.status)}
                      </td>
                      <td style={{ padding: '12px', color: '#64748b' }}>
                        {formatFileSize(rep.file_size_bytes)}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right' }}>
                        {rep.status === 'COMPLETED' ? (
                          <button
                            id={`download-report-${rep.id}`}
                            onClick={() => handleDownload(rep)}
                            disabled={downloadingId === rep.id}
                            style={{
                              padding: '6px 14px',
                              backgroundColor: '#059669',
                              color: '#ffffff',
                              border: 'none',
                              borderRadius: '6px',
                              fontWeight: 600,
                              fontSize: '12px',
                              cursor: downloadingId === rep.id ? 'not-allowed' : 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            {downloadingId === rep.id ? 'Downloading...' : '⬇ Download PDF'}
                          </button>
                        ) : rep.status === 'FAILED' ? (
                          <span style={{ fontSize: '12px', color: '#94a3b8' }}>Unavailable</span>
                        ) : (
                          <span style={{ fontSize: '12px', color: '#2563eb' }}>Processing...</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Generate Report Modal */}
          {showGenerateModal && (
            <div
              style={{
                position: 'fixed',
                inset: 0,
                backgroundColor: 'rgba(15, 23, 42, 0.5)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 9999,
                padding: '16px',
              }}
            >
              <div
                style={{
                  backgroundColor: '#ffffff',
                  borderRadius: '12px',
                  padding: '24px',
                  maxWidth: '480px',
                  width: '100%',
                  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 style={{ fontSize: '18px', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                    Generate White-Label PDF Report
                  </h3>
                  <button
                    onClick={() => setShowGenerateModal(false)}
                    style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#94a3b8' }}
                  >
                    ✕
                  </button>
                </div>

                <form onSubmit={handleGenerate}>
                  <div style={{ marginBottom: '14px' }}>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                      Report Title
                    </label>
                    <input
                      type="text"
                      value={reportTitle}
                      onChange={(e) => setReportTitle(e.target.value)}
                      placeholder="e.g. SEO Performance & Technical Audit Report"
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        border: '1px solid #cbd5e1',
                        borderRadius: '6px',
                        fontSize: '13px',
                        boxSizing: 'border-box',
                      }}
                      required
                    />
                  </div>

                  <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                      Client / Company Name (Optional)
                    </label>
                    <input
                      type="text"
                      value={clientName}
                      onChange={(e) => setClientName(e.target.value)}
                      placeholder="e.g. Acme Corp (leaves DoxaRank out of the report)"
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        border: '1px solid #cbd5e1',
                        borderRadius: '6px',
                        fontSize: '13px',
                        boxSizing: 'border-box',
                      }}
                    />
                    <small style={{ color: '#64748b', fontSize: '11px', display: 'block', marginTop: '4px' }}>
                      If provided, the report will be branded exclusively for this client with zero DoxaRank mentions.
                    </small>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                    <button
                      type="button"
                      onClick={() => setShowGenerateModal(false)}
                      style={{
                        padding: '8px 14px',
                        backgroundColor: '#f1f5f9',
                        color: '#475569',
                        border: '1px solid #cbd5e1',
                        borderRadius: '6px',
                        fontSize: '13px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isGenerating}
                      style={{
                        padding: '8px 18px',
                        backgroundColor: '#7c3aed',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: '6px',
                        fontSize: '13px',
                        fontWeight: 600,
                        cursor: isGenerating ? 'not-allowed' : 'pointer',
                      }}
                    >
                      {isGenerating ? 'Compiling PDF...' : 'Generate Report'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
};
