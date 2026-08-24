export type AuditStatus = 'pending' | 'running' | 'completed' | 'failed';

export type IssueSeverity = 'critical' | 'warning' | 'notice';

export interface SiteAudit {
  id: number;
  project: number;
  project_name: string;
  project_website_url: string;
  status: AuditStatus;
  score: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  error_message: string | null;
  issues_count?: number;
}

export interface CreateSiteAuditPayload {
  project: number;
  status?: AuditStatus;
  score?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
}

export interface UpdateSiteAuditPayload {
  status?: AuditStatus;
  score?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
}

export interface AuditIssue {
  id: number;
  audit: number;
  project_id?: number;
  project_name?: string;
  issue_type: string;
  severity: IssueSeverity;
  title: string;
  description: string;
  page_url: string | null;
  recommendation: string | null;
  created_at: string;
}

export interface CreateAuditIssuePayload {
  audit: number;
  issue_type: string;
  severity?: IssueSeverity;
  title: string;
  description: string;
  page_url?: string | null;
  recommendation?: string | null;
}

export interface UpdateAuditIssuePayload {
  issue_type?: string;
  severity?: IssueSeverity;
  title?: string;
  description?: string;
  page_url?: string | null;
  recommendation?: string | null;
}
