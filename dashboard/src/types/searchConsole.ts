export type SearchConsolePermission =
  | 'siteOwner'
  | 'siteFullUser'
  | 'siteRestrictedUser'
  | 'siteUnverifiedUser';

export type SearchConsoleSyncStatus =
  | 'idle'
  | 'syncing'
  | 'success'
  | 'failed';

export interface SearchConsoleConnection {
  id: number;
  project: number;
  project_name: string;
  project_website_url: string;
  property_url: string;
  permission_level: SearchConsolePermission;
  is_connected: boolean;
  connected_at: string;
  last_synced_at: string | null;
  sync_status: SearchConsoleSyncStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateSearchConsoleConnectionPayload {
  project: number;
  property_url: string;
  permission_level?: SearchConsolePermission;
  is_connected?: boolean;
  sync_status?: SearchConsoleSyncStatus;
  error_message?: string | null;
}

export interface UpdateSearchConsoleConnectionPayload {
  property_url?: string;
  permission_level?: SearchConsolePermission;
  is_connected?: boolean;
  sync_status?: SearchConsoleSyncStatus;
  error_message?: string | null;
  last_synced_at?: string | null;
}
