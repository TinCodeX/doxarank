export type SearchEngine = 'google';
export type CountryCode = 'ET';
export type LanguageCode = 'en' | 'am';
export type DeviceType = 'desktop' | 'mobile';

export interface Keyword {
  id: number;
  project: number;
  project_name: string;
  project_website_url: string;
  keyword: string;
  search_engine: SearchEngine;
  country: CountryCode;
  language: LanguageCode;
  device: DeviceType;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateKeywordPayload {
  project: number;
  keyword: string;
  search_engine?: SearchEngine;
  country?: CountryCode;
  language?: LanguageCode;
  device?: DeviceType;
  is_active?: boolean;
}

export interface UpdateKeywordPayload {
  keyword?: string;
  search_engine?: SearchEngine;
  country?: CountryCode;
  language?: LanguageCode;
  device?: DeviceType;
  is_active?: boolean;
}
