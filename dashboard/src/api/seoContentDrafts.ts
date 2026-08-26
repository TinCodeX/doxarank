import { apiFetch, getStoredTokens } from './client';
import type {
  SEOContentDraft,
  DraftStatus,
  GenerateDraftRequest,
  UpdateDraftRequest
} from '../types/seoContentDraft';
import type { BriefContentType } from '../types/seoContentBrief';

const API_BASE_URL = 'http://127.0.0.1:8000';

export interface SEOContentDraftFilterParams {
  project_id?: number;
  content_brief_id?: number;
  content_type?: BriefContentType;
  status?: DraftStatus;
}

/**
 * Fetch SEO content drafts with optional filtering.
 */
export async function getSEOContentDrafts(
  params: SEOContentDraftFilterParams = {}
): Promise<SEOContentDraft[]> {
  const searchParams = new URLSearchParams();
  if (params.project_id) searchParams.append('project_id', String(params.project_id));
  if (params.content_brief_id) searchParams.append('content_brief_id', String(params.content_brief_id));
  if (params.content_type) searchParams.append('content_type', params.content_type);
  if (params.status) searchParams.append('status', params.status);

  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return apiFetch<SEOContentDraft[]>(`/api/seo/ai/content-drafts/${query}`);
}

/**
 * Fetch a single SEO content draft by ID.
 */
export async function getSEOContentDraft(id: number): Promise<SEOContentDraft> {
  return apiFetch<SEOContentDraft>(`/api/seo/ai/content-drafts/${id}/`);
}

/**
 * Generate a new publish-ready SEO content draft from an SEOContentBrief.
 */
export async function generateSEOContentDraft(
  payload: GenerateDraftRequest
): Promise<SEOContentDraft> {
  return apiFetch<SEOContentDraft>('/api/seo/ai/content-drafts/generate/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update an SEO content draft (e.g. human editorial changes, status).
 */
export async function updateSEOContentDraft(
  id: number,
  payload: UpdateDraftRequest
): Promise<SEOContentDraft> {
  return apiFetch<SEOContentDraft>(`/api/seo/ai/content-drafts/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Delete an SEO content draft.
 */
export async function deleteSEOContentDraft(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/ai/content-drafts/${id}/`, {
    method: 'DELETE',
  });
}

/**
 * Trigger direct file download for Markdown, HTML, or PDF exports.
 */
export async function downloadSEOContentDraft(
  id: number,
  format: 'markdown' | 'html' | 'pdf',
  fallbackFilename: string = 'seo_content_draft'
): Promise<void> {
  const tokens = getStoredTokens();
  const url = `${API_BASE_URL}/api/seo/ai/content-drafts/${id}/export/?export_format=${format}`;

  const headers: HeadersInit = {};
  if (tokens?.access) {
    headers['Authorization'] = `Bearer ${tokens.access}`;
  }

  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`Failed to export content draft (${response.status} ${response.statusText})`);
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
