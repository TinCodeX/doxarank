import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.projects.models import Project

User = get_user_model()

def run_project_tests():
    print("==========================================")
    print("  DOXARANK PROJECTS API TEST SUITE        ")
    print("==========================================\n")

    client = APIClient()

    # Clean up test users
    email_a = "tester_a@doxarank.com"
    email_b = "tester_b@doxarank.com"
    User.objects.filter(email__in=[email_a, email_b]).delete()

    user_a = User.objects.create_user(
        email=email_a,
        password="Password123!",
        first_name="User",
        last_name="A"
    )
    user_b = User.objects.create_user(
        email=email_b,
        password="Password123!",
        first_name="User",
        last_name="B"
    )

    try:
        # TEST 1: Unauthenticated cannot list projects
        print("1. Testing Unauthenticated Access Rejection (GET /api/projects/)...")
        res = client.get('/api/projects/')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED, f"Expected 401, got {res.status_code}"
        print("   [PASS] 401 Unauthorized returned for unauthenticated request.")

        # TEST 2 & 3: Authenticated user creates project, automatic owner assignment
        print("\n2 & 3. Testing Project Creation & Automatic Owner Binding (POST /api/projects/)...")
        client.force_authenticate(user=user_a)
        payload = {
            "name": "Addis Insight SEO",
            "website_url": "https://addisinsight.net"
        }
        res = client.post('/api/projects/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED, f"Failed to create project: {res.data}"
        project_a_id = res.data['id']
        project_obj = Project.objects.get(id=project_a_id)
        assert project_obj.owner == user_a, "Project owner must be User A"
        assert res.data['owner_email'] == email_a, "Owner email must match User A"
        print(f"   [PASS] Created Project #{project_a_id} bound automatically to {email_a}.")

        # Create a project for User B
        client.force_authenticate(user=user_b)
        res_b = client.post('/api/projects/', {
            "name": "Shega Media",
            "website_url": "https://shega.co"
        }, format='json')
        assert res_b.status_code == status.HTTP_201_CREATED
        project_b_id = res_b.data['id']
        print(f"   [PASS] Created Project #{project_b_id} bound to {email_b}.")

        # TEST 4: User A lists only their own projects
        print("\n4. Testing Queryset Isolation (GET /api/projects/)...")
        client.force_authenticate(user=user_a)
        list_res = client.get('/api/projects/')
        assert list_res.status_code == status.HTTP_200_OK
        ids = [p['id'] for p in list_res.data]
        assert project_a_id in ids, "User A project should be present"
        assert project_b_id not in ids, "User B project MUST NOT be present in User A list"
        print(f"   [PASS] User A list only returned their own project(s): {ids}")

        # TEST 5: User A cannot read User B's project
        print("\n5. Testing Cross-Tenant Read Block (GET /api/projects/<user_b_id>/)...")
        cross_get_res = client.get(f'/api/projects/{project_b_id}/')
        assert cross_get_res.status_code == status.HTTP_404_NOT_FOUND, f"Expected 404, got {cross_get_res.status_code}"
        print(f"   [PASS] User A cannot access Project #{project_b_id} (Returned 404 Not Found).")

        # TEST 6: User A cannot modify User B's project
        print("\n6. Testing Cross-Tenant Modification Block (PATCH /api/projects/<user_b_id>/)...")
        cross_patch_res = client.patch(f'/api/projects/{project_b_id}/', {'name': 'Hacked Title'}, format='json')
        assert cross_patch_res.status_code == status.HTTP_404_NOT_FOUND
        proj_b_refreshed = Project.objects.get(id=project_b_id)
        assert proj_b_refreshed.name == "Shega Media", "Project name must remain unchanged"
        print("   [PASS] Modification blocked with 404 Not Found. Record intact.")

        # TEST 7: User A cannot delete User B's project
        print("\n7. Testing Cross-Tenant Deletion Block (DELETE /api/projects/<user_b_id>/)...")
        cross_del_res = client.delete(f'/api/projects/{project_b_id}/')
        assert cross_del_res.status_code == status.HTTP_404_NOT_FOUND
        assert Project.objects.filter(id=project_b_id).exists(), "User B project must not be deleted"
        print("   [PASS] Deletion blocked with 404 Not Found. Record intact.")

        # TEST 8: User A updates own project
        print("\n8. Testing Update Own Project (PATCH /api/projects/<user_a_id>/)...")
        patch_res = client.patch(f'/api/projects/{project_a_id}/', {'name': 'Addis Insight Pro'}, format='json')
        assert patch_res.status_code == status.HTTP_200_OK
        assert patch_res.data['name'] == 'Addis Insight Pro'
        print("   [PASS] User A updated own project successfully.")

        # TEST 9: User A deletes own project
        print("\n9. Testing Delete Own Project (DELETE /api/projects/<user_a_id>/)...")
        del_res = client.delete(f'/api/projects/{project_a_id}/')
        assert del_res.status_code == status.HTTP_204_NO_CONTENT
        assert not Project.objects.filter(id=project_a_id).exists()
        print("   [PASS] User A deleted own project successfully (204 No Content).")

        # TEST 10: Invalid URL rejected
        print("\n10. Testing URL Validation (POST /api/projects/)...")
        invalid_urls = ["ftp://invalid.com", "just-text", "https://"]
        for bad_url in invalid_urls:
            bad_res = client.post('/api/projects/', {'name': 'Bad URL', 'website_url': bad_url}, format='json')
            assert bad_res.status_code == status.HTTP_400_BAD_REQUEST, f"URL '{bad_url}' should fail"
        print("   [PASS] Invalid website URLs rejected with 400 Bad Request.")

        print("\n==========================================")
        print("   ALL 10 PROJECT TESTS PASSED! (100%)    ")
        print("==========================================\n")

    finally:
        User.objects.filter(email__in=[email_a, email_b]).delete()

if __name__ == '__main__':
    run_project_tests()
