import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { Project } from '../types/project';
import type { SearchConsoleConnection } from '../types/searchConsole';
import type {
  GSCPerformanceSummary,
  GSCQueryItem,
  GSCPageItem,
  GSCDeviceItem,
  GSCCountryItem,
  GSCSyncResponse,
  DateRangePreset,
} from '../types/searchConsoleAnalytics';
import {
  getSearchConsolePerformance,
  getSearchConsoleQueries,
  getSearchConsolePages,
  getSearchConsoleDevices,
  getSearchConsoleCountries,
  syncSearchConsole,
} from '../api/searchConsoleAnalytics';

interface SearchConsoleAnalyticsPanelProps {
  project: Project;
  connection?: SearchConsoleConnection | null;
  onConnectionRefresh?: () => void;
}

type TabType = 'queries' | 'pages' | 'devices' | 'countries';
type MetricViewType = 'clicks' | 'impressions' | 'ctr' | 'position';

export const SearchConsoleAnalyticsPanel: React.FC<SearchConsoleAnalyticsPanelProps> = ({
  project,
  connection,
  onConnectionRefresh,
}) => {
  // State
  const [datePreset, setDatePreset] = useState<DateRangePreset>('28d');
  const [customStartDate, setCustomStartDate] = useState<string>('');
  const [customEndDate, setCustomEndDate] = useState<string>('');
  const [activeTab, setActiveTab] = useState<TabType>('queries');
  const [metricView, setMetricView] = useState<MetricViewType>('clicks');
  const [searchFilter, setSearchFilter] = useState<string>('');

  // Data states
  const [performance, setPerformance] = useState<GSCPerformanceSummary | null>(null);
  const [queries, setQueries] = useState<GSCQueryItem[]>([]);
  const [pages, setPages] = useState<GSCPageItem[]>([]);
  const [devices, setDevices] = useState<GSCDeviceItem[]>([]);
  const [countries, setCountries] = useState<GSCCountryItem[]>([]);

  // Loading & Error states
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredPointIndex, setHoveredPointIndex] = useState<number | null>(null);

  // Sync state
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [syncSuccessSummary, setSyncSuccessSummary] = useState<GSCSyncResponse | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  // Calculate start_date and end_date strings based on preset
  const { startDateStr, endDateStr } = useMemo(() => {
    const today = new Date();
    const formatDate = (d: Date) => d.toISOString().split('T')[0];
    const todayStr = formatDate(today);

    if (datePreset === '7d') {
      const start = new Date();
      start.setDate(today.getDate() - 7);
      return { startDateStr: formatDate(start), endDateStr: todayStr };
    }
    if (datePreset === '28d') {
      const start = new Date();
      start.setDate(today.getDate() - 28);
      return { startDateStr: formatDate(start), endDateStr: todayStr };
    }
    if (datePreset === '90d') {
      const start = new Date();
      start.setDate(today.getDate() - 90);
      return { startDateStr: formatDate(start), endDateStr: todayStr };
    }
    if (datePreset === 'custom' && customStartDate && customEndDate) {
      return { startDateStr: customStartDate, endDateStr: customEndDate };
    }
    return { startDateStr: undefined, endDateStr: undefined };
  }, [datePreset, customStartDate, customEndDate]);

  // Fetch all analytics data for active project
  const fetchAnalytics = useCallback(async () => {
    if (!project?.id) return;
    setIsLoading(true);
    setError(null);

    const filterPayload = {
      project_id: project.id,
      start_date: startDateStr,
      end_date: endDateStr,
    };

    try {
      const [perfData, queryData, pageData, deviceData, countryData] = await Promise.all([
        getSearchConsolePerformance(filterPayload),
        getSearchConsoleQueries(filterPayload),
        getSearchConsolePages(filterPayload),
        getSearchConsoleDevices(filterPayload),
        getSearchConsoleCountries(filterPayload),
      ]);

      setPerformance(perfData);
      setQueries(queryData || []);
      setPages(pageData || []);
      setDevices(deviceData || []);
      setCountries(countryData || []);
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to load Search Console analytics.');
    } finally {
      setIsLoading(false);
    }
  }, [project?.id, startDateStr, endDateStr]);

  // Project Isolation: clear previous state immediately on project switch
  useEffect(() => {
    setPerformance(null);
    setQueries([]);
    setPages([]);
    setDevices([]);
    setCountries([]);
    setSearchFilter('');
    setSyncSuccessSummary(null);
    setSyncError(null);
    setHoveredPointIndex(null);

    if (project?.id) {
      fetchAnalytics();
    }
  }, [project?.id, fetchAnalytics]);

  // Handle Sync Now action
  const handleTriggerSync = async () => {
    if (!project?.id || isSyncing) return;
    setIsSyncing(true);
    setSyncError(null);
    setSyncSuccessSummary(null);

    try {
      const result = await syncSearchConsole({
        project_id: project.id,
        start_date: startDateStr,
        end_date: endDateStr,
      });
      setSyncSuccessSummary(result);
      // Refresh analytics data and parent connection metadata
      await fetchAnalytics();
      if (onConnectionRefresh) {
        onConnectionRefresh();
      }
    } catch (err: any) {
      setSyncError(err?.data?.detail || 'Synchronization failed. Please verify your Search Console connection.');
    } finally {
      setIsSyncing(false);
    }
  };

  // Filtered queries and pages by substring search
  const filteredQueries = useMemo(() => {
    if (!searchFilter.trim()) return queries;
    const lower = searchFilter.toLowerCase();
    return queries.filter((q) => q.query.toLowerCase().includes(lower));
  }, [queries, searchFilter]);

  const filteredPages = useMemo(() => {
    if (!searchFilter.trim()) return pages;
    const lower = searchFilter.toLowerCase();
    return pages.filter((p) => p.page.toLowerCase().includes(lower));
  }, [pages, searchFilter]);

  // SVG Chart Calculation
  const timeseries = performance?.timeseries || [];
  const chartData = useMemo(() => {
    if (!timeseries || timeseries.length === 0) return null;

    const width = 820;
    const height = 240;
    const padding = { top: 20, right: 30, bottom: 40, left: 55 };

    const innerWidth = width - padding.left - padding.right;
    const innerHeight = height - padding.top - padding.bottom;

    const values = timeseries.map((pt) => {
      if (metricView === 'clicks') return pt.clicks;
      if (metricView === 'impressions') return pt.impressions;
      if (metricView === 'ctr') return pt.ctr * 100;
      return pt.position;
    });

    const minVal = metricView === 'position' ? Math.min(1, ...values) : 0;
    let maxVal = Math.max(...values, 1);
    if (metricView === 'ctr') maxVal = Math.max(maxVal, 5);

    const getX = (idx: number) => {
      if (timeseries.length <= 1) return padding.left + innerWidth / 2;
      return padding.left + (idx / (timeseries.length - 1)) * innerWidth;
    };

    const getY = (val: number) => {
      if (metricView === 'position') {
        const posMin = Math.min(...values, 1);
        const posMax = Math.max(...values, 20);
        const range = posMax - posMin || 1;
        return padding.top + ((val - posMin) / range) * innerHeight;
      }
      const range = maxVal - minVal || 1;
      return padding.top + innerHeight - ((val - minVal) / range) * innerHeight;
    };

    const points = timeseries.map((pt, idx) => ({
      x: getX(idx),
      y: getY(values[idx]),
      val: values[idx],
      raw: pt,
    }));

    const pathD = points.length > 0 ? points.reduce((acc, pt, i) => `${acc} ${i === 0 ? 'M' : 'L'} ${pt.x} ${pt.y}`, '') : '';
    const areaD = points.length > 0 ? `${pathD} L ${points[points.length - 1].x} ${padding.top + innerHeight} L ${points[0].x} ${padding.top + innerHeight} Z` : '';

    return { width, height, padding, innerWidth, innerHeight, points, pathD, areaD, maxVal, minVal };
  }, [timeseries, metricView]);

  const metricColors: Record<MetricViewType, { stroke: string; fill: string; badge: string; label: string; unit: string }> = {
    clicks: { stroke: '#2563eb', fill: 'rgba(37, 99, 235, 0.12)', badge: '#dbeafe', label: 'Clicks', unit: '' },
    impressions: { stroke: '#7c3aed', fill: 'rgba(124, 58, 237, 0.12)', badge: '#ede9fe', label: 'Impressions', unit: '' },
    ctr: { stroke: '#059669', fill: 'rgba(5, 150, 105, 0.12)', badge: '#d1fae5', label: 'CTR', unit: '%' },
    position: { stroke: '#d97706', fill: 'rgba(217, 119, 6, 0.12)', badge: '#fef3c7', label: 'Avg Position', unit: '' },
  };

  const hasData = performance && (performance.total_clicks > 0 || performance.total_impressions > 0 || timeseries.length > 0);

  return (
    <section style={panelCardStyle} aria-labelledby="gsc-analytics-title">
      {/* Header */}
      <div style={headerContainerStyle}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '24px' }}>📈</span>
            <h3 id="gsc-analytics-title" style={panelTitleStyle}>
              Search Console Search Analytics
            </h3>
            {connection?.property_url && (
              <span style={propertyBadgeStyle} title={connection.property_url}>
                {connection.property_url}
              </span>
            )}
          </div>
          <p style={panelSubtitleStyle}>
            Organic search performance, keyword search queries, top pages, and device breakdowns for <strong>{project.name}</strong>.
          </p>
        </div>

        {/* Action Controls: Presets & Sync Button */}
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '10px' }}>
          {/* Date Presets */}
          <div style={presetGroupStyle}>
            <button
              id="gsc-preset-7d"
              onClick={() => setDatePreset('7d')}
              style={datePreset === '7d' ? activePresetBtnStyle : presetBtnStyle}
            >
              7 Days
            </button>
            <button
              id="gsc-preset-28d"
              onClick={() => setDatePreset('28d')}
              style={datePreset === '28d' ? activePresetBtnStyle : presetBtnStyle}
            >
              28 Days
            </button>
            <button
              id="gsc-preset-90d"
              onClick={() => setDatePreset('90d')}
              style={datePreset === '90d' ? activePresetBtnStyle : presetBtnStyle}
            >
              3 Months
            </button>
            <button
              id="gsc-preset-all"
              onClick={() => setDatePreset('all')}
              style={datePreset === 'all' ? activePresetBtnStyle : presetBtnStyle}
            >
              All Time
            </button>
            <button
              id="gsc-preset-custom"
              onClick={() => setDatePreset('custom')}
              style={datePreset === 'custom' ? activePresetBtnStyle : presetBtnStyle}
            >
              Custom
            </button>
          </div>

          {/* Custom Date Pickers */}
          {datePreset === 'custom' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <input
                id="gsc-custom-start-date"
                type="date"
                value={customStartDate}
                onChange={(e) => setCustomStartDate(e.target.value)}
                style={dateInputStyle}
              />
              <span style={{ color: '#9ca3af', fontSize: '12px' }}>to</span>
              <input
                id="gsc-custom-end-date"
                type="date"
                value={customEndDate}
                onChange={(e) => setCustomEndDate(e.target.value)}
                style={dateInputStyle}
              />
            </div>
          )}

          {/* Sync Now Button */}
          <button
            id="gsc-sync-now-button"
            onClick={handleTriggerSync}
            disabled={isSyncing || (connection ? !connection.is_connected : false)}
            style={isSyncing ? syncingBtnStyle : syncBtnStyle}
            title="Fetch and synchronize fresh Search Console performance records"
          >
            {isSyncing ? (
              <>
                <span className="spinner-icon" style={spinAnimation}>🔄</span>
                <span>Syncing...</span>
              </>
            ) : (
              <>
                <span>⚡</span>
                <span>Sync Now</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Sync Success Feedback Toast/Banner */}
      {syncSuccessSummary && (
        <div style={syncSuccessBannerStyle} role="alert">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '18px' }}>✅</span>
              <div>
                <strong style={{ fontSize: '14px', color: '#065f46' }}>Synchronization Complete!</strong>
                <div style={{ fontSize: '13px', color: '#047857' }}>
                  Fetched <strong>{syncSuccessSummary.records_fetched}</strong> records (Created:{' '}
                  {syncSuccessSummary.records_created}, Updated: {syncSuccessSummary.records_updated}) for range{' '}
                  {syncSuccessSummary.start_date} to {syncSuccessSummary.end_date}.
                </div>
              </div>
            </div>
            <button
              onClick={() => setSyncSuccessSummary(null)}
              style={dismissBtnStyle}
              aria-label="Dismiss summary"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Sync / General Error Banner */}
      {(syncError || error) && (
        <div style={errorBannerStyle} role="alert">
          <span style={{ fontSize: '18px' }}>⚠️</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: '14px', color: '#991b1b' }}>
              {syncError ? 'Sync Error' : 'Analytics Error'}
            </div>
            <div style={{ fontSize: '13px', color: '#b91c1c' }}>{syncError || error}</div>
          </div>
          <button
            onClick={() => {
              setSyncError(null);
              fetchAnalytics();
            }}
            style={retryBtnStyle}
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div style={loadingStateStyle}>
          <div style={spinnerStyle}></div>
          <p style={{ color: '#4b5563', fontSize: '14px', margin: '8px 0 0 0', fontWeight: 500 }}>
            Loading Search Console performance data for {project.name}...
          </p>
        </div>
      )}

      {/* Disconnected / Empty State */}
      {!isLoading && !hasData && (
        <div style={emptyStateCardStyle}>
          <div style={{ fontSize: '42px', marginBottom: '12px' }}>📊</div>
          <h4 style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: 700, color: '#111827' }}>
            No Search Console Analytics Data Yet
          </h4>
          <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: '#6b7280', maxWidth: '480px', lineHeight: 1.6 }}>
            {connection?.is_connected
              ? 'Your property is connected! Click "Sync Now" above to fetch your organic queries, clicks, impressions, and CTR.'
              : 'Google Search Console must be connected to this project before performance data can be tracked.'}
          </p>
          {connection?.is_connected ? (
            <button
              id="gsc-empty-sync-btn"
              onClick={handleTriggerSync}
              disabled={isSyncing}
              style={primaryActionBtnStyle}
            >
              {isSyncing ? 'Syncing...' : '⚡ Sync Search Console Data'}
            </button>
          ) : (
            <div style={{ fontSize: '13px', color: '#4b5563', fontWeight: 500 }}>
              Use the connection card above to link a Search Console property.
            </div>
          )}
        </div>
      )}

      {/* Populated Analytics Section */}
      {!isLoading && hasData && performance && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* 1. Overview Metric Cards */}
          <div style={kpiGridStyle}>
            {/* Total Clicks */}
            <div style={{ ...kpiCardStyle, borderTop: '4px solid #2563eb' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={kpiLabelStyle}>Total Clicks</span>
                <span style={{ fontSize: '20px' }}>🖱️</span>
              </div>
              <div style={{ ...kpiValueStyle, color: '#2563eb' }}>
                {performance.total_clicks.toLocaleString()}
              </div>
              <div style={kpiSubtextStyle}>Organic search visits to your site</div>
            </div>

            {/* Total Impressions */}
            <div style={{ ...kpiCardStyle, borderTop: '4px solid #7c3aed' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={kpiLabelStyle}>Total Impressions</span>
                <span style={{ fontSize: '20px' }}>👁️</span>
              </div>
              <div style={{ ...kpiValueStyle, color: '#7c3aed' }}>
                {performance.total_impressions.toLocaleString()}
              </div>
              <div style={kpiSubtextStyle}>Organic appearances on Google SERPs</div>
            </div>

            {/* Average CTR */}
            <div style={{ ...kpiCardStyle, borderTop: '4px solid #059669' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={kpiLabelStyle}>Average CTR</span>
                <span style={{ fontSize: '20px' }}>🎯</span>
              </div>
              <div style={{ ...kpiValueStyle, color: '#059669' }}>
                {(performance.average_ctr * 100).toFixed(2)}%
              </div>
              <div style={kpiSubtextStyle}>Clicks per 100 search impressions</div>
            </div>

            {/* Average Position */}
            <div style={{ ...kpiCardStyle, borderTop: '4px solid #d97706' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={kpiLabelStyle}>Average Position</span>
                <span style={{ fontSize: '20px' }}>🏆</span>
              </div>
              <div style={{ ...kpiValueStyle, color: '#d97706' }}>
                #{performance.average_position.toFixed(1)}
              </div>
              <div style={kpiSubtextStyle}>Average organic rank across queries</div>
            </div>
          </div>

          {/* 2. Interactive Time-Series Performance Chart */}
          {chartData && (
            <div style={chartContainerCardStyle}>
              <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', gap: '12px' }}>
                <div>
                  <h4 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: 700, color: '#111827' }}>
                    Performance Trend Over Time
                  </h4>
                  <p style={{ margin: 0, fontSize: '13px', color: '#6b7280' }}>
                    Daily search metrics across selected date window.
                  </p>
                </div>

                {/* Metric View Toggles */}
                <div style={metricToggleGroupStyle}>
                  {(['clicks', 'impressions', 'ctr', 'position'] as MetricViewType[]).map((m) => (
                    <button
                      key={m}
                      id={`gsc-metric-toggle-${m}`}
                      onClick={() => setMetricView(m)}
                      style={metricView === m ? { ...activeMetricToggleBtnStyle, borderColor: metricColors[m].stroke, color: metricColors[m].stroke } : metricToggleBtnStyle}
                    >
                      <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: metricColors[m].stroke, marginRight: '6px' }}></span>
                      {metricColors[m].label}
                    </button>
                  ))}
                </div>
              </div>

              {/* SVG Visualization */}
              <div style={{ width: '100%', overflowX: 'auto', position: 'relative' }}>
                <svg
                  viewBox={`0 0 ${chartData.width} ${chartData.height}`}
                  style={{ width: '100%', height: 'auto', minWidth: '600px', display: 'block' }}
                >
                  {/* Background Grid Lines */}
                  {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => {
                    const y = chartData.padding.top + chartData.innerHeight * ratio;
                    return (
                      <g key={idx}>
                        <line
                          x1={chartData.padding.left}
                          y1={y}
                          x2={chartData.width - chartData.padding.right}
                          y2={y}
                          stroke="#e5e7eb"
                          strokeDasharray="4 4"
                        />
                      </g>
                    );
                  })}

                  {/* Gradient Fill */}
                  <defs>
                    <linearGradient id={`grad-${metricView}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={metricColors[metricView].stroke} stopOpacity="0.25" />
                      <stop offset="100%" stopColor={metricColors[metricView].stroke} stopOpacity="0.0" />
                    </linearGradient>
                  </defs>

                  {/* Area Fill */}
                  <path d={chartData.areaD} fill={`url(#grad-${metricView})`} />

                  {/* Trend Polyline */}
                  <path
                    d={chartData.pathD}
                    fill="none"
                    stroke={metricColors[metricView].stroke}
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />

                  {/* Interactive Points */}
                  {chartData.points.map((pt, idx) => {
                    const isHovered = hoveredPointIndex === idx;
                    return (
                      <g key={idx}>
                        <circle
                          cx={pt.x}
                          cy={pt.y}
                          r={isHovered ? 6 : 4}
                          fill="#ffffff"
                          stroke={metricColors[metricView].stroke}
                          strokeWidth={isHovered ? 3 : 2}
                          style={{ cursor: 'pointer', transition: 'all 0.15s ease' }}
                          onMouseEnter={() => setHoveredPointIndex(idx)}
                          onMouseLeave={() => setHoveredPointIndex(null)}
                        />
                        {/* X-axis date labels */}
                        {(idx === 0 || idx === Math.floor(chartData.points.length / 2) || idx === chartData.points.length - 1) && (
                          <text
                            x={pt.x}
                            y={chartData.height - 10}
                            textAnchor="middle"
                            fontSize="11"
                            fill="#6b7280"
                            fontWeight="500"
                          >
                            {pt.raw.date}
                          </text>
                        )}
                      </g>
                    );
                  })}
                </svg>

                {/* Hover Tooltip Overlay */}
                {hoveredPointIndex !== null && chartData.points[hoveredPointIndex] && (
                  <div
                    style={{
                      ...tooltipStyle,
                      left: `${(chartData.points[hoveredPointIndex].x / chartData.width) * 100}%`,
                      top: '20px',
                    }}
                  >
                    <div style={{ fontWeight: 700, fontSize: '12px', color: '#111827', marginBottom: '4px' }}>
                      {chartData.points[hoveredPointIndex].raw.date}
                    </div>
                    <div style={{ fontSize: '11px', color: '#374151', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                      <div>🖱️ Clicks: <strong>{chartData.points[hoveredPointIndex].raw.clicks}</strong></div>
                      <div>👁️ Impressions: <strong>{chartData.points[hoveredPointIndex].raw.impressions}</strong></div>
                      <div>🎯 CTR: <strong>{(chartData.points[hoveredPointIndex].raw.ctr * 100).toFixed(2)}%</strong></div>
                      <div>🏆 Position: <strong>#{chartData.points[hoveredPointIndex].raw.position.toFixed(1)}</strong></div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 3. Performance Breakdown Tabs */}
          <div style={tabsCardStyle}>
            {/* Tabs Navigation & Search Filter */}
            <div style={tabsHeaderStyle}>
              <div style={tabButtonContainerStyle}>
                <button
                  id="gsc-tab-queries"
                  onClick={() => setActiveTab('queries')}
                  style={activeTab === 'queries' ? activeTabBtnStyle : tabBtnStyle}
                >
                  🔍 Top Queries ({queries.length})
                </button>
                <button
                  id="gsc-tab-pages"
                  onClick={() => setActiveTab('pages')}
                  style={activeTab === 'pages' ? activeTabBtnStyle : tabBtnStyle}
                >
                  📄 Top Pages ({pages.length})
                </button>
                <button
                  id="gsc-tab-devices"
                  onClick={() => setActiveTab('devices')}
                  style={activeTab === 'devices' ? activeTabBtnStyle : tabBtnStyle}
                >
                  💻 Devices ({devices.length})
                </button>
                <button
                  id="gsc-tab-countries"
                  onClick={() => setActiveTab('countries')}
                  style={activeTab === 'countries' ? activeTabBtnStyle : tabBtnStyle}
                >
                  🌍 Countries ({countries.length})
                </button>
              </div>

              {/* Substring Search Filter Input for Queries/Pages */}
              {(activeTab === 'queries' || activeTab === 'pages') && (
                <div style={{ minWidth: '220px' }}>
                  <input
                    id="gsc-table-search-filter"
                    type="text"
                    placeholder={`Filter ${activeTab}...`}
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    style={searchInputStyle}
                  />
                </div>
              )}
            </div>

            {/* Tab Contents */}
            <div style={{ padding: '20px' }}>
              {/* TAB 1: QUERIES */}
              {activeTab === 'queries' && (
                <div style={{ overflowX: 'auto' }}>
                  {filteredQueries.length === 0 ? (
                    <div style={emptyTabStyle}>No search queries match your filter.</div>
                  ) : (
                    <table style={tableStyle}>
                      <thead>
                        <tr style={tableHeaderRowStyle}>
                          <th style={{ ...thStyle, textAlign: 'left' }}>Search Query</th>
                          <th style={{ ...thStyle, textAlign: 'right' }}>Clicks</th>
                          <th style={{ ...thStyle, textAlign: 'right' }}>Impressions</th>
                          <th style={{ ...thStyle, textAlign: 'right' }}>CTR</th>
                          <th style={{ ...thStyle, textAlign: 'right' }}>Avg Position</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredQueries.map((item, idx) => (
                          <tr key={idx} style={tableRowStyle}>
                            <td style={{ ...tdStyle, fontWeight: 600, color: '#111827' }}>
                              {item.query}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600, color: '#2563eb' }}>
                              {item.clicks.toLocaleString()}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right', color: '#4b5563' }}>
                              {item.impressions.toLocaleString()}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right', color: '#059669', fontWeight: 600 }}>
                              {(item.ctr * 100).toFixed(2)}%
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right' }}>
                              <span style={positionBadgeStyle}>
                                #{item.position.toFixed(1)}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}

              {/* TAB 2: PAGES */}
              {activeTab === 'pages' && (
                <div style={{ overflowX: 'auto' }}>
                  {filteredPages.length === 0 ? (
                    <div style={emptyTabStyle}>No landing pages match your filter.</div>
                  ) : (
                    <table style={tableStyle}>
                      <thead>
                        <tr style={tableHeaderRowStyle}>
                          <th style={{ ...thStyle, textAlign: 'left' }}>Landing Page URL</th>
                          <th style={{ ...thStyle, textAlign: 'right' }}>Clicks</th>
                          <th style={{ ...thStyle, textAlign: 'right' }}>Impressions</th>
                          <th style={{ ...thStyle, textAlign: 'right' }}>CTR</th>
                          <th style={{ ...thStyle, textAlign: 'right' }}>Avg Position</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredPages.map((item, idx) => (
                          <tr key={idx} style={tableRowStyle}>
                            <td style={{ ...tdStyle, color: '#1d4ed8', wordBreak: 'break-all', maxWidth: '400px' }}>
                              <a
                                href={item.page}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{ color: '#1d4ed8', textDecoration: 'none' }}
                                title={item.page}
                              >
                                {item.page} ↗
                              </a>
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600, color: '#2563eb' }}>
                              {item.clicks.toLocaleString()}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right', color: '#4b5563' }}>
                              {item.impressions.toLocaleString()}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right', color: '#059669', fontWeight: 600 }}>
                              {(item.ctr * 100).toFixed(2)}%
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right' }}>
                              <span style={positionBadgeStyle}>
                                #{item.position.toFixed(1)}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}

              {/* TAB 3: DEVICES */}
              {activeTab === 'devices' && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px' }}>
                  {devices.length === 0 ? (
                    <div style={emptyTabStyle}>No device data available.</div>
                  ) : (
                    devices.map((dev, idx) => {
                      const icon = dev.device.toLowerCase() === 'mobile' ? '📱' : dev.device.toLowerCase() === 'tablet' ? '📟' : '💻';
                      const totalClicks = performance.total_clicks || 1;
                      const clickShare = ((dev.clicks / totalClicks) * 100).toFixed(1);

                      return (
                        <div key={idx} style={breakdownCardStyle}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span style={{ fontSize: '24px' }}>{icon}</span>
                              <span style={{ fontWeight: 700, fontSize: '16px', color: '#111827', textTransform: 'capitalize' }}>
                                {dev.device}
                              </span>
                            </div>
                            <span style={{ fontSize: '13px', fontWeight: 700, color: '#2563eb', backgroundColor: '#dbeafe', padding: '3px 8px', borderRadius: '12px' }}>
                              {clickShare}% share
                            </span>
                          </div>

                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '13px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#4b5563' }}>
                              <span>Clicks:</span>
                              <strong style={{ color: '#111827' }}>{dev.clicks.toLocaleString()}</strong>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#4b5563' }}>
                              <span>Impressions:</span>
                              <strong style={{ color: '#111827' }}>{dev.impressions.toLocaleString()}</strong>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#4b5563' }}>
                              <span>CTR:</span>
                              <strong style={{ color: '#059669' }}>{(dev.ctr * 100).toFixed(2)}%</strong>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#4b5563' }}>
                              <span>Avg Position:</span>
                              <strong style={{ color: '#d97706' }}>#{dev.position.toFixed(1)}</strong>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* TAB 4: COUNTRIES */}
              {activeTab === 'countries' && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
                  {countries.length === 0 ? (
                    <div style={emptyTabStyle}>No country data available.</div>
                  ) : (
                    countries.map((c, idx) => {
                      const flag = c.country.toLowerCase() === 'eth' ? '🇪🇹' : c.country.toLowerCase() === 'usa' ? '🇺🇸' : '🌍';
                      return (
                        <div key={idx} style={breakdownCardStyle}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span style={{ fontSize: '22px' }}>{flag}</span>
                              <span style={{ fontWeight: 700, fontSize: '15px', color: '#111827', textTransform: 'uppercase' }}>
                                {c.country}
                              </span>
                            </div>
                            <span style={{ fontWeight: 700, color: '#2563eb', fontSize: '14px' }}>
                              {c.clicks.toLocaleString()} clicks
                            </span>
                          </div>

                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '12px', color: '#4b5563' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <span>Impressions:</span>
                              <strong>{c.impressions.toLocaleString()}</strong>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <span>CTR:</span>
                              <strong style={{ color: '#059669' }}>{(c.ctr * 100).toFixed(2)}%</strong>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <span>Position:</span>
                              <strong style={{ color: '#d97706' }}>#{c.position.toFixed(1)}</strong>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

// Styles
const panelCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '12px',
  border: '1px solid #e5e7eb',
  padding: '24px',
  marginTop: '32px',
  boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
};

const headerContainerStyle: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  gap: '16px',
  marginBottom: '20px',
  paddingBottom: '16px',
  borderBottom: '1px solid #f3f4f6',
};

const panelTitleStyle: React.CSSProperties = {
  margin: 0,
  fontSize: '20px',
  fontWeight: 700,
  color: '#111827',
};

const panelSubtitleStyle: React.CSSProperties = {
  margin: '4px 0 0 0',
  fontSize: '13px',
  color: '#6b7280',
};

const propertyBadgeStyle: React.CSSProperties = {
  display: 'inline-block',
  fontSize: '11px',
  fontWeight: 600,
  padding: '2px 8px',
  borderRadius: '6px',
  backgroundColor: '#eff6ff',
  color: '#2563eb',
  border: '1px solid #bfdbfe',
};

const presetGroupStyle: React.CSSProperties = {
  display: 'flex',
  backgroundColor: '#f3f4f6',
  borderRadius: '8px',
  padding: '3px',
};

const presetBtnStyle: React.CSSProperties = {
  padding: '6px 12px',
  fontSize: '12px',
  fontWeight: 600,
  color: '#4b5563',
  backgroundColor: 'transparent',
  border: 'none',
  borderRadius: '6px',
  cursor: 'pointer',
  transition: 'all 0.15s',
};

const activePresetBtnStyle: React.CSSProperties = {
  ...presetBtnStyle,
  color: '#1d4ed8',
  backgroundColor: '#ffffff',
  boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
};

const dateInputStyle: React.CSSProperties = {
  padding: '5px 8px',
  fontSize: '12px',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  outline: 'none',
};

const syncBtnStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
  padding: '8px 16px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '8px',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
  boxShadow: '0 1px 2px rgba(37,99,235,0.2)',
  transition: 'background-color 0.15s',
};

const syncingBtnStyle: React.CSSProperties = {
  ...syncBtnStyle,
  backgroundColor: '#93c5fd',
  cursor: 'not-allowed',
};

const primaryActionBtnStyle: React.CSSProperties = {
  padding: '10px 20px',
  backgroundColor: '#2563eb',
  color: '#ffffff',
  border: 'none',
  borderRadius: '8px',
  fontSize: '14px',
  fontWeight: 600,
  cursor: 'pointer',
};

const syncSuccessBannerStyle: React.CSSProperties = {
  backgroundColor: '#ecfdf5',
  border: '1px solid #a7f3d0',
  borderRadius: '8px',
  padding: '12px 16px',
  marginBottom: '20px',
};

const dismissBtnStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: '#059669',
  fontSize: '16px',
  cursor: 'pointer',
  padding: '4px',
};

const errorBannerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '12px',
  backgroundColor: '#fef2f2',
  border: '1px solid #fecaca',
  borderRadius: '8px',
  padding: '12px 16px',
  marginBottom: '20px',
};

const retryBtnStyle: React.CSSProperties = {
  padding: '6px 12px',
  backgroundColor: '#ef4444',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
};

const loadingStateStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '48px 0',
};

const spinnerStyle: React.CSSProperties = {
  width: '32px',
  height: '32px',
  border: '3px solid #e5e7eb',
  borderTop: '3px solid #2563eb',
  borderRadius: '50%',
  animation: 'spin 0.8s linear infinite',
};

const emptyStateCardStyle: React.CSSProperties = {
  textAlign: 'center',
  padding: '40px 20px',
  backgroundColor: '#f9fafb',
  borderRadius: '10px',
  border: '1px dashed #d1d5db',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
};

const kpiGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
  gap: '16px',
};

const kpiCardStyle: React.CSSProperties = {
  backgroundColor: '#f9fafb',
  borderRadius: '10px',
  padding: '16px',
  border: '1px solid #e5e7eb',
};

const kpiLabelStyle: React.CSSProperties = {
  fontSize: '13px',
  fontWeight: 600,
  color: '#4b5563',
};

const kpiValueStyle: React.CSSProperties = {
  fontSize: '26px',
  fontWeight: 800,
  margin: '8px 0 4px 0',
  letterSpacing: '-0.5px',
};

const kpiSubtextStyle: React.CSSProperties = {
  fontSize: '12px',
  color: '#6b7280',
};

const chartContainerCardStyle: React.CSSProperties = {
  backgroundColor: '#f9fafb',
  borderRadius: '10px',
  padding: '20px',
  border: '1px solid #e5e7eb',
};

const metricToggleGroupStyle: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: '6px',
};

const metricToggleBtnStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  padding: '5px 10px',
  fontSize: '12px',
  fontWeight: 600,
  color: '#4b5563',
  backgroundColor: '#ffffff',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  cursor: 'pointer',
};

const activeMetricToggleBtnStyle: React.CSSProperties = {
  ...metricToggleBtnStyle,
  backgroundColor: '#ffffff',
  boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
};

const tooltipStyle: React.CSSProperties = {
  position: 'absolute',
  transform: 'translateX(-50%)',
  backgroundColor: '#ffffff',
  border: '1px solid #d1d5db',
  borderRadius: '8px',
  padding: '8px 12px',
  boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
  pointerEvents: 'none',
  zIndex: 10,
};

const tabsCardStyle: React.CSSProperties = {
  backgroundColor: '#ffffff',
  borderRadius: '10px',
  border: '1px solid #e5e7eb',
  overflow: 'hidden',
};

const tabsHeaderStyle: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: '12px',
  padding: '12px 20px',
  borderBottom: '1px solid #e5e7eb',
  backgroundColor: '#f9fafb',
};

const tabButtonContainerStyle: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: '8px',
};

const tabBtnStyle: React.CSSProperties = {
  padding: '8px 14px',
  fontSize: '13px',
  fontWeight: 600,
  color: '#6b7280',
  backgroundColor: 'transparent',
  border: 'none',
  borderRadius: '6px',
  cursor: 'pointer',
};

const activeTabBtnStyle: React.CSSProperties = {
  ...tabBtnStyle,
  color: '#1d4ed8',
  backgroundColor: '#eff6ff',
};

const searchInputStyle: React.CSSProperties = {
  width: '100%',
  padding: '7px 12px',
  fontSize: '13px',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  outline: 'none',
};

const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: '13px',
};

const tableHeaderRowStyle: React.CSSProperties = {
  borderBottom: '2px solid #e5e7eb',
};

const thStyle: React.CSSProperties = {
  padding: '10px 12px',
  fontWeight: 600,
  color: '#4b5563',
  fontSize: '12px',
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
};

const tableRowStyle: React.CSSProperties = {
  borderBottom: '1px solid #f3f4f6',
};

const tdStyle: React.CSSProperties = {
  padding: '12px',
};

const positionBadgeStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '3px 8px',
  borderRadius: '6px',
  fontSize: '12px',
  fontWeight: 700,
  backgroundColor: '#fef3c7',
  color: '#92400e',
};

const breakdownCardStyle: React.CSSProperties = {
  backgroundColor: '#f9fafb',
  border: '1px solid #e5e7eb',
  borderRadius: '8px',
  padding: '16px',
};

const emptyTabStyle: React.CSSProperties = {
  padding: '32px 0',
  textAlign: 'center',
  color: '#6b7280',
  fontSize: '14px',
};

const spinAnimation: React.CSSProperties = {
  display: 'inline-block',
  animation: 'spin 1s linear infinite',
};
