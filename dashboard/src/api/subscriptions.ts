import { apiFetch } from './client';
import type { UserSubscriptionSummary, PaymentTransaction, PlanSummary } from '../types/subscription';

export const getUserSubscription = async (): Promise<UserSubscriptionSummary> => {
  return await apiFetch<UserSubscriptionSummary>('/api/subscriptions/me/');
};

export const getPlans = async (): Promise<PlanSummary[]> => {
  return await apiFetch<PlanSummary[]>('/api/subscriptions/plans/');
};

export const createCheckoutSession = async (
  planCode: string,
  returnUrl?: string,
  cancelUrl?: string
): Promise<PaymentTransaction> => {
  return await apiFetch<PaymentTransaction>('/api/subscriptions/checkout/', {
    method: 'POST',
    body: JSON.stringify({
      plan_code: planCode,
      return_url: returnUrl || window.location.href,
      cancel_url: cancelUrl || window.location.href,
    }),
  });
};

export const getPayment = async (idOrRef: string | number): Promise<PaymentTransaction> => {
  return await apiFetch<PaymentTransaction>(`/api/subscriptions/payments/${idOrRef}/`);
};

export const verifyPayment = async (
  idOrRef: string | number,
  payload?: Record<string, unknown>
): Promise<PaymentTransaction> => {
  return await apiFetch<PaymentTransaction>(`/api/subscriptions/payments/${idOrRef}/verify/`, {
    method: 'POST',
    body: JSON.stringify({ payload: payload || { status: 'SUCCESS' } }),
  });
};

export const getPaymentHistory = async (): Promise<PaymentTransaction[]> => {
  return await apiFetch<PaymentTransaction[]>('/api/subscriptions/payments/');
};

