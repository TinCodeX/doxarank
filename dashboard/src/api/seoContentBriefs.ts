import { apiFetch, getStoredTokens } from './client';
import type {
  SEOContentBrief,
  BriefContentType,
  BriefStatus,
  GenerateContentBriefPayload,
  UpdateContentBriefPayload
} from '../types/seoContentBrief';

const API_BASE_URL = 'http://127.0.0.1:8000';

export interface SEOContentBriefFilterParams {
  project_id?: number;
  recommendation_id?: number;
  content_type?: BriefContentType;
  status?: BriefStatus;
}

/**
 * Fetch SEO content briefs with optional filtering.
 */
export async function getSEOContentBriefs(
  params: SEOContentBriefFilterParams = {}
): Promise<SEOContentBrief[]> {
  const searchParams = new URLSearchParams();
  if (params.project_id) searchParams.append('project_id', String(params.project_id));
  if (params.recommendation_id) searchParams.append('recommendation_id', String(params.recommendation_id));
  if (params.content_type) searchParams.append('content_type', params.content_type);
  if (params.status) searchParams.append('status', params.status);

  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return apiFetch<SEOContentBrief[]>(`/api/seo/ai/content-briefs/${query}`);
}

/**
 * Fetch a single SEO content brief by ID.
 */
export async function getSEOContentBrief(id: number): Promise<SEOContentBrief> {
  return apiFetch<SEOContentBrief>(`/api/seo/ai/content-briefs/${id}/`);
}

/**
 * Generate a new structured SEO content brief from an AI recommendation.
 */
export async function generateSEOContentBrief(
  payload: GenerateContentBriefPayload
): Promise<SEOContentBrief> {
  return apiFetch<SEOContentBrief>('/api/seo/ai/content-briefs/generate/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update an SEO content brief (e.g. status, content details).
 */
export async function updateSEOContentBrief(
  id: number,
  payload: UpdateContentBriefPayload
): Promise<SEOContentBrief> {
  return apiFetch<SEOContentBrief>(`/api/seo/ai/content-briefs/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Delete an SEO content brief.
 */
export async function deleteSEOContentBrief(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/ai/content-briefs/${id}/`, {
    method: 'DELETE',
  });
}

/**
 * Trigger direct file download for Markdown, CSV, or PDF exports.
 */
export async function downloadSEOContentBrief(
  id: number,
  format: 'markdown' | 'csv' | 'pdf',
  fallbackFilename: string = 'seo_content_brief'
): Promise<void> {
  const tokens = getStoredTokens();
  const url = `${API_BASE_URL}/api/seo/ai/content-briefs/${id}/export/?export_format=${format}`;
  
  const headers: HeadersInit = {};
  if (tokens?.access) {
    headers['Authorization'] = `Bearer ${tokens.access}`;
  }

  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`Failed to export content brief (${response.status} ${response.statusText})`);
  }

  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  
  const ext = format === 'markdown' ? 'md' : format;
  const contentDisp = response.headers.get('Content-Disposition');
  let filename = `${fallbackFilename}.${ext}`;
  if (contentDisp && contentDisp.includes('filename=')) {
    const match = contentDisp.match(/filename="?([^"]+)"?/);
    if (match && match[1]) {
      filename = match[1];
    }
  }
  
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(downloadUrl);
}
