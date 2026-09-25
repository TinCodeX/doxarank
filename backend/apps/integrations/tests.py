import json
from unittest.mock import patch, MagicMock
from datetime import timedelta

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from googleapiclient.errors import HttpError

from apps.integrations.models import (
    IntegrationConnection,
    IntegrationProvider,
    IntegrationStatus,
    ProjectGA4Connection,
    ProjectClarityConnection,
    ProjectGTMConnection,
)
from apps.integrations.services.google_oauth import (
    GoogleOAuthIntegrationService,
    OAuthStateService,
    InvalidOAuthStateError,
)
from apps.integrations.services.search_console import (
    SearchConsoleIntegrationService,
    SearchConsoleNotConnectedError,
    SearchConsoleCredentialsError,
)
from apps.subscriptions.models import Plan, PlanCode, FeatureCode
from apps.subscriptions.services import SubscriptionService
from apps.projects.models import Project

User = get_user_model()

MOCK_OAUTH_SETTINGS = {
    'GOOGLE_CLIENT_ID': 'mock-test-client-id.apps.googleusercontent.com',
    'GOOGLE_CLIENT_SECRET': 'mock-test-client-secret-xyz123',
    'GOOGLE_REDIRECT_URI': 'http://localhost:5173/integrations/google/callback',
    'MICROSOFT_OAUTH_CLIENT_ID': 'mock-ms-client-id-1234',
    'MICROSOFT_OAUTH_CLIENT_SECRET': 'mock-ms-client-secret-5678',
    'MICROSOFT_OAUTH_REDIRECT_URI': 'http://localhost:5173/integrations/microsoft/callback',
}


@override_settings(**MOCK_OAUTH_SETTINGS)
class GoogleOAuthTests(TestCase):
    """
    Tests for Google OAuth2 connection flow:
    - Authentication enforcement
    - State generation & tampering/replay protection
    - Authorization code exchange
    - Fernet token encryption at rest
    - Token exclusion from serializers
    """

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='Password123!'
        )
        # Assign Starter plan (includes FeatureCode.GSC)
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.client.force_authenticate(user=self.user)

    def test_connect_requires_authentication(self):
        unauth_client = APIClient()
        response = unauth_client.get('/api/integrations/google/connect/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_connect_generates_valid_state_url(self):
        response = self.client.get('/api/integrations/google/connect/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('authorization_url', response.data)
        auth_url = response.data['authorization_url']
        self.assertIn('accounts.google.com', auth_url)
        self.assertIn('mock-test-client-id', auth_url)
        self.assertIn('state=', auth_url)
        self.assertNotIn('mock-test-client-secret-xyz123', auth_url)

    def test_state_verification_succeeds_for_valid_state(self):
        state = OAuthStateService.generate_state(self.user)
        resolved_user, meta = OAuthStateService.verify_state(state, expected_user=self.user)
        self.assertEqual(resolved_user.id, self.user.id)

    def test_state_verification_rejects_tampered_state(self):
        state = OAuthStateService.generate_state(self.user)
        tampered_state = state[:-5] + 'XXXXX'
        with self.assertRaises(InvalidOAuthStateError):
            OAuthStateService.verify_state(tampered_state, expected_user=self.user)

    def test_state_verification_rejects_replayed_state(self):
        state = OAuthStateService.generate_state(self.user)
        # First verification succeeds
        OAuthStateService.verify_state(state, expected_user=self.user)
        # Second verification with same state must fail replay protection
        with self.assertRaises(InvalidOAuthStateError):
            OAuthStateService.verify_state(state, expected_user=self.user)

    def test_callback_handles_google_denial_error(self):
        response = self.client.get('/api/integrations/google/callback/?error=access_denied')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('denied by the user', response.data['detail'])

    def test_callback_rejects_missing_code_or_state(self):
        response = self.client.get('/api/integrations/google/callback/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.integrations.services.google_oauth.GoogleOAuthIntegrationService.fetch_user_identity')
    @patch('apps.integrations.services.google_oauth.GoogleOAuthIntegrationService.exchange_code')
    def test_successful_callback_stores_encrypted_tokens(self, mock_exchange, mock_identity):
        mock_exchange.return_value = {
            'access_token': 'ya29.mock_access_token_secret_123',
            'refresh_token': '1//mock_refresh_token_secret_456',
            'expires_in': 3600,
            'scope': 'https://www.googleapis.com/auth/webmasters.readonly openid'
        }
        mock_identity.return_value = {
            'email': 'gsc_owner@example.com',
            'name': 'GSC Owner',
            'id': 'google-uid-12345',
            'verified_email': True
        }

        state = OAuthStateService.generate_state(self.user)
        response = self.client.get(f'/api/integrations/google/callback/?code=mock_code_123&state={state}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['account_email'], 'gsc_owner@example.com')
        self.assertEqual(response.data['status'], 'connected')

        # Verify connection in DB
        connection = IntegrationConnection.objects.get(user=self.user, provider=IntegrationProvider.GOOGLE)
        self.assertEqual(connection.account_email, 'gsc_owner@example.com')
        self.assertEqual(connection.get_access_token(), 'ya29.mock_access_token_secret_123')
        self.assertEqual(connection.get_refresh_token(), '1//mock_refresh_token_secret_456')

        # Verify tokens are encrypted at rest and not stored in plaintext
        self.assertNotIn('ya29.mock_access_token_secret_123', connection.encrypted_access_token)
        self.assertNotIn('1//mock_refresh_token_secret_456', connection.encrypted_refresh_token)

        # Verify tokens are NEVER in serializer/API response
        response_json = json.dumps(response.data)
        self.assertNotIn('ya29.mock_access_token_secret_123', response_json)
        self.assertNotIn('1//mock_refresh_token_secret_456', response_json)
        self.assertNotIn('encrypted_access_token', response.data)
        self.assertNotIn('encrypted_refresh_token', response.data)

    def test_disconnect_clears_tokens(self):
        conn = IntegrationConnection.objects.create(
            user=self.user,
            provider=IntegrationProvider.GOOGLE,
            status=IntegrationStatus.CONNECTED,
            account_email='disconnect_me@example.com'
        )
        conn.set_access_token('access_secret')
        conn.set_refresh_token('refresh_secret')
        conn.save()

        with patch('requests.post') as mock_revoke:
            mock_revoke.return_value = MagicMock(status_code=200)
            response = self.client.post('/api/integrations/google/disconnect/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conn.refresh_from_db()
        self.assertEqual(conn.status, IntegrationStatus.DISCONNECTED)
        self.assertIsNone(conn.encrypted_access_token)
        self.assertIsNone(conn.encrypted_refresh_token)


@override_settings(**MOCK_OAUTH_SETTINGS)
class SearchConsoleIntegrationTests(TestCase):
    """
    Tests for Search Console integration:
    - Listing properties from Google Search Console API
    - Data normalization
    - Google API error handling
    - Token refresh handling
    - Association with project
    """

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user = User.objects.create_user(
            email='seo_user@example.com',
            password='Password123!'
        )
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.client.force_authenticate(user=self.user)

        self.connection = IntegrationConnection.objects.create(
            user=self.user,
            provider=IntegrationProvider.GOOGLE,
            status=IntegrationStatus.CONNECTED,
            account_email='seo_user@example.com',
            token_expires_at=timezone.now() + timedelta(hours=1)
        )
        self.connection.set_access_token('mock_access_token')
        self.connection.set_refresh_token('mock_refresh_token')
        self.connection.save()

    def test_unauthenticated_request_rejected(self):
        unauth_client = APIClient()
        response = unauth_client.get('/api/integrations/google/search-console/properties/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_disconnected_user_returns_error(self):
        self.connection.status = IntegrationStatus.DISCONNECTED
        self.connection.save()

        response = self.client.get('/api/integrations/google/search-console/properties/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not connected', response.data['detail'].lower())

    @patch('apps.integrations.services.search_console.SearchConsoleIntegrationService.get_client')
    def test_properties_normalized_successfully(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.sites().list().execute.return_value = {
            'siteEntry': [
                {'siteUrl': 'https://example.com/', 'permissionLevel': 'siteOwner'},
                {'siteUrl': 'sc-domain:example.org', 'permissionLevel': 'siteFullUser'},
            ]
        }
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/search-console/properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0], {
            'site_url': 'https://example.com/',
            'permission_level': 'siteOwner'
        })
        self.assertEqual(response.data[1], {
            'site_url': 'sc-domain:example.org',
            'permission_level': 'siteFullUser'
        })

    @patch('apps.integrations.services.search_console.SearchConsoleIntegrationService.get_client')
    def test_empty_properties_handled(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.sites().list().execute.return_value = {}
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/search-console/properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    @patch('apps.integrations.services.search_console.SearchConsoleIntegrationService.get_client')
    def test_google_api_403_error_handled(self, mock_get_client):
        mock_client = MagicMock()
        resp = MagicMock(status=403, reason='Forbidden')
        mock_client.sites().list().execute.side_effect = HttpError(resp=resp, content=b'Permission Denied')
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/search-console/properties/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('permission denied', response.data['detail'].lower())

    @patch('apps.integrations.services.google_oauth.GoogleOAuthIntegrationService.refresh_connection_tokens')
    @patch('apps.integrations.services.search_console.SearchConsoleIntegrationService.get_client')
    def test_token_refresh_invoked_on_expired_token(self, mock_get_client, mock_refresh):
        self.connection.token_expires_at = timezone.now() - timedelta(minutes=5)
        self.connection.save()

        mock_refresh.return_value = self.connection
        mock_client = MagicMock()
        mock_client.sites().list().execute.return_value = {'siteEntry': []}
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/search-console/properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_refresh.assert_called_once()

    @patch('apps.integrations.services.search_console.SearchConsoleIntegrationService.list_properties')
    def test_associate_project_property_success(self, mock_list):
        mock_list.return_value = [
            {'site_url': 'https://example.com/', 'permission_level': 'siteOwner'}
        ]

        project = Project.objects.create(
            owner=self.user,
            name='My Website',
            website_url='https://example.com'
        )

        response = self.client.post('/api/integrations/google/search-console/associate/', data={
            'project_id': project.id,
            'site_url': 'https://example.com/',
            'permission_level': 'siteOwner'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['property_url'], 'https://example.com/')
        self.assertTrue(response.data['is_connected'])


@override_settings(**MOCK_OAUTH_SETTINGS)
class SubscriptionEntitlementTests(TestCase):
    """
    Tests enforcing subscription rules:
    - Free tier rejected (403 FEATURE_NOT_ENTITLED)
    - Starter tier allowed
    - Agency tier allowed
    """

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user = User.objects.create_user(
            email='sub_user@example.com',
            password='Password123!'
        )
        self.client.force_authenticate(user=self.user)

    def test_free_tier_rejected_from_connect(self):
        SubscriptionService.assign_plan(self.user, PlanCode.FREE)
        response = self.client.get('/api/integrations/google/connect/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'FEATURE_NOT_ENTITLED')
        self.assertTrue(response.data['upgrade_required'])

    def test_free_tier_rejected_from_search_console_properties(self):
        SubscriptionService.assign_plan(self.user, PlanCode.FREE)
        response = self.client.get('/api/integrations/google/search-console/properties/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'FEATURE_NOT_ENTITLED')

    def test_starter_tier_allowed_to_connect(self):
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        response = self.client.get('/api/integrations/google/connect/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_agency_tier_allowed_to_connect(self):
        SubscriptionService.assign_plan(self.user, PlanCode.AGENCY)
        response = self.client.get('/api/integrations/google/connect/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(**MOCK_OAUTH_SETTINGS)
class TenantIsolationTests(TestCase):
    """
    Tests ensuring User A cannot access User B's Google connection,
    nor associate User B's properties or projects.
    """

    def setUp(self):
        self.client_a = APIClient()
        self.client_b = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user_a = User.objects.create_user(
            email='usera@example.com', password='Password123!'
        )
        self.user_b = User.objects.create_user(
            email='userb@example.com', password='Password123!'
        )
        SubscriptionService.assign_plan(self.user_a, PlanCode.STARTER)
        SubscriptionService.assign_plan(self.user_b, PlanCode.STARTER)

        self.client_a.force_authenticate(user=self.user_a)
        self.client_b.force_authenticate(user=self.user_b)

        # User A has connected Google account
        self.conn_a = IntegrationConnection.objects.create(
            user=self.user_a,
            provider=IntegrationProvider.GOOGLE,
            status=IntegrationStatus.CONNECTED,
            account_email='usera.google@gmail.com',
            token_expires_at=timezone.now() + timedelta(hours=1)
        )
        self.conn_a.set_access_token('token_user_a')
        self.conn_a.set_refresh_token('refresh_user_a')
        self.conn_a.save()

    def test_user_b_status_does_not_see_user_a_connection(self):
        response_b = self.client_b.get('/api/integrations/status/')
        self.assertEqual(response_b.status_code, status.HTTP_200_OK)
        # User B should see disconnected status
        self.assertFalse(response_b.data['google']['connected'])
        self.assertIsNone(response_b.data['google']['account_email'])

    def test_user_b_cannot_associate_user_a_project(self):
        proj_a = Project.objects.create(
            owner=self.user_a,
            name='User A Site',
            website_url='https://usera.com'
        )

        response_b = self.client_b.post('/api/integrations/google/search-console/associate/', data={
            'project_id': proj_a.id,
            'site_url': 'https://usera.com'
        })
        self.assertEqual(response_b.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not found or you do not have permission', response_b.data['detail'].lower())

    def test_callback_state_bound_to_user_a_rejects_user_b(self):
        state_for_a = OAuthStateService.generate_state(self.user_a)
        # User B attempts to complete OAuth callback with User A's state
        response = self.client_b.get(f'/api/integrations/google/callback/?code=test_code&state={state_for_a}')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('does not match the currently authenticated user', response.data['detail'])

    def test_user_b_cannot_associate_user_a_project_with_ga4(self):
        proj_a = Project.objects.create(
            owner=self.user_a,
            name='User A Project',
            website_url='https://usera.com'
        )

        response_b = self.client_b.post('/api/integrations/google/analytics/associate/', data={
            'project_id': proj_a.id,
            'property_id': '987654321',
            'display_name': 'Hacked Property'
        })
        self.assertEqual(response_b.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not found or you do not have permission', response_b.data['detail'].lower())

    def test_user_b_cannot_view_user_a_project_ga4_connection(self):
        proj_a = Project.objects.create(
            owner=self.user_a,
            name='User A Project',
            website_url='https://usera.com'
        )
        response_b = self.client_b.get(f'/api/integrations/google/analytics/project/?project_id={proj_a.id}')
        # Should report no connection or not found
        self.assertFalse(response_b.data.get('is_connected', False))


@override_settings(**MOCK_OAUTH_SETTINGS)
class GA4IntegrationTests(TestCase):
    """
    Tests for Google Analytics 4 (GA4) integration:
    - OAuth scope detection and missing scope handling
    - Reauthorization scope merging
    - Listing GA4 properties
    - Normalization of Google Analytics Admin API response
    - Error handling (401, 403, 429, 500)
    - Token refresh handling
    - Project association with GA4 property
    """

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user = User.objects.create_user(
            email='ga4_user@example.com',
            password='Password123!'
        )
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.client.force_authenticate(user=self.user)

        self.connection = IntegrationConnection.objects.create(
            user=self.user,
            provider=IntegrationProvider.GOOGLE,
            status=IntegrationStatus.CONNECTED,
            account_email='ga4_user@example.com',
            scopes=[
                'https://www.googleapis.com/auth/webmasters.readonly',
                'https://www.googleapis.com/auth/analytics.readonly',
                'openid',
                'https://www.googleapis.com/auth/userinfo.email',
            ],
            token_expires_at=timezone.now() + timedelta(hours=1)
        )
        self.connection.set_access_token('mock_ga4_access_token')
        self.connection.set_refresh_token('mock_ga4_refresh_token')
        self.connection.save()

    def test_unauthenticated_request_rejected(self):
        unauth_client = APIClient()
        response = unauth_client.get('/api/integrations/google/analytics/properties/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_disconnected_user_returns_error(self):
        self.connection.status = IntegrationStatus.DISCONNECTED
        self.connection.save()

        response = self.client.get('/api/integrations/google/analytics/properties/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('code'), 'NOT_CONNECTED')

    def test_missing_analytics_scope_handled(self):
        # Connection only has Search Console scope, missing analytics.readonly
        self.connection.scopes = ['https://www.googleapis.com/auth/webmasters.readonly']
        self.connection.save()

        response = self.client.get('/api/integrations/google/analytics/properties/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'ANALYTICS_SCOPE_MISSING')
        self.assertIn('reconnect your google account', response.data['detail'].lower())

    @patch('apps.integrations.services.google_oauth.GoogleOAuthIntegrationService.fetch_user_identity')
    @patch('apps.integrations.services.google_oauth.GoogleOAuthIntegrationService.exchange_code')
    def test_reauthorization_merges_scopes_safely(self, mock_exchange, mock_identity):
        # Existing connection with GSC scope only
        self.connection.scopes = ['https://www.googleapis.com/auth/webmasters.readonly']
        self.connection.save()

        # Reauthorization callback granting analytics.readonly
        mock_exchange.return_value = {
            'access_token': 'new_access_token',
            'refresh_token': 'new_refresh_token',
            'expires_in': 3600,
            'scope': 'https://www.googleapis.com/auth/analytics.readonly'
        }
        mock_identity.return_value = {
            'email': 'ga4_user@example.com',
            'name': 'GA4 User',
            'id': 'google-uid-ga4',
            'verified_email': True
        }

        state = OAuthStateService.generate_state(self.user)
        response = self.client.get(f'/api/integrations/google/callback/?code=reauth_code&state={state}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.connection.refresh_from_db()
        # Verify both scopes exist (non-destructive merge)
        self.assertIn('https://www.googleapis.com/auth/webmasters.readonly', self.connection.scopes)
        self.assertIn('https://www.googleapis.com/auth/analytics.readonly', self.connection.scopes)
        self.assertTrue(self.connection.has_analytics_scope)

    @patch('apps.integrations.services.analytics.GA4IntegrationService.get_client')
    def test_properties_normalized_successfully(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.accountSummaries().list().execute.return_value = {
            'accountSummaries': [
                {
                    'name': 'accountSummaries/12345',
                    'displayName': 'Example Corp',
                    'propertySummaries': [
                        {
                            'property': 'properties/987654321',
                            'displayName': 'Corporate Site',
                            'propertyType': 'PROPERTY_TYPE_ORDINARY'
                        },
                        {
                            'property': 'properties/112233445',
                            'displayName': 'Store Site',
                            'propertyType': 'PROPERTY_TYPE_ORDINARY'
                        }
                    ]
                }
            ]
        }
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/analytics/properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0], {
            'property_id': '987654321',
            'display_name': 'Corporate Site',
            'property_type': 'GA4'
        })
        self.assertEqual(response.data[1], {
            'property_id': '112233445',
            'display_name': 'Store Site',
            'property_type': 'GA4'
        })

    @patch('apps.integrations.services.analytics.GA4IntegrationService.get_client')
    def test_empty_properties_handled(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.accountSummaries().list().execute.return_value = {}
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/analytics/properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    @patch('apps.integrations.services.analytics.GA4IntegrationService.get_client')
    def test_google_api_403_handled(self, mock_get_client):
        mock_client = MagicMock()
        resp = MagicMock(status=403, reason='Forbidden')
        mock_client.accountSummaries().list().execute.side_effect = HttpError(resp=resp, content=b'Permission Denied')
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/analytics/properties/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data.get('code'), 'CREDENTIALS_INVALID')

    @patch('apps.integrations.services.analytics.GA4IntegrationService.get_client')
    def test_google_api_429_rate_limit_handled(self, mock_get_client):
        mock_client = MagicMock()
        resp = MagicMock(status=429, reason='Too Many Requests')
        mock_client.accountSummaries().list().execute.side_effect = HttpError(resp=resp, content=b'Rate Limit Exceeded')
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/analytics/properties/')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data.get('code'), 'RATE_LIMIT_EXCEEDED')

    @patch('apps.integrations.services.analytics.GA4IntegrationService.get_client')
    def test_google_api_500_handled(self, mock_get_client):
        mock_client = MagicMock()
        resp = MagicMock(status=500, reason='Internal Error')
        mock_client.accountSummaries().list().execute.side_effect = HttpError(resp=resp, content=b'Backend Error')
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/analytics/properties/')
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data.get('code'), 'GOOGLE_API_ERROR')

    @patch('apps.integrations.services.google_oauth.GoogleOAuthIntegrationService.refresh_connection_tokens')
    @patch('apps.integrations.services.analytics.GA4IntegrationService.get_client')
    def test_token_refresh_invoked_on_expired_token(self, mock_get_client, mock_refresh):
        self.connection.token_expires_at = timezone.now() - timedelta(minutes=5)
        self.connection.save()

        mock_refresh.return_value = self.connection
        mock_client = MagicMock()
        mock_client.accountSummaries().list().execute.return_value = {'accountSummaries': []}
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/analytics/properties/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_refresh.assert_called_once()

    @patch('apps.integrations.services.analytics.GA4IntegrationService.list_properties')
    def test_associate_project_property_success(self, mock_list):
        mock_list.return_value = [
            {'property_id': '987654321', 'display_name': 'Corporate Site', 'property_type': 'GA4'}
        ]

        project = Project.objects.create(
            owner=self.user,
            name='My Corporate Project',
            website_url='https://example.com'
        )

        response = self.client.post('/api/integrations/google/analytics/associate/', data={
            'project_id': project.id,
            'property_id': '987654321',
            'display_name': 'Corporate Site'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['property_id'], '987654321')
        self.assertTrue(response.data['is_connected'])

        # Check retrieval endpoint
        get_resp = self.client.get(f'/api/integrations/google/analytics/project/?project_id={project.id}')
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(get_resp.data['property_id'], '987654321')
        self.assertTrue(get_resp.data['is_connected'])

    @patch('apps.integrations.services.analytics.GA4IntegrationService.list_properties')
    def test_associate_project_property_rejects_unowned_property(self, mock_list):
        mock_list.return_value = [
            {'property_id': '987654321', 'display_name': 'Corporate Site', 'property_type': 'GA4'}
        ]

        project = Project.objects.create(
            owner=self.user,
            name='My Corporate Project',
            website_url='https://example.com'
        )

        # Attempt to associate a property ID not returned in list_properties
        response = self.client.post('/api/integrations/google/analytics/associate/', data={
            'project_id': project.id,
            'property_id': '999999999',
            'display_name': 'Fake Property'
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not found in your connected google account', response.data['detail'].lower())

    @patch('apps.integrations.services.analytics.GA4IntegrationService.list_properties')
    def test_duplicate_association_updates_safely(self, mock_list):
        mock_list.return_value = [
            {'property_id': '987654321', 'display_name': 'Corporate Site', 'property_type': 'GA4'},
            {'property_id': '112233445', 'display_name': 'Store Site', 'property_type': 'GA4'},
        ]

        project = Project.objects.create(
            owner=self.user,
            name='My Corporate Project',
            website_url='https://example.com'
        )

        # First association
        self.client.post('/api/integrations/google/analytics/associate/', data={
            'project_id': project.id,
            'property_id': '987654321',
        })

        # Second association updates project to new property
        resp = self.client.post('/api/integrations/google/analytics/associate/', data={
            'project_id': project.id,
            'property_id': '112233445',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['property_id'], '112233445')

    def test_free_tier_rejected_from_ga4_properties(self):
        SubscriptionService.assign_plan(self.user, PlanCode.FREE)
        response = self.client.get('/api/integrations/google/analytics/properties/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'FEATURE_NOT_ENTITLED')
        self.assertTrue(response.data.get('upgrade_required'))

    def test_starter_tier_allowed_ga4_properties(self):
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        with patch('apps.integrations.services.analytics.GA4IntegrationService.list_properties') as mock_list:
            mock_list.return_value = []
            response = self.client.get('/api/integrations/google/analytics/properties/')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_agency_tier_allowed_ga4_properties(self):
        SubscriptionService.assign_plan(self.user, PlanCode.AGENCY)
        with patch('apps.integrations.services.analytics.GA4IntegrationService.list_properties') as mock_list:
            mock_list.return_value = []
            response = self.client.get('/api/integrations/google/analytics/properties/')
            self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(**MOCK_OAUTH_SETTINGS)
class ClarityIntegrationTests(TestCase):
    """
    Focused test suite for Microsoft Clarity Integration:
    - Connection initiation & callback
    - Disconnect behavior
    - Project discovery & normalization
    - Google/Microsoft error mappings (401, 403, 429, 500)
    - Project association & tenant isolation
    - Subscription gating (Free rejected, Starter/Agency allowed)
    - Security: no token serialization, tenant isolation
    """

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user = User.objects.create_user(
            email='clarity_user@example.com',
            password='TestPassword123!'
        )
        self.other_user = User.objects.create_user(
            email='other_clarity_user@example.com',
            password='TestPassword123!'
        )


        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        SubscriptionService.assign_plan(self.other_user, PlanCode.STARTER)

        self.project = Project.objects.create(
            owner=self.user,
            name='Clarity Test Project',
            website_url='https://clarityexample.com'
        )

        # Set up an active Microsoft connection for self.user
        self.connection = IntegrationConnection.objects.create(
            user=self.user,
            provider=IntegrationProvider.MICROSOFT,
            status=IntegrationStatus.CONNECTED,
            account_email='clarity_user@example.com',
            account_name='Clarity User',
            metadata={
                'projects': [
                    {
                        'project_id': 'k9xyz123',
                        'name': 'Clarity Main Site',
                        'website': 'https://clarityexample.com'
                    },
                    {
                        'project_id': 'abc98765',
                        'name': 'Clarity Blog',
                        'website': 'https://blog.clarityexample.com'
                    }
                ]
            }
        )
        self.connection.set_access_token('initial_ms_access_token')
        self.connection.set_refresh_token('initial_ms_refresh_token')
        self.connection.token_expires_at = timezone.now() + timedelta(hours=1)
        self.connection.save()

        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_requests_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/integrations/microsoft/clarity/projects/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_connect_initiation_returns_authorization_url(self):
        response = self.client.get('/api/integrations/microsoft/clarity/connect/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('authorization_url', response.data)
        auth_url = response.data['authorization_url']
        self.assertIn('login.microsoftonline.com', auth_url)
        self.assertIn('client_id=', auth_url)
        self.assertIn('state=', auth_url)

    @patch('apps.integrations.services.clarity.requests.post')
    @patch('apps.integrations.services.clarity.requests.get')
    def test_successful_oauth_callback(self, mock_get, mock_post):
        # Mock token exchange
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            'access_token': 'new_ms_access_token',
            'refresh_token': 'new_ms_refresh_token',
            'expires_in': 3600,
            'scope': 'openid profile email User.Read'
        }
        mock_post.return_value = mock_token_resp

        # Mock Microsoft Graph profile
        mock_profile_resp = MagicMock()
        mock_profile_resp.status_code = 200
        mock_profile_resp.json.return_value = {
            'mail': 'live_ms_user@example.com',
            'displayName': 'Live MS User',
            'id': 'ms-guid-1234'
        }
        mock_get.return_value = mock_profile_resp

        state = OAuthStateService.generate_state(self.user, metadata={'provider': 'microsoft'})
        response = self.client.get(f'/api/integrations/microsoft/clarity/callback/?code=valid_code&state={state}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.get_access_token(), 'new_ms_access_token')
        self.assertEqual(self.connection.get_refresh_token(), 'new_ms_refresh_token')
        self.assertEqual(self.connection.account_email, 'live_ms_user@example.com')

    def test_oauth_callback_denied_error(self):
        response = self.client.get('/api/integrations/microsoft/clarity/callback/?error=access_denied&error_description=User+cancelled')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('code'), 'OAUTH_DENIED')

    def test_disconnect_microsoft_clarity(self):
        # Pre-associate a project
        ProjectClarityConnection.objects.create(
            project=self.project,
            clarity_project_id='k9xyz123',
            is_connected=True
        )

        response = self.client.post('/api/integrations/microsoft/clarity/disconnect/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, IntegrationStatus.DISCONNECTED)
        self.assertIsNone(self.connection.get_access_token())
        self.assertIsNone(self.connection.get_refresh_token())

        # Verify project connection was marked disconnected
        project_conn = ProjectClarityConnection.objects.get(project=self.project)
        self.assertFalse(project_conn.is_connected)

    def test_list_projects_normalized_response(self):
        response = self.client.get('/api/integrations/microsoft/clarity/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['project_id'], 'k9xyz123')
        self.assertEqual(response.data[0]['name'], 'Clarity Main Site')
        self.assertEqual(response.data[0]['website'], 'https://clarityexample.com')

    def test_list_projects_when_not_connected(self):
        self.connection.status = IntegrationStatus.DISCONNECTED
        self.connection.save()

        response = self.client.get('/api/integrations/microsoft/clarity/projects/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('code'), 'CLARITY_NOT_CONNECTED')

    @patch('apps.integrations.services.clarity.requests.get')
    def test_clarity_api_403_error_handled(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = 'Forbidden'
        mock_get.return_value = mock_resp

        # Association with API token triggers live validation
        response = self.client.post('/api/integrations/microsoft/clarity/associate/', data={
            'project_id': self.project.id,
            'clarity_project_id': 'k9xyz123',
            'api_token': 'invalid_token_403',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'CLARITY_AUTH_ERROR')

    @patch('apps.integrations.services.clarity.requests.get')
    def test_clarity_api_429_rate_limit_handled(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = 'Too Many Requests'
        mock_get.return_value = mock_resp

        response = self.client.post('/api/integrations/microsoft/clarity/associate/', data={
            'project_id': self.project.id,
            'clarity_project_id': 'k9xyz123',
            'api_token': 'rate_limited_token',
        })
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data.get('code'), 'CLARITY_RATE_LIMIT')

    @patch('apps.integrations.services.clarity.requests.get')
    def test_clarity_api_500_server_error_handled(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = 'Internal Server Error'
        mock_get.return_value = mock_resp

        response = self.client.post('/api/integrations/microsoft/clarity/associate/', data={
            'project_id': self.project.id,
            'clarity_project_id': 'k9xyz123',
            'api_token': 'server_error_token',
        })
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data.get('code'), 'CLARITY_API_ERROR')

    def test_valid_project_association_succeeds(self):
        response = self.client.post('/api/integrations/microsoft/clarity/associate/', data={
            'project_id': self.project.id,
            'clarity_project_id': 'k9xyz123',
            'name': 'Clarity Main Site',
            'website': 'https://clarityexample.com',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['clarity_project_id'], 'k9xyz123')
        self.assertEqual(response.data['project_name'], self.project.name)
        self.assertTrue(response.data['is_connected'])

        # Verify persisted in database
        conn = ProjectClarityConnection.objects.get(project=self.project)
        self.assertEqual(conn.clarity_project_id, 'k9xyz123')
        self.assertTrue(conn.is_connected)

    def test_project_owned_by_another_user_rejected(self):
        other_project = Project.objects.create(
            owner=self.other_user,
            name="Other User's Project",
            website_url='https://other.com'
        )

        response = self.client.post('/api/integrations/microsoft/clarity/associate/', data={
            'project_id': other_project.id,
            'clarity_project_id': 'k9xyz123',
        })
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data.get('code'), 'PROJECT_NOT_FOUND')

    def test_clarity_project_belonging_to_another_account_rejected(self):
        other_project = Project.objects.create(
            owner=self.other_user,
            name="Other Project",
            website_url='https://other.com'
        )
        # Other user already linked k9xyz123
        ProjectClarityConnection.objects.create(
            project=other_project,
            clarity_project_id='k9xyz123',
            is_connected=True
        )

        # Self attempts to associate the same project
        response = self.client.post('/api/integrations/microsoft/clarity/associate/', data={
            'project_id': self.project.id,
            'clarity_project_id': 'k9xyz123',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'CLARITY_AUTH_ERROR')

    def test_duplicate_association_updates_safely(self):
        # First association
        self.client.post('/api/integrations/microsoft/clarity/associate/', data={
            'project_id': self.project.id,
            'clarity_project_id': 'k9xyz123',
            'name': 'Old Name',
        })

        # Second association updates existing record
        response = self.client.post('/api/integrations/microsoft/clarity/associate/', data={
            'project_id': self.project.id,
            'clarity_project_id': 'abc98765',
            'name': 'Updated Name',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['clarity_project_id'], 'abc98765')
        self.assertEqual(response.data['name'], 'Updated Name')
        self.assertEqual(ProjectClarityConnection.objects.filter(project=self.project).count(), 1)

    def test_free_tier_rejected_from_clarity(self):
        SubscriptionService.assign_plan(self.user, PlanCode.FREE)
        response = self.client.get('/api/integrations/microsoft/clarity/projects/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'FEATURE_NOT_ENTITLED')
        self.assertTrue(response.data.get('upgrade_required'))

    def test_starter_tier_allowed_clarity(self):
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        response = self.client.get('/api/integrations/microsoft/clarity/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_agency_tier_allowed_clarity(self):
        SubscriptionService.assign_plan(self.user, PlanCode.AGENCY)
        response = self.client.get('/api/integrations/microsoft/clarity/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_status_endpoint_exposes_microsoft_and_project_clarity(self):
        # Associate project
        ProjectClarityConnection.objects.create(
            project=self.project,
            clarity_project_id='k9xyz123',
            name='Clarity Site',
            website_url='https://clarityexample.com',
            is_connected=True
        )

        response = self.client.get(f'/api/integrations/status/?project_id={self.project.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('microsoft', response.data)
        self.assertTrue(response.data['microsoft']['connected'])
        self.assertIn('project_clarity', response.data)
        self.assertEqual(response.data['project_clarity']['clarity_project_id'], 'k9xyz123')

    def test_credentials_never_serialized_to_frontend(self):
        response = self.client.get('/api/integrations/status/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ms_data = response.data.get('microsoft', {})
        self.assertNotIn('encrypted_access_token', ms_data)
        self.assertNotIn('encrypted_refresh_token', ms_data)
        self.assertNotIn('access_token', ms_data)
        self.assertNotIn('refresh_token', ms_data)


@override_settings(**MOCK_OAUTH_SETTINGS)
class GTMIntegrationTests(TestCase):
    """
    Tests for Google Tag Manager (GTM) integration:
    - Scope handling and verification
    - Scope merging during reauthorization
    - Token refresh behavior
    - Discovery of GTM accounts and containers
    - Google API error handling (401, 403, 429, 500)
    - Project container association (idempotent reassociation)
    - Tenant isolation & project ownership
    - Invalid container rejection
    - Subscription gating: Free blocked, Starter allowed, Agency allowed
    - Status endpoint and token security (no leakage)
    - Project disconnection
    """

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user = User.objects.create_user(
            email='gtm_user@example.com',
            password='Password123!'
        )
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.client.force_authenticate(user=self.user)

        self.project = Project.objects.create(
            name='GTM Web Project',
            website_url='https://gtm-example.com',
            owner=self.user
        )

        self.other_user = User.objects.create_user(
            email='other_gtm_user@example.com',
            password='Password123!'
        )
        SubscriptionService.assign_plan(self.other_user, PlanCode.STARTER)
        self.other_project = Project.objects.create(
            name='Other Web Project',
            website_url='https://other-example.com',
            owner=self.other_user
        )

        self.connection = IntegrationConnection.objects.create(
            user=self.user,
            provider=IntegrationProvider.GOOGLE,
            status=IntegrationStatus.CONNECTED,
            account_email='gtm_user@example.com',
            scopes=[
                'https://www.googleapis.com/auth/webmasters.readonly',
                'https://www.googleapis.com/auth/analytics.readonly',
                'https://www.googleapis.com/auth/tagmanager.readonly',
                'openid',
                'https://www.googleapis.com/auth/userinfo.email',
            ],
            token_expires_at=timezone.now() + timedelta(hours=1)
        )
        self.connection.set_access_token('mock_gtm_access_token')
        self.connection.set_refresh_token('mock_gtm_refresh_token')
        self.connection.save()

    def test_gtm_scope_property_on_connection(self):
        self.assertTrue(self.connection.has_gtm_scope)
        self.connection.scopes = ['https://www.googleapis.com/auth/webmasters.readonly']
        self.connection.save()
        self.assertFalse(self.connection.has_gtm_scope)

    @patch('apps.integrations.services.google_oauth.GoogleOAuthIntegrationService.fetch_user_identity')
    @patch('apps.integrations.services.google_oauth.GoogleOAuthIntegrationService.exchange_code')
    def test_reauthorization_merges_gtm_scope_safely(self, mock_exchange, mock_identity):
        self.connection.scopes = [
            'https://www.googleapis.com/auth/webmasters.readonly',
            'https://www.googleapis.com/auth/analytics.readonly',
        ]
        self.connection.save()

        mock_exchange.return_value = {
            'access_token': 'new_gtm_access_token',
            'refresh_token': 'new_gtm_refresh_token',
            'expires_in': 3600,
            'scope': 'https://www.googleapis.com/auth/tagmanager.readonly'
        }
        mock_identity.return_value = {
            'email': 'gtm_user@example.com',
            'name': 'GTM User',
            'id': 'google-uid-gtm',
            'verified_email': True
        }

        state = OAuthStateService.generate_state(self.user)
        response = self.client.get(f'/api/integrations/google/callback/?code=gtm_code&state={state}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.connection.refresh_from_db()
        self.assertIn('https://www.googleapis.com/auth/webmasters.readonly', self.connection.scopes)
        self.assertIn('https://www.googleapis.com/auth/analytics.readonly', self.connection.scopes)
        self.assertIn('https://www.googleapis.com/auth/tagmanager.readonly', self.connection.scopes)
        self.assertTrue(self.connection.has_gtm_scope)

    def test_unauthenticated_request_rejected(self):
        unauth_client = APIClient()
        response = unauth_client.get('/api/integrations/google/gtm/containers/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_disconnected_user_returns_400(self):
        self.connection.status = IntegrationStatus.DISCONNECTED
        self.connection.save()

        response = self.client.get('/api/integrations/google/gtm/containers/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('code'), 'NOT_CONNECTED')

    def test_missing_gtm_scope_returns_403(self):
        self.connection.scopes = [
            'https://www.googleapis.com/auth/webmasters.readonly',
            'https://www.googleapis.com/auth/analytics.readonly',
        ]
        self.connection.save()

        response = self.client.get('/api/integrations/google/gtm/containers/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'GTM_SCOPE_MISSING')
        self.assertIn('reconnect your google account', response.data['detail'].lower())

    @patch('apps.integrations.services.gtm.GTMIntegrationService.get_client')
    def test_list_containers_success_and_normalization(self, mock_get_client):
        mock_client = MagicMock()
        # Mock accounts list
        mock_client.accounts().list().execute.return_value = {
            'account': [
                {'accountId': '1001', 'name': 'Corporate Account'},
                {'accountId': '1002', 'name': 'Marketing Account'},
            ]
        }
        # Mock containers list per account
        def mock_containers_list(parent=None):
            req = MagicMock()
            if parent == 'accounts/1001':
                req.execute.return_value = {
                    'container': [
                        {
                            'accountId': '1001',
                            'containerId': '2001',
                            'publicId': 'GTM-AAA111',
                            'name': 'Corporate Main Site',
                            'usageContext': ['web'],
                        }
                    ]
                }
            elif parent == 'accounts/1002':
                req.execute.return_value = {
                    'container': [
                        {
                            'accountId': '1002',
                            'containerId': '2002',
                            'publicId': 'GTM-BBB222',
                            'name': 'Landing Pages',
                            'usageContext': ['web', 'amp'],
                        }
                    ]
                }
            else:
                req.execute.return_value = {}
            return req

        mock_client.accounts().containers().list.side_effect = mock_containers_list
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/gtm/containers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['container_id'], '2001')
        self.assertEqual(response.data[0]['public_id'], 'GTM-AAA111')
        self.assertEqual(response.data[0]['name'], 'Corporate Main Site')
        self.assertEqual(response.data[0]['account_id'], '1001')
        self.assertEqual(response.data[0]['account_name'], 'Corporate Account')
        self.assertEqual(response.data[0]['usage_context'], ['web'])

        self.assertEqual(response.data[1]['container_id'], '2002')
        self.assertEqual(response.data[1]['public_id'], 'GTM-BBB222')
        self.assertEqual(response.data[1]['name'], 'Landing Pages')
        self.assertEqual(response.data[1]['account_id'], '1002')
        self.assertEqual(response.data[1]['account_name'], 'Marketing Account')
        self.assertEqual(response.data[1]['usage_context'], ['web', 'amp'])

    @patch('apps.integrations.services.gtm.GTMIntegrationService.get_client')
    def test_list_containers_handles_google_api_429(self, mock_get_client):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 429
        mock_client.accounts().list().execute.side_effect = HttpError(resp=mock_resp, content=b'Rate limit exceeded')
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/gtm/containers/')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data.get('code'), 'RATE_LIMIT_EXCEEDED')

    @patch('apps.integrations.services.gtm.GTMIntegrationService.get_client')
    def test_list_containers_handles_google_api_403(self, mock_get_client):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 403
        mock_client.accounts().list().execute.side_effect = HttpError(resp=mock_resp, content=b'Forbidden')
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/gtm/containers/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data.get('code'), 'CREDENTIALS_INVALID')

    @patch('apps.integrations.services.gtm.GTMIntegrationService.get_client')
    def test_list_containers_handles_google_api_500(self, mock_get_client):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_client.accounts().list().execute.side_effect = HttpError(resp=mock_resp, content=b'Server Error')
        mock_get_client.return_value = mock_client

        response = self.client.get('/api/integrations/google/gtm/containers/')
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data.get('code'), 'GOOGLE_API_ERROR')

    @patch('apps.integrations.services.gtm.GTMIntegrationService.list_containers')
    def test_associate_container_success(self, mock_list):
        mock_list.return_value = [
            {
                'account_id': '1001',
                'account_name': 'Corporate Account',
                'container_id': '2001',
                'public_id': 'GTM-AAA111',
                'name': 'Corporate Main Site',
                'usage_context': ['web'],
            }
        ]

        response = self.client.post('/api/integrations/google/gtm/associate/', data={
            'project_id': self.project.id,
            'container_id': '2001',
            'container_public_id': 'GTM-AAA111',
            'name': 'Corporate Main Site',
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['container_id'], '2001')
        self.assertEqual(response.data['container_public_id'], 'GTM-AAA111')
        self.assertEqual(response.data['project_id'], self.project.id)
        self.assertTrue(response.data['is_connected'])

        conn = ProjectGTMConnection.objects.get(project=self.project)
        self.assertEqual(conn.container_id, '2001')
        self.assertEqual(conn.container_public_id, 'GTM-AAA111')
        self.assertTrue(conn.is_connected)

    @patch('apps.integrations.services.gtm.GTMIntegrationService.list_containers')
    def test_associate_container_idempotent_reassociation(self, mock_list):
        mock_list.return_value = [
            {
                'account_id': '1001',
                'account_name': 'Corporate Account',
                'container_id': '2001',
                'public_id': 'GTM-AAA111',
                'name': 'First Container',
                'usage_context': ['web'],
            },
            {
                'account_id': '1001',
                'account_name': 'Corporate Account',
                'container_id': '2002',
                'public_id': 'GTM-BBB222',
                'name': 'Second Container',
                'usage_context': ['web'],
            }
        ]

        # First association
        self.client.post('/api/integrations/google/gtm/associate/', data={
            'project_id': self.project.id,
            'container_id': '2001',
        })

        # Second association updates existing record without duplicate
        response = self.client.post('/api/integrations/google/gtm/associate/', data={
            'project_id': self.project.id,
            'container_id': '2002',
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['container_id'], '2002')
        self.assertEqual(response.data['container_public_id'], 'GTM-BBB222')
        self.assertEqual(ProjectGTMConnection.objects.filter(project=self.project).count(), 1)

    @patch('apps.integrations.services.gtm.GTMIntegrationService.list_containers')
    def test_associate_container_invalid_container_rejected(self, mock_list):
        mock_list.return_value = [
            {
                'account_id': '1001',
                'account_name': 'Corporate Account',
                'container_id': '2001',
                'public_id': 'GTM-AAA111',
                'name': 'Valid Container',
                'usage_context': ['web'],
            }
        ]

        response = self.client.post('/api/integrations/google/gtm/associate/', data={
            'project_id': self.project.id,
            'container_id': 'NONEXISTENT_CONTAINER',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not found', response.data['detail'].lower())

    @patch('apps.integrations.services.gtm.GTMIntegrationService.list_containers')
    def test_associate_container_tenant_isolation(self, mock_list):
        mock_list.return_value = [
            {
                'account_id': '1001',
                'account_name': 'Corporate Account',
                'container_id': '2001',
                'public_id': 'GTM-AAA111',
                'name': 'Valid Container',
                'usage_context': ['web'],
            }
        ]

        # User attempts to associate container with another user's project
        response = self.client.post('/api/integrations/google/gtm/associate/', data={
            'project_id': self.other_project.id,
            'container_id': '2001',
        })

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data.get('code'), 'PROJECT_NOT_FOUND')

    def test_get_project_connection_success(self):
        ProjectGTMConnection.objects.create(
            project=self.project,
            account_id='1001',
            container_id='2001',
            container_public_id='GTM-AAA111',
            name='My GTM Web Container',
            usage_context=['web'],
            is_connected=True
        )

        response = self.client.get(f'/api/integrations/google/gtm/project/?project_id={self.project.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['container_id'], '2001')
        self.assertEqual(response.data['container_public_id'], 'GTM-AAA111')
        self.assertTrue(response.data['is_connected'])

    def test_get_project_connection_not_connected(self):
        response = self.client.get(f'/api/integrations/google/gtm/project/?project_id={self.project.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_connected'])

    def test_disconnect_project_gtm(self):
        ProjectGTMConnection.objects.create(
            project=self.project,
            account_id='1001',
            container_id='2001',
            container_public_id='GTM-AAA111',
            name='My GTM Web Container',
            usage_context=['web'],
            is_connected=True
        )

        response = self.client.post('/api/integrations/google/gtm/disconnect/', data={
            'project_id': self.project.id
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['disconnected'])

        conn = ProjectGTMConnection.objects.get(project=self.project)
        self.assertFalse(conn.is_connected)

    def test_free_subscription_blocked_from_gtm(self):
        SubscriptionService.assign_plan(self.user, PlanCode.FREE)
        response = self.client.get('/api/integrations/google/gtm/containers/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'FEATURE_NOT_ENTITLED')
        self.assertTrue(response.data.get('upgrade_required'))

    @patch('apps.integrations.services.gtm.GTMIntegrationService.list_containers')
    def test_starter_subscription_allowed_gtm(self, mock_list):
        mock_list.return_value = []
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        response = self.client.get('/api/integrations/google/gtm/containers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('apps.integrations.services.gtm.GTMIntegrationService.list_containers')
    def test_agency_subscription_allowed_gtm(self, mock_list):
        mock_list.return_value = []
        SubscriptionService.assign_plan(self.user, PlanCode.AGENCY)
        response = self.client.get('/api/integrations/google/gtm/containers/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_status_endpoint_includes_has_gtm_scope_and_project_gtm(self):
        ProjectGTMConnection.objects.create(
            project=self.project,
            account_id='1001',
            container_id='2001',
            container_public_id='GTM-AAA111',
            name='My GTM Web Container',
            usage_context=['web'],
            is_connected=True
        )

        response = self.client.get(f'/api/integrations/status/?project_id={self.project.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('google', response.data)
        self.assertTrue(response.data['google']['has_gtm_scope'])
        self.assertIn('project_gtm', response.data)
        self.assertEqual(response.data['project_gtm']['container_public_id'], 'GTM-AAA111')

    def test_serializer_never_exposes_tokens(self):
        response = self.client.get('/api/integrations/status/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        google_data = response.data.get('google', {})
        self.assertNotIn('encrypted_access_token', google_data)
        self.assertNotIn('encrypted_refresh_token', google_data)
        self.assertNotIn('access_token', google_data)
        self.assertNotIn('refresh_token', google_data)

    @patch('apps.integrations.services.google_oauth.GoogleOAuthIntegrationService.refresh_connection_tokens')
    def test_token_refresh_behavior(self, mock_refresh):
        self.connection.token_expires_at = timezone.now() - timedelta(minutes=5)
        self.connection.save()

        mock_refresh.return_value = self.connection

        from apps.integrations.services.gtm import GTMIntegrationService
        creds = GTMIntegrationService.get_credentials(self.connection)
        mock_refresh.assert_called_once_with(self.connection)
        self.assertEqual(creds.token, 'mock_gtm_access_token')


