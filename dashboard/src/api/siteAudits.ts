import { apiFetch } from './client';
import type {
  SiteAudit,
  CreateSiteAuditPayload,
  UpdateSiteAuditPayload,
  AuditIssue,
  CreateAuditIssuePayload,
  UpdateAuditIssuePayload,
} from '../types/siteAudit';

/**
 * Fetch site audits belonging to authenticated user's projects.
 * Supports optional project_id filtering: /api/seo/audits/?project_id=<id>
 */
export async function getSiteAudits(projectId?: number): Promise<SiteAudit[]> {
  const query = projectId ? `?project_id=${projectId}` : '';
  return apiFetch<SiteAudit[]>(`/api/seo/audits/${query}`);
}

/**
 * Fetch a single site audit record by ID.
 * (GET /api/seo/audits/<id>/)
 */
export async function getSiteAudit(id: number): Promise<SiteAudit> {
  return apiFetch<SiteAudit>(`/api/seo/audits/${id}/`);
}

/**
 * Create a new site audit record for a project.
 * (POST /api/seo/audits/)
 */
export async function createSiteAudit(payload: CreateSiteAuditPayload): Promise<SiteAudit> {
  return apiFetch<SiteAudit>('/api/seo/audits/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update an existing site audit record.
 * (PATCH /api/seo/audits/<id>/)
 */
export async function updateSiteAudit(
  id: number,
  payload: UpdateSiteAuditPayload
): Promise<SiteAudit> {
  return apiFetch<SiteAudit>(`/api/seo/audits/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Delete a site audit record and its cascaded issues.
 * (DELETE /api/seo/audits/<id>/)
 */
export async function deleteSiteAudit(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/audits/${id}/`, {
    method: 'DELETE',
  });
}

/**
 * Fetch audit issues.
 * Supports optional audit_id filtering: /api/seo/issues/?audit_id=<id>
 */
export async function getAuditIssues(auditId?: number): Promise<AuditIssue[]> {
  const query = auditId ? `?audit_id=${auditId}` : '';
  return apiFetch<AuditIssue[]>(`/api/seo/issues/${query}`);
}

/**
 * Fetch a single audit issue by ID.
 * (GET /api/seo/issues/<id>/)
 */
export async function getAuditIssue(id: number): Promise<AuditIssue> {
  return apiFetch<AuditIssue>(`/api/seo/issues/${id}/`);
}

/**
 * Create a new audit issue under a site audit.
 * (POST /api/seo/issues/)
 */
export async function createAuditIssue(payload: CreateAuditIssuePayload): Promise<AuditIssue> {
  return apiFetch<AuditIssue>('/api/seo/issues/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update an existing audit issue.
 * (PATCH /api/seo/issues/<id>/)
 */
export async function updateAuditIssue(
  id: number,
  payload: UpdateAuditIssuePayload
): Promise<AuditIssue> {
  return apiFetch<AuditIssue>(`/api/seo/issues/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Delete an audit issue.
 * (DELETE /api/seo/issues/<id>/)
 */
export async function deleteAuditIssue(id: number): Promise<void> {
  return apiFetch<void>(`/api/seo/issues/${id}/`, {
    method: 'DELETE',
  });
}
