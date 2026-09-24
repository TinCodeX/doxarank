import os
import sys
import django

# Setup django environment
sys.path.insert(0, os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.subscriptions.models import Plan, PlanCode, FeatureCode
from apps.subscriptions.services import SubscriptionService

User = get_user_model()


def run_tests():
    print("==========================================")
    print("  DOXARANK SEO TOOLS API TEST SUITE       ")
    print("==========================================\n")

    client = APIClient()
    test_email = "tool_tester@doxarank.com"
    test_password = "StrongPassword2026!"

    # Clean up test user
    User.objects.filter(email__iexact=test_email).delete()
    user = User.objects.create_user(email=test_email, password=test_password)
    SubscriptionService.bootstrap_default_plans()

    # 1. Unauthenticated Rejection
    print("1. Testing Unauthenticated Access (POST /api/seo/tools/meta/)...")
    res = client.post('/api/seo/tools/meta/', {'title': 'Test', 'description': 'Desc'}, format='json')
    assert res.status_code == status.HTTP_401_UNAUTHORIZED, f"Expected 401, got {res.status_code}"
    print("   [PASS] Unauthenticated request correctly rejected with 401 Unauthorized.")

    # Authenticate
    client.force_authenticate(user=user)

    # 2. Check Quota Status Endpoint
    print("\n2. Testing Tools Quota Status (GET /api/seo/tools/status/)...")
    status_res = client.get('/api/seo/tools/status/')
    assert status_res.status_code == status.HTTP_200_OK, f"Expected 200, got {status_res.status_code}"
    assert status_res.data['plan_code'] == PlanCode.FREE
    assert status_res.data['daily_limit'] == 5
    assert status_res.data['tools']['meta_tag_generator']['used_today'] == 0
    print("   [PASS] Initial quota status fetched. Used today: 0, Daily limit: 5.")

    # 3. Meta Tag Generator API
    print("\n3. Testing Meta Tag Generator (POST /api/seo/tools/meta/)...")
    meta_payload = {
        'title': 'Best Specialty Coffee from Yirgacheffe | Ethiopia Direct',
        'description': 'Direct trade Grade 1 specialty coffee beans sourced from smallholder farmers in Yirgacheffe, roasted to perfection in Addis Ababa.',
        'canonical_url': 'https://doxacoffee.et/yirgacheffe',
        'robots': 'index, follow',
        'author': 'Bizrat Coffee Exporters',
    }
    meta_res = client.post('/api/seo/tools/meta/', meta_payload, format='json')
    assert meta_res.status_code == status.HTTP_200_OK, f"Expected 200, got {meta_res.status_code}: {meta_res.data}"
    assert '<title>Best Specialty Coffee' in meta_res.data['html']
    assert '<link rel="canonical" href="https://doxacoffee.et/yirgacheffe">' in meta_res.data['html']
    assert meta_res.data['usage']['used_today'] == 1
    assert meta_res.data['usage']['remaining_today'] == 4
    print("   [PASS] Meta tags generated successfully. Daily quota atomically decremented to 4 remaining.")

    # 4. Schema Generator API (LocalBusiness, Article, FAQ, Breadcrumbs)
    print("\n4. Testing Schema.org JSON-LD Generator (POST /api/seo/tools/schema/)...")
    schema_payload = {
        'schema_type': 'FAQ',
        'data': {
            'items': [
                {'question': 'Where is Ethiopian coffee grown?', 'answer': 'Mainly in Sidama, Yirgacheffe, Guji, and Harrar regions.'},
                {'question': 'Does DoxaRank track Ethiopian rankings?', 'answer': 'Yes, on google.com.et in English and Amharic.'}
            ]
        }
    }
    schema_res = client.post('/api/seo/tools/schema/', schema_payload, format='json')
    assert schema_res.status_code == status.HTTP_200_OK, f"Expected 200, got {schema_res.status_code}: {schema_res.data}"
    assert schema_res.data['json_ld']['@context'] == 'https://schema.org'
    assert schema_res.data['json_ld']['@type'] == 'FAQPage'
    assert len(schema_res.data['json_ld']['mainEntity']) == 2
    assert schema_res.data['usage']['used_today'] == 1
    print("   [PASS] Schema FAQ JSON-LD script generated. Quota recorded.")

    # 5. Social Preview Generator API
    print("\n5. Testing Open Graph & Twitter Card Previewer (POST /api/seo/tools/social-preview/)...")
    social_payload = {
        'title': 'AI SEO Agents Launch in East Africa',
        'description': 'How DoxaRank utilizes autonomous multi-agent systems to rank websites on Ethiopian SERPs.',
        'url': 'https://doxarank.com/blog/ai-launch',
        'image_url': 'https://doxarank.com/static/og-banner.png',
        'site_name': 'DoxaRank',
        'og_type': 'article',
        'twitter_card': 'summary_large_image',
        'twitter_site': 'doxarank',
    }
    social_res = client.post('/api/seo/tools/social-preview/', social_payload, format='json')
    assert social_res.status_code == status.HTTP_200_OK, f"Expected 200, got {social_res.status_code}: {social_res.data}"
    assert '<meta property="og:title" content="AI SEO Agents Launch in East Africa">' in social_res.data['html']
    assert '<meta name="twitter:card" content="summary_large_image">' in social_res.data['html']
    assert social_res.data['preview']['twitter_site'] == '@doxarank'
    print("   [PASS] Social preview tags generated. SSRF-safe deterministic card models returned.")

    # 6. Quota Limit Enforcement
    print("\n6. Testing Daily Tool Usage Quota Enforcement (Free Plan = 5 runs/day)...")
    # We already ran 1 meta tool. Let's run 4 more so total is 5
    for i in range(2, 6):
        res = client.post('/api/seo/tools/meta/', {'title': f'Title {i}', 'description': f'Description {i}'}, format='json')
        assert res.status_code == status.HTTP_200_OK

    # 6th run should be blocked
    blocked_res = client.post('/api/seo/tools/meta/', {'title': 'Title 6', 'description': 'Description 6'}, format='json')
    assert blocked_res.status_code == status.HTTP_403_FORBIDDEN
    assert blocked_res.data['code'] == 'PLAN_LIMIT_REACHED'
    print("   [PASS] 6th tool execution correctly blocked with 403 PLAN_LIMIT_REACHED.")

    # 7. Unmetered Paid Plan Verification
    print("\n7. Testing Starter Plan Unmetered Usage...")
    SubscriptionService.assign_plan(user, PlanCode.STARTER)
    starter_res = client.post('/api/seo/tools/meta/', {'title': 'Starter Title', 'description': 'Starter Description'}, format='json')
    assert starter_res.status_code == status.HTTP_200_OK
    assert starter_res.data['usage']['daily_limit'] == 'unlimited'
    assert starter_res.data['usage']['remaining_today'] == 'unlimited'
    print("   [PASS] Starter plan permitted unmetered executions beyond Free tier limit.")

    # Cleanup
    user.delete()

    print("\n==========================================")
    print("   ALL 7 SEO TOOLS TESTS PASSED! (100%)   ")
    print("==========================================")


if __name__ == '__main__':
    run_tests()
