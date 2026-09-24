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

export interface SEOToolsQuotaStatus {
  plan_code: string;
  daily_limit: number | string;
  tools: {
    meta_tag_generator: {
      used_today: number;
      remaining: number | string;
    };
    schema_generator: {
      used_today: number;
      remaining: number | string;
    };
    open_graph_previewer: {
      used_today: number;
      remaining: number | string;
    };
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
};
