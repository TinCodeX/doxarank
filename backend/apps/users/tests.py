from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


class AuthAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = '/api/auth/register/'
        self.login_url = '/api/auth/login/'
        self.refresh_url = '/api/auth/token/refresh/'
        self.logout_url = '/api/auth/logout/'
        self.me_url = '/api/auth/me/'

        self.user_data = {
            'email': 'intern@doxarank.com',
            'password': 'SecurePassword123!',
            'first_name': 'Doxa',
            'last_name': 'Intern'
        }

    def test_user_registration_success(self):
        """Test registering a new user returns 201 and JWT tokens."""
        response = self.client.post(self.register_url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])
        self.assertEqual(response.data['user']['email'], 'intern@doxarank.com')
        self.assertEqual(response.data['user']['first_name'], 'Doxa')
        self.assertEqual(response.data['user']['last_name'], 'Intern')

    def test_duplicate_registration_fails(self):
        """Test registration with existing email returns 400."""
        self.client.post(self.register_url, self.user_data, format='json')
        response = self.client.post(self.register_url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_user_login_success(self):
        """Test login returns 200 and valid tokens."""
        self.client.post(self.register_url, self.user_data, format='json')
        
        login_data = {
            'email': 'intern@doxarank.com',
            'password': 'SecurePassword123!'
        }
        response = self.client.post(self.login_url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])

    def test_user_login_invalid_credentials(self):
        """Test login with wrong password fails with 400."""
        self.client.post(self.register_url, self.user_data, format='json')
        
        login_data = {
            'email': 'intern@doxarank.com',
            'password': 'WrongPassword123!'
        }
        response = self.client.post(self.login_url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_me_endpoint_requires_auth(self):
        """Test GET /api/auth/me/ returns 401 when not authenticated."""
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_endpoint_with_valid_token(self):
        """Test GET /api/auth/me/ returns profile when authenticated with Bearer token."""
        reg_response = self.client.post(self.register_url, self.user_data, format='json')
        access_token = reg_response.data['tokens']['access']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'intern@doxarank.com')

    def test_token_refresh(self):
        """Test POST /api/auth/token/refresh/ generates a new access token."""
        reg_response = self.client.post(self.register_url, self.user_data, format='json')
        refresh_token = reg_response.data['tokens']['refresh']

        response = self.client.post(self.refresh_url, {'refresh': refresh_token}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_logout_and_token_blacklisting(self):
        """Test logout blacklists refresh token so it cannot be reused."""
        reg_response = self.client.post(self.register_url, self.user_data, format='json')
        access_token = reg_response.data['tokens']['access']
        refresh_token = reg_response.data['tokens']['refresh']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        logout_response = self.client.post(self.logout_url, {'refresh': refresh_token}, format='json')
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)

        # Attempting to refresh with the blacklisted token should now fail with 401
        refresh_response = self.client.post(self.refresh_url, {'refresh': refresh_token}, format='json')
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)
