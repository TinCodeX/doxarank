from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
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
    PlanCode,
    SubscriptionStatus,
    FeatureCode,
)
from .services import (
    SubscriptionService,
    PlanEntitlementService,
    UsageLimitService,
    get_user_subscription_summary,
)
from .exceptions import PlanLimitReachedException, FeatureNotEntitledException
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
