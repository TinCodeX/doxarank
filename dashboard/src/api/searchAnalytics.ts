import { apiFetch } from './client';
import type { SearchAnalyticsData, SearchAnalyticsFilters } from '../types/searchAnalytics';

/**
 * Build URL search query string from filters object.
 */
function buildQueryString(filters?: SearchAnalyticsFilters): string {
  if (!filters) return '';
  const params = new URLSearchParams();

  if (filters.project_id !== undefined && filters.project_id !== null) {
    params.set('project_id', String(filters.project_id));
  }
  if (filters.connection_id !== undefined && filters.connection_id !== null) {
    params.set('connection_id', String(filters.connection_id));
  }
  if (filters.date) {
    params.set('date', filters.date);
  }
  if (filters.start_date) {
    params.set('start_date', filters.start_date);
  }
  if (filters.end_date) {
    params.set('end_date', filters.end_date);
  }
  if (filters.query) {
    params.set('query', filters.query);
  }
  if (filters.page) {
    params.set('page', filters.page);
  }
  if (filters.country) {
    params.set('country', filters.country);
  }
  if (filters.device) {
    params.set('device', filters.device);
  }

  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

/**
 * Fetch Search Analytics observations with optional filtering.
 * (GET /api/seo/search-analytics/)
 */
export async function getSearchAnalytics(
  filters?: SearchAnalyticsFilters
): Promise<SearchAnalyticsData[]> {
  const query = buildQueryString(filters);
  return apiFetch<SearchAnalyticsData[]>(`/api/seo/search-analytics/${query}`);
}

/**
 * Fetch Search Analytics observations for a specific project.
 * (GET /api/seo/search-analytics/?project_id=<projectId>)
 */
export async function getSearchAnalyticsByProject(
  projectId: number,
  additionalFilters?: Omit<SearchAnalyticsFilters, 'project_id'>
): Promise<SearchAnalyticsData[]> {
  return getSearchAnalytics({
    project_id: projectId,
    ...additionalFilters,
  });
}

/**
 * Fetch Search Analytics observations for a specific project within a date range.
 * (GET /api/seo/search-analytics/?project_id=<projectId>&start_date=<startDate>&end_date=<endDate>)
 */
export async function getSearchAnalyticsByDateRange(
  projectId: number,
  startDate: string,
  endDate: string,
  additionalFilters?: Omit<SearchAnalyticsFilters, 'project_id' | 'start_date' | 'end_date'>
): Promise<SearchAnalyticsData[]> {
  return getSearchAnalytics({
    project_id: projectId,
    start_date: startDate,
    end_date: endDate,
    ...additionalFilters,
  });
}

/**
 * Fetch a single Search Analytics record by ID.
 * (GET /api/seo/search-analytics/<id>/)
 */
export async function getSearchAnalyticsById(
  id: number
): Promise<SearchAnalyticsData> {
  return apiFetch<SearchAnalyticsData>(`/api/seo/search-analytics/${id}/`);
}
