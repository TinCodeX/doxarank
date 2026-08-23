import type { AuthTokens } from '../types/auth';

const API_BASE_URL = 'http://127.0.0.1:8000';

const ACCESS_TOKEN_KEY = 'doxarank_access_token';
const REFRESH_TOKEN_KEY = 'doxarank_refresh_token';

export const getStoredTokens = (): AuthTokens | null => {
  const access = localStorage.getItem(ACCESS_TOKEN_KEY);
  const refresh = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!access || !refresh) return null;
  return { access, refresh };
};

export const setStoredTokens = (tokens: AuthTokens) => {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
};

export const clearStoredTokens = () => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
};

/**
 * Enhanced fetch wrapper that:
 * 1. Attaches the Bearer access token if available.
 * 2. Automatically attempts token refresh if receiving 401 Unauthorized.
 * 3. Retries original request once on successful refresh.
 */
export async function apiFetch<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  const tokens = getStoredTokens();

  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  if (tokens?.access) {
    headers.set('Authorization', `Bearer ${tokens.access}`);
  }

  let response = await fetch(url, {
    ...options,
    headers,
  });

  // If unauthorized and we have a refresh token, try refreshing the token
  if (response.status === 401 && tokens?.refresh && endpoint !== '/api/auth/token/refresh/' && endpoint !== '/api/auth/login/') {
    try {
      const refreshResponse = await fetch(`${API_BASE_URL}/api/auth/token/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: tokens.refresh }),
      });

      if (refreshResponse.ok) {
        const data = await refreshResponse.json();
        const newTokens: AuthTokens = {
          access: data.access,
          refresh: data.refresh || tokens.refresh,
        };
        setStoredTokens(newTokens);

        // Retry the original request with new access token
        headers.set('Authorization', `Bearer ${newTokens.access}`);
        response = await fetch(url, {
          ...options,
          headers,
        });
      } else {
        // Refresh token is expired or invalid -> log out
        clearStoredTokens();
      }
    } catch {
      clearStoredTokens();
    }
  }

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw {
      status: response.status,
      data,
    };
  }

  return data as T;
}
