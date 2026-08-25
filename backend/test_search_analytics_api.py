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
    SearchAnalyticsData
)

User = get_user_model()

def run_search_analytics_tests():
    print("=====================================================")
    print(" DOXARANK SEARCH ANALYTICS BACKEND API TEST SUITE    ")
    print("=====================================================\n")

    client = APIClient()

    # Clean up test users
    email_a = "analytics_tester_a@doxarank.com"
    email_b = "analytics_tester_b@doxarank.com"
    User.objects.filter(email__in=[email_a, email_b]).delete()

    user_a = User.objects.create_user(
        email=email_a,
        password="Password123!",
        first_name="Analytics",
        last_name="TesterA"
    )
    user_b = User.objects.create_user(
        email=email_b,
        password="Password123!",
        first_name="Analytics",
        last_name="TesterB"
    )

    try:
        # Create projects for both users
        proj_a = Project.objects.create(
            owner=user_a,
            name="Addis Tech Insight",
            website_url="https://addisinsight.net"
        )
        proj_b = Project.objects.create(
            owner=user_b,
            name="Shega Tech Digest",
            website_url="https://shega.co"
        )

        # Create Search Console connections for both users
        conn_a = SearchConsoleConnection.objects.create(
            project=proj_a,
            property_url="sc-domain:addisinsight.net",
            permission_level="siteOwner",
            is_connected=True
        )
        conn_b = SearchConsoleConnection.objects.create(
            project=proj_b,
            property_url="https://shega.co/",
            permission_level="siteFullUser",
            is_connected=True
        )

        today = date.today()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        # 1. TEST UNAUTHENTICATED GET REJECTED
        print("1. Testing Unauthenticated Access Rejection (GET /api/seo/search-analytics/)...")
        res_unauth = client.get('/api/seo/search-analytics/')
        assert res_unauth.status_code == status.HTTP_401_UNAUTHORIZED, f"Expected 401, got {res_unauth.status_code}"
        print("   [PASS] 401 Unauthorized returned for unauthenticated request.")

        # 2. USER A CAN CREATE SEARCH ANALYTICS RECORD FOR OWN CONNECTION
        print("\n2. Testing Search Analytics Creation for User A's Connection...")
        client.force_authenticate(user=user_a)
        payload_a1 = {
            'connection': conn_a.id,
            'date': str(today),
            'query': 'ethiopia startup news',
            'page': 'https://addisinsight.net/startups',
            'country': 'eth',
            'device': 'desktop',
            'clicks': 142,
            'impressions': 2850,
            'ctr': '0.0498',
            'position': '3.20'
        }
        res_a1 = client.post('/api/seo/search-analytics/', payload_a1, format='json')
        assert res_a1.status_code == status.HTTP_201_CREATED, f"Failed: {res_a1.data}"
        rec_a1_id = res_a1.data['id']
        assert res_a1.data['connection'] == conn_a.id
        assert res_a1.data['project_id'] == proj_a.id
        assert res_a1.data['project_name'] == "Addis Tech Insight"
        assert res_a1.data['property_url'] == "sc-domain:addisinsight.net"
        assert res_a1.data['query'] == 'ethiopia startup news'
        assert res_a1.data['clicks'] == 142
        assert res_a1.data['impressions'] == 2850
        print(f"   [PASS] User A created Search Analytics Record #{rec_a1_id} for Connection #{conn_a.id}.")

        # 3. USER B CAN CREATE SEARCH ANALYTICS RECORD FOR OWN CONNECTION
        print("\n3. Testing Search Analytics Creation for User B's Connection...")
        client.force_authenticate(user=user_b)
        payload_b1 = {
            'connection': conn_b.id,
            'date': str(today),
            'query': 'addis fintech review',
            'page': 'https://shega.co/fintech',
            'country': 'eth',
            'device': 'mobile',
            'clicks': 88,
            'impressions': 1200,
            'ctr': '0.0733',
            'position': '2.10'
        }
        res_b1 = client.post('/api/seo/search-analytics/', payload_b1, format='json')
        assert res_b1.status_code == status.HTTP_201_CREATED, f"Failed: {res_b1.data}"
        rec_b1_id = res_b1.data['id']
        assert res_b1.data['connection'] == conn_b.id
        assert res_b1.data['project_id'] == proj_b.id
        print(f"   [PASS] User B created Search Analytics Record #{rec_b1_id} for Connection #{conn_b.id}.")

        # 4. CROSS-USER INJECTION BLOCK: USER A CANNOT CREATE ANALYTICS FOR USER B'S CONNECTION
        print("\n4. Testing Cross-User Connection Injection Block (User A -> User B's Connection)...")
        client.force_authenticate(user=user_a)
        malicious_payload = {
            'connection': conn_b.id,
            'date': str(today),
            'query': 'hacked query',
            'page': 'https://shega.co/hacked',
            'country': 'eth',
            'device': 'desktop',
            'clicks': 10,
            'impressions': 100,
            'ctr': '0.1000',
            'position': '1.00'
        }
        res_cross = client.post('/api/seo/search-analytics/', malicious_payload, format='json')
        assert res_cross.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400, got {res_cross.status_code}"
        assert 'connection' in res_cross.data, f"Expected connection error: {res_cross.data}"
        print("   [PASS] Cross-user creation blocked with 400 Bad Request.")

        # 5. USER A ONLY SEES USER A'S ANALYTICS
        print("\n5. Testing List Isolation (User A only sees own records)...")
        res_a_list = client.get('/api/seo/search-analytics/')
        assert res_a_list.status_code == status.HTTP_200_OK
        ids = [item['id'] for item in res_a_list.data]
        assert rec_a1_id in ids, "User A's record missing"
        assert rec_b1_id not in ids, "User B's record leaked to User A"
        print(f"   [PASS] User A list only contains own records ({len(ids)} items). User B's record is isolated.")

        # 6. USER A CANNOT RETRIEVE USER B'S ANALYTICS
        print("\n6. Testing Cross-User Detail Retrieve Block (GET /api/seo/search-analytics/<user_b_id>/)...")
        res_get_b = client.get(f'/api/seo/search-analytics/{rec_b1_id}/')
        assert res_get_b.status_code == status.HTTP_404_NOT_FOUND, f"Expected 404, got {res_get_b.status_code}"
        print("   [PASS] Cross-user retrieve blocked with 404 Not Found.")

        # 7. USER A CANNOT MODIFY USER B'S ANALYTICS
        print("\n7. Testing Cross-User Modification Block (PATCH /api/seo/search-analytics/<user_b_id>/)...")
        res_patch_b = client.patch(f'/api/seo/search-analytics/{rec_b1_id}/', {'clicks': 9999}, format='json')
        assert res_patch_b.status_code == status.HTTP_404_NOT_FOUND, f"Expected 404, got {res_patch_b.status_code}"
        rec_b_check = SearchAnalyticsData.objects.get(id=rec_b1_id)
        assert rec_b_check.clicks == 88, "Record was modified unexpectedly"
        print("   [PASS] Cross-user modification blocked with 404 Not Found.")

        # 8. USER A CANNOT DELETE USER B'S ANALYTICS
        print("\n8. Testing Cross-User Deletion Block (DELETE /api/seo/search-analytics/<user_b_id>/)...")
        res_del_b = client.delete(f'/api/seo/search-analytics/{rec_b1_id}/')
        assert res_del_b.status_code == status.HTTP_404_NOT_FOUND, f"Expected 404, got {res_del_b.status_code}"
        assert SearchAnalyticsData.objects.filter(id=rec_b1_id).exists(), "User B's record was deleted"
        print("   [PASS] Cross-user deletion blocked with 404 Not Found.")

        # 9. USER A CAN UPDATE OWN ANALYTICS
        print("\n9. Testing Update Own Analytics Record (PATCH)...")
        res_patch_a = client.patch(f'/api/seo/search-analytics/{rec_a1_id}/', {'clicks': 160, 'position': '2.80'}, format='json')
        assert res_patch_a.status_code == status.HTTP_200_OK, f"Failed: {res_patch_a.data}"
        assert res_patch_a.data['clicks'] == 160
        assert Decimal(str(res_patch_a.data['position'])) == Decimal('2.80')
        print(f"   [PASS] User A updated Record #{rec_a1_id} clicks to 160, position to 2.80.")

        # Seed additional records for filtering tests
        rec_a2 = SearchAnalyticsData.objects.create(
            connection=conn_a,
            date=yesterday,
            query='telecom ethiopia 5g',
            page='https://addisinsight.net/telecom',
            country='eth',
            device='mobile',
            clicks=75,
            impressions=1500,
            ctr=Decimal('0.0500'),
            position=Decimal('4.50')
        )
        rec_a3 = SearchAnalyticsData.objects.create(
            connection=conn_a,
            date=two_days_ago,
            query='addis tech summit',
            page='https://addisinsight.net/events',
            country='usa',
            device='desktop',
            clicks=30,
            impressions=800,
            ctr=Decimal('0.0375'),
            position=Decimal('6.10')
        )

        # 10. PROJECT FILTERING (?project_id=...)
        print("\n10. Testing Project Filtering (?project_id=...)...")
        res_f_proj = client.get(f'/api/seo/search-analytics/?project_id={proj_a.id}')
        assert res_f_proj.status_code == status.HTTP_200_OK
        f_ids = [r['id'] for r in res_f_proj.data]
        assert len(f_ids) == 3
        assert rec_a1_id in f_ids and rec_a2.id in f_ids and rec_a3.id in f_ids
        print(f"   [PASS] Filter by Project #{proj_a.id} returned all 3 owned records.")

        # Cross-user project filter returns empty
        res_cross_proj = client.get(f'/api/seo/search-analytics/?project_id={proj_b.id}')
        assert res_cross_proj.status_code == status.HTTP_200_OK
        assert len(res_cross_proj.data) == 0
        print("   [PASS] Cross-user project filter safely returned empty list [].")

        # 11. CONNECTION FILTERING (?connection_id=...)
        print("\n11. Testing Connection Filtering (?connection_id=...)...")
        res_f_conn = client.get(f'/api/seo/search-analytics/?connection_id={conn_a.id}')
        assert res_f_conn.status_code == status.HTTP_200_OK
        assert len(res_f_conn.data) == 3
        print(f"   [PASS] Filter by Connection #{conn_a.id} returned all 3 owned records.")

        # 12. EXACT DATE FILTERING (?date=...)
        print("\n12. Testing Exact Date Filtering (?date=...)...")
        res_f_date = client.get(f'/api/seo/search-analytics/?date={yesterday}')
        assert res_f_date.status_code == status.HTTP_200_OK
        assert len(res_f_date.data) == 1
        assert res_f_date.data[0]['id'] == rec_a2.id
        print(f"   [PASS] Filter by Date {yesterday} returned exact record #{rec_a2.id}.")

        # 13. DATE RANGE FILTERING (?start_date=...&end_date=...)
        print("\n13. Testing Date Range Filtering (?start_date=...&end_date=...)...")
        res_f_range = client.get(f'/api/seo/search-analytics/?start_date={yesterday}&end_date={today}')
        assert res_f_range.status_code == status.HTTP_200_OK
        range_ids = [r['id'] for r in res_f_range.data]
        assert len(range_ids) == 2
        assert rec_a1_id in range_ids and rec_a2.id in range_ids
        assert rec_a3.id not in range_ids
        print(f"   [PASS] Date range filter returned 2 records within range [{yesterday} -> {today}].")

        # 14. QUERY FILTERING (?query=...)
        print("\n14. Testing Query Filtering (?query=...)...")
        res_f_query = client.get('/api/seo/search-analytics/?query=startup')
        assert res_f_query.status_code == status.HTTP_200_OK
        assert len(res_f_query.data) == 1
        assert res_f_query.data[0]['id'] == rec_a1_id
        print("   [PASS] Query substring filter returned matching record.")

        # 15. PAGE FILTERING (?page=...)
        print("\n15. Testing Page URL Filtering (?page=...)...")
        res_f_page = client.get('/api/seo/search-analytics/?page=telecom')
        assert res_f_page.status_code == status.HTTP_200_OK
        assert len(res_f_page.data) == 1
        assert res_f_page.data[0]['id'] == rec_a2.id
        print("   [PASS] Page substring filter returned matching record.")

        # 16. COUNTRY FILTERING (?country=...)
        print("\n16. Testing Country Filtering (?country=...)...")
        res_f_country = client.get('/api/seo/search-analytics/?country=usa')
        assert res_f_country.status_code == status.HTTP_200_OK
        assert len(res_f_country.data) == 1
        assert res_f_country.data[0]['id'] == rec_a3.id
        print("   [PASS] Country filter returned matching record.")

        # 17. DEVICE FILTERING (?device=...)
        print("\n17. Testing Device Filtering (?device=...)...")
        res_f_device = client.get('/api/seo/search-analytics/?device=mobile')
        assert res_f_device.status_code == status.HTTP_200_OK
        assert len(res_f_device.data) == 1
        assert res_f_device.data[0]['id'] == rec_a2.id
        print("   [PASS] Device filter returned matching record.")

        # 18. NEGATIVE CLICKS REJECTED
        print("\n18. Testing Negative Clicks Rejection...")
        bad_clicks_payload = {
            'connection': conn_a.id,
            'date': str(today),
            'query': 'new query 1',
            'clicks': -5,
            'impressions': 100
        }
        res_bad_clicks = client.post('/api/seo/search-analytics/', bad_clicks_payload, format='json')
        assert res_bad_clicks.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Negative clicks rejected with 400 Bad Request.")

        # 19. NEGATIVE IMPRESSIONS REJECTED
        print("\n19. Testing Negative Impressions Rejection...")
        bad_imp_payload = {
            'connection': conn_a.id,
            'date': str(today),
            'query': 'new query 2',
            'clicks': 5,
            'impressions': -100
        }
        res_bad_imp = client.post('/api/seo/search-analytics/', bad_imp_payload, format='json')
        assert res_bad_imp.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Negative impressions rejected with 400 Bad Request.")

        # 20. INVALID CTR REJECTED
        print("\n20. Testing Invalid CTR Rejection...")
        bad_ctr_payload = {
            'connection': conn_a.id,
            'date': str(today),
            'query': 'new query 3',
            'clicks': 5,
            'impressions': 100,
            'ctr': '-0.50'
        }
        res_bad_ctr = client.post('/api/seo/search-analytics/', bad_ctr_payload, format='json')
        assert res_bad_ctr.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Negative CTR rejected with 400 Bad Request.")

        # 21. INVALID AVERAGE POSITION REJECTED
        print("\n21. Testing Invalid Average Position Rejection...")
        bad_pos_payload = {
            'connection': conn_a.id,
            'date': str(today),
            'query': 'new query 4',
            'clicks': 5,
            'impressions': 100,
            'position': '-1.00'
        }
        res_bad_pos = client.post('/api/seo/search-analytics/', bad_pos_payload, format='json')
        assert res_bad_pos.status_code == status.HTTP_400_BAD_REQUEST

        bad_pos_overflow = {
            'connection': conn_a.id,
            'date': str(today),
            'query': 'new query 5',
            'clicks': 5,
            'impressions': 100,
            'position': '1005.00'
        }
        res_overflow = client.post('/api/seo/search-analytics/', bad_pos_overflow, format='json')
        assert res_overflow.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Invalid average position values rejected with 400 Bad Request.")

        # 22. DUPLICATE OBSERVATION REJECTED
        print("\n22. Testing Duplicate Observation Prevention...")
        duplicate_payload = {
            'connection': conn_a.id,
            'date': str(today),
            'query': 'ethiopia startup news',
            'page': 'https://addisinsight.net/startups',
            'country': 'eth',
            'device': 'desktop',
            'clicks': 50,
            'impressions': 1000
        }
        res_dup = client.post('/api/seo/search-analytics/', duplicate_payload, format='json')
        assert res_dup.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400, got {res_dup.status_code}"
        print("   [PASS] Duplicate observation rejected with 400 Bad Request.")

        # 23. USER A CAN DELETE OWN ANALYTICS RECORD
        print("\n23. Testing User A Delete Own Analytics Record (DELETE)...")
        res_del_own = client.delete(f'/api/seo/search-analytics/{rec_a3.id}/')
        assert res_del_own.status_code == status.HTTP_204_NO_CONTENT
        assert not SearchAnalyticsData.objects.filter(id=rec_a3.id).exists()
        print(f"   [PASS] Record #{rec_a3.id} deleted successfully (204 No Content).")

        # 24. CASCADE DELETION ON SEARCH CONSOLE CONNECTION AND PROJECT DELETE
        print("\n24. Testing Cascade Deletion on GSC Connection and Project Deletion...")
        test_proj_cascade = Project.objects.create(
            owner=user_a,
            name="Cascade Test Portal",
            website_url="https://cascade-test.com"
        )
        test_conn_cascade = SearchConsoleConnection.objects.create(
            project=test_proj_cascade,
            property_url="sc-domain:cascade-test.com",
            permission_level="siteOwner",
            is_connected=True
        )
        cascade_rec = SearchAnalyticsData.objects.create(
            connection=test_conn_cascade,
            date=today,
            query="cascade query",
            clicks=10,
            impressions=100
        )
        cascade_rec_id = cascade_rec.id
        assert SearchAnalyticsData.objects.filter(id=cascade_rec_id).exists()

        # Delete project
        test_proj_cascade.delete()
        assert not SearchConsoleConnection.objects.filter(id=test_conn_cascade.id).exists()
        assert not SearchAnalyticsData.objects.filter(id=cascade_rec_id).exists()
        print(f"   [PASS] Deleting parent Project cascaded and removed SearchAnalyticsData record #{cascade_rec_id}.")

        print("\n=====================================================")
        print(" ALL 24 SEARCH ANALYTICS API TESTS PASSED!           ")
        print("=====================================================\n")

    finally:
        # Clean up test users
        User.objects.filter(email__in=[email_a, email_b]).delete()

if __name__ == '__main__':
    run_search_analytics_tests()
