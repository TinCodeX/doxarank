import os
import sys

# Force UTF-8 for console output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import json
from decimal import Decimal
from datetime import timedelta
import django

# Setup django environment
sys.path.insert(0, os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
settings.CELERY_TASK_ALWAYS_EAGER = True
settings.CELERY_TASK_EAGER_PROPAGATES = True

from config.celery import app as celery_app
celery_app.conf.update(
    task_always_eager=True,
    task_eager_propagates=True,
    result_backend='cache+memory://',
)

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.projects.models import Project
from apps.seo.models import (
    Keyword,
    KeywordRanking,
    RankCheckJob,
    Competitor,
    Recommendation,
)
from apps.subscriptions.models import (
    Plan,
    PlanCode,
    Subscription,
    SubscriptionStatus,
    PaymentTransaction,
    PaymentStatus,
)
from apps.subscriptions.services import SubscriptionService, PaymentService
from apps.subscriptions.tasks import expire_subscriptions

User = get_user_model()


def log_step(title):
    print(f"\n---> {title}")


def run_e2e_audit():
    print("=" * 70)
    print("      DOXARANK END-TO-END INTEGRATION & JOURNEY AUDIT")
    print("=" * 70)

    client = APIClient()
    test_email = "e2e_journey_user@doxarank.com"
    test_password = "E2E_SecurePassword_2026!"

    # Ensure plans are seeded
    SubscriptionService.bootstrap_default_plans()

    # Clean up prior test data
    User.objects.filter(email__iexact=test_email).delete()

    # -------------------------------------------------------------------------
    # STEP 1: MARKETING INTEGRATION VERIFICATION
    # -------------------------------------------------------------------------
    log_step("STEP 1: Verify Marketing to Dashboard Link Integrity")
    marketing_login_path = os.path.abspath("../marketing/src/pages/login.astro")
    marketing_signup_path = os.path.abspath("../marketing/src/pages/signup.astro")
    assert os.path.exists(marketing_login_path), "Marketing login.astro file missing"
    assert os.path.exists(marketing_signup_path), "Marketing signup.astro file missing"

    with open(marketing_login_path, 'r', encoding='utf-8') as f:
        login_content = f.read()
        assert "dashboardUrl}/login" in login_content, "Marketing login doesn't link to dashboard /login"

    with open(marketing_signup_path, 'r', encoding='utf-8') as f:
        signup_content = f.read()
        assert "dashboardUrl}/register" in signup_content, "Marketing signup doesn't link to dashboard /register"
    print("   [PASS] Marketing pages correctly route to Dashboard /login and /register.")

    # -------------------------------------------------------------------------
    # STEP 2: USER REGISTRATION & AUTHENTICATION
    # -------------------------------------------------------------------------
    log_step("STEP 2: User Registration & JWT Authentication (POST /api/auth/register/)")
    reg_res = client.post(
        '/api/auth/register/',
        {
            'email': test_email,
            'password': test_password,
            'first_name': 'E2E',
            'last_name': 'Auditor',
        },
        format='json'
    )
    assert reg_res.status_code == status.HTTP_201_CREATED, f"Registration failed: {reg_res.data}"
    user_id = reg_res.data['user']['id']
    tokens = reg_res.data['tokens']
    access_token = tokens['access']
    refresh_token = tokens['refresh']
    print(f"   [PASS] User registered (ID: {user_id}). JWT tokens received.")

    # Test login
    log_step("STEP 2b: User Login (POST /api/auth/login/)")
    login_res = client.post(
        '/api/auth/login/',
        {'email': test_email, 'password': test_password},
        format='json'
    )
    assert login_res.status_code == status.HTTP_200_OK, f"Login failed: {login_res.data}"
    access_token = login_res.data['tokens']['access']
    refresh_token = login_res.data['tokens']['refresh']
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    # Verify Profile
    me_res = client.get('/api/auth/me/')
    assert me_res.status_code == status.HTTP_200_OK
    assert me_res.data['email'] == test_email
    print(f"   [PASS] User profile authenticated: {me_res.data['full_name']}")

    # -------------------------------------------------------------------------
    # STEP 3: INITIAL SUBSCRIPTION STATUS
    # -------------------------------------------------------------------------
    log_step("STEP 3: Check Initial Subscription Status (GET /api/subscriptions/me/)")
    sub_res = client.get('/api/subscriptions/me/')
    assert sub_res.status_code == status.HTTP_200_OK
    plan_code = sub_res.data.get('plan_code') or sub_res.data.get('plan', {}).get('code')
    assert plan_code == PlanCode.FREE, f"Default plan should be FREE, got {plan_code}"
    print(f"   [PASS] Initial subscription correctly assigned to FREE tier.")

    # -------------------------------------------------------------------------
    # STEP 4: PROJECT CREATION
    # -------------------------------------------------------------------------
    log_step("STEP 4: Project Creation (POST /api/projects/)")
    proj_res = client.post(
        '/api/projects/',
        {
            'name': 'Addis Grand Hotel SEO',
            'website_url': 'https://addisgrandhotel.com',
        },
        format='json'
    )
    assert proj_res.status_code == status.HTTP_201_CREATED, f"Project creation failed: {proj_res.data}"
    project_id = proj_res.data['id']
    website_url = proj_res.data['website_url']
    proj_obj = Project.objects.get(id=project_id)
    from urllib.parse import urlparse
    domain = urlparse(proj_obj.website_url).netloc
    assert domain == 'addisgrandhotel.com'
    print(f"   [PASS] Project created #{project_id} for URL '{website_url}' (domain: '{domain}').")

    # -------------------------------------------------------------------------
    # STEP 5: KEYWORD MANAGEMENT (Multi-lingual & Devices)
    # -------------------------------------------------------------------------
    log_step("STEP 5: Multi-lingual Keyword Management (English, Amharic, Oromo)")
    keywords_to_create = [
        {'keyword': 'luxury hotel addis ababa', 'language': 'en', 'device': 'desktop'},
        {'keyword': 'በአዲስ አበባ ምርጥ ሆቴል', 'language': 'am', 'device': 'desktop'},
        {'keyword': 'Hoteela gaarii Finfinnee', 'language': 'om', 'device': 'mobile'},
    ]
    created_keywords = []
    for kw_data in keywords_to_create:
        kw_res = client.post(
            '/api/seo/keywords/',
            {
                'project': project_id,
                'keyword': kw_data['keyword'],
                'search_engine': 'google',
                'search_domain': 'google.com.et',
                'country': 'ET',
                'language': kw_data['language'],
                'device': kw_data['device'],
                'is_active': True,
            },
            format='json'
        )
        assert kw_res.status_code == status.HTTP_201_CREATED, f"Keyword creation failed: {kw_res.data}"
        created_keywords.append(kw_res.data)
        print(f"   [PASS] Added keyword #{kw_res.data['id']}: '{kw_data['keyword']}' ({kw_data['language']}/{kw_data['device']}).")

    # -------------------------------------------------------------------------
    # STEP 6: STANDALONE SEO TOOLS EXECUTION & FREE PLAN QUOTA
    # -------------------------------------------------------------------------
    # STEP 6: STANDALONE SEO TOOLS EXECUTION & FREE PLAN QUOTA
    # -------------------------------------------------------------------------
    log_step("STEP 6: Standalone SEO Tools & Free Tier Quota Check")
    meta_res = client.post(
        '/api/seo/tools/meta/',
        {
            'title': 'Addis Grand Hotel - Luxury Stay in Ethiopia',
            'description': 'Experience the finest luxury accommodations in the heart of Addis Ababa, Ethiopia.',
            'canonical_url': 'https://addisgrandhotel.com',
        },
        format='json'
    )
    assert meta_res.status_code == status.HTTP_200_OK, f"Meta tool failed: {meta_res.data}"
    assert '<title>Addis Grand Hotel' in meta_res.data['html']
    print("   [PASS] Meta tag generator executed successfully.")

    # Test Amharic Fidel Normalizer Tool
    amharic_res = client.post(
        '/api/seo/tools/amharic-normalizer/',
        {
            'text': 'በአዲስ አበባ ሐይቅ ሆቴል እና ኅብረት',
        },
        format='json'
    )
    assert amharic_res.status_code == status.HTTP_200_OK, f"Amharic normalizer failed: {amharic_res.data}"
    assert amharic_res.data['has_amharic_script'] is True
    print(f"   [PASS] Amharic Fidel Normalizer executed. Output: '{amharic_res.data['normalized_text']}'")

    # Check quota status
    quota_res = client.get('/api/seo/tools/status/')
    assert quota_res.status_code == status.HTTP_200_OK
    assert quota_res.data['plan_code'] == PlanCode.FREE
    assert quota_res.data['daily_limit'] == 5
    meta_used = quota_res.data['tools']['meta_tag_generator']['used_today']
    print(f"   [PASS] Tools quota: {meta_used}/{quota_res.data['daily_limit']} used today for meta tag generator.")

    # -------------------------------------------------------------------------
    # STEP 7: RANK TRACKING GATING ON FREE TIER
    # -------------------------------------------------------------------------
    log_step("STEP 7: Rank Tracker Gating Check on Free Tier")
    free_check_res = client.post(
        '/api/seo/rankings/check/',
        {'project_id': project_id},
        format='json'
    )
    assert free_check_res.status_code == status.HTTP_403_FORBIDDEN, f"Free plan should block rank tracking: {free_check_res.data}"
    print("   [PASS] Rank tracking correctly blocked on FREE tier with 403 Forbidden.")

    # -------------------------------------------------------------------------
    # STEP 8: SUBSCRIPTION UPGRADE & PAYMENT SANDBOX (STARTER PLAN)
    # -------------------------------------------------------------------------
    log_step("STEP 8: Subscription Upgrade via Doxa Payments Sandbox (1,500 ETB)")
    plans_res = client.get('/api/subscriptions/plans/')
    assert plans_res.status_code == status.HTTP_200_OK
    starter_plan = next((p for p in plans_res.data if p['code'] == PlanCode.STARTER), None)
    assert starter_plan is not None, "Starter plan not found in plan list"
    print(f"   [PASS] Found Starter Plan: {starter_plan['name']} - {starter_plan['monthly_price']} {starter_plan['currency']}/mo.")

    # Create Checkout Session
    checkout_res = client.post(
        '/api/subscriptions/checkout/',
        {
            'plan_code': PlanCode.STARTER,
            'return_url': 'http://localhost:5173/billing?status=success',
            'cancel_url': 'http://localhost:5173/billing?status=cancelled',
        },
        format='json'
    )
    assert checkout_res.status_code == status.HTTP_201_CREATED, f"Checkout creation failed: {checkout_res.data}"
    tx_id = checkout_res.data['id']
    ref = checkout_res.data['checkout_reference']
    amount = checkout_res.data['amount']
    currency = checkout_res.data['currency']
    print(f"   [PASS] Checkout session created: Tx #{tx_id} (Ref: {ref}), {amount} {currency}.")

    # Verify / Settle in Sandbox mode
    verify_res = client.post(
        f"/api/subscriptions/payments/{tx_id}/verify/",
        {
            'payload': {
                'status': 'SUCCESS',
                'provider_transaction_id': f"doxa_sim_{ref}",
            }
        },
        format='json'
    )
    assert verify_res.status_code == status.HTTP_200_OK, f"Verification failed: {verify_res.data}"
    assert verify_res.data['status'] == PaymentStatus.SUCCESS
    print(f"   [PASS] Payment verified and settled with status SUCCESS.")

    # Verify user is now on Starter Plan
    sub_me_after = client.get('/api/subscriptions/me/')
    assert sub_me_after.status_code == status.HTTP_200_OK
    current_plan = sub_me_after.data.get('plan_code') or sub_me_after.data.get('plan', {}).get('code')
    assert current_plan == PlanCode.STARTER, f"Plan should now be STARTER, got {current_plan}"
    print(f"   [PASS] User successfully upgraded to {current_plan.upper()} plan!")
    print(f"         Status: {sub_me_after.data.get('status')}, Renews: {sub_me_after.data.get('current_period_end')}")

    # Verify unmetered tools on Starter plan
    tool_status_after = client.get('/api/seo/tools/status/')
    assert tool_status_after.data['plan_code'] == PlanCode.STARTER
    assert tool_status_after.data['daily_limit'] == 'unlimited'
    print(f"   [PASS] Tool executions are now unmetered on STARTER plan.")

    # -------------------------------------------------------------------------
    # STEP 9: RANK TRACKING ON STARTER TIER (Execution & Statuses)
    # -------------------------------------------------------------------------
    log_step("STEP 9: Rank Tracker Execution on google.com.et (Permitted on Starter Plan)")
    from unittest.mock import patch

    # Mock outbound SERP client to return deterministic organic results
    mock_organic_html = """
    <html><body><div id="search"><div class="g">
      <div class="yuRUbf"><a href="https://addisgrandhotel.com/rooms"><h3 class="LC20lb">Addis Grand Hotel Official</h3></a></div>
    </div></div></body></html>
    """
    with patch('apps.seo.services.rank_tracker.GoogleEtSerpClient.fetch_serp', return_value=mock_organic_html):
        check_launch_res = client.post(
            '/api/seo/rankings/check/',
            {'project_id': project_id},
            format='json'
        )
        assert check_launch_res.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED), f"Check launch failed: {check_launch_res.data}"
        job_id = check_launch_res.data.get('job_id')
        print(f"   [PASS] Rank check launched, Job #{job_id}. Status: {check_launch_res.data.get('status')}")

    # Inspect rankings table
    rankings_res = client.get(f"/api/seo/rankings/?project_id={project_id}")
    assert rankings_res.status_code == status.HTTP_200_OK
    ranking_records = rankings_res.data if isinstance(rankings_res.data, list) else rankings_res.data.get('results', [])
    print(f"   [PASS] Fetched {len(ranking_records)} ranking observations.")
    for rec in ranking_records:
        pos_display = rec.get('position') if rec.get('position') is not None else "NOT FOUND"
        print(f"         Keyword #{rec.get('keyword')}: {pos_display} (status: {rec.get('result_status')}, domain: {rec.get('search_engine')})")

    # -------------------------------------------------------------------------
    # STEP 10: COMPETITOR SNAPSHOTS GATING & UPGRADE TO AGENCY
    # -------------------------------------------------------------------------
    log_step("STEP 10: Competitor Snapshots Gating on Starter & Upgrade to Agency")
    starter_comp_res = client.post(
        '/api/seo/competitors/',
        {
            'project': project_id,
            'domain': 'rivalhotel-addis.com',
            'name': 'Rival Hotel Addis',
            'is_active': True,
        },
        format='json'
    )
    assert starter_comp_res.status_code == status.HTTP_403_FORBIDDEN, "Competitors should require Agency plan"
    print("   [PASS] Competitor Snapshots correctly blocked on Starter tier with 403 Forbidden.")

    # Upgrade from Starter to Agency via Doxa Payments
    log_step("STEP 10b: Upgrade to Agency Plan (6,000 ETB)")
    agency_checkout_res = client.post(
        '/api/subscriptions/checkout/',
        {
            'plan_code': PlanCode.AGENCY,
            'return_url': 'http://localhost:5173/billing?status=success',
            'cancel_url': 'http://localhost:5173/billing?status=cancelled',
        },
        format='json'
    )
    assert agency_checkout_res.status_code == status.HTTP_201_CREATED
    agency_tx_id = agency_checkout_res.data['id']
    agency_ref = agency_checkout_res.data['checkout_reference']

    # Settle in sandbox
    agency_verify_res = client.post(
        f"/api/subscriptions/payments/{agency_tx_id}/verify/",
        {
            'payload': {
                'status': 'SUCCESS',
                'provider_transaction_id': f"doxa_sim_{agency_ref}",
            }
        },
        format='json'
    )
    assert agency_verify_res.status_code == status.HTTP_200_OK

    # Now on Agency tier: create competitor
    agency_comp_res = client.post(
        '/api/seo/competitors/',
        {
            'project': project_id,
            'domain': 'rivalhotel-addis.com',
            'name': 'Rival Hotel Addis',
            'is_active': True,
        },
        format='json'
    )
    assert agency_comp_res.status_code == status.HTTP_201_CREATED, f"Competitor creation failed on Agency: {agency_comp_res.data}"
    comp_id = agency_comp_res.data['id']
    print(f"   [PASS] Added competitor #{comp_id} on Agency tier: 'rivalhotel-addis.com'.")

    # -------------------------------------------------------------------------
    # STEP 11: SEO RECOMMENDATIONS FEED
    # -------------------------------------------------------------------------
    log_step("STEP 11: SEO Recommendations Feed Integration")
    rec_res = client.get(f"/api/seo/recommendations/?project_id={project_id}")
    assert rec_res.status_code == status.HTTP_200_OK
    print(f"   [PASS] Recommendations feed accessible. Returned status 200.")

    # -------------------------------------------------------------------------
    # STEP 12: SUBSCRIPTION EXPIRATION & REVERSION TO FREE TIER
    # -------------------------------------------------------------------------
    log_step("STEP 12: Scheduled Subscription Expiration Task")
    user_sub = Subscription.objects.filter(user_id=user_id).first()
    assert user_sub is not None
    # Simulate subscription running past end timestamp
    user_sub.current_period_end = timezone.now() - timedelta(minutes=10)
    user_sub.save(update_fields=['current_period_end'])

    # Run celery expiration task
    result_msg = expire_subscriptions()
    print(f"   [TASK] expire_subscriptions result: '{result_msg}'")

    user_sub.refresh_from_db()
    assert user_sub.status == SubscriptionStatus.EXPIRED, f"Status should be EXPIRED, got {user_sub.status}"
    assert user_sub.plan.code == PlanCode.FREE, f"Plan should be downgraded to FREE, got {user_sub.plan.code}"
    print(f"   [PASS] Expired subscription successfully downgraded back to FREE tier safely.")

    # Cleanup test user
    User.objects.filter(email__iexact=test_email).delete()

    print("\n" + "=" * 70)
    print("      ALL END-TO-END JOURNEY CHECKS PASSED SUCCESSFULLY (100%)")
    print("=" * 70)


if __name__ == '__main__':
    run_e2e_audit()
