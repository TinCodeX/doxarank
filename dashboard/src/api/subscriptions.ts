import { apiFetch } from './client';
import type { UserSubscriptionSummary } from '../types/subscription';

export const getUserSubscription = async (): Promise<UserSubscriptionSummary> => {
  return await apiFetch<UserSubscriptionSummary>('/api/subscriptions/me/');
};

export const getPlans = async (): Promise<any[]> => {
  return await apiFetch<any[]>('/api/subscriptions/plans/');
};
