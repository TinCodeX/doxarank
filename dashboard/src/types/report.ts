export type ReportStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';

export interface SEOReport {
  id: number;
  project: number;
  project_name: string;
  project_website_url: string;
  title: string;
  client_name: string;
  status: ReportStatus;
  file_size_bytes: number;
  download_url: string | null;
  summary_data: {
    crawler_available?: boolean;
    total_keywords?: number;
    top_10_count?: number;
    competitors_count?: number;
    recommendations_count?: number;
    overall_status?: string;
    [key: string]: any;
  };
  error_message: string;
  created_at: string;
  completed_at: string | null;
}

export interface GenerateReportPayload {
  project_id: number;
  client_name?: string;
  title?: string;
  async?: boolean;
}
