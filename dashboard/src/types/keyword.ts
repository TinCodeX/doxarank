export type SearchEngine = 'google';
export type CountryCode = 'ET';
export type LanguageCode = 'en' | 'am' | 'om';
export type DeviceType = 'desktop' | 'mobile';

export type CompetitionLevel = 'LOW' | 'MEDIUM' | 'HIGH';
export type SearchIntent = 'informational' | 'commercial' | 'transactional' | 'navigational';
export type IntelligenceStatus = 'FRESH' | 'STALE' | 'REFRESHING' | 'UNAVAILABLE' | 'ERROR';

export interface KeywordIntelligence {
  id: number;
  keyword: number;
  keyword_name?: string;
  search_volume: number | null;
  cpc: string | null;
  currency: string;
  competition: CompetitionLevel | null;
  competition_index: number | null;
  difficulty: number | null;
  intent: SearchIntent | null;
  source: string;
  status: IntelligenceStatus;
  error_message?: string;
  last_refreshed_at: string | null;
  is_fresh: boolean;
  created_at: string;
  updated_at: string;
}

export interface KeywordIntelligenceSnapshot {
  id: number;
  keyword: number;
  search_volume: number | null;
  cpc: string | null;
  currency: string;
  competition: CompetitionLevel | null;
  competition_index: number | null;
  difficulty: number | null;
  intent: SearchIntent | null;
  source: string;
  recorded_at: string;
}

export interface Keyword {
  id: number;
  project: number;
  project_name: string;
  project_website_url: string;
  keyword: string;
  search_engine: SearchEngine;
  search_domain?: string;
  country: CountryCode;
  language: LanguageCode;
  device: DeviceType;
  is_active: boolean;
  intelligence?: KeywordIntelligence | null;
  created_at: string;
  updated_at: string;
}

export interface CreateKeywordPayload {
  project: number;
  keyword: string;
  search_engine?: SearchEngine;
  search_domain?: string;
  country?: CountryCode;
  language?: LanguageCode;
  device?: DeviceType;
  is_active?: boolean;
}

export interface UpdateKeywordPayload {
  keyword?: string;
  search_engine?: SearchEngine;
  search_domain?: string;
  country?: CountryCode;
  language?: LanguageCode;
  device?: DeviceType;
  is_active?: boolean;
}
