import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from apps.projects.models import Project
from apps.seo.models import (
    SearchConsoleConnection,
    SearchConsolePermission,
    SearchConsoleSyncStatus
)

User = get_user_model()

def run_search_console_tests():
    print("==========================================")
    print(" DOXARANK SEARCH CONSOLE API TEST SUITE   ")
    print("==========================================\n")

    client = APIClient()

    # Clean up test users
    email_a = "gsc_tester_a@doxarank.com"
    email_b = "gsc_tester_b@doxarank.com"
    User.objects.filter(email__in=[email_a, email_b]).delete()

    user_a = User.objects.create_user(
        email=email_a,
        password="Password123!",
        first_name="GSC",
        last_name="TesterA"
    )
    user_b = User.objects.create_user(
        email=email_b,
        password="Password123!",
        first_name="GSC",
        last_name="TesterB"
    )

    try:
        # Create projects for both users
        proj_a = Project.objects.create(
            owner=user_a,
            name="Addis Insight Portal",
            website_url="https://addisinsight.net"
        )
        proj_b = Project.objects.create(
            owner=user_b,
            name="Shega Tech Media",
            website_url="https://shega.co"
        )

        # 1. TEST UNAUTHENTICATED GET REJECTED
        print("1. Testing Unauthenticated Access Rejection (GET /api/seo/search-console/)...")
        res_unauth = client.get('/api/seo/search-console/')
        assert res_unauth.status_code == status.HTTP_401_UNAUTHORIZED
        print("   [PASS] 401 Unauthorized returned for unauthenticated request.")

        # 2. USER A CAN CREATE SEARCH CONSOLE CONNECTION FOR OWN PROJECT
        print("\n2. Testing GSC Connection Creation for User A's Project...")
        client.force_authenticate(user=user_a)
        payload_a = {
            'project': proj_a.id,
            'property_url': 'sc-domain:addisinsight.net',
            'permission_level': 'siteOwner',
            'is_connected': True,
            'sync_status': 'idle'
        }
        res_a_create = client.post('/api/seo/search-console/', payload_a, format='json')
        assert res_a_create.status_code == status.HTTP_201_CREATED, f"Failed: {res_a_create.data}"
        conn_a_id = res_a_create.data['id']
        assert res_a_create.data['project'] == proj_a.id
        assert res_a_create.data['project_name'] == "Addis Insight Portal"
        assert res_a_create.data['property_url'] == 'sc-domain:addisinsight.net'
        assert res_a_create.data['permission_level'] == 'siteOwner'
        assert res_a_create.data['is_connected'] is True
        print(f"   [PASS] User A created GSC Connection #{conn_a_id} for Project #{proj_a.id}.")

        # 3. USER B CAN CREATE SEARCH CONSOLE CONNECTION FOR OWN PROJECT
        print("\n3. Testing GSC Connection Creation for User B's Project...")
        client.force_authenticate(user=user_b)
        payload_b = {
            'project': proj_b.id,
            'property_url': 'https://shega.co/',
            'permission_level': 'siteFullUser',
            'is_connected': True
        }
        res_b_create = client.post('/api/seo/search-console/', payload_b, format='json')
        assert res_b_create.status_code == status.HTTP_201_CREATED, f"Failed: {res_b_create.data}"
        conn_b_id = res_b_create.data['id']
        assert res_b_create.data['project'] == proj_b.id
        assert res_b_create.data['property_url'] == 'https://shega.co/'
        print(f"   [PASS] User B created GSC Connection #{conn_b_id} for Project #{proj_b.id}.")

        # 4. USER A CANNOT CREATE CONNECTION FOR USER B'S PROJECT
        print("\n4. Testing Cross-User Project Connection Injection Block...")
        client.force_authenticate(user=user_a)
        res_cross_create = client.post('/api/seo/search-console/', {
            'project': proj_b.id, # User B's project!
            'property_url': 'sc-domain:hacked.com'
        }, format='json')
        assert res_cross_create.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Blocked with 400 Bad Request (Ownership validation).")

        # 5. USER A ONLY SEES OWN CONNECTIONS IN LIST
        print("\n5. Testing List Isolation (User A only sees own connections)...")
        res_a_list = client.get('/api/seo/search-console/')
        assert res_a_list.status_code == status.HTTP_200_OK
        conn_ids = [c['id'] for c in res_a_list.data]
        assert conn_a_id in conn_ids
        assert conn_b_id not in conn_ids
        print(f"   [PASS] User A list only contains own connection ({len(conn_ids)} items). User B's connection is isolated.")

        # 6. USER A CANNOT RETRIEVE USER B'S CONNECTION DETAIL
        print("\n6. Testing Cross-User Detail Retrieve Block (GET /api/seo/search-console/<user_b_id>/)...")
        res_cross_get = client.get(f'/api/seo/search-console/{conn_b_id}/')
        assert res_cross_get.status_code == status.HTTP_404_NOT_FOUND
        print("   [PASS] Blocked with 404 Not Found.")

        # 7. USER A CANNOT MODIFY USER B'S CONNECTION
        print("\n7. Testing Cross-User Modification Block (PATCH /api/seo/search-console/<user_b_id>/)...")
        res_cross_patch = client.patch(f'/api/seo/search-console/{conn_b_id}/', {'property_url': 'sc-domain:tampered.com'}, format='json')
        assert res_cross_patch.status_code == status.HTTP_404_NOT_FOUND
        b_conn_obj = SearchConsoleConnection.objects.get(id=conn_b_id)
        assert b_conn_obj.property_url == 'https://shega.co/'
        print("   [PASS] Blocked with 404 Not Found. Connection record untouched.")

        # 8. USER A CANNOT DELETE USER B'S CONNECTION
        print("\n8. Testing Cross-User Deletion Block (DELETE /api/seo/search-console/<user_b_id>/)...")
        res_cross_delete = client.delete(f'/api/seo/search-console/{conn_b_id}/')
        assert res_cross_delete.status_code == status.HTTP_404_NOT_FOUND
        assert SearchConsoleConnection.objects.filter(id=conn_b_id).exists()
        print("   [PASS] Blocked with 404 Not Found. Connection record intact.")

        # 9. USER A CAN UPDATE OWN CONNECTION
        print("\n9. Testing Update Own Connection (PATCH /api/seo/search-console/<user_a_id>/)...")
        now_iso = timezone.now().isoformat()
        res_a_update = client.patch(f'/api/seo/search-console/{conn_a_id}/', {
            'sync_status': 'success',
            'last_synced_at': now_iso,
            'is_connected': True
        }, format='json')
        assert res_a_update.status_code == status.HTTP_200_OK
        assert res_a_update.data['sync_status'] == 'success'
        assert res_a_update.data['is_connected'] is True
        print(f"   [PASS] Updated Connection #{conn_a_id} sync_status to 'success'.")

        # 10. USER A CAN DELETE / DISCONNECT OWN CONNECTION
        print("\n10. Testing Delete Own Connection (DELETE /api/seo/search-console/<user_a_id>/)...")
        proj_temp = Project.objects.create(owner=user_a, name="Temp Project", website_url="https://temp.et")
        temp_conn = SearchConsoleConnection.objects.create(
            project=proj_temp,
            property_url="sc-domain:temp.et"
        )
        temp_conn_id = temp_conn.id
        res_a_delete = client.delete(f'/api/seo/search-console/{temp_conn_id}/')
        assert res_a_delete.status_code == status.HTTP_204_NO_CONTENT
        assert not SearchConsoleConnection.objects.filter(id=temp_conn_id).exists()
        print(f"   [PASS] Deleted / disconnected Connection #{temp_conn_id} successfully (204 No Content).")

        # 11. PROJECT FILTERING WORKS
        print("\n11. Testing Project Filtering (?project_id=...)...")
        proj_a2 = Project.objects.create(owner=user_a, name="Secondary A Project", website_url="https://second.et")
        conn_a2 = SearchConsoleConnection.objects.create(
            project=proj_a2,
            property_url="sc-domain:second.et"
        )

        res_filter_proj = client.get(f'/api/seo/search-console/?project_id={proj_a.id}')
        assert res_filter_proj.status_code == status.HTTP_200_OK
        filtered_ids = [c['id'] for c in res_filter_proj.data]
        assert conn_a_id in filtered_ids
        assert conn_a2.id not in filtered_ids
        print(f"   [PASS] Filter by Project #{proj_a.id} returned only its GSC connection.")

        # 12. CROSS-USER PROJECT FILTERING IS ISOLATED
        print("\n12. Testing Cross-User Project Filter Isolation...")
        res_cross_filter = client.get(f'/api/seo/search-console/?project_id={proj_b.id}')
        assert res_cross_filter.status_code == status.HTTP_200_OK
        assert len(res_cross_filter.data) == 0
        print("   [PASS] Querying with another user's project_id safely returned empty list [].")

        # 13. DUPLICATE CONNECTION PREVENTION PER PROJECT
        print("\n13. Testing Duplicate Connection Prevention Per Project...")
        res_dup_create = client.post('/api/seo/search-console/', {
            'project': proj_a.id, # Connection already exists for proj_a!
            'property_url': 'sc-domain:duplicate.com'
        }, format='json')
        assert res_dup_create.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Duplicate connection on project rejected with 400 Bad Request.")

        # 14. INVALID DATA REJECTION
        print("\n14. Testing Invalid Data Rejection (blank property_url, invalid choices)...")
        res_bad_url = client.post('/api/seo/search-console/', {
            'project': proj_temp.id,
            'property_url': '   '
        }, format='json')
        assert res_bad_url.status_code == status.HTTP_400_BAD_REQUEST

        res_bad_perm = client.post('/api/seo/search-console/', {
            'project': proj_temp.id,
            'property_url': 'sc-domain:valid.com',
            'permission_level': 'superAdminInvalid'
        }, format='json')
        assert res_bad_perm.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Blank property URLs and invalid permission choices rejected with 400 Bad Request.")

        # 15. CASCADE DELETION ON PROJECT DELETE
        print("\n15. Testing Cascade Deletion on Project Delete...")
        assert SearchConsoleConnection.objects.filter(id=conn_a2.id).exists()
        proj_a2_id = proj_a2.id
        proj_a2.delete()
        assert not SearchConsoleConnection.objects.filter(id=conn_a2.id).exists()
        print(f"   [PASS] Deleting Project #{proj_a2_id} cascaded and removed SearchConsoleConnection.")

        print("\n==========================================")
        print(" ALL 15 SEARCH CONSOLE TESTS PASSED!      ")
        print("==========================================\n")

    finally:
        User.objects.filter(email__in=[email_a, email_b]).delete()

if __name__ == '__main__':
    run_search_console_tests()
