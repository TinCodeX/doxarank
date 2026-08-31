import { apiFetch } from './client';
import type { SearchConsoleConnection } from '../types/searchConsole';

export interface GoogleAuthorizationUrlResponse {
  authorization_url: string;
}

export interface GoogleOAuthCallbackPayload {
  code?: string;
  state?: string;
  error?: string;
  error_description?: string;
  redirect_uri?: string;
}

/**
 * Request a Google OAuth2 authorization URL bound to a specific project.
 * (GET /api/seo/integrations/google/authorization-url/?project_id=<id>)
 */
export async function getGoogleAuthorizationUrl(
  projectId: number
): Promise<GoogleAuthorizationUrlResponse> {
  return apiFetch<GoogleAuthorizationUrlResponse>(
    `/api/seo/integrations/google/authorization-url/?project_id=${projectId}`
  );
}

/**
 * Exchange Google OAuth2 callback code and state for Search Console connection and credentials.
 * (POST /api/seo/integrations/google/callback/)
 */
export async function exchangeGoogleOAuthCallback(
  payload: GoogleOAuthCallbackPayload
): Promise<SearchConsoleConnection> {
  return apiFetch<SearchConsoleConnection>('/api/seo/integrations/google/callback/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
