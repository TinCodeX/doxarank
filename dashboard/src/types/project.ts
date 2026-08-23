export interface Project {
  id: number;
  name: string;
  website_url: string;
  owner_email: string;
  created_at: string;
  updated_at: string;
}

export interface CreateProjectPayload {
  name: string;
  website_url: string;
}

export interface UpdateProjectPayload {
  name?: string;
  website_url?: string;
}
