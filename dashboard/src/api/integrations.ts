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
  has_analytics_scope?: boolean;
  has_gtm_scope?: boolean;
  project_ga4?: ProjectGA4ConnectionResponse | null;
  project_clarity?: ProjectClarityConnectionResponse | null;
  project_gtm?: ProjectGTMConnectionResponse | null;
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

export interface GA4Property {
  property_id: string;
  display_name: string;
  property_type: string;
}

export interface AssociateGA4PropertyPayload {
  project_id: number;
  property_id: string;
  display_name?: string;
}

export interface AssociateGA4PropertyResponse {
  project_id: number;
  project_name: string;
  property_id: string;
  display_name: string;
  account_id?: string;
  is_connected: boolean;
  connected_at: string;
}

export interface ProjectGA4ConnectionResponse {
  project_id: number;
  project_name: string;
  property_id: string;
  display_name: string;
  account_id?: string;
  is_connected: boolean;
  connected_at: string;
}

export interface ClarityProject {
  project_id: string;
  name: string;
  website?: string;
}

export interface AssociateClarityPayload {
  project_id: number;
  clarity_project_id: string;
  name?: string;
  website?: string;
  api_token?: string;
}

export interface AssociateClarityResponse {
  project_id: number;
  project_name: string;
  clarity_project_id: string;
  name: string;
  website: string;
  is_connected: boolean;
  connected_at: string;
}

export interface ProjectClarityConnectionResponse {
  project_id: number;
  project_name: string;
  clarity_project_id: string;
  name: string;
  website: string;
  is_connected: boolean;
  connected_at: string;
}

/**
 * Retrieve integration connection statuses for the authenticated user.
 * (GET /api/integrations/status/)
 */
export async function getIntegrationsStatus(projectId?: number): Promise<IntegrationsStatusResponse> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
  return apiFetch<IntegrationsStatusResponse>(`/api/integrations/status/${query}`);
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

/**
 * Retrieve accessible Google Analytics 4 (GA4) properties for the connected user.
 * (GET /api/integrations/google/analytics/properties/)
 */
export async function getGA4Properties(): Promise<GA4Property[]> {
  return apiFetch<GA4Property[]>('/api/integrations/google/analytics/properties/');
}

/**
 * Associate an accessible GA4 property with a DoxaRank project.
 * (POST /api/integrations/google/analytics/associate/)
 */
export async function associateGA4Property(
  payload: AssociateGA4PropertyPayload
): Promise<AssociateGA4PropertyResponse> {
  return apiFetch<AssociateGA4PropertyResponse>('/api/integrations/google/analytics/associate/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Retrieve active GA4 connection for a specific project.
 * (GET /api/integrations/google/analytics/project/?project_id=<id>)
 */
export async function getProjectGA4Connection(
  projectId: number
): Promise<ProjectGA4ConnectionResponse | null> {
  try {
    return await apiFetch<ProjectGA4ConnectionResponse>(
      `/api/integrations/google/analytics/project/?project_id=${encodeURIComponent(projectId)}`
    );
  } catch (err: any) {
    if (err?.status === 404 || err?.data?.detail?.includes('not associated') || err?.data?.code === 'NOT_FOUND') {
      return null;
    }
    throw err;
  }
}

/**
 * Generate Microsoft OAuth2 authorization URL to connect user's Microsoft account.
 * (GET /api/integrations/microsoft/clarity/connect/)
 */
export async function getMicrosoftClarityConnectUrl(redirectUri?: string): Promise<{ authorization_url: string }> {
  const query = redirectUri ? `?redirect_uri=${encodeURIComponent(redirectUri)}` : '';
  return apiFetch<{ authorization_url: string }>(`/api/integrations/microsoft/clarity/connect/${query}`);
}

/**
 * Safely disconnect user's connected Microsoft Clarity account.
 * (POST /api/integrations/microsoft/clarity/disconnect/)
 */
export async function disconnectMicrosoftClarity(): Promise<{ detail: string }> {
  return apiFetch<{ detail: string }>('/api/integrations/microsoft/clarity/disconnect/', {
    method: 'POST',
  });
}

/**
 * Retrieve accessible Microsoft Clarity projects for the connected user.
 * (GET /api/integrations/microsoft/clarity/projects/)
 */
export async function getClarityProjects(): Promise<ClarityProject[]> {
  return apiFetch<ClarityProject[]>('/api/integrations/microsoft/clarity/projects/');
}

/**
 * Associate an accessible Microsoft Clarity project with a DoxaRank project.
 * (POST /api/integrations/microsoft/clarity/associate/)
 */
export async function associateClarityProject(
  payload: AssociateClarityPayload
): Promise<AssociateClarityResponse> {
  return apiFetch<AssociateClarityResponse>('/api/integrations/microsoft/clarity/associate/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Retrieve active Clarity connection for a specific project.
 * (GET /api/integrations/microsoft/clarity/project/?project_id=<id>)
 */
export async function getProjectClarityConnection(
  projectId: number
): Promise<ProjectClarityConnectionResponse | null> {
  try {
    return await apiFetch<ProjectClarityConnectionResponse>(
      `/api/integrations/microsoft/clarity/project/?project_id=${encodeURIComponent(projectId)}`
    );
  } catch (err: any) {
    if (err?.status === 404 || err?.data?.detail?.includes('not associated') || err?.data?.code === 'NOT_FOUND') {
      return null;
    }
    throw err;
  }
}

export interface GTMContainer {
  account_id: string;
  account_name?: string;
  container_id: string;
  public_id: string;
  name: string;
  usage_context?: string[];
}

export interface AssociateGTMPayload {
  project_id: number;
  container_id: string;
  account_id?: string;
  container_public_id?: string;
  name?: string;
  usage_context?: string[];
}

export interface AssociateGTMResponse {
  project_id: number;
  project_name: string;
  account_id: string;
  container_id: string;
  container_public_id: string;
  name: string;
  usage_context: string[];
  is_connected: boolean;
  connected_at: string;
}

export interface ProjectGTMConnectionResponse {
  project_id: number;
  project_name: string;
  account_id: string;
  container_id: string;
  container_public_id: string;
  name: string;
  usage_context: string[];
  is_connected: boolean;
  connected_at: string;
}

/**
 * Retrieve accessible Google Tag Manager (GTM) containers for the connected user.
 * (GET /api/integrations/google/gtm/containers/)
 */
export async function getGTMContainers(): Promise<GTMContainer[]> {
  return apiFetch<GTMContainer[]>('/api/integrations/google/gtm/containers/');
}

/**
 * Associate an accessible GTM container with a DoxaRank project.
 * (POST /api/integrations/google/gtm/associate/)
 */
export async function associateGTMContainer(
  payload: AssociateGTMPayload
): Promise<AssociateGTMResponse> {
  return apiFetch<AssociateGTMResponse>('/api/integrations/google/gtm/associate/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Retrieve active GTM connection for a specific project.
 * (GET /api/integrations/google/gtm/project/?project_id=<id>)
 */
export async function getProjectGTMConnection(
  projectId: number
): Promise<ProjectGTMConnectionResponse | null> {
  try {
    const res = await apiFetch<any>(
      `/api/integrations/google/gtm/project/?project_id=${encodeURIComponent(projectId)}`
    );
    if (!res || res.is_connected === false) {
      return null;
    }
    return res as ProjectGTMConnectionResponse;
  } catch (err: any) {
    if (err?.status === 404 || err?.data?.detail?.includes('not associated') || err?.data?.code === 'NOT_FOUND') {
      return null;
    }
    throw err;
  }
}

/**
 * Disconnect GTM container from a project.
 * (POST /api/integrations/google/gtm/disconnect/)
 */
export async function disconnectProjectGTM(projectId: number): Promise<{ disconnected: boolean }> {
  return apiFetch<{ disconnected: boolean }>('/api/integrations/google/gtm/disconnect/', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId }),
  });
}



