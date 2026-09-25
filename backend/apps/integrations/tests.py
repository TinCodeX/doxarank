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
