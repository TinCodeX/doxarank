import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { Project } from '../types/project';
import type { SearchAnalyticsData } from '../types/searchAnalytics';
import { getSearchAnalyticsByProject } from '../api/searchAnalytics';

interface SearchAnalyticsPanelProps {
  project: Project;
}

type DateRangePreset = '7d' | '28d' | '90d' | 'all' | 'custom';
type ActiveTableTab = 'queries' | 'pages' | 'devices' | 'countries';

function formatDateISO(d: Date): string {
  return d.toISOString().split('T')[0];
}

export const SearchAnalyticsPanel: React.FC<SearchAnalyticsPanelProps> = ({ project }) => {
  const [analytics, setAnalytics] = useState<SearchAnalyticsData[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [datePreset, setDatePreset] = useState<DateRangePreset>('28d');
  const [customStartDate, setCustomStartDate] = useState<string>('');
  const [customEndDate, setCustomEndDate] = useState<string>('');
  const [deviceFilter, setDeviceFilter] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [activeTab, setActiveTab] = useState<ActiveTableTab>('queries');

  // Hovered chart point
  const [hoveredPointIndex, setHoveredPointIndex] = useState<number | null>(null);

  // Calculate start & end date strings based on preset
  const dateRange = useMemo<{ startDate?: string; endDate?: string }>(() => {
    const today = new Date();
    if (datePreset === '7d') {
      const start = new Date();
      start.setDate(today.getDate() - 7);
      return { startDate: formatDateISO(start), endDate: formatDateISO(today) };
    }
    if (datePreset === '28d') {
      const start = new Date();
      start.setDate(today.getDate() - 28);
      return { startDate: formatDateISO(start), endDate: formatDateISO(today) };
    }
    if (datePreset === '90d') {
      const start = new Date();
      start.setDate(today.getDate() - 90);
      return { startDate: formatDateISO(start), endDate: formatDateISO(today) };
    }
    if (datePreset === 'custom') {
      return {
        startDate: customStartDate || undefined,
        endDate: customEndDate || undefined,
      };
    }
    return {}; // 'all'
  }, [datePreset, customStartDate, customEndDate]);

  // Fetch search analytics data strictly scoped to project
  const fetchAnalytics = useCallback(async (projectId: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const filters: {
        start_date?: string;
        end_date?: string;
        device?: string;
      } = {};

      if (dateRange.startDate) filters.start_date = dateRange.startDate;
      if (dateRange.endDate) filters.end_date = dateRange.endDate;
      if (deviceFilter && deviceFilter !== 'all') filters.device = deviceFilter;

      const data = await getSearchAnalyticsByProject(projectId, filters);
      setAnalytics(data);
    } catch (err: any) {
      setError(err?.data?.detail || 'Failed to load Search Analytics data for this project.');
    } finally {
      setIsLoading(false);
    }
  }, [dateRange, deviceFilter]);

  // Project Isolation effect: clear old data immediately on project switch
  useEffect(() => {
    if (project?.id) {
      setAnalytics([]);
      setHoveredPointIndex(null);
      fetchAnalytics(project.id);
    } else {
      setAnalytics([]);
    }
  }, [project?.id, fetchAnalytics]);

  // Aggregate Metrics Calculations
  const metrics = useMemo(() => {
    if (analytics.length === 0) {
      return {
        totalClicks: 0,
        totalImpressions: 0,
        averageCtr: 0,
        averagePosition: 0,
        uniqueQueries: 0,
        uniquePages: 0,
      };
    }

    let totalClicks = 0;
    let totalImpressions = 0;
    let positionSum = 0;
    let positionCount = 0;
    const queriesSet = new Set<string>();
    const pagesSet = new Set<string>();

    analytics.forEach((item) => {
      totalClicks += Number(item.clicks) || 0;
      totalImpressions += Number(item.impressions) || 0;
      const pos = Number(item.position);
      if (!isNaN(pos) && pos > 0) {
        positionSum += pos;
        positionCount += 1;
      }
      if (item.query) queriesSet.add(item.query.toLowerCase().trim());
      if (item.page) pagesSet.add(item.page.trim());
    });

    const averageCtr = totalImpressions > 0 ? (totalClicks / totalImpressions) * 100 : 0;
    const averagePosition = positionCount > 0 ? positionSum / positionCount : 0;

    return {
      totalClicks,
      totalImpressions,
      averageCtr,
      averagePosition,
      uniqueQueries: queriesSet.size,
      uniquePages: pagesSet.size,
    };
  }, [analytics]);

  // Daily Chart Trend Data
  const dailyChartData = useMemo(() => {
    if (analytics.length === 0) return [];

    const dateMap = new Map<string, { date: string; clicks: number; impressions: number; totalPos: number; countPos: number }>();

    analytics.forEach((item) => {
      const d = item.date;
      const existing = dateMap.get(d) || { date: d, clicks: 0, impressions: 0, totalPos: 0, countPos: 0 };
      existing.clicks += Number(item.clicks) || 0;
      existing.impressions += Number(item.impressions) || 0;
      const pos = Number(item.position);
      if (!isNaN(pos) && pos > 0) {
        existing.totalPos += pos;
        existing.countPos += 1;
      }
      dateMap.set(d, existing);
    });

    const sorted = Array.from(dateMap.values()).sort((a, b) => a.date.localeCompare(b.date));

    return sorted.map((entry) => ({
      date: entry.date,
      clicks: entry.clicks,
      impressions: entry.impressions,
      ctr: entry.impressions > 0 ? ((entry.clicks / entry.impressions) * 100).toFixed(2) : '0.00',
      avgPosition: entry.countPos > 0 ? (entry.totalPos / entry.countPos).toFixed(1) : '0.0',
    }));
  }, [analytics]);

  // Aggregated Queries Table Data
  const queryRows = useMemo(() => {
    const map = new Map<string, { query: string; clicks: number; impressions: number; totalPos: number; count: number }>();

    analytics.forEach((item) => {
      const q = item.query || '(not set)';
      const existing = map.get(q) || { query: q, clicks: 0, impressions: 0, totalPos: 0, count: 0 };
      existing.clicks += Number(item.clicks) || 0;
      existing.impressions += Number(item.impressions) || 0;
      const pos = Number(item.position);
      if (!isNaN(pos) && pos > 0) {
        existing.totalPos += pos;
        existing.count += 1;
      }
      map.set(q, existing);
    });

    let list = Array.from(map.values()).map((q) => ({
      query: q.query,
      clicks: q.clicks,
      impressions: q.impressions,
      ctr: q.impressions > 0 ? ((q.clicks / q.impressions) * 100).toFixed(2) : '0.00',
      position: q.count > 0 ? (q.totalPos / q.count).toFixed(1) : '0.0',
    }));

    if (searchTerm.trim()) {
      const lower = searchTerm.toLowerCase().trim();
      list = list.filter((item) => item.query.toLowerCase().includes(lower));
    }

    return list.sort((a, b) => b.clicks - a.clicks || b.impressions - a.impressions);
  }, [analytics, searchTerm]);

  // Aggregated Pages Table Data
  const pageRows = useMemo(() => {
    const map = new Map<string, { page: string; clicks: number; impressions: number; totalPos: number; count: number }>();

    analytics.forEach((item) => {
      const p = item.page || '(not set)';
      const existing = map.get(p) || { page: p, clicks: 0, impressions: 0, totalPos: 0, count: 0 };
      existing.clicks += Number(item.clicks) || 0;
      existing.impressions += Number(item.impressions) || 0;
      const pos = Number(item.position);
      if (!isNaN(pos) && pos > 0) {
        existing.totalPos += pos;
        existing.count += 1;
      }
      map.set(p, existing);
    });

    let list = Array.from(map.values()).map((p) => ({
      page: p.page,
      clicks: p.clicks,
      impressions: p.impressions,
      ctr: p.impressions > 0 ? ((p.clicks / p.impressions) * 100).toFixed(2) : '0.00',
      position: p.count > 0 ? (p.totalPos / p.count).toFixed(1) : '0.0',
    }));

    if (searchTerm.trim()) {
      const lower = searchTerm.toLowerCase().trim();
      list = list.filter((item) => item.page.toLowerCase().includes(lower));
    }

    return list.sort((a, b) => b.clicks - a.clicks || b.impressions - a.impressions);
  }, [analytics, searchTerm]);

  // Aggregated Devices Data
  const deviceRows = useMemo(() => {
    const map = new Map<string, { device: string; clicks: number; impressions: number }>();

    analytics.forEach((item) => {
      const d = (item.device || 'desktop').toLowerCase();
      const existing = map.get(d) || { device: d, clicks: 0, impressions: 0 };
      existing.clicks += Number(item.clicks) || 0;
      existing.impressions += Number(item.impressions) || 0;
      map.set(d, existing);
    });

    return Array.from(map.values()).map((d) => ({
      device: d.device,
      clicks: d.clicks,
      impressions: d.impressions,
      ctr: d.impressions > 0 ? ((d.clicks / d.impressions) * 100).toFixed(2) : '0.00',
    })).sort((a, b) => b.clicks - a.clicks);
  }, [analytics]);

  // Aggregated Countries Data
  const countryRows = useMemo(() => {
    const map = new Map<string, { country: string; clicks: number; impressions: number }>();

    analytics.forEach((item) => {
      const c = (item.country || 'ET').toUpperCase();
      const existing = map.get(c) || { country: c, clicks: 0, impressions: 0 };
      existing.clicks += Number(item.clicks) || 0;
      existing.impressions += Number(item.impressions) || 0;
      map.set(c, existing);
    });

    return Array.from(map.values()).map((c) => ({
      country: c.country,
      clicks: c.clicks,
      impressions: c.impressions,
      ctr: c.impressions > 0 ? ((c.clicks / c.impressions) * 100).toFixed(2) : '0.00',
    })).sort((a, b) => b.clicks - a.clicks);
  }, [analytics]);

  // SVG Chart Dimensions & Helpers
  const chartWidth = 900;
  const chartHeight = 220;
  const paddingX = 40;
  const paddingY = 30;

  const maxClicks = Math.max(...dailyChartData.map((d) => d.clicks), 5);
  const maxImpressions = Math.max(...dailyChartData.map((d) => d.impressions), 20);

  const getCoordinates = (index: number, total: number, value: number, max: number) => {
    const x = total > 1 ? paddingX + (index / (total - 1)) * (chartWidth - paddingX * 2) : chartWidth / 2;
    const y = chartHeight - paddingY - (value / max) * (chartHeight - paddingY * 2);
    return { x, y };
  };

  return (
    <section
      id="search-analytics-section"
      style={{
        marginTop: '40px',
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #e2e8f0',
        padding: '24px',
        boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.05)',
      }}
    >
      {/* Header & Controls */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '20px',
          borderBottom: '1px solid #f1f5f9',
          paddingBottom: '16px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                fontSize: '11px',
                textTransform: 'uppercase',
                fontWeight: 700,
                color: '#2563eb',
                backgroundColor: '#eff6ff',
                padding: '2px 8px',
                borderRadius: '4px',
              }}
            >
              Google Search Console
            </span>
            <span style={{ fontSize: '13px', color: '#6b7280' }}>
              Project: <strong>{project.name}</strong>
            </span>
          </div>
          <h3 style={{ margin: '6px 0 2px 0', fontSize: '22px', fontWeight: 700, color: '#0f172a' }}>
            Search Analytics Performance
          </h3>
          <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
            Organic search performance metrics across queries, landing pages, devices, and countries.
          </p>
        </div>

        {/* Date Filter Bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', backgroundColor: '#f1f5f9', borderRadius: '8px', padding: '3px' }}>
            {(['7d', '28d', '90d', 'all', 'custom'] as DateRangePreset[]).map((preset) => (
              <button
                key={preset}
                id={`date-preset-${preset}`}
                onClick={() => setDatePreset(preset)}
                style={{
                  padding: '5px 12px',
                  fontSize: '12px',
                  fontWeight: datePreset === preset ? 700 : 500,
                  color: datePreset === preset ? '#1e40af' : '#475569',
                  backgroundColor: datePreset === preset ? '#ffffff' : 'transparent',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  boxShadow: datePreset === preset ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
                  transition: 'all 0.15s ease',
                }}
              >
                {preset === '7d'
                  ? '7 Days'
                  : preset === '28d'
                  ? '28 Days'
                  : preset === '90d'
                  ? '3 Months'
                  : preset === 'all'
                  ? 'All Time'
                  : 'Custom'}
              </button>
            ))}
          </div>

          {/* Device Filter */}
          <select
            id="analytics-device-filter"
            value={deviceFilter}
            onChange={(e) => setDeviceFilter(e.target.value)}
            style={{
              padding: '6px 12px',
              fontSize: '12px',
              fontWeight: 500,
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              color: '#334155',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            <option value="all">All Devices</option>
            <option value="desktop">💻 Desktop</option>
            <option value="mobile">📱 Mobile</option>
            <option value="tablet">📟 Tablet</option>
          </select>

          {/* Refresh Button */}
          <button
            id="refresh-analytics-button"
            onClick={() => fetchAnalytics(project.id)}
            disabled={isLoading}
            style={{
              padding: '6px 12px',
              fontSize: '12px',
              fontWeight: 600,
              color: '#334155',
              backgroundColor: '#f8fafc',
              border: '1px solid #cbd5e1',
              borderRadius: '8px',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* Custom Date Pickers (Shown only when 'custom' is active) */}
      {datePreset === 'custom' && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            marginBottom: '16px',
            padding: '12px 16px',
            backgroundColor: '#f8fafc',
            borderRadius: '8px',
            border: '1px solid #e2e8f0',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>From:</label>
            <input
              id="analytics-start-date"
              type="date"
              value={customStartDate}
              onChange={(e) => setCustomStartDate(e.target.value)}
              style={{
                padding: '4px 8px',
                fontSize: '12px',
                border: '1px solid #cbd5e1',
                borderRadius: '6px',
                outline: 'none',
              }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>To:</label>
            <input
              id="analytics-end-date"
              type="date"
              value={customEndDate}
              onChange={(e) => setCustomEndDate(e.target.value)}
              style={{
                padding: '4px 8px',
                fontSize: '12px',
                border: '1px solid #cbd5e1',
                borderRadius: '6px',
                outline: 'none',
              }}
            />
          </div>
          <button
            id="apply-custom-date-button"
            onClick={() => fetchAnalytics(project.id)}
            style={{
              padding: '4px 12px',
              fontSize: '12px',
              fontWeight: 600,
              backgroundColor: '#2563eb',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            Apply Range
          </button>
        </div>
      )}

      {/* Error Alert */}
      {error && (
        <div
          style={{
            backgroundColor: '#fef2f2',
            color: '#b91c1c',
            border: '1px solid #fecaca',
            borderRadius: '8px',
            padding: '12px 16px',
            fontSize: '14px',
            marginBottom: '16px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>⚠️ {error}</span>
          <button
            onClick={() => fetchAnalytics(project.id)}
            style={{
              background: 'none',
              border: 'none',
              color: '#b91c1c',
              fontWeight: 700,
              textDecoration: 'underline',
              cursor: 'pointer',
            }}
          >
            Try Again
          </button>
        </div>
      )}

      {/* Loading State */}
      {isLoading ? (
        <div
          style={{
            padding: '60px 20px',
            textAlign: 'center',
            backgroundColor: '#f8fafc',
            borderRadius: '10px',
            border: '1px solid #e2e8f0',
          }}
        >
          <div style={{ fontSize: '32px', marginBottom: '12px', animation: 'spin 1s linear infinite' }}>⏳</div>
          <p style={{ color: '#475569', fontSize: '15px', fontWeight: 600, margin: '0 0 4px 0' }}>
            Loading Google Search Console Analytics...
          </p>
          <p style={{ color: '#94a3b8', fontSize: '13px', margin: 0 }}>
            Fetching performance metrics for {project.name}
          </p>
        </div>
      ) : analytics.length === 0 ? (
        /* Empty State */
        <div
          id="search-analytics-empty-state"
          style={{
            padding: '48px 24px',
            textAlign: 'center',
            backgroundColor: '#f8fafc',
            borderRadius: '12px',
            border: '1px dashed #cbd5e1',
          }}
        >
          <div style={{ fontSize: '40px', marginBottom: '12px' }}>📈</div>
          <h4 style={{ margin: '0 0 6px 0', fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
            No Search Analytics data yet
          </h4>
          <p style={{ margin: '0 auto 16px auto', fontSize: '14px', color: '#64748b', maxWidth: '480px' }}>
            Search Console analytics data for <strong>{project.name}</strong> will populate automatically once your Google Search Console property is synchronized.
          </p>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              backgroundColor: '#eff6ff',
              color: '#1d4ed8',
              borderRadius: '20px',
              fontSize: '12px',
              fontWeight: 600,
            }}
          >
            <span>💡 Tip: Ensure Search Console connection is active above.</span>
          </div>
        </div>
      ) : (
        /* Data Presentation */
        <div>
          {/* SECTION A: Overview Metric Cards */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '16px',
              marginBottom: '24px',
            }}
          >
            {/* Card 1: Total Clicks */}
            <div
              id="analytics-card-clicks"
              style={{
                backgroundColor: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '10px',
                padding: '16px 20px',
                borderLeft: '4px solid #2563eb',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
                  Total Clicks
                </span>
                <span style={{ fontSize: '16px' }}>👆</span>
              </div>
              <div style={{ fontSize: '26px', fontWeight: 800, color: '#1e3a8a' }}>
                {metrics.totalClicks.toLocaleString()}
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                Across {metrics.uniqueQueries} search queries
              </div>
            </div>

            {/* Card 2: Total Impressions */}
            <div
              id="analytics-card-impressions"
              style={{
                backgroundColor: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '10px',
                padding: '16px 20px',
                borderLeft: '4px solid #7c3aed',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
                  Total Impressions
                </span>
                <span style={{ fontSize: '16px' }}>👁️</span>
              </div>
              <div style={{ fontSize: '26px', fontWeight: 800, color: '#4c1d95' }}>
                {metrics.totalImpressions.toLocaleString()}
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                Organic SERP views
              </div>
            </div>

            {/* Card 3: Average CTR */}
            <div
              id="analytics-card-ctr"
              style={{
                backgroundColor: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '10px',
                padding: '16px 20px',
                borderLeft: '4px solid #059669',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
                  Average CTR
                </span>
                <span style={{ fontSize: '16px' }}>🎯</span>
              </div>
              <div style={{ fontSize: '26px', fontWeight: 800, color: '#065f46' }}>
                {metrics.averageCtr.toFixed(2)}%
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                Clicks ÷ Impressions
              </div>
            </div>

            {/* Card 4: Average Position */}
            <div
              id="analytics-card-position"
              style={{
                backgroundColor: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '10px',
                padding: '16px 20px',
                borderLeft: '4px solid #d97706',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
                  Average Position
                </span>
                <span style={{ fontSize: '16px' }}>🏆</span>
              </div>
              <div style={{ fontSize: '26px', fontWeight: 800, color: '#92400e' }}>
                #{metrics.averagePosition.toFixed(1)}
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                In organic search results
              </div>
            </div>
          </div>

          {/* SECTION B: Clicks & Impressions Trend Chart */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid #e2e8f0',
              borderRadius: '10px',
              padding: '20px',
              marginBottom: '24px',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px',
                flexWrap: 'wrap',
                gap: '8px',
              }}
            >
              <div>
                <h4 style={{ margin: '0 0 2px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                  Performance Trend Over Time
                </h4>
                <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>
                  Daily clicks (blue) vs impressions (purple) from Google Search
                </p>
              </div>

              {/* Legend */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: '12px', height: '12px', borderRadius: '3px', backgroundColor: '#2563eb' }} />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>Clicks</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: '12px', height: '12px', borderRadius: '3px', backgroundColor: '#8b5cf6' }} />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>Impressions</span>
                </div>
              </div>
            </div>

            {/* SVG Trend Chart */}
            {dailyChartData.length > 0 && (
              <div style={{ width: '100%', overflowX: 'auto' }}>
                <svg
                  viewBox={`0 0 ${chartWidth} ${chartHeight}`}
                  style={{ width: '100%', height: 'auto', minWidth: '600px', display: 'block' }}
                >
                  {/* Grid Lines */}
                  {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => {
                    const y = chartHeight - paddingY - ratio * (chartHeight - paddingY * 2);
                    return (
                      <line
                        key={i}
                        x1={paddingX}
                        y1={y}
                        x2={chartWidth - paddingX}
                        y2={y}
                        stroke="#f1f5f9"
                        strokeWidth="1"
                      />
                    );
                  })}

                  {/* Clicks Area & Line */}
                  <polyline
                    fill="none"
                    stroke="#2563eb"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    points={dailyChartData
                      .map((d, i) => {
                        const { x, y } = getCoordinates(i, dailyChartData.length, d.clicks, maxClicks);
                        return `${x},${y}`;
                      })
                      .join(' ')}
                  />

                  {/* Impressions Area & Line */}
                  <polyline
                    fill="none"
                    stroke="#8b5cf6"
                    strokeWidth="2"
                    strokeDasharray="4 4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    points={dailyChartData
                      .map((d, i) => {
                        const { x, y } = getCoordinates(i, dailyChartData.length, d.impressions, maxImpressions);
                        return `${x},${y}`;
                      })
                      .join(' ')}
                  />

                  {/* Data Points */}
                  {dailyChartData.map((d, i) => {
                    const clickCoord = getCoordinates(i, dailyChartData.length, d.clicks, maxClicks);
                    const isHovered = hoveredPointIndex === i;
                    return (
                      <g key={i}>
                        {/* Click Circle */}
                        <circle
                          cx={clickCoord.x}
                          cy={clickCoord.y}
                          r={isHovered ? 6 : 4}
                          fill="#2563eb"
                          stroke="#ffffff"
                          strokeWidth="2"
                          style={{ cursor: 'pointer', transition: 'all 0.15s ease' }}
                          onMouseEnter={() => setHoveredPointIndex(i)}
                          onMouseLeave={() => setHoveredPointIndex(null)}
                        />

                        {/* Date Label on X Axis */}
                        {i % Math.ceil(dailyChartData.length / 7) === 0 && (
                          <text
                            x={clickCoord.x}
                            y={chartHeight - 8}
                            textAnchor="middle"
                            fontSize="11"
                            fill="#64748b"
                            fontWeight="500"
                          >
                            {d.date.slice(5)}
                          </text>
                        )}
                      </g>
                    );
                  })}
                </svg>
              </div>
            )}

            {/* Hovered Point Tooltip */}
            {hoveredPointIndex !== null && dailyChartData[hoveredPointIndex] && (
              <div
                style={{
                  marginTop: '12px',
                  padding: '8px 14px',
                  backgroundColor: '#0f172a',
                  color: '#f8fafc',
                  borderRadius: '8px',
                  fontSize: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '12px',
                }}
              >
                <span>📅 Date: <strong>{dailyChartData[hoveredPointIndex].date}</strong></span>
                <span>👆 Clicks: <strong>{dailyChartData[hoveredPointIndex].clicks}</strong></span>
                <span>👁️ Impressions: <strong>{dailyChartData[hoveredPointIndex].impressions}</strong></span>
                <span>🎯 CTR: <strong>{dailyChartData[hoveredPointIndex].ctr}%</strong></span>
                <span>🏆 Avg Pos: <strong>#{dailyChartData[hoveredPointIndex].avgPosition}</strong></span>
              </div>
            )}
          </div>

          {/* SECTION C: Detailed Breakdown Tabs & Table */}
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid #e2e8f0',
              borderRadius: '10px',
              overflow: 'hidden',
            }}
          >
            {/* Tab Navigation & Search Bar */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                borderBottom: '1px solid #e2e8f0',
                padding: '12px 16px',
                backgroundColor: '#f8fafc',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              {/* Tabs */}
              <div style={{ display: 'flex', gap: '4px' }}>
                <button
                  id="tab-queries"
                  onClick={() => { setActiveTab('queries'); setSearchTerm(''); }}
                  style={{
                    padding: '6px 14px',
                    fontSize: '13px',
                    fontWeight: activeTab === 'queries' ? 700 : 500,
                    color: activeTab === 'queries' ? '#2563eb' : '#475569',
                    backgroundColor: activeTab === 'queries' ? '#ffffff' : 'transparent',
                    border: activeTab === 'queries' ? '1px solid #cbd5e1' : '1px solid transparent',
                    borderRadius: '6px',
                    cursor: 'pointer',
                  }}
                >
                  🔍 Queries ({queryRows.length})
                </button>
                <button
                  id="tab-pages"
                  onClick={() => { setActiveTab('pages'); setSearchTerm(''); }}
                  style={{
                    padding: '6px 14px',
                    fontSize: '13px',
                    fontWeight: activeTab === 'pages' ? 700 : 500,
                    color: activeTab === 'pages' ? '#2563eb' : '#475569',
                    backgroundColor: activeTab === 'pages' ? '#ffffff' : 'transparent',
                    border: activeTab === 'pages' ? '1px solid #cbd5e1' : '1px solid transparent',
                    borderRadius: '6px',
                    cursor: 'pointer',
                  }}
                >
                  📄 Pages ({pageRows.length})
                </button>
                <button
                  id="tab-devices"
                  onClick={() => setActiveTab('devices')}
                  style={{
                    padding: '6px 14px',
                    fontSize: '13px',
                    fontWeight: activeTab === 'devices' ? 700 : 500,
                    color: activeTab === 'devices' ? '#2563eb' : '#475569',
                    backgroundColor: activeTab === 'devices' ? '#ffffff' : 'transparent',
                    border: activeTab === 'devices' ? '1px solid #cbd5e1' : '1px solid transparent',
                    borderRadius: '6px',
                    cursor: 'pointer',
                  }}
                >
                  💻 Devices ({deviceRows.length})
                </button>
                <button
                  id="tab-countries"
                  onClick={() => setActiveTab('countries')}
                  style={{
                    padding: '6px 14px',
                    fontSize: '13px',
                    fontWeight: activeTab === 'countries' ? 700 : 500,
                    color: activeTab === 'countries' ? '#2563eb' : '#475569',
                    backgroundColor: activeTab === 'countries' ? '#ffffff' : 'transparent',
                    border: activeTab === 'countries' ? '1px solid #cbd5e1' : '1px solid transparent',
                    borderRadius: '6px',
                    cursor: 'pointer',
                  }}
                >
                  🌍 Countries ({countryRows.length})
                </button>
              </div>

              {/* Table Search Input (for queries / pages) */}
              {(activeTab === 'queries' || activeTab === 'pages') && (
                <div style={{ position: 'relative' }}>
                  <input
                    id="analytics-search-input"
                    type="text"
                    placeholder={`Filter ${activeTab}...`}
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    style={{
                      padding: '6px 12px 6px 28px',
                      fontSize: '12px',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      outline: 'none',
                      width: '200px',
                    }}
                  />
                  <span style={{ position: 'absolute', left: '8px', top: '7px', fontSize: '12px', color: '#94a3b8' }}>
                    🔍
                  </span>
                </div>
              )}
            </div>

            {/* TAB 1: QUERIES TABLE */}
            {activeTab === 'queries' && (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>
                      <th style={thStyle}>Search Query</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>Clicks</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>Impressions</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>CTR</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>Avg Position</th>
                    </tr>
                  </thead>
                  <tbody>
                    {queryRows.length === 0 ? (
                      <tr>
                        <td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: '#94a3b8' }}>
                          No queries matching filter
                        </td>
                      </tr>
                    ) : (
                      queryRows.map((q, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={tdStyle}>
                            <span style={{ fontWeight: 600, color: '#0f172a' }}>{q.query}</span>
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#2563eb' }}>
                            {q.clicks.toLocaleString()}
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right', color: '#475569' }}>
                            {q.impressions.toLocaleString()}
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right', color: '#059669', fontWeight: 600 }}>
                            {q.ctr}%
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right' }}>
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                padding: '2px 8px',
                                borderRadius: '6px',
                                fontWeight: 700,
                                fontSize: '12px',
                                backgroundColor: Number(q.position) <= 3 ? '#fef3c7' : Number(q.position) <= 10 ? '#dbeafe' : '#f1f5f9',
                                color: Number(q.position) <= 3 ? '#92400e' : Number(q.position) <= 10 ? '#1e40af' : '#475569',
                              }}
                            >
                              #{q.position}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* TAB 2: TOP PAGES TABLE */}
            {activeTab === 'pages' && (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>
                      <th style={thStyle}>Page URL</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>Clicks</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>Impressions</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>CTR</th>
                      <th style={{ ...thStyle, textAlign: 'right' }}>Avg Position</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageRows.length === 0 ? (
                      <tr>
                        <td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: '#94a3b8' }}>
                          No pages matching filter
                        </td>
                      </tr>
                    ) : (
                      pageRows.map((p, idx) => (
                        <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={tdStyle}>
                            <a
                              href={p.page.startsWith('http') ? p.page : `https://${p.page}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{
                                color: '#2563eb',
                                textDecoration: 'none',
                                fontWeight: 500,
                                display: 'inline-block',
                                maxWidth: '380px',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              }}
                              title={p.page}
                            >
                              🔗 {p.page}
                            </a>
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: '#2563eb' }}>
                            {p.clicks.toLocaleString()}
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right', color: '#475569' }}>
                            {p.impressions.toLocaleString()}
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right', color: '#059669', fontWeight: 600 }}>
                            {p.ctr}%
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right' }}>
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                padding: '2px 8px',
                                borderRadius: '6px',
                                fontWeight: 700,
                                fontSize: '12px',
                                backgroundColor: Number(p.position) <= 3 ? '#fef3c7' : Number(p.position) <= 10 ? '#dbeafe' : '#f1f5f9',
                                color: Number(p.position) <= 3 ? '#92400e' : Number(p.position) <= 10 ? '#1e40af' : '#475569',
                              }}
                            >
                              #{p.position}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* TAB 3: DEVICES BREAKDOWN */}
            {activeTab === 'devices' && (
              <div style={{ padding: '20px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
                  {deviceRows.map((d, idx) => {
                    const icon = d.device.includes('mobile') ? '📱' : d.device.includes('tablet') ? '📟' : '💻';
                    const percentage = metrics.totalClicks > 0 ? ((d.clicks / metrics.totalClicks) * 100).toFixed(1) : '0';
                    return (
                      <div
                        key={idx}
                        style={{
                          backgroundColor: '#f8fafc',
                          border: '1px solid #e2e8f0',
                          borderRadius: '8px',
                          padding: '16px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                          <span style={{ fontSize: '20px' }}>{icon}</span>
                          <h5 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a', textTransform: 'capitalize' }}>
                            {d.device}
                          </h5>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: '#475569', marginBottom: '6px' }}>
                          <span>Clicks: <strong>{d.clicks.toLocaleString()}</strong> ({percentage}%)</span>
                          <span>CTR: <strong>{d.ctr}%</strong></span>
                        </div>
                        <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '8px' }}>
                          Impressions: {d.impressions.toLocaleString()}
                        </div>
                        <div style={{ width: '100%', height: '6px', backgroundColor: '#e2e8f0', borderRadius: '3px', overflow: 'hidden' }}>
                          <div
                            style={{
                              width: `${percentage}%`,
                              height: '100%',
                              backgroundColor: '#2563eb',
                              borderRadius: '3px',
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* TAB 4: COUNTRIES BREAKDOWN */}
            {activeTab === 'countries' && (
              <div style={{ padding: '20px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
                  {countryRows.map((c, idx) => {
                    const isEthiopia = c.country === 'ET' || c.country === 'ETH';
                    const flag = isEthiopia ? '🇪🇹' : '🌍';
                    const countryName = isEthiopia ? 'Ethiopia' : c.country;
                    return (
                      <div
                        key={idx}
                        style={{
                          backgroundColor: '#f8fafc',
                          border: isEthiopia ? '1px solid #bfdbfe' : '1px solid #e2e8f0',
                          borderRadius: '8px',
                          padding: '16px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                          <span style={{ fontSize: '20px' }}>{flag}</span>
                          <h5 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                            {countryName} ({c.country})
                          </h5>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: '#475569', marginBottom: '4px' }}>
                          <span>Clicks: <strong>{c.clicks.toLocaleString()}</strong></span>
                          <span>CTR: <strong>{c.ctr}%</strong></span>
                        </div>
                        <div style={{ fontSize: '12px', color: '#64748b' }}>
                          Impressions: {c.impressions.toLocaleString()}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
};

// Styles
const thStyle: React.CSSProperties = {
  padding: '10px 16px',
  fontWeight: 600,
  fontSize: '12px',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
};

const tdStyle: React.CSSProperties = {
  padding: '12px 16px',
  verticalAlign: 'middle',
};
