import type { SearchEngine, CountryCode, LanguageCode, DeviceType } from './keyword';

export interface Ranking {
  id: number;
  keyword: number;
  keyword_name?: string;
  project_id?: number;
  project_name?: string;
  position: number;
  ranking_url: string | null;
  search_engine: SearchEngine;
  country: CountryCode;
  language: LanguageCode;
  device: DeviceType;
  recorded_at: string;
  created_at: string;
}

export interface CreateRankingPayload {
  keyword: number;
  position: number;
  ranking_url?: string;
  search_engine?: SearchEngine;
  country?: CountryCode;
  language?: LanguageCode;
  device?: DeviceType;
  recorded_at?: string;
}

export interface UpdateRankingPayload {
  keyword?: number;
  position?: number;
  ranking_url?: string;
  search_engine?: SearchEngine;
  country?: CountryCode;
  language?: LanguageCode;
  device?: DeviceType;
  recorded_at?: string;
}
