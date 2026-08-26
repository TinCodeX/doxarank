export interface GSCPerformancePoint {
  date: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface GSCPerformanceSummary {
  total_clicks: number;
  total_impressions: number;
  average_ctr: number;
  average_position: number;
  timeseries: GSCPerformancePoint[];
  count: number;
}

export interface GSCQueryItem {
  query: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface GSCPageItem {
  page: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface GSCDeviceItem {
  device: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface GSCCountryItem {
  country: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface GSCSyncResponse {
  success: boolean;
  records_fetched: number;
  records_created: number;
  records_updated: number;
  start_date: string;
  end_date: string;
  property_url: string;
  sync_status: string;
  last_synced_at: string;
}

export interface GSCAnalyticsFilters {
  project_id?: number;
  connection_id?: number;
  start_date?: string;
  end_date?: string;
  query?: string;
  page?: string;
  country?: string;
  device?: string;
  search_appearance?: string;
}

export type DateRangePreset = '7d' | '28d' | '90d' | 'all' | 'custom';
