from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from .models import Project

User = get_user_model()


class ProjectAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.projects_url = '/api/projects/'

        # Create two test users
        self.user_a = User.objects.create_user(
            email='user_a@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='user_b@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='B'
        )

        # Create a project owned by User A and one owned by User B
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Project A1',
            website_url='https://project-a1.com'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Project B1',
            website_url='https://project-b1.com'
        )

    def test_unauthenticated_cannot_list_projects(self):
        """1. Unauthenticated user cannot list projects (401)."""
        response = self.client.get(self.projects_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_can_create_project(self):
        """2. Authenticated user can create a project (201)."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'name': 'Addis Insight',
            'website_url': 'https://addisinsight.net'
        }
        response = self.client.post(self.projects_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Addis Insight')
        self.assertEqual(response.data['website_url'], 'https://addisinsight.net')

    def test_created_project_automatically_assigned_to_user(self):
        """3. Created project automatically belongs to authenticated user."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'name': 'Shega Media',
            'website_url': 'https://shega.co'
        }
        response = self.client.post(self.projects_url, payload, format='json')
        project_id = response.data['id']
        project = Project.objects.get(id=project_id)
        self.assertEqual(project.owner, self.user_a)

    def test_user_can_list_own_projects(self):
        """4. User can list their own projects only (200)."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(self.projects_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # User A owns 1 initial project
        project_ids = [p['id'] for p in response.data]
        self.assertIn(self.project_a.id, project_ids)
        self.assertNotIn(self.project_b.id, project_ids)

    def test_user_cannot_access_another_users_project(self):
        """5. User cannot access another user's project (404)."""
        self.client.force_authenticate(user=self.user_a)
        # Attempt to access User B's project
        response = self.client.get(f'/api/projects/{self.project_b.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_modify_another_users_project(self):
        """6. User cannot modify another user's project (404)."""
        self.client.force_authenticate(user=self.user_a)
        payload = {'name': 'Hacked Name'}
        response = self.client.patch(f'/api/projects/{self.project_b.id}/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.project_b.refresh_from_db()
        self.assertEqual(self.project_b.name, 'Project B1')

    def test_user_cannot_delete_another_users_project(self):
        """7. User cannot delete another user's project (404)."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(f'/api/projects/{self.project_b.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Project.objects.filter(id=self.project_b.id).exists())

    def test_user_can_update_own_project(self):
        """8. User can update their own project (200)."""
        self.client.force_authenticate(user=self.user_a)
        payload = {'name': 'Project A1 Updated'}
        response = self.client.patch(f'/api/projects/{self.project_a.id}/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project_a.refresh_from_db()
        self.assertEqual(self.project_a.name, 'Project A1 Updated')

    def test_user_can_delete_own_project(self):
        """9. User can delete their own project (204)."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(f'/api/projects/{self.project_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Project.objects.filter(id=self.project_a.id).exists())

    def test_invalid_website_url_is_rejected(self):
        """10. Invalid website URL is rejected (400)."""
        self.client.force_authenticate(user=self.user_a)
        # Missing scheme or invalid domain
        invalid_payloads = [
            {'name': 'Invalid 1', 'website_url': 'ftp://invalid-scheme.com'},
            {'name': 'Invalid 2', 'website_url': 'not-a-valid-url'},
            {'name': 'Invalid 3', 'website_url': 'https://'},
        ]
        for payload in invalid_payloads:
            response = self.client.post(self.projects_url, payload, format='json')
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Payload {payload} should have failed"
            )
