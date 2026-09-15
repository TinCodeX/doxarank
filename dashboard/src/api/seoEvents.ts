import { apiFetch } from './client';
import type {
  SEOEvent,
  SEOEventMetrics,
  SEOEventIngestPayload,
} from '../types/seoEvent';
import type { AgentRun } from '../types/agentRun';

/**
 * Fetch all SEO events for a project with optional filters.
 */
export async function getSEOEvents(
  projectId?: number,
  filters?: { event_type?: string; status?: string; severity?: string }
): Promise<SEOEvent[]> {
  const params = new URLSearchParams();
  if (projectId) params.append('project', projectId.toString());
  if (filters?.event_type) params.append('event_type', filters.event_type);
  if (filters?.status) params.append('status', filters.status);
  if (filters?.severity) params.append('severity', filters.severity);

  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<SEOEvent[]>(`/api/seo/ai/events/${query}`);
}

/**
 * Fetch single SEO event details.
 */
export async function getSEOEvent(id: number): Promise<SEOEvent> {
  return apiFetch<SEOEvent>(`/api/seo/ai/events/${id}/`);
}

/**
 * Fetch AgentRuns triggered by a specific event.
 */
export async function getSEOEventRuns(id: number): Promise<AgentRun[]> {
  return apiFetch<AgentRun[]>(`/api/seo/ai/events/${id}/runs/`);
}

/**
 * Fetch runtime evaluation metrics for event-driven operations.
 */
export async function getSEOEventMetrics(
  projectId: number,
  eventType?: string
): Promise<SEOEventMetrics> {
  const params = new URLSearchParams({ project: projectId.toString() });
  if (eventType) params.append('event_type', eventType);
  return apiFetch<SEOEventMetrics>(`/api/seo/ai/events/metrics/?${params.toString()}`);
}

/**
 * Ingest an SEO event into DoxaRank to trigger agent workflows.
 */
export async function ingestSEOEvent(
  payload: SEOEventIngestPayload
): Promise<SEOEvent> {
  return apiFetch<SEOEvent>('/api/seo/ai/events/ingest/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
