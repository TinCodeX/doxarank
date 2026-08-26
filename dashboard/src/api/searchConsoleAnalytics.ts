import { apiFetch } from './client';
import type {
  GSCPerformanceSummary,
  GSCQueryItem,
  GSCPageItem,
  GSCDeviceItem,
  GSCCountryItem,
  GSCSyncResponse,
  GSCAnalyticsFilters,
} from '../types/searchConsoleAnalytics';

/**
 * Convert filter object to URL query parameter string.
 */
function buildQueryParams(filters?: GSCAnalyticsFilters): string {
  if (!filters) return '';
  const params = new URLSearchParams();

  if (filters.project_id) params.append('project_id', String(filters.project_id));
  if (filters.connection_id) params.append('connection_id', String(filters.connection_id));
  if (filters.start_date) params.append('start_date', filters.start_date);
  if (filters.end_date) params.append('end_date', filters.end_date);
  if (filters.query) params.append('query', filters.query);
  if (filters.page) params.append('page', filters.page);
  if (filters.country) params.append('country', filters.country);
  if (filters.device) params.append('device', filters.device);
  if (filters.search_appearance) params.append('search_appearance', filters.search_appearance);

  const queryStr = params.toString();
  return queryStr ? `?${queryStr}` : '';
}

/**
 * Fetch Search Console performance summary (totals and timeseries).
 * Endpoint: GET /api/seo/search-console/performance/?project_id=<id>...
 */
export async function getSearchConsolePerformance(
  filters?: GSCAnalyticsFilters
): Promise<GSCPerformanceSummary> {
  const query = buildQueryParams(filters);
  return apiFetch<GSCPerformanceSummary>(`/api/seo/search-console/performance/${query}`);
}

/**
 * Fetch Search Console top queries breakdown.
 * Endpoint: GET /api/seo/search-console/queries/?project_id=<id>...
 */
export async function getSearchConsoleQueries(
  filters?: GSCAnalyticsFilters
): Promise<GSCQueryItem[]> {
  const query = buildQueryParams(filters);
  return apiFetch<GSCQueryItem[]>(`/api/seo/search-console/queries/${query}`);
}

/**
 * Fetch Search Console top landing pages breakdown.
 * Endpoint: GET /api/seo/search-console/pages/?project_id=<id>...
 */
export async function getSearchConsolePages(
  filters?: GSCAnalyticsFilters
): Promise<GSCPageItem[]> {
  const query = buildQueryParams(filters);
  return apiFetch<GSCPageItem[]>(`/api/seo/search-console/pages/${query}`);
}

/**
 * Fetch Search Console device breakdown.
 * Endpoint: GET /api/seo/search-console/devices/?project_id=<id>...
 */
export async function getSearchConsoleDevices(
  filters?: GSCAnalyticsFilters
): Promise<GSCDeviceItem[]> {
  const query = buildQueryParams(filters);
  return apiFetch<GSCDeviceItem[]>(`/api/seo/search-console/devices/${query}`);
}

/**
 * Fetch Search Console country breakdown.
 * Endpoint: GET /api/seo/search-console/countries/?project_id=<id>...
 */
export async function getSearchConsoleCountries(
  filters?: GSCAnalyticsFilters
): Promise<GSCCountryItem[]> {
  const query = buildQueryParams(filters);
  return apiFetch<GSCCountryItem[]>(`/api/seo/search-console/countries/${query}`);
}

/**
 * Trigger Search Console synchronization.
 * Endpoint: POST /api/seo/search-console/sync/
 */
export async function syncSearchConsole(payload: {
  project_id?: number;
  connection_id?: number;
  start_date?: string;
  end_date?: string;
}): Promise<GSCSyncResponse> {
  return apiFetch<GSCSyncResponse>('/api/seo/search-console/sync/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
