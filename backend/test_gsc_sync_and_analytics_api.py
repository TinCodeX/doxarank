import os
import sys
import django
from datetime import date, timedelta
from decimal import Decimal

# Setup Django environment
sys.path.insert(0, os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.projects.models import Project
from apps.seo.models import (
    SearchConsoleConnection,
    SearchAnalyticsData,
    SearchConsoleSyncStatus
)
from apps.seo.services.search_console import GoogleSearchConsoleService, MockGoogleSearchConsoleClient

User = get_user_model()


def run_gsc_sync_and_analytics_tests():
    print("==================================================================")
    print(" DOXARANK GSC SYNC SERVICE & ANALYTICS API TEST SUITE             ")
    print("==================================================================\n")

    client = APIClient()

    # Clean up test users
    email_a = "gsc_sync_tester_a@doxarank.com"
    email_b = "gsc_sync_tester_b@doxarank.com"
    User.objects.filter(email__in=[email_a, email_b]).delete()

    user_a = User.objects.create_user(
        email=email_a,
        password="Password123!",
        first_name="Sync",
        last_name="TesterA"
    )
    user_b = User.objects.create_user(
        email=email_b,
        password="Password123!",
        first_name="Sync",
        last_name="TesterB"
    )

    try:
        # Create projects
        proj_a = Project.objects.create(
            owner=user_a,
            name="Addis Portal Tech",
            website_url="https://addisportal.et"
        )
        proj_b = Project.objects.create(
            owner=user_b,
            name="Shega Digest Portal",
            website_url="https://shegadigest.et"
        )

        # Create connections
        conn_a = SearchConsoleConnection.objects.create(
            project=proj_a,
            property_url="sc-domain:addisportal.et",
            permission_level="siteOwner",
            is_connected=True,
            sync_status=SearchConsoleSyncStatus.IDLE
        )
        conn_b = SearchConsoleConnection.objects.create(
            project=proj_b,
            property_url="https://shegadigest.et/",
            permission_level="siteFullUser",
            is_connected=True,
            sync_status=SearchConsoleSyncStatus.IDLE
        )

        today = date.today()
        yesterday = today - timedelta(days=1)

        # 1. UNAUTHENTICATED SYNC AND ANALYTICS REJECTED (401)
        print("1. Testing Unauthenticated Request Rejection...")
        res_sync_unauth = client.post('/api/seo/search-console/sync/', {'project_id': proj_a.id}, format='json')
        assert res_sync_unauth.status_code == status.HTTP_401_UNAUTHORIZED
        res_perf_unauth = client.get('/api/seo/search-console/performance/')
        assert res_perf_unauth.status_code == status.HTTP_401_UNAUTHORIZED
        print("   [PASS] 401 Unauthorized returned for unauthenticated sync and analytics requests.")

        # 2. USER A SYNCS OWN PROJECT (POST /api/seo/search-console/sync/)
        print("\n2. Testing GSC Sync for User A's Project...")
        client.force_authenticate(user=user_a)
        sync_payload = {
            'project_id': proj_a.id,
            'start_date': str(yesterday),
            'end_date': str(today)
        }
        res_sync_a = client.post('/api/seo/search-console/sync/', sync_payload, format='json')
        assert res_sync_a.status_code == status.HTTP_200_OK, f"Failed: {res_sync_a.data}"
        assert res_sync_a.data['success'] is True
        assert res_sync_a.data['records_fetched'] > 0
        assert res_sync_a.data['records_created'] > 0
        assert res_sync_a.data['sync_status'] == SearchConsoleSyncStatus.SUCCESS
        
        # Verify connection updated in database
        conn_a.refresh_from_db()
        assert conn_a.sync_status == SearchConsoleSyncStatus.SUCCESS
        assert conn_a.last_synced_at is not None
        assert conn_a.error_message is None
        print(f"   [PASS] User A synced {res_sync_a.data['records_created']} records successfully. Connection updated to SUCCESS.")

        # 3. REPEATED SYNC UPSERTS WITHOUT CREATING DUPLICATES
        print("\n3. Testing Idempotent Sync / Upsert Duplicate Prevention...")
        res_sync_repeat = client.post('/api/seo/search-console/sync/', sync_payload, format='json')
        assert res_sync_repeat.status_code == status.HTTP_200_OK
        assert res_sync_repeat.data['records_created'] == 0
        assert res_sync_repeat.data['records_updated'] == res_sync_a.data['records_fetched']
        print(f"   [PASS] Repeated sync updated {res_sync_repeat.data['records_updated']} existing records without creating duplicates.")

        # 4. CROSS-USER SYNC INJECTION BLOCKED
        print("\n4. Testing Cross-User Sync Injection Block (User A -> User B's Project & Connection)...")
        # Attempt sync by other user's project_id
        res_cross_proj = client.post('/api/seo/search-console/sync/', {'project_id': proj_b.id}, format='json')
        assert res_cross_proj.status_code == status.HTTP_404_NOT_FOUND

        # Attempt sync by other user's connection_id
        res_cross_conn = client.post('/api/seo/search-console/sync/', {'connection_id': conn_b.id}, format='json')
        assert res_cross_conn.status_code == status.HTTP_404_NOT_FOUND
        print("   [PASS] Cross-user sync requests blocked with 404 Not Found.")

        # 5. DISCONNECTED PROPERTY SYNC REJECTED
        print("\n5. Testing Disconnected Property Sync Rejection...")
        conn_disconnected = SearchConsoleConnection.objects.create(
            project=Project.objects.create(owner=user_a, name="Disconnected Proj", website_url="https://disc.et"),
            property_url="sc-domain:disc.et",
            is_connected=False
        )
        res_disc = client.post('/api/seo/search-console/sync/', {'connection_id': conn_disconnected.id}, format='json')
        assert res_disc.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Disconnected connection sync rejected with 400 Bad Request.")

        # 6. DIRECT SERVICE SYNC ERROR HANDLING
        print("\n6. Testing Sync Failure Handling & Error Recording...")
        failing_client = MockGoogleSearchConsoleClient(fail_sync=True, error_message="Google API Quota Exceeded")
        try:
            GoogleSearchConsoleService.sync_search_analytics(connection=conn_a, client=failing_client)
        except Exception:
            pass
        conn_a.refresh_from_db()
        assert conn_a.sync_status == SearchConsoleSyncStatus.FAILED
        assert "Google API Quota Exceeded" in str(conn_a.error_message)
        print("   [PASS] Sync failure properly recorded sync_status=FAILED and error_message in database.")

        # 7. PERFORMANCE OVERVIEW ENDPOINT (GET /api/seo/search-console/performance/)
        print("\n7. Testing Performance Overview Endpoint...")
        # Re-sync to restore clean success state
        GoogleSearchConsoleService.sync_search_analytics(connection=conn_a)
        res_perf = client.get(f'/api/seo/search-console/performance/?project_id={proj_a.id}')
        assert res_perf.status_code == status.HTTP_200_OK
        assert 'total_clicks' in res_perf.data
        assert 'total_impressions' in res_perf.data
        assert 'average_ctr' in res_perf.data
        assert 'average_position' in res_perf.data
        assert 'timeseries' in res_perf.data
        assert res_perf.data['total_clicks'] > 0
        print(f"   [PASS] Performance overview returned {res_perf.data['total_clicks']} clicks, {res_perf.data['total_impressions']} impressions, CTR {res_perf.data['average_ctr']}.")

        # 8. QUERIES BREAKDOWN ENDPOINT (GET /api/seo/search-console/queries/)
        print("\n8. Testing Queries Breakdown Endpoint...")
        res_queries = client.get(f'/api/seo/search-console/queries/?project_id={proj_a.id}')
        assert res_queries.status_code == status.HTTP_200_OK
        assert len(res_queries.data) > 0
        assert 'query' in res_queries.data[0]
        assert 'clicks' in res_queries.data[0]
        print(f"   [PASS] Queries breakdown returned {len(res_queries.data)} search queries.")

        # 9. PAGES BREAKDOWN ENDPOINT (GET /api/seo/search-console/pages/)
        print("\n9. Testing Pages Breakdown Endpoint...")
        res_pages = client.get(f'/api/seo/search-console/pages/?project_id={proj_a.id}')
        assert res_pages.status_code == status.HTTP_200_OK
        assert len(res_pages.data) > 0
        assert 'page' in res_pages.data[0]
        print(f"   [PASS] Pages breakdown returned {len(res_pages.data)} landing pages.")

        # 10. DEVICES BREAKDOWN ENDPOINT (GET /api/seo/search-console/devices/)
        print("\n10. Testing Devices Breakdown Endpoint...")
        res_devices = client.get(f'/api/seo/search-console/devices/?project_id={proj_a.id}')
        assert res_devices.status_code == status.HTTP_200_OK
        assert len(res_devices.data) > 0
        assert 'device' in res_devices.data[0]
        print(f"   [PASS] Devices breakdown returned {len(res_devices.data)} device categories.")

        # 11. COUNTRIES BREAKDOWN ENDPOINT (GET /api/seo/search-console/countries/)
        print("\n11. Testing Countries Breakdown Endpoint...")
        res_countries = client.get(f'/api/seo/search-console/countries/?project_id={proj_a.id}')
        assert res_countries.status_code == status.HTTP_200_OK
        assert len(res_countries.data) > 0
        assert 'country' in res_countries.data[0]
        print(f"   [PASS] Countries breakdown returned {len(res_countries.data)} countries.")

        # 12. CROSS-USER ANALYTICS ISOLATION
        print("\n12. Testing Cross-User Analytics Queryset Isolation...")
        res_cross_perf = client.get(f'/api/seo/search-console/performance/?project_id={proj_b.id}')
        assert res_cross_perf.status_code == status.HTTP_200_OK
        assert res_cross_perf.data['total_clicks'] == 0
        assert len(res_cross_perf.data['timeseries']) == 0

        res_cross_q = client.get(f'/api/seo/search-console/queries/?project_id={proj_b.id}')
        assert res_cross_q.status_code == status.HTTP_200_OK
        assert len(res_cross_q.data) == 0
        print("   [PASS] Querying with another user's project_id safely returned 0 metrics / empty list [].")

        print("\n==================================================================")
        print(" ALL 12 GSC SYNC & ANALYTICS TESTS PASSED!                        ")
        print("==================================================================\n")

    finally:
        # Clean up test users
        User.objects.filter(email__in=[email_a, email_b]).delete()


if __name__ == '__main__':
    run_gsc_sync_and_analytics_tests()
