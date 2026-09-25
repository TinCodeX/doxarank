from django.urls import path
from apps.integrations.views import (
    GoogleConnectView,
    GoogleCallbackView,
    IntegrationStatusView,
    GoogleDisconnectView,
    SearchConsolePropertiesView,
    SearchConsoleAssociatePropertyView,
    GA4PropertiesView,
    GA4AssociatePropertyView,
    GA4ProjectConnectionView,
)

app_name = 'integrations'

urlpatterns = [
    # Status
    path('status/', IntegrationStatusView.as_view(), name='integration-status'),

    # Google OAuth
    path('google/connect/', GoogleConnectView.as_view(), name='google-connect'),
    path('google/callback/', GoogleCallbackView.as_view(), name='google-callback'),
    path('google/disconnect/', GoogleDisconnectView.as_view(), name='google-disconnect'),

    # Google Search Console
    path('google/search-console/properties/', SearchConsolePropertiesView.as_view(), name='search-console-properties'),
    path('google/search-console/associate/', SearchConsoleAssociatePropertyView.as_view(), name='search-console-associate'),

    # Google Analytics 4 (GA4)
    path('google/analytics/properties/', GA4PropertiesView.as_view(), name='ga4-properties'),
    path('google/analytics/associate/', GA4AssociatePropertyView.as_view(), name='ga4-associate'),
    path('google/analytics/project/', GA4ProjectConnectionView.as_view(), name='ga4-project-connection'),
]
