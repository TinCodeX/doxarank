export interface SearchAnalyticsData {
  id: number;
  connection: number;
  project_id: number;
  project_name: string;
  property_url: string;
  date: string;
  query: string;
  page: string;
  country: string;
  device: string;
  clicks: number;
  impressions: number;
  ctr: string | number;
  position: string | number;
  created_at: string;
  updated_at: string;
}

export interface SearchAnalyticsFilters {
  project_id?: number;
  connection_id?: number;
  date?: string;
  start_date?: string;
  end_date?: string;
  query?: string;
  page?: string;
  country?: string;
  device?: string;
}

export interface SearchAnalyticsAggregates {
  totalClicks: number;
  totalImpressions: number;
  averageCtr: number;
  averagePosition: number;
  queryCount: number;
  pageCount: number;
}
