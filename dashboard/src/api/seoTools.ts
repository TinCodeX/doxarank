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

// --- TOOL 7: SERP SNIPPET PREVIEW INTERFACES ---
export interface SerpSnippetInput {
  title: string;
  description: string;
  url: string;
  device?: 'desktop' | 'mobile';
}

export interface SerpSnippetResult {
  title: string;
  rendered_title: string;
  description: string;
  rendered_description: string;
  url: string;
  breadcrumb: string;
  device: 'desktop' | 'mobile';
  metrics: {
    title_length: number;
    title_pixel_width: number;
    title_max_pixels: number;
    title_truncated: boolean;
    title_status: string;
    description_length: number;
    description_pixel_width: number;
    description_max_pixels: number;
    description_truncated: boolean;
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

// --- TOOL 8: PAGESPEED / CORE WEB VITALS INTERFACES ---
export interface PageSpeedInput {
  url: string;
  strategy?: 'mobile' | 'desktop';
}

export interface CoreWebVitalsItem {
  id: string;
  title: string;
  display_value: string;
  numeric_value?: number | null;
  score?: number | null;
  status: 'good' | 'needs-improvement' | 'poor' | 'unknown';
  description: string;
}

export interface PageSpeedDiagnostic {
  id: string;
  title: string;
  display_value: string;
  description: string;
  score: number;
}

export interface PageSpeedResult {
  url: string;
  strategy: string;
  fetch_time: string;
  scores: {
    performance: number | null;
    accessibility: number | null;
    best_practices: number | null;
    seo: number | null;
  };
  core_web_vitals: {
    lcp: CoreWebVitalsItem;
    fid_inp?: CoreWebVitalsItem | null;
    cls: CoreWebVitalsItem;
    fcp: CoreWebVitalsItem;
    ttfb: CoreWebVitalsItem;
    tbt?: CoreWebVitalsItem | null;
    speed_index?: CoreWebVitalsItem | null;
  };
  crux_summary: {
    overall_category: string;
  };
  diagnostics: PageSpeedDiagnostic[];
  usage: {
    tool_code: string;
    plan_code: string;
    used_today: number;
    daily_limit: number | string;
    remaining_today: number | string;
  };
}

// --- TOOL 9: SINGLE-PAGE BROKEN LINK CHECKER INTERFACES ---
export interface BrokenLinksInput {
  url: string;
}

export interface BrokenLinkItem {
  url: string;
  anchor_text: string;
  status_code: number | null;
  is_internal: boolean;
  is_broken: boolean;
  error_type: string | null;
  error_message?: string | null;
  response_time_ms: number;
}

export interface BrokenLinksResult {
  target_url: string;
  summary: {
    total_links: number;
    internal_links: number;
    external_links: number;
    broken_links: number;
    healthy_links: number;
    has_broken_links: boolean;
  };
  links: BrokenLinkItem[];
  usage: {
    tool_code: string;
    plan_code: string;
    used_today: number;
    daily_limit: number | string;
    remaining_today: number | string;
  };
}

// --- TOOL 10: AMHARIC FIDEL NORMALIZER INTERFACES ---
export interface AmharicNormalizerInput {
  text: string;
  comparison_text?: string;
}

export interface AmharicTransformation {
  position: number;
  original: string;
  replacement: string;
  type: string;
  description: string;
}

export interface AmharicNormalizerResult {
  original_text: string;
  normalized_text: string;
  has_amharic_script: boolean;
  modifications_count: number;
  transformations_applied: AmharicTransformation[];
  comparison_text?: string | null;
  normalized_comparison?: string | null;
  is_equivalent?: boolean | null;
  metrics: {
    original_length: number;
    normalized_length: number;
    original_words: number;
    normalized_words: number;
  };
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
    serp_snippet_checker: ToolUsageStat;
    pagespeed_analyzer: ToolUsageStat;
    broken_link_checker: ToolUsageStat;
    amharic_normalizer: ToolUsageStat;
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

  analyzeSerpSnippet: async (payload: SerpSnippetInput): Promise<SerpSnippetResult> => {
    return apiFetch<SerpSnippetResult>('/api/seo/tools/serp-snippet/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  analyzePageSpeed: async (payload: PageSpeedInput): Promise<PageSpeedResult> => {
    return apiFetch<PageSpeedResult>('/api/seo/tools/pagespeed/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  checkBrokenLinks: async (payload: BrokenLinksInput): Promise<BrokenLinksResult> => {
    return apiFetch<BrokenLinksResult>('/api/seo/tools/broken-links/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  normalizeAmharic: async (payload: AmharicNormalizerInput): Promise<AmharicNormalizerResult> => {
    return apiFetch<AmharicNormalizerResult>('/api/seo/tools/amharic-normalizer/', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};

