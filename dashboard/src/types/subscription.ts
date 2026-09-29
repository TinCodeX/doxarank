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

export interface PaymentTransaction {
  id: number;
  checkout_reference: string;
  plan: PlanSummary;
  plan_code: string;
  plan_name: string;
  amount: string;
  currency: string;
  provider: string;
  provider_transaction_id: string | null;
  status: 'PENDING' | 'SUCCESS' | 'FAILED' | 'CANCELLED' | 'REFUNDED';
  checkout_url: string;
  metadata?: Record<string, unknown>;
  error_message?: string;
  paid_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserSubscriptionSummary {
  plan: PlanSummary;
  subscription: SubscriptionStatusInfo;
  usage: {
    projects: ResourceQuota;
    keywords: ResourceQuota;
    tools_today: Array<{ tool_code: string; count: number }>;
  };
  latest_payment?: {
    id: number;
    checkout_reference: string;
    status: string;
    amount: string;
    currency: string;
    paid_at: string | null;
    plan_code: string;
    checkout_url?: string;
  } | null;
}

