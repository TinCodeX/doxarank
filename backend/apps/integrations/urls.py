from django.urls import path
from apps.integrations.views import (
    GoogleConnectView,
    GoogleCallbackView,
    IntegrationStatusView,
    GoogleDisconnectView,
    SearchConsolePropertiesView,
    SearchConsoleAssociatePropertyView,
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
]
