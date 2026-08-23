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
from apps.seo.models import Keyword, SearchEngine, Country, Language, Device

User = get_user_model()

def run_seo_tests():
    print("==========================================")
    print("  DOXARANK SEO KEYWORDS API TEST SUITE    ")
    print("==========================================\n")

    client = APIClient()

    # Clean up test users
    email_a = "seo_tester_a@doxarank.com"
    email_b = "seo_tester_b@doxarank.com"
    User.objects.filter(email__in=[email_a, email_b]).delete()

    user_a = User.objects.create_user(
        email=email_a,
        password="Password123!",
        first_name="SEO",
        last_name="TesterA"
    )
    user_b = User.objects.create_user(
        email=email_b,
        password="Password123!",
        first_name="SEO",
        last_name="TesterB"
    )

    try:
        # Create projects
        proj_a1 = Project.objects.create(
            owner=user_a,
            name="Addis Insight",
            website_url="https://addisinsight.net"
        )
        proj_a2 = Project.objects.create(
            owner=user_a,
            name="Ethio Telecom Blog",
            website_url="https://ethiotelecom.et"
        )
        proj_b1 = Project.objects.create(
            owner=user_b,
            name="Shega Media",
            website_url="https://shega.co"
        )

        # 1. TEST UNAUTHENTICATED GET
        print("1. Testing Unauthenticated Access Rejection (GET /api/seo/keywords/)...")
        res = client.get('/api/seo/keywords/')
        assert res.status_code == status.HTTP_401_UNAUTHORIZED, f"Expected 401, got {res.status_code}"
        print("   [PASS] 401 Unauthorized returned for unauthenticated request.")

        # 2 & 3 & 4. TEST CREATE KEYWORD & ATTRIBUTION
        print("\n2, 3 & 4. Testing Keyword Creation & Project Attribution (POST /api/seo/keywords/)...")
        client.force_authenticate(user=user_a)
        kw_payload = {
            "project": proj_a1.id,
            "keyword": "ethiopia tech startups",
            "search_engine": "google",
            "country": "ET",
            "language": "en",
            "device": "desktop"
        }
        create_res = client.post('/api/seo/keywords/', kw_payload, format='json')
        assert create_res.status_code == status.HTTP_201_CREATED, f"Creation failed: {create_res.data}"
        kw_a1_id = create_res.data['id']
        assert create_res.data['project'] == proj_a1.id
        assert create_res.data['project_name'] == "Addis Insight"
        print(f"   [PASS] Created Keyword #{kw_a1_id} '{create_res.data['keyword']}' attached to Project #{proj_a1.id}.")

        # Create another keyword for User A in proj_a2
        client.post('/api/seo/keywords/', {
            "project": proj_a2.id,
            "keyword": "telecom data packages addis",
            "language": "am"
        }, format='json')

        # Create a keyword for User B in proj_b1
        client.force_authenticate(user=user_b)
        b_create_res = client.post('/api/seo/keywords/', {
            "project": proj_b1.id,
            "keyword": "fintech ethiopia news",
            "country": "ET"
        }, format='json')
        kw_b1_id = b_create_res.data['id']
        print(f"   [PASS] Created Keyword #{kw_b1_id} for User B attached to Project #{proj_b1.id}.")

        # 5. TEST CANNOT CREATE KEYWORD IN ANOTHER USER'S PROJECT
        print("\n5. Testing Cross-User Project Injection Block (POST /api/seo/keywords/ with other user's project)...")
        client.force_authenticate(user=user_a)
        unauth_proj_res = client.post('/api/seo/keywords/', {
            "project": proj_b1.id, # Owned by User B!
            "keyword": "hacked keyword"
        }, format='json')
        assert unauth_proj_res.status_code == status.HTTP_400_BAD_REQUEST, "Should block creating keyword in other's project"
        print("   [PASS] Creation blocked with 400 Bad Request (Permission check in serializer).")

        # 6. TEST CANNOT RETRIEVE ANOTHER USER'S KEYWORD
        print("\n6. Testing Cross-User Keyword Read Block (GET /api/seo/keywords/<user_b_kw_id>/)...")
        cross_get_res = client.get(f'/api/seo/keywords/{kw_b1_id}/')
        assert cross_get_res.status_code == status.HTTP_404_NOT_FOUND
        print(f"   [PASS] Read blocked with 404 Not Found.")

        # 7. TEST CANNOT MODIFY ANOTHER USER'S KEYWORD
        print("\n7. Testing Cross-User Keyword Modify Block (PATCH /api/seo/keywords/<user_b_kw_id>/)...")
        cross_patch_res = client.patch(f'/api/seo/keywords/{kw_b1_id}/', {'keyword': 'hacked name'}, format='json')
        assert cross_patch_res.status_code == status.HTTP_404_NOT_FOUND
        print("   [PASS] Modification blocked with 404 Not Found.")

        # 8. TEST CANNOT DELETE ANOTHER USER'S KEYWORD
        print("\n8. Testing Cross-User Keyword Delete Block (DELETE /api/seo/keywords/<user_b_kw_id>/)...")
        cross_del_res = client.delete(f'/api/seo/keywords/{kw_b1_id}/')
        assert cross_del_res.status_code == status.HTTP_404_NOT_FOUND
        assert Keyword.objects.filter(id=kw_b1_id).exists(), "User B keyword must remain untouched"
        print("   [PASS] Deletion blocked with 404 Not Found. Record intact.")

        # 9. TEST USER UPDATES OWN KEYWORD
        print("\n9. Testing Update Own Keyword (PATCH /api/seo/keywords/<user_a_kw_id>/)...")
        patch_res = client.patch(f'/api/seo/keywords/{kw_a1_id}/', {'is_active': False, 'device': 'mobile'}, format='json')
        assert patch_res.status_code == status.HTTP_200_OK
        assert patch_res.data['is_active'] is False
        assert patch_res.data['device'] == 'mobile'
        print("   [PASS] Updated own keyword active state and device successfully.")

        # 10. TEST USER DELETES OWN KEYWORD
        print("\n10. Testing Delete Own Keyword (DELETE /api/seo/keywords/<user_a_kw_id>/)...")
        del_res = client.delete(f'/api/seo/keywords/{kw_a1_id}/')
        assert del_res.status_code == status.HTTP_204_NO_CONTENT
        assert not Keyword.objects.filter(id=kw_a1_id).exists()
        print("   [PASS] Deleted own keyword successfully (204 No Content).")

        # 11, 12, 13, 14. TEST VALIDATIONS
        print("\n11 - 14. Testing Field Validations (keyword, search_engine, language, device)...")
        bad_tests = [
            ({'project': proj_a1.id, 'keyword': ' '}, "empty keyword"),
            ({'project': proj_a1.id, 'keyword': 'a'}, "short keyword"),
            ({'project': proj_a1.id, 'keyword': 'valid kw', 'search_engine': 'yahoo'}, "unsupported engine"),
            ({'project': proj_a1.id, 'keyword': 'valid kw', 'language': 'fr'}, "unsupported language"),
            ({'project': proj_a1.id, 'keyword': 'valid kw', 'device': 'smart_tv'}, "unsupported device"),
        ]
        for bad_payload, label in bad_tests:
            bad_res = client.post('/api/seo/keywords/', bad_payload, format='json')
            assert bad_res.status_code == status.HTTP_400_BAD_REQUEST, f"Failed for {label}: {bad_res.data}"
        print("   [PASS] All invalid field inputs correctly rejected with 400 Bad Request.")

        # 15 & 16. TEST PROJECT FILTERING & OWNERSHIP PROTECTION
        print("\n15 & 16. Testing Project Filtering & Isolation (?project_id=...)...")
        # Filter by own project proj_a2
        filter_res = client.get(f'/api/seo/keywords/?project_id={proj_a2.id}')
        assert filter_res.status_code == status.HTTP_200_OK
        assert len(filter_res.data) == 1
        assert filter_res.data[0]['project'] == proj_a2.id
        print(f"   [PASS] Filtered by Project #{proj_a2.id} returned exactly 1 matching keyword.")

        # Filter by User B's project proj_b1 -> Must return []
        cross_filter_res = client.get(f'/api/seo/keywords/?project_id={proj_b1.id}')
        assert cross_filter_res.status_code == status.HTTP_200_OK
        assert len(cross_filter_res.data) == 0, "Cross-user project filter MUST return empty list"
        print("   [PASS] Cross-user project filter safely returned empty list [].")

        # 17. TEST DUPLICATE KEYWORD CONFIGURATION
        print("\n17. Testing Duplicate Keyword Constraint Prevention...")
        dup_payload = {
            "project": proj_a2.id,
            "keyword": "telecom data packages addis",
            "search_engine": "google",
            "country": "ET",
            "language": "am",
            "device": "desktop"
        }
        dup_res = client.post('/api/seo/keywords/', dup_payload, format='json')
        assert dup_res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'keyword' in dup_res.data or 'non_field_errors' in dup_res.data
        print("   [PASS] Duplicate keyword configuration rejected with 400 Bad Request.")

        print("\n==========================================")
        print("   ALL 17 SEO KEYWORD TESTS PASSED! (100%)")
        print("==========================================\n")

    finally:
        User.objects.filter(email__in=[email_a, email_b]).delete()

if __name__ == '__main__':
    run_seo_tests()
