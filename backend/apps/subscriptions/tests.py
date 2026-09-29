import hmac
import hashlib
import json
from unittest.mock import patch
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from apps.projects.models import Project
from apps.seo.models import Keyword, SearchEngine, Country, Language, Device
from .models import (
    Plan,
    Subscription,
    ToolUsage,
    PaymentTransaction,
    PlanCode,
    SubscriptionStatus,
    PaymentStatus,
    FeatureCode,
)
from .services import (
    SubscriptionService,
    PlanEntitlementService,
    UsageLimitService,
    PaymentService,
    get_user_subscription_summary,
)
from .tasks import expire_subscriptions
from .exceptions import PlanLimitReachedException, FeatureNotEntitledException, InvalidPlanException
from .permissions import require_feature, CanAccessRankTracking, CanAccessCompetitorSnapshots

User = get_user_model()


class PlanAndSubscriptionBaseTestCase(TestCase):
    """
    Base setup for subscription tests ensuring standard plans are initialized.
    """
    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user_free = User.objects.create_user(
            email='free_user@doxarank.com',
            password='TestPassword123!',
            first_name='Free',
            last_name='User'
        )
        self.user_starter = User.objects.create_user(
            email='starter_user@doxarank.com',
            password='TestPassword123!',
            first_name='Starter',
            last_name='User'
        )
        SubscriptionService.assign_plan(self.user_starter, PlanCode.STARTER)

        self.user_agency = User.objects.create_user(
            email='agency_user@doxarank.com',
            password='TestPassword123!',
            first_name='Agency',
            last_name='User'
        )
        SubscriptionService.assign_plan(self.user_agency, PlanCode.AGENCY)


class PlanModelTests(PlanAndSubscriptionBaseTestCase):
    """
    Tests proving Plan definitions match the Original DoxaRank SRS.
    """
    def test_plans_exist(self):
        self.assertTrue(Plan.objects.filter(code=PlanCode.FREE).exists())
        self.assertTrue(Plan.objects.filter(code=PlanCode.STARTER).exists())
        self.assertTrue(Plan.objects.filter(code=PlanCode.AGENCY).exists())

    def test_free_plan_parameters(self):
        free = Plan.objects.get(code=PlanCode.FREE)
        self.assertEqual(free.monthly_price, Decimal('0.00'))
        self.assertEqual(free.currency, 'ETB')
        self.assertEqual(free.max_projects, 1)
        self.assertEqual(free.max_keywords, 3)
        self.assertEqual(free.basic_tool_daily_limit, 5)
        self.assertIn(FeatureCode.BASIC_SEO_TOOLS, free.features)
        self.assertNotIn(FeatureCode.RANK_TRACKING, free.features)
        self.assertFalse(free.is_tool_unlimited)

    def test_starter_plan_parameters(self):
        starter = Plan.objects.get(code=PlanCode.STARTER)
        self.assertEqual(starter.monthly_price, Decimal('1500.00'))
        self.assertEqual(starter.currency, 'ETB')
        self.assertEqual(starter.max_projects, 3)
        self.assertEqual(starter.max_keywords, 50)
        self.assertEqual(starter.basic_tool_daily_limit, 0)
        self.assertTrue(starter.is_tool_unlimited)
        for f in [FeatureCode.BASIC_SEO_TOOLS, FeatureCode.RANK_TRACKING, FeatureCode.GSC, FeatureCode.GA4, FeatureCode.CLARITY, FeatureCode.GTM, FeatureCode.TECHNICAL_CRAWLER]:
            self.assertIn(f, starter.features)
        self.assertNotIn(FeatureCode.COMPETITOR_SNAPSHOTS, starter.features)
        self.assertNotIn(FeatureCode.WHITE_LABEL_REPORTS, starter.features)

    def test_agency_plan_parameters(self):
        agency = Plan.objects.get(code=PlanCode.AGENCY)
        self.assertEqual(agency.monthly_price, Decimal('6000.00'))
        self.assertEqual(agency.currency, 'ETB')
        self.assertEqual(agency.max_projects, 20)
        self.assertEqual(agency.max_keywords, 500)
        self.assertEqual(agency.basic_tool_daily_limit, 0)
        self.assertTrue(agency.is_tool_unlimited)
        self.assertIn(FeatureCode.COMPETITOR_SNAPSHOTS, agency.features)
        self.assertIn(FeatureCode.WHITE_LABEL_REPORTS, agency.features)


class SubscriptionModelTests(PlanAndSubscriptionBaseTestCase):
    """
    Tests user subscription life-cycle and defaults.
    """
    def test_default_user_subscription_is_free(self):
        sub = SubscriptionService.get_or_create_user_subscription(self.user_free)
        self.assertEqual(sub.plan.code, PlanCode.FREE)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertTrue(sub.is_active_subscription)

    def test_plan_assignment(self):
        sub = SubscriptionService.assign_plan(self.user_free, PlanCode.STARTER)
        self.assertEqual(sub.plan.code, PlanCode.STARTER)
        active_plan = SubscriptionService.get_user_plan(self.user_free)
        self.assertEqual(active_plan.code, PlanCode.STARTER)

    def test_expired_subscription_status(self):
        past_date = timezone.now() - timedelta(days=1)
        sub = SubscriptionService.assign_plan(
            self.user_free,
            PlanCode.STARTER,
            status=SubscriptionStatus.ACTIVE,
            current_period_end=past_date
        )
        self.assertFalse(sub.is_active_subscription)


class ProjectLimitsEnforcementTests(PlanAndSubscriptionBaseTestCase):
    """
    Tests enforcing site/project quotas:
    FREE: 1 site
    STARTER: 3 sites
    AGENCY: 20 sites
    """
    def test_free_tier_allows_one_project_blocks_second(self):
        self.client.force_authenticate(user=self.user_free)

        # 1st project allowed
        res1 = self.client.post('/api/projects/', {
            'name': 'Site One',
            'website_url': 'https://siteone.et'
        }, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # 2nd project blocked
        res2 = self.client.post('/api/projects/', {
            'name': 'Site Two',
            'website_url': 'https://sitetwo.et'
        }, format='json')
        self.assertEqual(res2.status_code, status.HTTP_403_FORBIDDEN)
        data = res2.json()
        self.assertEqual(data.get('code'), 'PLAN_LIMIT_REACHED')
        self.assertEqual(data.get('resource'), 'projects')
        self.assertEqual(data.get('current'), 1)
        self.assertEqual(data.get('limit'), 1)
        self.assertEqual(data.get('plan'), PlanCode.FREE)
        self.assertTrue(data.get('upgrade_required'))

    def test_starter_tier_allows_three_projects_blocks_fourth(self):
        self.client.force_authenticate(user=self.user_starter)

        for i in range(1, 4):
            res = self.client.post('/api/projects/', {
                'name': f'Starter Site {i}',
                'website_url': f'https://startersite{i}.com'
            }, format='json')
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # 4th project blocked
        res_blocked = self.client.post('/api/projects/', {
            'name': 'Starter Site 4',
            'website_url': 'https://startersite4.com'
        }, format='json')
        self.assertEqual(res_blocked.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_blocked.json().get('code'), 'PLAN_LIMIT_REACHED')
        self.assertEqual(res_blocked.json().get('limit'), 3)

    def test_agency_tier_allows_twenty_projects_blocks_twenty_first(self):
        self.client.force_authenticate(user=self.user_agency)

        # Create 20 projects
        for i in range(1, 21):
            Project.objects.create(
                owner=self.user_agency,
                name=f'Agency Client {i}',
                website_url=f'https://client{i}.et'
            )

        # 21st project via API blocked
        res_blocked = self.client.post('/api/projects/', {
            'name': 'Agency Client 21',
            'website_url': 'https://client21.et'
        }, format='json')
        self.assertEqual(res_blocked.status_code, status.HTTP_403_FORBIDDEN)
        data = res_blocked.json()
        self.assertEqual(data.get('code'), 'PLAN_LIMIT_REACHED')
        self.assertEqual(data.get('limit'), 20)
        self.assertEqual(data.get('current'), 20)


class KeywordLimitsEnforcementTests(PlanAndSubscriptionBaseTestCase):
    """
    Tests enforcing keyword tracking quotas across user projects:
    FREE: 3 keywords
    STARTER: 50 keywords
    AGENCY: 500 keywords
    """
    def setUp(self):
        super().setUp()
        self.proj_free = Project.objects.create(
            owner=self.user_free,
            name='Free Test Project',
            website_url='https://free-seo.et'
        )
        self.proj_starter = Project.objects.create(
            owner=self.user_starter,
            name='Starter Test Project',
            website_url='https://starter-seo.et'
        )

    def test_free_tier_allows_three_keywords_blocks_fourth(self):
        self.client.force_authenticate(user=self.user_free)

        for i in range(1, 4):
            res = self.client.post('/api/seo/keywords/', {
                'project': self.proj_free.id,
                'keyword': f'free keyword {i}',
                'search_engine': 'google',
                'country': 'ET',
                'language': 'en',
                'device': 'desktop'
            }, format='json')
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # 4th keyword blocked
        res_blocked = self.client.post('/api/seo/keywords/', {
            'project': self.proj_free.id,
            'keyword': 'free keyword 4',
            'search_engine': 'google',
            'country': 'ET',
            'language': 'en',
            'device': 'desktop'
        }, format='json')
        self.assertEqual(res_blocked.status_code, status.HTTP_403_FORBIDDEN)
        data = res_blocked.json()
        self.assertEqual(data.get('code'), 'PLAN_LIMIT_REACHED')
        self.assertEqual(data.get('resource'), 'keywords')
        self.assertEqual(data.get('current'), 3)
        self.assertEqual(data.get('limit'), 3)
        self.assertEqual(data.get('plan'), PlanCode.FREE)

    def test_keywords_span_multiple_projects_under_same_user_quota(self):
        # Upgrade free user to Starter so they can create multiple projects
        SubscriptionService.assign_plan(self.user_free, PlanCode.STARTER)
        proj_free_2 = Project.objects.create(
            owner=self.user_free,
            name='Second Project',
            website_url='https://free-two.et'
        )
        # Downgrade back to FREE to test cumulative quota across projects
        SubscriptionService.assign_plan(self.user_free, PlanCode.FREE)

        self.client.force_authenticate(user=self.user_free)

        # Add 2 keywords to project 1
        for i in range(2):
            self.client.post('/api/seo/keywords/', {
                'project': self.proj_free.id,
                'keyword': f'project one kw {i}'
            }, format='json')

        # Add 1 keyword to project 2 (reaches total 3)
        res3 = self.client.post('/api/seo/keywords/', {
            'project': proj_free_2.id,
            'keyword': 'project two kw 1'
        }, format='json')
        self.assertEqual(res3.status_code, status.HTTP_201_CREATED)

        # 4th keyword across both projects must be blocked
        res4 = self.client.post('/api/seo/keywords/', {
            'project': proj_free_2.id,
            'keyword': 'project two kw 2'
        }, format='json')
        self.assertEqual(res4.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res4.json().get('code'), 'PLAN_LIMIT_REACHED')

    def test_starter_tier_allows_fifty_keywords_blocks_fifty_first(self):
        self.client.force_authenticate(user=self.user_starter)

        # Bulk create 50 keywords directly in ORM for the starter project
        for i in range(1, 51):
            Keyword.objects.create(
                project=self.proj_starter,
                keyword=f'starter kw {i}',
                search_engine=SearchEngine.GOOGLE,
                country=Country.ET,
                language=Language.EN,
                device=Device.DESKTOP
            )

        # 51st keyword via API blocked
        res_blocked = self.client.post('/api/seo/keywords/', {
            'project': self.proj_starter.id,
            'keyword': 'starter kw 51'
        }, format='json')
        self.assertEqual(res_blocked.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_blocked.json().get('code'), 'PLAN_LIMIT_REACHED')
        self.assertEqual(res_blocked.json().get('limit'), 50)
        self.assertEqual(res_blocked.json().get('current'), 50)


class FeatureEntitlementTests(PlanAndSubscriptionBaseTestCase):
    """
    Tests feature flags and permissions for:
    BASIC_SEO_TOOLS, RANK_TRACKING, GSC, GA4, CLARITY, GTM, TECHNICAL_CRAWLER,
    COMPETITOR_SNAPSHOTS, WHITE_LABEL_REPORTS.
    """
    def test_free_plan_feature_entitlements(self):
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_free, FeatureCode.BASIC_SEO_TOOLS))
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_free, FeatureCode.RANK_TRACKING))
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_free, FeatureCode.TECHNICAL_CRAWLER))
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_free, FeatureCode.COMPETITOR_SNAPSHOTS))
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_free, FeatureCode.WHITE_LABEL_REPORTS))

        with self.assertRaises(FeatureNotEntitledException) as ctx:
            PlanEntitlementService.check_can_use_feature(self.user_free, FeatureCode.RANK_TRACKING)
        self.assertEqual(ctx.exception.detail['code'], 'FEATURE_NOT_ENTITLED')
        self.assertEqual(ctx.exception.detail['feature'], FeatureCode.RANK_TRACKING)

    def test_starter_plan_feature_entitlements(self):
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.BASIC_SEO_TOOLS))
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.RANK_TRACKING))
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.GSC))
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.GA4))
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.CLARITY))
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.GTM))
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.TECHNICAL_CRAWLER))

        # Starter does not include agency features
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.COMPETITOR_SNAPSHOTS))
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.WHITE_LABEL_REPORTS))

    def test_agency_plan_feature_entitlements(self):
        for f in FeatureCode.values:
            self.assertTrue(PlanEntitlementService.can_use_feature(self.user_agency, f))


class DailyToolUsageLimitTests(PlanAndSubscriptionBaseTestCase):
    """
    Tests daily tool quota tracking, concurrency locks, date resets, and paid unmetered access.
    """
    def test_free_user_tool_usage_increments_and_blocks_at_limit(self):
        tool = 'meta_tag_generator'

        # Execute 5 times (allowed)
        for i in range(1, 6):
            allowed, count, limit = UsageLimitService.can_use_tool(self.user_free, tool)
            self.assertTrue(allowed)
            usage = UsageLimitService.check_and_record_tool_usage(self.user_free, tool)
            self.assertEqual(usage.count, i)

        # 6th execution must be blocked
        allowed, count, limit = UsageLimitService.can_use_tool(self.user_free, tool)
        self.assertFalse(allowed)
        self.assertEqual(count, 5)
        self.assertEqual(limit, 5)

        with self.assertRaises(PlanLimitReachedException) as ctx:
            UsageLimitService.check_and_record_tool_usage(self.user_free, tool)
        self.assertEqual(ctx.exception.detail['code'], 'PLAN_LIMIT_REACHED')
        self.assertEqual(ctx.exception.detail['current'], 5)
        self.assertEqual(ctx.exception.detail['limit'], 5)

    def test_new_day_resets_tool_usage(self):
        tool = 'robots_tester'
        yesterday = timezone.localdate() - timedelta(days=1)
        today = timezone.localdate()

        # Simulate 5 usages yesterday
        ToolUsage.objects.create(
            user=self.user_free,
            tool_code=tool,
            usage_date=yesterday,
            count=5
        )

        # Today should be fresh
        today_count = UsageLimitService.get_today_tool_usage(self.user_free, tool, target_date=today)
        self.assertEqual(today_count, 0)
        allowed, count, limit = UsageLimitService.can_use_tool(self.user_free, tool, target_date=today)
        self.assertTrue(allowed)

        # Today's execution records under today's date
        usage = UsageLimitService.check_and_record_tool_usage(self.user_free, tool, target_date=today)
        self.assertEqual(usage.count, 1)
        self.assertEqual(usage.usage_date, today)

    def test_starter_and_agency_have_unlimited_tool_usage(self):
        tool = 'schema_generator'
        # Record 20 times for starter user
        for _ in range(20):
            usage = UsageLimitService.check_and_record_tool_usage(self.user_starter, tool)
        self.assertEqual(usage.count, 20)

        # Still allowed
        allowed, current, limit = UsageLimitService.can_use_tool(self.user_starter, tool)
        self.assertTrue(allowed)
        self.assertEqual(limit, 0)  # 0 indicates unlimited


class TenantSecurityAndIsolationTests(PlanAndSubscriptionBaseTestCase):
    """
    Tests that tenant quotas are isolated and cannot be bypassed.
    """
    def test_user_a_cannot_consume_user_b_quota(self):
        proj_free = Project.objects.create(
            owner=self.user_free,
            name='User Free Project',
            website_url='https://free.et'
        )
        proj_starter = Project.objects.create(
            owner=self.user_starter,
            name='User Starter Project',
            website_url='https://starter.et'
        )

        # User Free fills all 3 keywords
        for i in range(3):
            Keyword.objects.create(
                project=proj_free,
                keyword=f'kw {i}',
                search_engine=SearchEngine.GOOGLE,
                country=Country.ET,
                language=Language.EN,
                device=Device.DESKTOP
            )

        # User Starter can still create keywords normally
        self.client.force_authenticate(user=self.user_starter)
        res = self.client.post('/api/seo/keywords/', {
            'project': proj_starter.id,
            'keyword': 'starter independent kw'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_user_cannot_bypass_limits_by_targeting_another_users_project(self):
        proj_starter = Project.objects.create(
            owner=self.user_starter,
            name='Target Project',
            website_url='https://target.et'
        )

        self.client.force_authenticate(user=self.user_free)
        # Attempting to post to user_starter's project
        res = self.client.post('/api/seo/keywords/', {
            'project': proj_starter.id,
            'keyword': 'exploit attempt kw'
        }, format='json')
        # Cross-tenant permission check blocks before quota or handles cleanly
        self.assertIn(res.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND])


class SubscriptionAPIEndpointsTests(PlanAndSubscriptionBaseTestCase):
    """
    Tests public and authenticated REST endpoints:
    /api/subscriptions/plans/
    /api/subscriptions/me/
    /api/subscriptions/tools/check/
    /api/subscriptions/assign/
    """
    def test_get_public_plans(self):
        res = self.client.get('/api/subscriptions/plans/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        codes = [p['code'] for p in data]
        self.assertIn(PlanCode.FREE, codes)
        self.assertIn(PlanCode.STARTER, codes)
        self.assertIn(PlanCode.AGENCY, codes)

    def test_get_user_subscription_summary(self):
        self.client.force_authenticate(user=self.user_free)
        Project.objects.create(
            owner=self.user_free,
            name='Summary Proj',
            website_url='https://sum.et'
        )

        res = self.client.get('/api/subscriptions/me/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['plan']['code'], PlanCode.FREE)
        self.assertEqual(data['usage']['projects']['current'], 1)
        self.assertEqual(data['usage']['projects']['limit'], 1)
        self.assertEqual(data['usage']['projects']['remaining'], 0)
        self.assertEqual(data['usage']['keywords']['limit'], 3)

    def test_tool_usage_check_endpoint(self):
        self.client.force_authenticate(user=self.user_free)
        res = self.client.post('/api/subscriptions/tools/check/', {
            'tool_code': 'meta_generator',
            'record': True
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertTrue(data['allowed'])
        self.assertEqual(data['current_usage'], 1)
        self.assertEqual(data['daily_limit'], 5)

    def test_plan_assignment_endpoint(self):
        self.client.force_authenticate(user=self.user_free)
        res = self.client.post('/api/subscriptions/assign/', {
            'plan_code': PlanCode.AGENCY
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['plan']['code'], PlanCode.AGENCY)
        self.assertEqual(data['usage']['projects']['limit'], 20)
        self.assertEqual(data['usage']['keywords']['limit'], 500)


class PaymentBillingIntegrationTests(PlanAndSubscriptionBaseTestCase):
    """
    Focused test suite covering all 22 required payment, billing, and subscription scenarios
    for the Doxa Payments integration.
    """

    def setUp(self):
        super().setUp()
        self.user_payer = User.objects.create_user(
            email='payer@doxarank.com',
            password='TestPassword123!',
            first_name='Payer',
            last_name='User'
        )
        self.user_other = User.objects.create_user(
            email='other@doxarank.com',
            password='TestPassword123!',
            first_name='Other',
            last_name='User'
        )

    # 1. Free subscription creation
    def test_01_free_subscription_creation(self):
        user = User.objects.create_user(
            email='new_free@doxarank.com',
            password='Password123!',
            first_name='New',
            last_name='Free'
        )
        sub = SubscriptionService.get_or_create_user_subscription(user)
        self.assertEqual(sub.plan.code, PlanCode.FREE)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertTrue(sub.is_active_subscription)
        self.assertIsNone(sub.current_period_end)
        # Limits check
        self.assertEqual(sub.plan.max_projects, 1)
        self.assertEqual(sub.plan.max_keywords, 3)
        self.assertEqual(sub.plan.basic_tool_daily_limit, 5)

    # 2. Starter checkout creation
    def test_02_starter_checkout_creation(self):
        self.client.force_authenticate(user=self.user_payer)
        res = self.client.post('/api/subscriptions/checkout/', {
            'plan_code': 'STARTER',
            'return_url': 'http://localhost:5173/billing/complete',
            'cancel_url': 'http://localhost:5173/billing/cancel',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data['status'], PaymentStatus.PENDING)
        self.assertEqual(Decimal(data['amount']), Decimal('1500.00'))
        self.assertEqual(data['currency'], 'ETB')
        self.assertEqual(data['plan_code'], PlanCode.STARTER)
        self.assertTrue(data['checkout_reference'].startswith('doxa_chk_'))
        self.assertIn('checkout_url', data)

    # 3. Agency checkout creation
    def test_03_agency_checkout_creation(self):
        self.client.force_authenticate(user=self.user_payer)
        res = self.client.post('/api/subscriptions/checkout/', {
            'plan_code': 'AGENCY'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data['status'], PaymentStatus.PENDING)
        self.assertEqual(Decimal(data['amount']), Decimal('6000.00'))
        self.assertEqual(data['currency'], 'ETB')
        self.assertEqual(data['plan_code'], PlanCode.AGENCY)

    # 4. Invalid plan rejection
    def test_04_invalid_plan_rejection(self):
        self.client.force_authenticate(user=self.user_payer)
        # Non-existent plan
        res_invalid = self.client.post('/api/subscriptions/checkout/', {
            'plan_code': 'ENTERPRISE_DOES_NOT_EXIST'
        }, format='json')
        self.assertEqual(res_invalid.status_code, status.HTTP_400_BAD_REQUEST)

        # Free plan checkout rejection
        res_free = self.client.post('/api/subscriptions/checkout/', {
            'plan_code': 'FREE'
        }, format='json')
        self.assertEqual(res_free.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Free plan does not require payment', str(res_free.json()))

    # 5. Server-side price enforcement
    def test_05_server_side_price_enforcement(self):
        self.client.force_authenticate(user=self.user_payer)
        # Attempt to pass spoofed client-side amount and currency
        res = self.client.post('/api/subscriptions/checkout/', {
            'plan_code': 'STARTER',
            'amount': '1.00',
            'currency': 'USD'
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        # Price must strictly match database plan price (1500.00 ETB), not client input
        self.assertEqual(Decimal(data['amount']), Decimal('1500.00'))
        self.assertEqual(data['currency'], 'ETB')

    # 6. Pending transaction creation
    def test_06_pending_transaction_creation(self):
        tx = PaymentService.create_checkout_session(
            user=self.user_payer,
            plan_code=PlanCode.STARTER
        )
        self.assertEqual(tx.status, PaymentStatus.PENDING)
        self.assertEqual(tx.amount, Decimal('1500.00'))
        self.assertEqual(tx.currency, 'ETB')
        self.assertEqual(tx.user, self.user_payer)
        self.assertTrue(PaymentTransaction.objects.filter(checkout_reference=tx.checkout_reference).exists())

    # 7. Successful payment verification
    def test_07_successful_payment_verification(self):
        self.client.force_authenticate(user=self.user_payer)
        # Create checkout
        tx = PaymentService.create_checkout_session(
            user=self.user_payer,
            plan_code=PlanCode.STARTER
        )
        # Verify payment
        res = self.client.post(f'/api/subscriptions/payments/{tx.id}/verify/', {
            'payload': {
                'status': 'SUCCESS',
                'amount': '1500.00',
                'currency': 'ETB',
                'provider_transaction_id': 'doxa_live_12345'
            }
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['status'], PaymentStatus.SUCCESS)
        self.assertEqual(data['provider_transaction_id'], 'doxa_live_12345')
        self.assertIsNotNone(data['paid_at'])

        # Subscription active and upgraded to Starter
        self.user_payer.refresh_from_db()
        sub = Subscription.objects.get(user=self.user_payer)
        self.assertEqual(sub.plan.code, PlanCode.STARTER)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertIsNotNone(sub.current_period_end)
        self.assertTrue(sub.current_period_end > timezone.now())

    # 8. Failed payment verification
    def test_08_failed_payment_verification(self):
        self.client.force_authenticate(user=self.user_payer)
        tx = PaymentService.create_checkout_session(
            user=self.user_payer,
            plan_code=PlanCode.STARTER
        )
        res = self.client.post(f'/api/subscriptions/payments/{tx.id}/verify/', {
            'payload': {
                'status': 'FAILED',
                'error_message': 'Insufficient funds on Telebirr wallet'
            }
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['status'], PaymentStatus.FAILED)
        self.assertIn('Insufficient funds', data['error_message'])

        # Subscription must NOT be upgraded
        sub = SubscriptionService.get_or_create_user_subscription(self.user_payer)
        self.assertEqual(sub.plan.code, PlanCode.FREE)

    # 9. Invalid payment reference
    def test_09_invalid_payment_reference(self):
        self.client.force_authenticate(user=self.user_payer)
        res_get = self.client.get('/api/subscriptions/payments/non_existent_ref_99999/')
        self.assertEqual(res_get.status_code, status.HTTP_404_NOT_FOUND)

        res_post = self.client.post('/api/subscriptions/payments/non_existent_ref_99999/verify/')
        self.assertEqual(res_post.status_code, status.HTTP_404_NOT_FOUND)

    # 10. Invalid amount rejection
    def test_10_invalid_amount_rejection(self):
        tx = PaymentService.create_checkout_session(
            user=self.user_payer,
            plan_code=PlanCode.STARTER
        )
        # Attempt verification with underpaid amount (e.g. 500 ETB instead of 1500 ETB)
        processed_tx = PaymentService.verify_and_process_payment(
            transaction_id_or_ref=tx.id,
            payload={
                'status': 'SUCCESS',
                'amount': '500.00',
                'currency': 'ETB'
            }
        )
        self.assertEqual(processed_tx.status, PaymentStatus.FAILED)
        self.assertIn('Amount mismatch', processed_tx.error_message)
        # User not upgraded
        sub = SubscriptionService.get_or_create_user_subscription(self.user_payer)
        self.assertEqual(sub.plan.code, PlanCode.FREE)

    # 11. Invalid currency rejection
    def test_11_invalid_currency_rejection(self):
        tx = PaymentService.create_checkout_session(
            user=self.user_payer,
            plan_code=PlanCode.STARTER
        )
        processed_tx = PaymentService.verify_and_process_payment(
            transaction_id_or_ref=tx.id,
            payload={
                'status': 'SUCCESS',
                'amount': '1500.00',
                'currency': 'EUR'
            }
        )
        self.assertEqual(processed_tx.status, PaymentStatus.FAILED)
        self.assertIn('Currency mismatch', processed_tx.error_message)
        sub = SubscriptionService.get_or_create_user_subscription(self.user_payer)
        self.assertEqual(sub.plan.code, PlanCode.FREE)

    # 12. Duplicate webhook idempotency
    def test_12_duplicate_webhook_idempotency(self):
        tx = PaymentService.create_checkout_session(
            user=self.user_payer,
            plan_code=PlanCode.STARTER
        )
        webhook_payload = {
            'checkout_reference': tx.checkout_reference,
            'status': 'SUCCESS',
            'amount': '1500.00',
            'currency': 'ETB',
            'transaction_id': 'doxa_webhook_tx_101'
        }
        raw_body = json.dumps(webhook_payload).encode('utf-8')

        # 1st webhook call
        tx1, state1 = PaymentService.handle_webhook(
            provider_name='doxa',
            payload=webhook_payload,
            raw_body=raw_body,
            headers={}
        )
        self.assertEqual(tx1.status, PaymentStatus.SUCCESS)
        self.assertEqual(state1, "processed")
        first_period_end = Subscription.objects.get(user=self.user_payer).current_period_end

        # 2nd webhook call (duplicate)
        tx2, state2 = PaymentService.handle_webhook(
            provider_name='doxa',
            payload=webhook_payload,
            raw_body=raw_body,
            headers={}
        )
        self.assertEqual(tx2.status, PaymentStatus.SUCCESS)
        self.assertEqual(state2, "already_processed")
        self.assertEqual(Subscription.objects.get(user=self.user_payer).current_period_end, first_period_end)

    # 13. Repeated callback idempotency
    def test_13_repeated_callback_idempotency(self):
        self.client.force_authenticate(user=self.user_payer)
        tx = PaymentService.create_checkout_session(
            user=self.user_payer,
            plan_code=PlanCode.STARTER
        )
        verify_data = {
            'payload': {
                'status': 'SUCCESS',
                'amount': '1500.00',
                'currency': 'ETB',
            }
        }
        res1 = self.client.post(f'/api/subscriptions/payments/{tx.id}/verify/', verify_data, format='json')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        initial_period_end = Subscription.objects.get(user=self.user_payer).current_period_end

        # Repeated verification call
        res2 = self.client.post(f'/api/subscriptions/payments/{tx.id}/verify/', verify_data, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        # Period end must remain identical (no double extension)
        self.assertEqual(Subscription.objects.get(user=self.user_payer).current_period_end, initial_period_end)

    # 14. Already completed transaction cannot be altered
    def test_14_already_completed_transaction_cannot_be_altered(self):
        tx = PaymentService.create_checkout_session(
            user=self.user_payer,
            plan_code=PlanCode.STARTER
        )
        PaymentService.verify_and_process_payment(tx.id, {'status': 'SUCCESS', 'amount': '1500.00'})
        tx.refresh_from_db()
        self.assertEqual(tx.status, PaymentStatus.SUCCESS)
        original_paid_at = tx.paid_at

        # Attempt to inject FAILED on already SUCCESS transaction
        updated_tx = PaymentService.verify_and_process_payment(tx.id, {'status': 'FAILED'})
        self.assertEqual(updated_tx.status, PaymentStatus.SUCCESS)
        self.assertEqual(updated_tx.paid_at, original_paid_at)

    # 15. Subscription activation unlocks features
    def test_15_subscription_activation_unlocks_features(self):
        # Initial Free state
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_payer, FeatureCode.RANK_TRACKING))
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_payer, FeatureCode.TECHNICAL_CRAWLER))
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_payer, FeatureCode.COMPETITOR_SNAPSHOTS))
        current, limit = PlanEntitlementService.get_project_usage(self.user_payer)
        self.assertEqual(limit, 1)

        # Pay for Agency tier
        tx = PaymentService.create_checkout_session(user=self.user_payer, plan_code=PlanCode.AGENCY)
        PaymentService.verify_and_process_payment(tx.id, {'status': 'SUCCESS', 'amount': '6000.00'})

        # Verify all Agency features unlocked
        self.user_payer.refresh_from_db()
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_payer, FeatureCode.RANK_TRACKING))
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_payer, FeatureCode.TECHNICAL_CRAWLER))
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_payer, FeatureCode.COMPETITOR_SNAPSHOTS))
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_payer, FeatureCode.WHITE_LABEL_REPORTS))
        _, agency_limit = PlanEntitlementService.get_project_usage(self.user_payer)
        self.assertEqual(agency_limit, 20)

    # 16. Subscription expiration via Celery task
    def test_16_subscription_expiration_via_celery_task(self):
        # Assign Starter plan expired 2 days ago
        sub = SubscriptionService.assign_plan(
            self.user_payer,
            PlanCode.STARTER,
            status=SubscriptionStatus.ACTIVE,
            current_period_end=timezone.now() - timedelta(days=2)
        )
        # Immediate entitlement fallback to Free
        active_plan = SubscriptionService.get_user_plan(self.user_payer)
        self.assertEqual(active_plan.code, PlanCode.FREE)

        # Execute scheduled Celery sweep task
        result_msg = expire_subscriptions()
        self.assertIn("1 expired subscription(s)", result_msg)

        sub.refresh_from_db()
        self.assertEqual(sub.plan.code, PlanCode.FREE)
        self.assertEqual(sub.status, SubscriptionStatus.EXPIRED)
        self.assertIsNone(sub.current_period_end)

        # Unrelated lifetime Free user was not modified
        free_sub = SubscriptionService.get_or_create_user_subscription(self.user_other)
        self.assertEqual(free_sub.status, SubscriptionStatus.ACTIVE)

    # 17. Subscription renewal extends period safely
    def test_17_subscription_renewal(self):
        # User has an active Starter plan expiring 15 days in the future
        future_end = timezone.now() + timedelta(days=15)
        SubscriptionService.assign_plan(
            self.user_payer,
            PlanCode.STARTER,
            status=SubscriptionStatus.ACTIVE,
            current_period_end=future_end
        )
        # Process renewal checkout
        tx = PaymentService.create_checkout_session(user=self.user_payer, plan_code=PlanCode.STARTER)
        PaymentService.verify_and_process_payment(tx.id, {'status': 'SUCCESS', 'amount': '1500.00'})

        sub = Subscription.objects.get(user=self.user_payer)
        # Renewal adds 30 days onto the 15 remaining days (~45 days from now)
        expected_min = future_end + timedelta(days=29)
        expected_max = future_end + timedelta(days=31)
        self.assertTrue(expected_min <= sub.current_period_end <= expected_max)


    # 18. Tenant isolation
    def test_18_tenant_isolation(self):
        tx_payer = PaymentService.create_checkout_session(user=self.user_payer, plan_code=PlanCode.STARTER)

        # Authenticate as user_other (unauthorized tenant)
        self.client.force_authenticate(user=self.user_other)

        # Cannot read user_payer's transaction
        res_get = self.client.get(f'/api/subscriptions/payments/{tx_payer.id}/')
        self.assertEqual(res_get.status_code, status.HTTP_404_NOT_FOUND)

        # Cannot verify user_payer's transaction
        res_post = self.client.post(f'/api/subscriptions/payments/{tx_payer.id}/verify/')
        self.assertEqual(res_post.status_code, status.HTTP_404_NOT_FOUND)

        # Payments list only includes owned transactions
        res_list = self.client.get('/api/subscriptions/payments/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.json()), 0)

    # 19. Unauthorized payment access
    def test_19_unauthorized_payment_access(self):
        self.client.logout()
        res_checkout = self.client.post('/api/subscriptions/checkout/', {'plan_code': 'STARTER'})
        self.assertEqual(res_checkout.status_code, status.HTTP_401_UNAUTHORIZED)

        res_payments = self.client.get('/api/subscriptions/payments/')
        self.assertEqual(res_payments.status_code, status.HTTP_401_UNAUTHORIZED)

    # 20. Webhook security and signature verification
    @override_settings(DOXA_PAYMENTS_WEBHOOK_SECRET='test_doxa_secret_key_123')
    def test_20_webhook_security_signature_verification(self):
        tx = PaymentService.create_checkout_session(user=self.user_payer, plan_code=PlanCode.STARTER)
        payload = {
            'checkout_reference': tx.checkout_reference,
            'status': 'SUCCESS',
            'amount': '1500.00',
            'currency': 'ETB',
            'transaction_id': 'doxa_sig_tx_99'
        }
        body_bytes = json.dumps(payload).encode('utf-8')

        # 1. Invalid signature rejected
        bad_sig = 'invalid_hex_signature'
        res_bad = self.client.post(
            '/api/subscriptions/webhooks/doxa/',
            data=body_bytes,
            content_type='application/json',
            HTTP_X_DOXA_SIGNATURE=bad_sig
        )
        self.assertEqual(res_bad.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Missing signature rejected when secret is configured
        res_missing = self.client.post(
            '/api/subscriptions/webhooks/doxa/',
            data=body_bytes,
            content_type='application/json'
        )
        self.assertEqual(res_missing.status_code, status.HTTP_401_UNAUTHORIZED)

        # 3. Valid HMAC-SHA256 signature accepted
        valid_sig = hmac.new(
            b'test_doxa_secret_key_123',
            body_bytes,
            hashlib.sha256
        ).hexdigest()

        res_good = self.client.post(
            '/api/subscriptions/webhooks/doxa/',
            data=body_bytes,
            content_type='application/json',
            HTTP_X_DOXA_SIGNATURE=valid_sig
        )
        self.assertEqual(res_good.status_code, status.HTTP_200_OK)
        tx.refresh_from_db()
        self.assertEqual(tx.status, PaymentStatus.SUCCESS)

    # 21. Payment secrets not exposed in API responses
    def test_21_payment_secrets_not_exposed(self):
        self.client.force_authenticate(user=self.user_payer)
        res = self.client.post('/api/subscriptions/checkout/', {'plan_code': 'STARTER'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        raw_text = res.content.decode('utf-8')

        # None of the secret settings names or secret tokens should appear
        self.assertNotIn('DOXA_PAYMENTS_API_KEY', raw_text)
        self.assertNotIn('DOXA_PAYMENTS_WEBHOOK_SECRET', raw_text)
        self.assertNotIn('secret', raw_text.lower())

    # 22. Existing subscription entitlement tests still pass
    def test_22_existing_subscription_entitlements_still_pass(self):
        # Free user quota: 1 project, 3 keywords, 5 tools
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_free, FeatureCode.BASIC_SEO_TOOLS))
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_free, FeatureCode.RANK_TRACKING))

        # Starter user: Rank tracking, GSC, GA4, Clarity, GTM, Crawler
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.RANK_TRACKING))
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.TECHNICAL_CRAWLER))
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.COMPETITOR_SNAPSHOTS))

        # Agency user: Competitor snapshots, White label reports
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_agency, FeatureCode.COMPETITOR_SNAPSHOTS))
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_agency, FeatureCode.WHITE_LABEL_REPORTS))

