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
from apps.seo.models import Keyword, KeywordRanking, SearchEngine, Country, Language, Device

User = get_user_model()

def run_rankings_tests():
    print("==========================================")
    print("  DOXARANK KEYWORD RANKINGS API TEST SUITE")
    print("==========================================\n")

    client = APIClient()

    # Clean up test users
    email_a = "ranking_runner_a@doxarank.com"
    email_b = "ranking_runner_b@doxarank.com"
    User.objects.filter(email__in=[email_a, email_b]).delete()

    user_a = User.objects.create_user(
        email=email_a,
        password="Password123!",
        first_name="Rank",
        last_name="TesterA"
    )
    user_b = User.objects.create_user(
        email=email_b,
        password="Password123!",
        first_name="Rank",
        last_name="TesterB"
    )

    try:
        # Create projects and keywords
        proj_a = Project.objects.create(
            owner=user_a,
            name="Addis Insight",
            website_url="https://addisinsight.net"
        )
        proj_b = Project.objects.create(
            owner=user_b,
            name="Shega Media",
            website_url="https://shega.co"
        )

        kw_a1 = Keyword.objects.create(
            project=proj_a,
            keyword="ethiopia tech news"
        )
        kw_a2 = Keyword.objects.create(
            project=proj_a,
            keyword="addis fintech trends"
        )
        kw_b1 = Keyword.objects.create(
            project=proj_b,
            keyword="shega venture report"
        )

        # 1. TEST UNAUTHENTICATED GET
        print("1. Testing Unauthenticated Access Rejection (GET /api/seo/rankings/)...")
        res = client.get('/api/seo/rankings/')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED
        print("   [PASS] 401 Unauthorized returned for unauthenticated request.")

        # 2 & 3. TEST CREATE RANKING OBSERVATIONS
        print("\n2 & 3. Testing Ranking Observation Creation for User A & User B...")
        client.force_authenticate(user=user_a)
        ts1 = timezone.now() - timezone.timedelta(days=1)
        r_a1_payload = {
            "keyword": kw_a1.id,
            "position": 14,
            "ranking_url": "https://addisinsight.net/ethiopia-tech-news",
            "search_engine": "google",
            "country": "ET",
            "language": "en",
            "device": "desktop",
            "recorded_at": ts1.isoformat()
        }
        res_a1 = client.post('/api/seo/rankings/', r_a1_payload, format='json')
        assert res_a1.status_code == status.HTTP_201_CREATED, f"Failed: {res_a1.data}"
        ranking_a1_id = res_a1.data['id']
        assert res_a1.data['position'] == 14
        assert res_a1.data['keyword_name'] == "ethiopia tech news"
        assert res_a1.data['project_name'] == "Addis Insight"
        print(f"   [PASS] User A created Ranking #{ranking_a1_id} (Position 14) for Keyword #{kw_a1.id}.")

        # User B creates ranking for kw_b1
        client.force_authenticate(user=user_b)
        res_b1 = client.post('/api/seo/rankings/', {
            "keyword": kw_b1.id,
            "position": 3,
            "ranking_url": "https://shega.co/report",
            "recorded_at": ts1.isoformat()
        }, format='json')
        assert res_b1.status_code == status.HTTP_201_CREATED
        ranking_b1_id = res_b1.data['id']
        print(f"   [PASS] User B created Ranking #{ranking_b1_id} (Position 3) for Keyword #{kw_b1.id}.")

        # 4. TEST USER A CANNOT CREATE RANKING FOR USER B'S KEYWORD
        print("\n4. Testing Cross-User Ranking Injection Block...")
        client.force_authenticate(user=user_a)
        cross_create_res = client.post('/api/seo/rankings/', {
            "keyword": kw_b1.id, # Owned by User B!
            "position": 1,
            "recorded_at": timezone.now().isoformat()
        }, format='json')
        assert cross_create_res.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Blocked with 400 Bad Request (Serializer ownership validation).")

        # 5 & 6. TEST LIST ISOLATION
        print("\n5 & 6. Testing List Isolation (User A only sees own rankings)...")
        list_res = client.get('/api/seo/rankings/')
        assert list_res.status_code == status.HTTP_200_OK
        ids = [r['id'] for r in list_res.data]
        assert ranking_a1_id in ids
        assert ranking_b1_id not in ids
        print(f"   [PASS] User A list only contains own rankings ({len(ids)} items). User B's ranking is hidden.")

        # 7. TEST CROSS-USER RETRIEVE BLOCK
        print("\n7. Testing Cross-User Retrieve Block (GET /api/seo/rankings/<user_b_id>/)...")
        get_b_res = client.get(f'/api/seo/rankings/{ranking_b1_id}/')
        assert get_b_res.status_code == status.HTTP_404_NOT_FOUND
        print("   [PASS] Blocked with 404 Not Found.")

        # 8. TEST CROSS-USER MODIFY BLOCK
        print("\n8. Testing Cross-User Modify Block (PATCH /api/seo/rankings/<user_b_id>/)...")
        patch_b_res = client.patch(f'/api/seo/rankings/{ranking_b1_id}/', {'position': 99}, format='json')
        assert patch_b_res.status_code == status.HTTP_404_NOT_FOUND
        print("   [PASS] Blocked with 404 Not Found.")

        # 9. TEST CROSS-USER DELETE BLOCK
        print("\n9. Testing Cross-User Delete Block (DELETE /api/seo/rankings/<user_b_id>/)...")
        del_b_res = client.delete(f'/api/seo/rankings/{ranking_b1_id}/')
        assert del_b_res.status_code == status.HTTP_404_NOT_FOUND
        assert KeywordRanking.objects.filter(id=ranking_b1_id).exists()
        print("   [PASS] Blocked with 404 Not Found. Record intact.")

        # 10. TEST UPDATE OWN RANKING
        print("\n10. Testing Update Own Ranking (PATCH /api/seo/rankings/<user_a_id>/)...")
        patch_a_res = client.patch(f'/api/seo/rankings/{ranking_a1_id}/', {
            'position': 11,
            'ranking_url': 'https://addisinsight.net/updated-slug'
        }, format='json')
        assert patch_a_res.status_code == status.HTTP_200_OK
        assert patch_a_res.data['position'] == 11
        print("   [PASS] Updated position to 11 and ranking URL successfully.")

        # 11. TEST DELETE OWN RANKING
        print("\n11. Testing Delete Own Ranking (DELETE /api/seo/rankings/<user_a_id>/)...")
        del_a_res = client.delete(f'/api/seo/rankings/{ranking_a1_id}/')
        assert del_a_res.status_code == status.HTTP_204_NO_CONTENT
        assert not KeywordRanking.objects.filter(id=ranking_a1_id).exists()
        print("   [PASS] Deleted own ranking observation (204 No Content).")

        # 12 & 13. TEST VALIDATIONS (POSITION & URL)
        print("\n12 & 13. Testing Validations (Position & URL)...")
        bad_pos_res = client.post('/api/seo/rankings/', {
            'keyword': kw_a1.id,
            'position': 0, # Invalid <= 0
            'recorded_at': timezone.now().isoformat()
        }, format='json')
        assert bad_pos_res.status_code == status.HTTP_400_BAD_REQUEST

        bad_url_res = client.post('/api/seo/rankings/', {
            'keyword': kw_a1.id,
            'position': 5,
            'ranking_url': 'invalid_url_format',
            'recorded_at': timezone.now().isoformat()
        }, format='json')
        assert bad_url_res.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Position <= 0 and malformed URLs rejected with 400 Bad Request.")

        # 14 & 15. TEST KEYWORD FILTERING & ISOLATION
        print("\n14 & 15. Testing Keyword Filtering (?keyword_id=...)...")
        ts_now = timezone.now()
        r_new1 = KeywordRanking.objects.create(keyword=kw_a1, position=7, recorded_at=ts_now)
        r_new2 = KeywordRanking.objects.create(keyword=kw_a2, position=18, recorded_at=ts_now)

        filter_res = client.get(f'/api/seo/rankings/?keyword_id={kw_a1.id}')
        assert filter_res.status_code == status.HTTP_200_OK
        ids = [r['id'] for r in filter_res.data]
        assert r_new1.id in ids
        assert r_new2.id not in ids
        print(f"   [PASS] Filter by Keyword #{kw_a1.id} returned only its ranking history.")

        cross_filter_res = client.get(f'/api/seo/rankings/?keyword_id={kw_b1.id}')
        assert cross_filter_res.status_code == status.HTTP_200_OK
        assert len(cross_filter_res.data) == 0
        print("   [PASS] Cross-user keyword filter returned empty list [].")

        # 16. TEST DUPLICATE CONSTRAINT
        print("\n16. Testing Duplicate Observation Constraint...")
        dup_res = client.post('/api/seo/rankings/', {
            'keyword': kw_a1.id,
            'position': 9,
            'search_engine': 'google',
            'country': 'ET',
            'language': 'en',
            'device': 'desktop',
            'recorded_at': ts_now.isoformat()
        }, format='json')
        assert dup_res.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Duplicate observation at exact timestamp rejected with 400 Bad Request.")

        # 17 & 18. TEST ASSOCIATION & CASCADE DELETION
        print("\n17 & 18. Testing Association & Cascade Deletion on Keyword Delete...")
        assert r_new1.keyword == kw_a1
        assert r_new1.keyword.project == proj_a
        kw_a1_id = kw_a1.id
        kw_a1.delete()
        assert not KeywordRanking.objects.filter(id=r_new1.id).exists()
        print(f"   [PASS] Deleting Keyword #{kw_a1_id} cascaded and removed ranking observations.")

        print("\n==========================================")
        print("  ALL 18 KEYWORD RANKING TESTS PASSED!    ")
        print("==========================================\n")

    finally:
        User.objects.filter(email__in=[email_a, email_b]).delete()

if __name__ == '__main__':
    run_rankings_tests()
