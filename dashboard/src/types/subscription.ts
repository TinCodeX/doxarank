export interface PlanSummary {
  code: 'FREE' | 'STARTER' | 'AGENCY' | string;
  name: string;
  monthly_price: string;
  currency: string;
  basic_tool_daily_limit: number;
  is_tool_unlimited: boolean;
  features: string[];
}

export interface SubscriptionStatusInfo {
  status: string;
  started_at: string;
  current_period_end: string | null;
  is_active: boolean;
}

export interface ResourceQuota {
  current: number;
  limit: number;
  remaining: number;
}

export interface UserSubscriptionSummary {
  plan: PlanSummary;
  subscription: SubscriptionStatusInfo;
  usage: {
    projects: ResourceQuota;
    keywords: ResourceQuota;
    tools_today: Array<{ tool_code: string; count: number }>;
  };
}
