import { apiFetch } from './client';

export interface MetaTagInput {
  title: string;
  description: string;
  canonical_url?: string;
  robots?: string;
  author?: string;
  keywords?: string;
}

export interface MetaTagResult {
  html: string;
  tags: string[];
  metrics: {
    title_length: number;
    title_status: string;
    description_length: number;
    description_status: string;
  };
  warnings: string[];
  usage: {
    tool_code: string;
    plan_code: string;
    used_today: number;
    daily_limit: number | string;
    remaining_today: number | string;
  };
}

export interface SchemaInput {
  schema_type: 'LocalBusiness' | 'Article' | 'Product' | 'FAQ' | 'BreadcrumbList';
  data: Record<string, any>;
}

export interface SchemaResult {
  schema_type: string;
  json_ld: Record<string, any>;
  formatted_json: string;
  script_tag: string;
  usage: {
    tool_code: string;
    plan_code: string;
    used_today: number;
    daily_limit: number | string;
    remaining_today: number | string;
  };
}

export interface SocialPreviewInput {
  title: string;
  description: string;
  url?: string;
  image_url?: string;
  site_name?: string;
  og_type?: string;
  twitter_card?: string;
  twitter_site?: string;
}

export interface SocialPreviewResult {
  html: string;
  tags: string[];
  og_tags: string[];
  twitter_tags: string[];
  preview: {
    title: string;
    description: string;
    url: string;
    domain: string;
    image_url?: string;
    site_name?: string;
    og_type: string;
    twitter_card: string;
    twitter_site?: string;
  };
  metrics: {
    title_length: number;
    description_length: number;
    has_image: boolean;
    has_url: boolean;
  };
  warnings: string[];
  usage: {
    tool_code: string;
    plan_code: string;
    used_today: number;
    daily_limit: number | string;
    remaining_today: number | string;
  };
}

// --- ROBOTS.TXT TOOL INTERFACES ---
export interface RobotsRuleGroup {
  user_agent: string;
  allow?: string[] | string;
  disallow?: string[] | string;
  crawl_delay?: number | string;
}

export interface RobotsToolInput {
  action: 'generate' | 'test';
  groups?: RobotsRuleGroup[];
  sitemaps?: string[];
  host?: string;
  robots_content?: string;
  path?: string;
  user_agent?: string;
}

export interface RobotsToolResult {
  action: 'generate' | 'test';
  content?: string;
  groups?: RobotsRuleGroup[];
  sitemaps?: string[];
  warnings?: string[];
  metrics?: {
    group_count: number;
    sitemap_count: number;
    lines_count: number;
  };
  allowed?: boolean;
  status?: 'ALLOWED' | 'BLOCKED';
  user_agent?: string;
  test_path?: string;
  matched_rule?: string | null;
  reason?: string;
  usage: {
    tool_code: string;
    plan_code: string;
    used_today: number;
    daily_limit: number | string;
    remaining_today: number | string;
  };
}

// --- XML SITEMAP TOOL INTERFACES ---
export interface SitemapEntry {
  loc: string;
  lastmod?: string;
  changefreq?: string;
  priority?: string | number;
}

export interface SitemapToolInput {
  action: 'generate' | 'validate';
  entries?: SitemapEntry[];
  xml_content?: string;
}

export interface SitemapToolResult {
  action: 'generate' | 'validate';
  xml?: string;
  entries?: SitemapEntry[];
  is_valid?: boolean;
  root_tag?: string;
  url_count?: number;
  errors?: string[];
  warnings?: string[];
  urls?: SitemapEntry[];
  metrics?: {
    url_count: number;
    byte_size: number;
  };
  usage: {
    tool_code: string;
    plan_code: string;
    used_today: number;
    daily_limit: number | string;
    remaining_today: number | string;
  };
}

// --- HREFLANG BUILDER INTERFACES ---
export interface HreflangEntry {
  lang: string;
  url: string;
  language_label?: string;
}

export interface HreflangInput {
  entries: HreflangEntry[];
  x_default?: string;
}

export interface HreflangResult {
  html: string;
  html_tags: string[];
  xml_snippet: string;
  http_header: string;
  entries: HreflangEntry[];
  metrics: {
    language_count: number;
    has_x_default: boolean;
    has_english: boolean;
    has_amharic: boolean;
    has_oromo: boolean;
  };
  warnings: string[];
  usage: {
    tool_code: string;
    plan_code: string;
    used_today: number;
    daily_limit: number | string;
    remaining_today: number | string;
  };
}

// --- QUOTA STATUS ---
export interface ToolUsageStat {
  used_today: number;
  remaining: number | string;
}

export interface SEOToolsQuotaStatus {
  plan_code: string;
  daily_limit: number | string;
  tools: {
    meta_tag_generator: ToolUsageStat;
    schema_generator: ToolUsageStat;
    open_graph_previewer: ToolUsageStat;
    robots_txt_tool: ToolUsageStat;
    xml_sitemap_tool: ToolUsageStat;
    hreflang_builder: ToolUsageStat;
  };
}

export const seoToolsApi = {
  getQuotaStatus: async (): Promise<SEOToolsQuotaStatus> => {
    return apiFetch<SEOToolsQuotaStatus>('/api/seo/tools/status/');
  },

  generateMetaTags: async (payload: MetaTagInput): Promise<MetaTagResult> => {
    return apiFetch<MetaTagResult>('/api/seo/tools/meta/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  generateSchema: async (payload: SchemaInput): Promise<SchemaResult> => {
    return apiFetch<SchemaResult>('/api/seo/tools/schema/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  generateSocialPreview: async (payload: SocialPreviewInput): Promise<SocialPreviewResult> => {
    return apiFetch<SocialPreviewResult>('/api/seo/tools/social-preview/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  processRobots: async (payload: RobotsToolInput): Promise<RobotsToolResult> => {
    return apiFetch<RobotsToolResult>('/api/seo/tools/robots/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  processSitemap: async (payload: SitemapToolInput): Promise<SitemapToolResult> => {
    return apiFetch<SitemapToolResult>('/api/seo/tools/sitemap/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  generateHreflang: async (payload: HreflangInput): Promise<HreflangResult> => {
    return apiFetch<HreflangResult>('/api/seo/tools/hreflang/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};
