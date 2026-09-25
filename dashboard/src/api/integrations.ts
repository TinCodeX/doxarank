import { apiFetch } from './client';

export interface IntegrationConnectionStatus {
  id?: number;
  connected: boolean;
  status: 'connected' | 'disconnected' | 'expired' | 'error';
  account_email?: string | null;
  account_name?: string | null;
  scopes?: string[];
  connected_at?: string | null;
  updated_at?: string | null;
  has_valid_credentials?: boolean;
}

export type IntegrationsStatusResponse = Record<string, IntegrationConnectionStatus>;

export interface SearchConsoleProperty {
  site_url: string;
  permission_level: string;
}

export interface GoogleConnectResponse {
  authorization_url: string;
}

export interface AssociatePropertyPayload {
  project_id: number;
  site_url: string;
  permission_level?: string;
}

export interface AssociatePropertyResponse {
  project_id: number;
  project_name: string;
  property_url: string;
  permission_level: string;
  is_connected: boolean;
  google_account_email?: string;
}

/**
 * Retrieve integration connection statuses for the authenticated user.
 * (GET /api/integrations/status/)
 */
export async function getIntegrationsStatus(): Promise<IntegrationsStatusResponse> {
  return apiFetch<IntegrationsStatusResponse>('/api/integrations/status/');
}

/**
 * Generate Google OAuth2 authorization URL to connect user's Google account.
 * (GET /api/integrations/google/connect/)
 */
export async function getGoogleConnectUrl(redirectUri?: string): Promise<GoogleConnectResponse> {
  const query = redirectUri ? `?redirect_uri=${encodeURIComponent(redirectUri)}` : '';
  return apiFetch<GoogleConnectResponse>(`/api/integrations/google/connect/${query}`);
}

/**
 * Safely disconnect user's connected Google account.
 * (POST /api/integrations/google/disconnect/)
 */
export async function disconnectGoogle(): Promise<{ detail: string }> {
  return apiFetch<{ detail: string }>('/api/integrations/google/disconnect/', {
    method: 'POST',
  });
}

/**
 * Retrieve verified Search Console properties for the connected user.
 * (GET /api/integrations/google/search-console/properties/)
 */
export async function getSearchConsoleProperties(): Promise<SearchConsoleProperty[]> {
  return apiFetch<SearchConsoleProperty[]>('/api/integrations/google/search-console/properties/');
}

/**
 * Exchange Google OAuth2 callback code and state for user account integration.
 * (POST /api/integrations/google/callback/)
 */
export async function exchangeUserGoogleOAuthCallback(payload: {
  code: string;
  state: string;
}): Promise<IntegrationConnectionStatus> {
  return apiFetch<IntegrationConnectionStatus>('/api/integrations/google/callback/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Associate a verified Search Console property with a DoxaRank project.
 * (POST /api/integrations/google/search-console/associate/)
 */
export async function associateSearchConsoleProperty(
  payload: AssociatePropertyPayload
): Promise<AssociatePropertyResponse> {
  return apiFetch<AssociatePropertyResponse>('/api/integrations/google/search-console/associate/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
