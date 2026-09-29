import React, { useState, useEffect } from 'react';
import type { UserSubscriptionSummary, PlanSummary, PaymentTransaction } from '../types/subscription';
import { getPlans, createCheckoutSession, verifyPayment, getPaymentHistory } from '../api/subscriptions';

interface SubscriptionModalProps {
  isOpen: boolean;
  onClose: () => void;
  subscriptionSummary: UserSubscriptionSummary | null;
  onSubscriptionUpdated: () => void;
}

export const SubscriptionModal: React.FC<SubscriptionModalProps> = ({
  isOpen,
  onClose,
  subscriptionSummary,
  onSubscriptionUpdated,
}) => {
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [activeTab, setActiveTab] = useState<'plans' | 'checkout' | 'history'>('plans');
  const [isLoadingPlans, setIsLoadingPlans] = useState(false);
  const [checkoutTx, setCheckoutTx] = useState<PaymentTransaction | null>(null);
  const [isProcessingCheckout, setIsProcessingCheckout] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [paymentHistory, setPaymentHistory] = useState<PaymentTransaction[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  const loadPlans = React.useCallback(async () => {
    setIsLoadingPlans(true);
    try {
      const data = await getPlans();
      setPlans(data);
    } catch (err: unknown) {
      console.error('Failed to load plans:', err);
    } finally {
      setIsLoadingPlans(false);
    }
  }, []);

  const loadHistory = React.useCallback(async () => {
    setIsLoadingHistory(true);
    try {
      const history = await getPaymentHistory();
      setPaymentHistory(history);
    } catch (err: unknown) {
      console.error('Failed to load payment history:', err);
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      queueMicrotask(() => {
        loadPlans();
        loadHistory();
      });
    }
  }, [isOpen, loadPlans, loadHistory]);

  const handleInitiateCheckout = async (planCode: string) => {
    setIsProcessingCheckout(true);
    setActionMessage(null);
    try {
      const tx = await createCheckoutSession(planCode);
      setCheckoutTx(tx);
      setActiveTab('checkout');
      setActionMessage({
        type: 'info',
        text: `Checkout created for ${tx.plan_name} (${tx.amount} ${tx.currency}). Proceed with Doxa Payments settlement.`,
      });
    } catch (err: unknown) {
      const error = err as { data?: { detail?: string }; message?: string };
      setActionMessage({
        type: 'error',
        text: error?.data?.detail || error?.message || 'Failed to initiate checkout. Please try again.',
      });
    } finally {
      setIsProcessingCheckout(false);
    }
  };

  const handleVerifyCheckout = async () => {
    if (!checkoutTx) return;
    setIsVerifying(true);
    setActionMessage(null);
    try {
      const updated = await verifyPayment(checkoutTx.id, { status: 'SUCCESS' });
      setCheckoutTx(updated);
      if (updated.status === 'SUCCESS') {
        setActionMessage({
          type: 'success',
          text: `Payment verified! You are now subscribed to the ${updated.plan_name} plan.`,
        });
        onSubscriptionUpdated();
        loadHistory();
      } else if (updated.status === 'FAILED') {
        setActionMessage({
          type: 'error',
          text: `Payment verification indicated failure: ${updated.error_message || 'Payment not settled.'}`,
        });
      } else {
        setActionMessage({
          type: 'info',
          text: 'Payment is still pending settlement with Doxa Payments.',
        });
      }
    } catch (err: unknown) {
      const error = err as { data?: { detail?: string }; message?: string };
      setActionMessage({
        type: 'error',
        text: error?.data?.detail || error?.message || 'Verification check failed.',
      });
    } finally {
      setIsVerifying(false);
    }
  };

  if (!isOpen) return null;

  const currentPlanCode = subscriptionSummary?.plan?.code || 'FREE';

  const starterPlan = plans.find((p) => p.code === 'STARTER');
  const agencyPlan = plans.find((p) => p.code === 'AGENCY');
  const starterPrice = starterPlan
    ? `${starterPlan.currency} ${Number(starterPlan.monthly_price).toLocaleString()}`
    : 'ETB 1,500';
  const agencyPrice = agencyPlan
    ? `${agencyPlan.currency} ${Number(agencyPlan.monthly_price).toLocaleString()}`
    : 'ETB 6,000';

  return (
    <div
      id="subscription-modal-backdrop"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.75)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: '16px',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        id="subscription-modal-container"
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '16px',
          width: '100%',
          maxWidth: '960px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          overflow: 'hidden',
          fontFamily: 'system-ui, -apple-system, sans-serif',
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'linear-gradient(to right, #f8fafc, #ffffff)',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '20px' }}>💳</span>
              <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>
                Subscription & Billing
              </h2>
            </div>
            <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#64748b' }}>
              Doxa Payments integration for Ethiopia-first SEO tiers. Authoritative server pricing.
            </p>
          </div>

          <button
            id="close-subscription-modal-btn"
            onClick={onClose}
            style={{
              background: '#f1f5f9',
              border: 'none',
              borderRadius: '8px',
              padding: '6px 12px',
              fontSize: '14px',
              fontWeight: 600,
              cursor: 'pointer',
              color: '#475569',
            }}
          >
            ✕ Close
          </button>
        </div>

        {/* Tab Navigation */}
        <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', padding: '0 24px', gap: '24px' }}>
          <button
            id="tab-plans-btn"
            onClick={() => setActiveTab('plans')}
            style={{
              padding: '12px 4px',
              border: 'none',
              background: 'none',
              borderBottom: activeTab === 'plans' ? '2px solid #2563eb' : '2px solid transparent',
              fontWeight: activeTab === 'plans' ? 700 : 500,
              color: activeTab === 'plans' ? '#2563eb' : '#64748b',
              cursor: 'pointer',
              fontSize: '14px',
            }}
          >
            Plans & Pricing
          </button>
          {checkoutTx && (
            <button
              id="tab-checkout-btn"
              onClick={() => setActiveTab('checkout')}
              style={{
                padding: '12px 4px',
                border: 'none',
                background: 'none',
                borderBottom: activeTab === 'checkout' ? '2px solid #2563eb' : '2px solid transparent',
                fontWeight: activeTab === 'checkout' ? 700 : 500,
                color: activeTab === 'checkout' ? '#2563eb' : '#64748b',
                cursor: 'pointer',
                fontSize: '14px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span>Active Checkout</span>
              <span
                style={{
                  padding: '2px 6px',
                  borderRadius: '10px',
                  fontSize: '11px',
                  backgroundColor: checkoutTx.status === 'SUCCESS' ? '#dcfce7' : '#fef3c7',
                  color: checkoutTx.status === 'SUCCESS' ? '#166534' : '#92400e',
                  fontWeight: 700,
                }}
              >
                {checkoutTx.status}
              </span>
            </button>
          )}
          <button
            id="tab-history-btn"
            onClick={() => setActiveTab('history')}
            style={{
              padding: '12px 4px',
              border: 'none',
              background: 'none',
              borderBottom: activeTab === 'history' ? '2px solid #2563eb' : '2px solid transparent',
              fontWeight: activeTab === 'history' ? 700 : 500,
              color: activeTab === 'history' ? '#2563eb' : '#64748b',
              cursor: 'pointer',
              fontSize: '14px',
            }}
          >
            Payment History
          </button>
        </div>

        {/* Global Feedback Banner */}
        {actionMessage && (
          <div
            id="subscription-action-message"
            style={{
              margin: '16px 24px 0 24px',
              padding: '12px 16px',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: 500,
              backgroundColor:
                actionMessage.type === 'success'
                  ? '#f0fdf4'
                  : actionMessage.type === 'error'
                  ? '#fef2f2'
                  : '#eff6ff',
              border: `1px solid ${
                actionMessage.type === 'success'
                  ? '#bbf7d0'
                  : actionMessage.type === 'error'
                  ? '#fecaca'
                  : '#bfdbfe'
              }`,
              color:
                actionMessage.type === 'success'
                  ? '#166534'
                  : actionMessage.type === 'error'
                  ? '#991b1b'
                  : '#1e40af',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>{actionMessage.text}</span>
            <button
              onClick={() => setActionMessage(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }}
            >
              ✕
            </button>
          </div>
        )}

        {/* Modal Body */}
        <div style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
          {activeTab === 'plans' && (
            <div>
              {/* Current Active Plan Status Banner */}
              <div
                style={{
                  padding: '16px',
                  borderRadius: '12px',
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  marginBottom: '24px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '12px',
                }}
              >
                <div>
                  <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>
                    Current Subscription
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '4px' }}>
                    <span style={{ fontSize: '18px', fontWeight: 800, color: '#0f172a' }}>
                      {subscriptionSummary?.plan?.name || 'Free'} Plan
                    </span>
                    <span
                      style={{
                        padding: '3px 8px',
                        borderRadius: '6px',
                        fontSize: '11px',
                        fontWeight: 700,
                        backgroundColor:
                          subscriptionSummary?.subscription?.is_active ? '#dcfce7' : '#fee2e2',
                        color:
                          subscriptionSummary?.subscription?.is_active ? '#166534' : '#991b1b',
                      }}
                    >
                      {subscriptionSummary?.subscription?.status?.toUpperCase() || 'ACTIVE'}
                    </span>
                  </div>
                </div>

                <div style={{ fontSize: '13px', color: '#475569' }}>
                  {subscriptionSummary?.subscription?.current_period_end ? (
                    <span>
                      Renews / Expires:{' '}
                      <strong>
                        {new Date(subscriptionSummary.subscription.current_period_end).toLocaleDateString()}
                      </strong>
                    </span>
                  ) : (
                    <span>Free perpetual tier</span>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '16px', fontSize: '12px', color: '#64748b' }}>
                  <div>
                    Sites:{' '}
                    <strong>{subscriptionSummary?.usage?.projects?.current || 0}</strong>/
                    {subscriptionSummary?.usage?.projects?.limit || 1}
                  </div>
                  <div>
                    Keywords:{' '}
                    <strong>{subscriptionSummary?.usage?.keywords?.current || 0}</strong>/
                    {subscriptionSummary?.usage?.keywords?.limit || 3}
                  </div>
                </div>
              </div>

              {/* Plans Comparison Grid */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                  gap: '20px',
                }}
              >
                {/* 1. FREE PLAN */}
                <div
                  id="plan-card-free"
                  style={{
                    borderRadius: '12px',
                    border: currentPlanCode === 'FREE' ? '2px solid #3b82f6' : '1px solid #e2e8f0',
                    padding: '20px',
                    backgroundColor: '#ffffff',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                      Free
                    </h3>
                    <div style={{ margin: '12px 0', fontSize: '28px', fontWeight: 800, color: '#0f172a' }}>
                      ETB 0
                      <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}> / month</span>
                    </div>
                    <p style={{ fontSize: '13px', color: '#64748b', marginBottom: '16px' }}>
                      Basic tools for freelancers and early testing in Ethiopia.
                    </p>

                    <div style={{ borderTop: '1px solid #f1f5f9', paddingTop: '16px', fontSize: '13px' }}>
                      <div style={{ marginBottom: '8px' }}>✓ <strong>1</strong> tracked website</div>
                      <div style={{ marginBottom: '8px' }}>✓ <strong>3</strong> keywords</div>
                      <div style={{ marginBottom: '8px' }}>✓ <strong>5</strong> daily SEO tool runs</div>
                      <div style={{ marginBottom: '8px', color: '#94a3b8' }}>✕ No rank tracking</div>
                      <div style={{ marginBottom: '8px', color: '#94a3b8' }}>✕ No GSC / GA4 integrations</div>
                      <div style={{ color: '#94a3b8' }}>✕ No technical crawler</div>
                    </div>
                  </div>

                  <button
                    disabled={currentPlanCode === 'FREE'}
                    style={{
                      marginTop: '20px',
                      padding: '10px 16px',
                      borderRadius: '8px',
                      border: 'none',
                      backgroundColor: currentPlanCode === 'FREE' ? '#f1f5f9' : '#e2e8f0',
                      color: currentPlanCode === 'FREE' ? '#0f172a' : '#475569',
                      fontWeight: 600,
                      cursor: currentPlanCode === 'FREE' ? 'default' : 'not-allowed',
                      width: '100%',
                    }}
                  >
                    {currentPlanCode === 'FREE' ? 'Current Plan' : 'Free Tier'}
                  </button>
                </div>

                {/* 2. STARTER PLAN */}
                <div
                  id="plan-card-starter"
                  style={{
                    borderRadius: '12px',
                    border: currentPlanCode === 'STARTER' ? '2px solid #2563eb' : '1px solid #cbd5e1',
                    padding: '20px',
                    backgroundColor: '#ffffff',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)',
                    position: 'relative',
                  }}
                >
                  <div
                    style={{
                      position: 'absolute',
                      top: '-10px',
                      right: '16px',
                      backgroundColor: '#2563eb',
                      color: '#ffffff',
                      fontSize: '11px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '10px',
                      textTransform: 'uppercase',
                    }}
                  >
                    Popular
                  </div>

                  <div>
                    <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                      Starter
                    </h3>
                    <div style={{ margin: '12px 0', fontSize: '28px', fontWeight: 800, color: '#1d4ed8' }}>
                      {isLoadingPlans ? '...' : starterPrice}
                      <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}> / month</span>
                    </div>
                    <p style={{ fontSize: '13px', color: '#64748b', marginBottom: '16px' }}>
                      Complete rank tracking & analytics integrations for growing Ethiopian brands.
                    </p>

                    <div style={{ borderTop: '1px solid #f1f5f9', paddingTop: '16px', fontSize: '13px' }}>
                      <div style={{ marginBottom: '8px' }}>✓ <strong>3</strong> tracked websites</div>
                      <div style={{ marginBottom: '8px' }}>✓ <strong>50</strong> keywords on google.com.et</div>
                      <div style={{ marginBottom: '8px' }}>✓ <strong>Unlimited</strong> tool usage</div>
                      <div style={{ marginBottom: '8px' }}>✓ Daily Google Ethiopia rank tracker</div>
                      <div style={{ marginBottom: '8px' }}>✓ GSC, GA4, Clarity & GTM OAuth</div>
                      <div style={{ marginBottom: '8px' }}>✓ Technical site audit crawler</div>
                      <div style={{ color: '#94a3b8' }}>✕ Competitor SERP snapshots</div>
                    </div>
                  </div>

                  <button
                    id="upgrade-starter-btn"
                    onClick={() => handleInitiateCheckout('STARTER')}
                    disabled={isProcessingCheckout}
                    style={{
                      marginTop: '20px',
                      padding: '10px 16px',
                      borderRadius: '8px',
                      border: 'none',
                      backgroundColor: currentPlanCode === 'STARTER' ? '#3b82f6' : '#2563eb',
                      color: '#ffffff',
                      fontWeight: 600,
                      cursor: isProcessingCheckout ? 'not-allowed' : 'pointer',
                      width: '100%',
                    }}
                  >
                    {currentPlanCode === 'STARTER' ? 'Renew / Extend Starter' : 'Upgrade to Starter'}
                  </button>
                </div>

                {/* 3. AGENCY PLAN */}
                <div
                  id="plan-card-agency"
                  style={{
                    borderRadius: '12px',
                    border: currentPlanCode === 'AGENCY' ? '2px solid #7c3aed' : '1px solid #cbd5e1',
                    padding: '20px',
                    backgroundColor: '#ffffff',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                      Agency
                    </h3>
                    <div style={{ margin: '12px 0', fontSize: '28px', fontWeight: 800, color: '#6d28d9' }}>
                      {isLoadingPlans ? '...' : agencyPrice}
                      <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}> / month</span>
                    </div>
                    <p style={{ fontSize: '13px', color: '#64748b', marginBottom: '16px' }}>
                      Enterprise power for agencies managing client portfolios with competitor intelligence.
                    </p>

                    <div style={{ borderTop: '1px solid #f1f5f9', paddingTop: '16px', fontSize: '13px' }}>
                      <div style={{ marginBottom: '8px' }}>✓ <strong>20</strong> tracked websites</div>
                      <div style={{ marginBottom: '8px' }}>✓ <strong>500</strong> keywords</div>
                      <div style={{ marginBottom: '8px' }}>✓ Everything in Starter tier</div>
                      <div style={{ marginBottom: '8px' }}>✓ Weekly Competitor SERP snapshots</div>
                      <div style={{ marginBottom: '8px' }}>✓ White-label PDF reporting</div>
                      <div style={{ marginBottom: '8px' }}>✓ Multi-site audit automation</div>
                    </div>
                  </div>

                  <button
                    id="upgrade-agency-btn"
                    onClick={() => handleInitiateCheckout('AGENCY')}
                    disabled={isProcessingCheckout}
                    style={{
                      marginTop: '20px',
                      padding: '10px 16px',
                      borderRadius: '8px',
                      border: 'none',
                      backgroundColor: '#7c3aed',
                      color: '#ffffff',
                      fontWeight: 600,
                      cursor: isProcessingCheckout ? 'not-allowed' : 'pointer',
                      width: '100%',
                    }}
                  >
                    {currentPlanCode === 'AGENCY' ? 'Renew / Extend Agency' : 'Upgrade to Agency'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'checkout' && checkoutTx && (
            <div id="checkout-session-panel" style={{ maxWidth: '600px', margin: '0 auto' }}>
              <div
                style={{
                  padding: '24px',
                  borderRadius: '12px',
                  border: '1px solid #e2e8f0',
                  backgroundColor: '#ffffff',
                  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                    Order Details
                  </h3>
                  <span
                    id="checkout-status-badge"
                    style={{
                      padding: '4px 10px',
                      borderRadius: '8px',
                      fontSize: '12px',
                      fontWeight: 700,
                      backgroundColor:
                        checkoutTx.status === 'SUCCESS'
                          ? '#dcfce7'
                          : checkoutTx.status === 'FAILED'
                          ? '#fee2e2'
                          : '#fef3c7',
                      color:
                        checkoutTx.status === 'SUCCESS'
                          ? '#166534'
                          : checkoutTx.status === 'FAILED'
                          ? '#991b1b'
                          : '#92400e',
                    }}
                  >
                    {checkoutTx.status}
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '14px', borderBottom: '1px solid #f1f5f9', paddingBottom: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#64748b' }}>Plan Tier:</span>
                    <span style={{ fontWeight: 600 }}>{checkoutTx.plan_name}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#64748b' }}>Billing Cycle:</span>
                    <span>30 Days (Monthly)</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#64748b' }}>Payment Provider:</span>
                    <span style={{ textTransform: 'capitalize' }}>{checkoutTx.provider} Payments</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: '#64748b' }}>Reference ID:</span>
                    <span style={{ fontFamily: 'monospace', fontSize: '12px', color: '#475569' }}>
                      {checkoutTx.checkout_reference}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '16px', fontWeight: 700, color: '#0f172a', paddingTop: '8px', borderTop: '1px solid #f8fafc' }}>
                    <span>Amount Due:</span>
                    <span style={{ color: '#2563eb' }}>
                      {checkoutTx.amount} {checkoutTx.currency}
                    </span>
                  </div>
                </div>

                {/* Supported Payment Channels */}
                <div style={{ margin: '16px 0', padding: '12px', borderRadius: '8px', backgroundColor: '#f8fafc', fontSize: '12px', color: '#475569' }}>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>Supported Ethiopian Channels:</div>
                  <div>📱 Telebirr • 🏦 Commercial Bank of Ethiopia (CBE Birr) • 💳 Chapa / Awash / Stripe</div>
                </div>

                {/* Actions */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '20px' }}>
                  {checkoutTx.status === 'PENDING' ? (
                    <>
                      <button
                        id="verify-payment-btn"
                        onClick={handleVerifyCheckout}
                        disabled={isVerifying}
                        style={{
                          padding: '12px',
                          borderRadius: '8px',
                          border: 'none',
                          backgroundColor: '#10b981',
                          color: '#ffffff',
                          fontWeight: 700,
                          fontSize: '14px',
                          cursor: isVerifying ? 'not-allowed' : 'pointer',
                        }}
                      >
                        {isVerifying ? 'Verifying with Gateway...' : '✓ Confirm & Verify Payment'}
                      </button>

                      <button
                        onClick={() => setActiveTab('plans')}
                        style={{
                          padding: '10px',
                          borderRadius: '8px',
                          border: '1px solid #cbd5e1',
                          backgroundColor: '#ffffff',
                          color: '#475569',
                          fontWeight: 600,
                          fontSize: '13px',
                          cursor: 'pointer',
                        }}
                      >
                        ← Back to Plans
                      </button>
                    </>
                  ) : checkoutTx.status === 'SUCCESS' ? (
                    <div style={{ textAlign: 'center', padding: '16px 0' }}>
                      <div style={{ fontSize: '32px', marginBottom: '8px' }}>🎉</div>
                      <div style={{ fontSize: '16px', fontWeight: 700, color: '#166534', marginBottom: '12px' }}>
                        Subscription Active!
                      </div>
                      <button
                        onClick={onClose}
                        style={{
                          padding: '10px 20px',
                          borderRadius: '8px',
                          border: 'none',
                          backgroundColor: '#2563eb',
                          color: '#ffffff',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        Return to Dashboard
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => handleInitiateCheckout(checkoutTx.plan_code)}
                      style={{
                        padding: '12px',
                        borderRadius: '8px',
                        border: 'none',
                        backgroundColor: '#ef4444',
                        color: '#ffffff',
                        fontWeight: 700,
                        cursor: 'pointer',
                      }}
                    >
                      ↺ Retry Payment
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'history' && (
            <div>
              <h3 style={{ margin: '0 0 16px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                Your Payment History
              </h3>

              {isLoadingHistory ? (
                <div style={{ textAlign: 'center', padding: '32px', color: '#64748b', fontSize: '14px' }}>
                  Loading payment history...
                </div>
              ) : paymentHistory.length === 0 ? (
                <div
                  style={{
                    padding: '32px',
                    textAlign: 'center',
                    border: '1px dashed #cbd5e1',
                    borderRadius: '12px',
                    color: '#64748b',
                    fontSize: '14px',
                  }}
                >
                  No payment transactions recorded yet.
                </div>
              ) : (
                <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
                    <thead>
                      <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569' }}>
                        <th style={{ padding: '10px 14px' }}>Date</th>
                        <th style={{ padding: '10px 14px' }}>Reference</th>
                        <th style={{ padding: '10px 14px' }}>Plan</th>
                        <th style={{ padding: '10px 14px' }}>Amount</th>
                        <th style={{ padding: '10px 14px' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paymentHistory.map((tx) => (
                        <tr key={tx.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={{ padding: '10px 14px', color: '#64748b' }}>
                            {new Date(tx.created_at).toLocaleDateString()}
                          </td>
                          <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontSize: '12px' }}>
                            {tx.checkout_reference}
                          </td>
                          <td style={{ padding: '10px 14px', fontWeight: 600 }}>
                            {tx.plan_name}
                          </td>
                          <td style={{ padding: '10px 14px', fontWeight: 600, color: '#0f172a' }}>
                            {tx.amount} {tx.currency}
                          </td>
                          <td style={{ padding: '10px 14px' }}>
                            <span
                              style={{
                                padding: '3px 8px',
                                borderRadius: '6px',
                                fontSize: '11px',
                                fontWeight: 700,
                                backgroundColor:
                                  tx.status === 'SUCCESS'
                                    ? '#dcfce7'
                                    : tx.status === 'FAILED'
                                    ? '#fee2e2'
                                    : '#fef3c7',
                                color:
                                  tx.status === 'SUCCESS'
                                    ? '#166534'
                                    : tx.status === 'FAILED'
                                    ? '#991b1b'
                                    : '#92400e',
                              }}
                            >
                              {tx.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
