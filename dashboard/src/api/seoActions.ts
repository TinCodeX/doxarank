import { apiFetch } from './client';
import type {
  SEOAction,
  SEOActionGeneratePayload,
  SEOActionUpdatePayload,
  ActionStatusCounts,
  ActionStatus,
  ActionType,
  ActionPriority
} from '../types/seoAction';

export interface SEOActionFilterParams {
  project_id?: number;
  recommendation_id?: number;
  content_draft_id?: number;
  content_brief_id?: number;
  action_type?: ActionType | string;
  priority?: ActionPriority | string;
  status?: ActionStatus | string;
}

/**
 * Fetch SEO Actions with optional filtering.
 */
export async function getSEOActions(
  params: SEOActionFilterParams = {}
): Promise<SEOAction[]> {
  const searchParams = new URLSearchParams();
  if (params.project_id) searchParams.append('project_id', String(params.project_id));
  if (params.recommendation_id) searchParams.append('recommendation_id', String(params.recommendation_id));
  if (params.content_draft_id) searchParams.append('content_draft_id', String(params.content_draft_id));
  if (params.content_brief_id) searchParams.append('content_brief_id', String(params.content_brief_id));
  if (params.action_type && params.action_type !== 'all') searchParams.append('action_type', params.action_type);
  if (params.priority && params.priority !== 'all') searchParams.append('priority', params.priority);
  if (params.status && params.status !== 'all') searchParams.append('status', params.status);

  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return apiFetch<SEOAction[]>(`/api/seo/ai/actions/${query}`);
}

/**
 * Fetch a single SEO Action by ID.
 */
export async function getSEOAction(id: number): Promise<SEOAction> {
  return apiFetch<SEOAction>(`/api/seo/ai/actions/${id}/`);
}

/**
 * Synthesize a new executable SEO Action.
 */
export async function generateSEOAction(
  payload: SEOActionGeneratePayload
): Promise<SEOAction> {
  return apiFetch<SEOAction>('/api/seo/ai/actions/generate/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update an SEO Action details.
 */
export async function updateSEOAction(
  id: number,
  payload: SEOActionUpdatePayload
): Promise<SEOAction> {
  return apiFetch<SEOAction>(`/api/seo/ai/actions/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Transition an SEO Action to reviewed.
 */
export async function reviewSEOAction(id: number): Promise<SEOAction> {
  return apiFetch<SEOAction>(`/api/seo/ai/actions/${id}/review/`, {
    method: 'POST',
  });
}

/**
 * Human approve an SEO Action.
 */
export async function approveSEOAction(id: number): Promise<SEOAction> {
  return apiFetch<SEOAction>(`/api/seo/ai/actions/${id}/approve/`, {
    method: 'POST',
  });
}

/**
 * Human reject an SEO Action with mandatory reason.
 */
export async function rejectSEOAction(id: number, reason: string): Promise<SEOAction> {
  return apiFetch<SEOAction>(`/api/seo/ai/actions/${id}/reject/`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

/**
 * Generate a safe non-destructive visual diff preview for an SEO Action.
 */
export async function previewSEOAction(id: number): Promise<{
  action_id: number;
  preview: any;
  status: ActionStatus;
  requires_human_approval: boolean;
}> {
  return apiFetch<{
    action_id: number;
    preview: any;
    status: ActionStatus;
    requires_human_approval: boolean;
  }>(`/api/seo/ai/actions/${id}/preview/`);
}

/**
 * Cancel an SEO Action.
 */
export async function cancelSEOAction(id: number): Promise<SEOAction> {
  return apiFetch<SEOAction>(`/api/seo/ai/actions/${id}/cancel/`, {
    method: 'POST',
  });
}

/**
 * Execute an approved SEO Action in safe staging mode.
 */
export async function executeSEOAction(id: number): Promise<SEOAction> {
  return apiFetch<SEOAction>(`/api/seo/ai/actions/${id}/execute/`, {
    method: 'POST',
  });
}

/**
 * Delete an SEO Action.
 */
export async function deleteSEOAction(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/ai/actions/${id}/`, {
    method: 'DELETE',
  });
}

/**
 * Empirically verify the real-world outcome of an executed SEO Action.
 */
export async function verifySEOAction(id: number): Promise<{ action: SEOAction; verification: Record<string, any> }> {
  return apiFetch<{ action: SEOAction; verification: Record<string, any> }>(`/api/seo/ai/actions/${id}/verify/`, {
    method: 'POST',
  });
}

/**
 * Fetch action status counts for a project.
 */
export async function getSEOActionStatusCounts(
  projectId: number
): Promise<ActionStatusCounts> {
  return apiFetch<ActionStatusCounts>(`/api/seo/ai/actions/status-counts/?project_id=${projectId}`);
}
