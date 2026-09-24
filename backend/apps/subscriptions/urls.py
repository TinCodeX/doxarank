from django.urls import path
from .views import (
    PlanListView,
    UserSubscriptionSummaryView,
    ToolUsageCheckView,
    SubscriptionPlanAssignView
)

app_name = 'subscriptions'

urlpatterns = [
    path('plans/', PlanListView.as_view(), name='plan-list'),
    path('me/', UserSubscriptionSummaryView.as_view(), name='subscription-me'),
    path('tools/check/', ToolUsageCheckView.as_view(), name='tool-usage-check'),
    path('assign/', SubscriptionPlanAssignView.as_view(), name='plan-assign'),
]
