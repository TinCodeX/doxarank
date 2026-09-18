import { apiFetch } from './client';
import type {
  LongTermSEOStrategy,
  StrategicObjective,
  StrategicInitiative,
  StrategyReviewRecord,
  StrategyMetrics,
} from '../types/strategy';

/**
 * Fetch project-scoped long-term SEO strategies.
 */
export async function getStrategies(projectId?: number): Promise<LongTermSEOStrategy[]> {
  const query = projectId ? `?project_id=${projectId}` : '';
  return apiFetch<LongTermSEOStrategy[]>(`/api/seo/ai/long-term-strategy/${query}`);
}

/**
 * Fetch a specific long-term SEO strategy version.
 */
export async function getStrategy(strategyId: number): Promise<LongTermSEOStrategy> {
  return apiFetch<LongTermSEOStrategy>(`/api/seo/ai/long-term-strategy/${strategyId}/`);
}

/**
 * Fetch objectives for a specific strategy's project.
 */
export async function getStrategyObjectives(strategyId: number): Promise<StrategicObjective[]> {
  return apiFetch<StrategicObjective[]>(`/api/seo/ai/long-term-strategy/${strategyId}/objectives/`);
}

/**
 * Fetch initiatives attached to a specific strategy version.
 */
export async function getStrategyInitiatives(strategyId: number): Promise<StrategicInitiative[]> {
  return apiFetch<StrategicInitiative[]>(`/api/seo/ai/long-term-strategy/${strategyId}/initiatives/`);
}

/**
 * Fetch historical strategy versions for a project.
 */
export async function getStrategyVersions(strategyId: number): Promise<LongTermSEOStrategy[]> {
  return apiFetch<LongTermSEOStrategy[]>(`/api/seo/ai/long-term-strategy/${strategyId}/versions/`);
}

/**
 * Fetch reviews conducted for a strategy.
 */
export async function getStrategyReviews(strategyId: number): Promise<StrategyReviewRecord[]> {
  return apiFetch<StrategyReviewRecord[]>(`/api/seo/ai/long-term-strategy/${strategyId}/reviews/`);
}

/**
 * Fetch dynamic strategy evaluation metrics for a project.
 */
export async function getStrategyMetrics(projectId: number): Promise<StrategyMetrics> {
  return apiFetch<StrategyMetrics>(`/api/seo/ai/long-term-strategy/metrics/?project_id=${projectId}`);
}

/**
 * Trigger an on-demand strategic review cycle.
 */
export async function triggerStrategyReview(
  projectId: number,
  triggerSource: string = 'dashboard_user'
): Promise<{ review_id: number; cycle: number; decision: string; approval_status: string; proposed_version?: number }> {
  return apiFetch('/api/seo/ai/long-term-strategy/review/', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, trigger_source: triggerSource }),
  });
}

/**
 * Authorize and activate a proposed strategy version under Human-In-The-Loop.
 */
export async function approveStrategy(
  strategyId: number
): Promise<{ message: string; strategy: LongTermSEOStrategy }> {
  return apiFetch<{ message: string; strategy: LongTermSEOStrategy }>(
    `/api/seo/ai/long-term-strategy/${strategyId}/approve/`,
    { method: 'POST' }
  );
}

/**
 * Reject a proposed strategy version under Human-In-The-Loop.
 */
export async function rejectStrategy(
  strategyId: number,
  reason: string = 'Rejected by dashboard operator'
): Promise<{ message: string; review_id: number; approval_status: string }> {
  return apiFetch<{ message: string; review_id: number; approval_status: string }>(
    `/api/seo/ai/long-term-strategy/${strategyId}/reject/`,
    {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }
  );
}
