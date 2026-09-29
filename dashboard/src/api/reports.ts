import { apiFetch, getStoredTokens } from './client';
import type { SEOReport, GenerateReportPayload } from '../types/report';

const API_BASE_URL = 'http://127.0.0.1:8000';

export async function getReports(projectId?: number): Promise<SEOReport[]> {
  const query = projectId ? `?project_id=${projectId}` : '';
  const data = await apiFetch<any>(`/api/seo/reports/${query}`);
  return Array.isArray(data) ? data : data.results || [];
}

export async function getReport(reportId: number): Promise<SEOReport> {
  return apiFetch<SEOReport>(`/api/seo/reports/${reportId}/`);
}

export async function generateReport(payload: GenerateReportPayload): Promise<SEOReport> {
  return apiFetch<SEOReport>('/api/seo/reports/generate/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function downloadReportFile(reportId: number, fallbackFilename?: string): Promise<void> {
  const tokens = getStoredTokens();
  const headers = new Headers();
  if (tokens?.access) {
    headers.set('Authorization', `Bearer ${tokens.access}`);
  }

  const response = await fetch(`${API_BASE_URL}/api/seo/reports/${reportId}/download/`, {
    headers,
  });

  if (!response.ok) {
    let errMessage = 'Failed to download report.';
    try {
      const errJson = await response.json();
      errMessage = errJson.detail || errMessage;
    } catch {
      // fallback
    }
    throw new Error(errMessage);
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fallbackFilename || `seo_report_${reportId}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}
