import { apiFetch } from './client';
import type {
  SEOActionPlan,
  SEOActionPlanCreatePayload,
  ActionPlanStatus,
  ActionRiskLevel,
  VerificationStatus
} from '../types/seoAction';

export interface SEOActionPlanFilterParams {
  project_id?: number;
  status?: ActionPlanStatus | string;
  risk_level?: ActionRiskLevel | string;
  verification_status?: VerificationStatus | string;
}

/**
 * Fetch SEO Action Plans with optional filtering.
 */
export async function getSEOActionPlans(
  params: SEOActionPlanFilterParams = {}
): Promise<SEOActionPlan[]> {
  const searchParams = new URLSearchParams();
  if (params.project_id) searchParams.append('project_id', String(params.project_id));
  if (params.status && params.status !== 'all') searchParams.append('status', params.status);
  if (params.risk_level && params.risk_level !== 'all') searchParams.append('risk_level', params.risk_level);
  if (params.verification_status && params.verification_status !== 'all') {
    searchParams.append('verification_status', params.verification_status);
  }

  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return apiFetch<SEOActionPlan[]>(`/api/seo/ai/action-plans/${query}`);
}

/**
 * Fetch a single SEO Action Plan by ID with nested actions.
 */
export async function getSEOActionPlan(id: number): Promise<SEOActionPlan> {
  return apiFetch<SEOActionPlan>(`/api/seo/ai/action-plans/${id}/`);
}

/**
 * Autonomously generate a structured SEO Action Plan from multi-source evidence.
 */
export async function generateSEOActionPlan(
  payload: SEOActionPlanCreatePayload
): Promise<SEOActionPlan> {
  return apiFetch<SEOActionPlan>('/api/seo/ai/action-plans/plan/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Human approve an SEO Action Plan and all its pending child actions.
 */
export async function approveSEOActionPlan(id: number): Promise<SEOActionPlan> {
  return apiFetch<SEOActionPlan>(`/api/seo/ai/action-plans/${id}/approve/`, {
    method: 'POST',
  });
}

/**
 * Human reject an SEO Action Plan with mandatory reason.
 */
export async function rejectSEOActionPlan(id: number, reason: string): Promise<SEOActionPlan> {
  return apiFetch<SEOActionPlan>(`/api/seo/ai/action-plans/${id}/reject/`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

/**
 * Execute all approved actions in an SEO Action Plan.
 */
export async function executeSEOActionPlan(id: number): Promise<SEOActionPlan> {
  return apiFetch<SEOActionPlan>(`/api/seo/ai/action-plans/${id}/execute/`, {
    method: 'POST',
  });
}

/**
 * Perform empirical real-world verification on an SEO Action Plan.
 */
export async function verifySEOActionPlan(
  id: number
): Promise<{ plan: SEOActionPlan; verification_summary: Record<string, any> }> {
  return apiFetch<{ plan: SEOActionPlan; verification_summary: Record<string, any> }>(
    `/api/seo/ai/action-plans/${id}/verify/`,
    {
      method: 'POST',
    }
  );
}

/**
 * Delete an SEO Action Plan.
 */
export async function deleteSEOActionPlan(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/ai/action-plans/${id}/`, {
    method: 'DELETE',
  });
}

/**
 * Perform empirical real-world outcome measurement on an SEO Action Plan.
 */
export async function measureSEOActionPlanOutcome(
  id: number,
  windowDays: number = 14
): Promise<{ plan: SEOActionPlan; outcome_summary: Record<string, any> }> {
  return apiFetch<{ plan: SEOActionPlan; outcome_summary: Record<string, any> }>(
    `/api/seo/ai/action-plans/${id}/measure-outcome/`,
    {
      method: 'POST',
      body: JSON.stringify({ window_days: windowDays }),
    }
  );
}
