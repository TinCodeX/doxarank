from django.urls import path
from .views import (
    PlanListView,
    UserSubscriptionSummaryView,
    ToolUsageCheckView,
    SubscriptionPlanAssignView,
    CheckoutView,
    PaymentDetailView,
    PaymentVerifyView,
    PaymentListView,
    DoxaWebhookView,
)

app_name = 'subscriptions'

urlpatterns = [
    path('plans/', PlanListView.as_view(), name='plan-list'),
    path('me/', UserSubscriptionSummaryView.as_view(), name='subscription-me'),
    path('tools/check/', ToolUsageCheckView.as_view(), name='tool-usage-check'),
    path('assign/', SubscriptionPlanAssignView.as_view(), name='plan-assign'),
    path('checkout/', CheckoutView.as_view(), name='subscription-checkout'),
    path('payments/', PaymentListView.as_view(), name='payment-list'),
    path('payments/<str:pk_or_ref>/', PaymentDetailView.as_view(), name='payment-detail'),
    path('payments/<str:pk_or_ref>/verify/', PaymentVerifyView.as_view(), name='payment-verify'),
    path('webhooks/doxa/', DoxaWebhookView.as_view(), name='webhook-doxa'),
]

