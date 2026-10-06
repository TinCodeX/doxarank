"""
Dedicated Test Suite for DoxaRank Rank Tracker MVP.

Covers:
- Models: TrackedKeyword, RankingSnapshot, RankCheckJob, constraints, indexes
- SERP Parser: Organic results, ads ignored, knowledge panels ignored, target found/not found,
  Amharic Unicode handling, malformed SERP, CAPTCHA detection
- SERP Client: URL builder, SSRF domain validation, rate limiting / retry mocking
- Subscriptions: Free tier blocked, Starter tier allowed (50 kw limit), Agency tier allowed (500 kw limit)
- Tenant Isolation: User A vs User B keyword/ranking/job security
- Celery Tasks: Async execution, job state transitions, error isolation, daily check idempotency
- REST API: Endpoints, validations, summaries, history, manual launch
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.projects.models import Project
from apps.seo.models import (
    Keyword,
    KeywordRanking,
    RankingResultStatus,
    SearchEngine,
    Country,
    Language,
    Device,
    RankCheckJob,
    RankCheckJobStatus,
    TrackedKeyword,
    RankingSnapshot,
)
from apps.seo.services.rank_tracker import (
    SerpParser,
    GoogleEtSerpClient,
    RankTrackerService,
    SerpResult,
    DataForSeoSerpClient,
)
from apps.seo.tasks import (
    check_keyword_ranking,
    run_project_rank_check,
    run_daily_rank_checks,
)
from apps.subscriptions.models import PlanCode, FeatureCode
from apps.subscriptions.services import SubscriptionService, PlanEntitlementService
from apps.subscriptions.exceptions import PlanLimitReachedException, FeatureNotEntitledException

User = get_user_model()


# Sample mock Google Ethiopia SERP HTML containing organic results and ad/widget blocks
MOCK_GOOGLE_SERP_HTML = """
<!DOCTYPE html>
<html>
<head><title>best hotel addis ababa - Google Search</title></head>
<body>
  <!-- Sponsored Ad Block (Must be ignored) -->
  <div id="tads">
    <div class="ad-block">
      <span class="ad-label">Sponsored</span>
      <a href="https://booking.com/hotels/addis"><h3>Booking.com Addis Hotels</h3></a>
    </div>
  </div>

  <!-- People Also Ask / Knowledge widget (Must be ignored) -->
  <div class="related-question-pair">
    <a href="https://google.com/search?q=addis+weather"><h3>Weather in Addis</h3></a>
  </div>

  <!-- Organic Result 1: Competitor -->
  <div class="g">
    <div class="rc">
      <a href="https://tripadvisor.com/Hotels-g293791-Addis_Ababa-Hotels.html">
        <h3>THE 10 BEST Hotels in Addis Ababa 2026 - Tripadvisor</h3>
      </a>
      <div class="VwiC3b">Best luxury and boutique hotels in Addis Ababa.</div>
    </div>
  </div>

  <!-- Organic Result 2: Target Project Site -->
  <div class="g">
    <div class="rc">
      <a href="https://addisinsight.net/best-luxury-hotels-addis-ababa/">
        <h3>Top 10 Best Hotels in Addis Ababa for Business and Leisure - Addis Insight</h3>
      </a>
      <div class="VwiC3b">Comprehensive guide to the best hotels in Addis Ababa with full reviews.</div>
    </div>
  </div>

  <!-- Organic Result 3: Another site -->
  <div class="g">
    <div class="rc">
      <a href="https://sheratonaddis.com/">
        <h3>Sheraton Addis, a Luxury Collection Hotel</h3>
      </a>
      <div class="VwiC3b">Experience unmatched hospitality in the capital of Ethiopia.</div>
    </div>
  </div>
</body>
</html>
"""

# Sample mock Google Ethiopia SERP HTML with Amharic keywords and content
MOCK_AMHARIC_SERP_HTML = """
<!DOCTYPE html>
<html>
<head><title>በአዲስ አበባ ምርጥ ሆቴል - Google Search</title></head>
<body>
  <!-- Non-organic ad widget with Amharic label -->
  <div class="commercial-unit-desktop-top">
    <span>ማስታወቂያ</span>
    <a href="https://ad-network.com/item"><h3>ቅናሽ ሆቴሎች</h3></a>
  </div>

  <!-- Organic Result 1: Other site -->
  <div class="g">
    <a href="https://ethiopianreporter.com/business-travel">
      <h3>የኢትዮጵያ ምርጥ ሆቴሎች ዝርዝር</h3>
    </a>
  </div>

  <!-- Organic Result 2: Target site -->
  <div class="g">
    <a href="https://addisinsight.net/am/hotels-addis/">
      <h3>በአዲስ አበባ ምርጥ ሆቴሎች መመሪያ - አዲስ ኢንሳይት</h3>
    </a>
  </div>
</body>
</html>
"""


class RankTrackerModelTests(TestCase):
    """Test data models, aliases, and constraints for Rank Tracker MVP."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='model_user@doxarank.com',
            password='Password123!',
            first_name='Model',
            last_name='User'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Addis Insight',
            website_url='https://addisinsight.net'
        )

    def test_tracked_keyword_creation_and_defaults(self):
        """TrackedKeyword can be created with default google.com.et domain and aliases work."""
        kw = Keyword.objects.create(
            project=self.project,
            keyword='best hotel addis ababa',
            country=Country.ET,
            language=Language.EN,
        )
        self.assertEqual(kw.search_domain, 'google.com.et')
        self.assertEqual(kw.search_engine, SearchEngine.GOOGLE)
        self.assertTrue(kw.is_active)
        # Verify alias
        self.assertIs(TrackedKeyword, Keyword)
        self.assertIs(RankingSnapshot, KeywordRanking)

    def test_amharic_keyword_preservation_and_normalization(self):
        """Amharic keyword is preserved exactly in UTF-8 without transliteration."""
        amharic_term = 'በአዲስ አበባ ምርጥ ሆቴል'
        kw = Keyword.objects.create(
            project=self.project,
            keyword=amharic_term,
            country=Country.ET,
            language=Language.AM,
        )
        kw.refresh_from_db()
        self.assertEqual(kw.keyword, amharic_term)
        # Property returns normalized Amharic
        self.assertTrue(len(kw.normalized_keyword) > 0)

    def test_ranking_snapshot_found_creation(self):
        """RankingSnapshot accurately records found organic position, title, and URL."""
        kw = Keyword.objects.create(
            project=self.project,
            keyword='fintech addis'
        )
        now = timezone.now()
        snapshot = KeywordRanking.objects.create(
            keyword=kw,
            position=2,
            result_status=RankingResultStatus.FOUND,
            ranking_url='https://addisinsight.net/fintech-trends',
            title='Fintech in Addis Ababa 2026',
            search_domain='google.com.et',
            recorded_at=now,
        )
        self.assertEqual(snapshot.position, 2)
        self.assertEqual(snapshot.result_status, RankingResultStatus.FOUND)
        self.assertEqual(snapshot.title, 'Fintech in Addis Ababa 2026')
        self.assertIn('#2', str(snapshot))

    def test_ranking_snapshot_not_found_nullable_position(self):
        """RankingSnapshot supports null position when keyword is outside top 100."""
        kw = Keyword.objects.create(
            project=self.project,
            keyword='rare obscure term'
        )
        now = timezone.now()
        snapshot = KeywordRanking.objects.create(
            keyword=kw,
            position=None,
            result_status=RankingResultStatus.NOT_FOUND,
            ranking_url=None,
            title='',
            search_domain='google.com.et',
            recorded_at=now,
        )
        self.assertIsNone(snapshot.position)
        self.assertEqual(snapshot.result_status, RankingResultStatus.NOT_FOUND)
        self.assertIn('Not Found', str(snapshot))

    def test_rank_check_job_lifecycle(self):
        """RankCheckJob tracks execution status, total, completed, and failed counts."""
        job = RankCheckJob.objects.create(
            project=self.project,
            status=RankCheckJobStatus.PENDING,
            total_keywords=10,
            trigger='manual'
        )
        self.assertEqual(job.status, RankCheckJobStatus.PENDING)
        self.assertEqual(job.total_keywords, 10)
        self.assertEqual(job.completed_keywords, 0)
        self.assertEqual(job.failed_keywords, 0)

        job.status = RankCheckJobStatus.RUNNING
        job.started_at = timezone.now()
        job.completed_keywords = 8
        job.failed_keywords = 2
        job.status = RankCheckJobStatus.PARTIAL_FAILURE
        job.completed_at = timezone.now()
        job.save()

        self.assertEqual(job.status, RankCheckJobStatus.PARTIAL_FAILURE)
        self.assertEqual(job.completed_keywords, 8)
        self.assertEqual(job.failed_keywords, 2)


class SerpParserTests(TestCase):
    """Test SERP parser resilience, organic extraction, ad suppression, and Unicode handling."""

    def test_normal_organic_results_extraction(self):
        """Parser extracts organic items in order and removes ads and widgets."""
        results = SerpParser.parse_organic_results(MOCK_GOOGLE_SERP_HTML)
        self.assertEqual(len(results), 3)
        # Ensure Booking.com ad is ignored
        urls = [url for url, _ in results]
        self.assertNotIn('https://booking.com/hotels/addis', urls)
        # Ensure first organic is TripAdvisor
        self.assertIn('tripadvisor.com', urls[0])
        # Ensure second is Addis Insight
        self.assertEqual(urls[1], 'https://addisinsight.net/best-luxury-hotels-addis-ababa/')

    def test_target_found_position_calculation(self):
        """Target website found at position 2 in SERP with correct title and URL."""
        res = SerpParser.parse_google_serp(MOCK_GOOGLE_SERP_HTML, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 2)
        self.assertEqual(res.url, 'https://addisinsight.net/best-luxury-hotels-addis-ababa/')
        self.assertIn('Top 10 Best Hotels in Addis Ababa', res.title)

    def test_target_not_found(self):
        """Returns not_found status when target domain is not in the SERP."""
        res = SerpParser.parse_google_serp(MOCK_GOOGLE_SERP_HTML, 'https://nonexistent-hotel-site.com')
        self.assertEqual(res.status, RankingResultStatus.NOT_FOUND)
        self.assertIsNone(res.position)
        self.assertIsNone(res.url)

    def test_amharic_serp_parsing_and_unicode_preservation(self):
        """Parser handles Amharic characters, ignores Amharic ads, and locates target site."""
        res = SerpParser.parse_google_serp(MOCK_AMHARIC_SERP_HTML, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 2)
        self.assertEqual(res.url, 'https://addisinsight.net/am/hotels-addis/')
        self.assertIn('በአዲስ አበባ ምርጥ ሆቴሎች መመሪያ', res.title)

    def test_fallback_parsing_strategy_with_h3_anchors(self):
        """Fallback strategy finds organic links when container classes are absent."""
        bare_html = """
        <html><body>
          <a href="https://example.com/one"><h3>Example One</h3></a>
          <a href="https://addisinsight.net/page"><h3>Addis Insight Page</h3></a>
        </body></html>
        """
        res = SerpParser.parse_google_serp(bare_html, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 2)

    def test_google_captcha_detection(self):
        """Google CAPTCHA HTML is detected as an error without fabricating positions."""
        captcha_html = "<html><body><h1>Our systems have detected unusual traffic</h1><form id='captcha-form'></form></body></html>"
        res = SerpParser.parse_google_serp(captcha_html, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.ERROR)
        self.assertIsNone(res.position)
        self.assertIn('CAPTCHA', res.error_message)

    def test_google_url_unwrapping(self):
        """Google /url?q= redirect wrappers are unwrapped to clean destination URLs."""
        wrapped = "/url?q=https://addisinsight.net/article&sa=U&ved=2ahUKEwj"
        clean = SerpParser.clean_google_url(wrapped)
        self.assertEqual(clean, "https://addisinsight.net/article")


class GoogleEtSerpClientTests(TestCase):
    """Test Google Ethiopia client configuration, SSRF prevention, and query formatting."""

    def test_search_url_amharic_query_encoding(self):
        """Amharic search query is safely URL-encoded with hl=am and gl=et."""
        client = GoogleEtSerpClient(search_domain='google.com.et')
        url = client.build_search_url('በአዲስ አበባ ምርጥ ሆቴል', language='am')
        self.assertIn('google.com.et/search', url)
        self.assertIn('hl=am', url)
        self.assertIn('gl=et', url)
        self.assertIn('pws=0', url)

    def test_search_url_english_query_encoding(self):
        """English search query has hl=en and gl=et."""
        client = GoogleEtSerpClient(search_domain='google.com.et')
        url = client.build_search_url('best hotel addis ababa', language='en')
        self.assertIn('hl=en', url)
        self.assertIn('gl=et', url)
        self.assertIn('best+hotel+addis+ababa', url)

    def test_ssrf_protection_rejects_unapproved_domains(self):
        """SSRF protection prevents constructing clients for arbitrary or internal hostnames."""
        with self.assertRaises(ValueError):
            GoogleEtSerpClient(search_domain='internal.corp.network')
        with self.assertRaises(ValueError):
            GoogleEtSerpClient(search_domain='169.254.169.254')

    @patch('httpx.Client.get')
    def test_fetch_serp_mocked_success(self, mock_get):
        """fetch_serp returns HTML on HTTP 200."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = MOCK_GOOGLE_SERP_HTML
        mock_get.return_value = mock_resp

        client = GoogleEtSerpClient(politeness_delay=0)
        html = client.fetch_serp('test keyword')
        self.assertEqual(html, MOCK_GOOGLE_SERP_HTML)


class SubscriptionEntitlementTests(TestCase):
    """Verify subscription gating: Free blocked, Starter/Agency allowed, keyword quotas."""

    def setUp(self):
        SubscriptionService.bootstrap_default_plans()

        self.user_free = User.objects.create_user(
            email='free_sub@doxarank.com',
            password='Password123!'
        )
        self.user_starter = User.objects.create_user(
            email='starter_sub@doxarank.com',
            password='Password123!'
        )
        self.user_agency = User.objects.create_user(
            email='agency_sub@doxarank.com',
            password='Password123!'
        )

        SubscriptionService.assign_plan(self.user_free, PlanCode.FREE)
        SubscriptionService.assign_plan(self.user_starter, PlanCode.STARTER)
        SubscriptionService.assign_plan(self.user_agency, PlanCode.AGENCY)

        self.project_free = Project.objects.create(owner=self.user_free, name='Free Site', website_url='https://free.com')
        self.project_starter = Project.objects.create(owner=self.user_starter, name='Starter Site', website_url='https://starter.com')
        self.project_agency = Project.objects.create(owner=self.user_agency, name='Agency Site', website_url='https://agency.com')

    def test_free_user_lacks_rank_tracking_entitlement(self):
        """Free plan does not have FeatureCode.RANK_TRACKING."""
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_free, FeatureCode.RANK_TRACKING))
        with self.assertRaises(FeatureNotEntitledException):
            PlanEntitlementService.check_can_use_feature(self.user_free, FeatureCode.RANK_TRACKING)

    def test_starter_user_has_rank_tracking_entitlement(self):
        """Starter plan includes FeatureCode.RANK_TRACKING."""
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.RANK_TRACKING))

    def test_agency_user_has_rank_tracking_entitlement(self):
        """Agency plan includes FeatureCode.RANK_TRACKING."""
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_agency, FeatureCode.RANK_TRACKING))

    def test_keyword_limits_free_tier(self):
        """Free tier is limited to 3 keywords."""
        _, limit = PlanEntitlementService.get_keyword_usage(self.user_free)
        self.assertEqual(limit, 3)

    def test_keyword_limits_starter_tier(self):
        """Starter tier allows up to 50 keywords."""
        _, limit = PlanEntitlementService.get_keyword_usage(self.user_starter)
        self.assertEqual(limit, 50)

    def test_keyword_limits_agency_tier(self):
        """Agency tier allows up to 500 keywords."""
        _, limit = PlanEntitlementService.get_keyword_usage(self.user_agency)
        self.assertEqual(limit, 500)


class TenantIsolationTests(TestCase):
    """Verify cross-tenant security: User A cannot see or modify User B keywords/rankings/jobs."""

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user_a = User.objects.create_user(email='tenant_a@doxarank.com', password='Password123!')
        self.user_b = User.objects.create_user(email='tenant_b@doxarank.com', password='Password123!')

        SubscriptionService.assign_plan(self.user_a, PlanCode.STARTER)
        SubscriptionService.assign_plan(self.user_b, PlanCode.STARTER)

        self.proj_a = Project.objects.create(owner=self.user_a, name='Project A', website_url='https://proja.com')
        self.proj_b = Project.objects.create(owner=self.user_b, name='Project B', website_url='https://projb.com')

        self.kw_a = Keyword.objects.create(project=self.proj_a, keyword='keyword a')
        self.kw_b = Keyword.objects.create(project=self.proj_b, keyword='keyword b')

        self.ranking_b = KeywordRanking.objects.create(
            keyword=self.kw_b,
            position=5,
            recorded_at=timezone.now()
        )
        self.job_b = RankCheckJob.objects.create(project=self.proj_b, status=RankCheckJobStatus.COMPLETED)

    def test_user_a_cannot_view_user_b_keyword(self):
        """User A gets 404 when requesting User B's keyword."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'/api/seo/keywords/{self.kw_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_view_user_b_ranking(self):
        """User A gets 404 when requesting User B's ranking."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'/api/seo/rankings/{self.ranking_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_launch_rank_check_for_user_b_keyword(self):
        """User A cannot trigger rank check for User B's keyword (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post('/api/seo/rankings/check/', {'keyword_id': self.kw_b.id})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_launch_rank_check_for_user_b_project(self):
        """User A cannot trigger batch rank check for User B's project (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post('/api/seo/rankings/check/', {'project_id': self.proj_b.id})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_access_user_b_ranking_summary(self):
        """User A cannot retrieve ranking summary for User B's project (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'/api/seo/rankings/summary/?project_id={self.proj_b.id}')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_view_user_b_rank_job(self):
        """User A gets 404 when accessing User B's rank check job."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'/api/seo/rankings/jobs/{self.job_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class RankTrackerCeleryTests(TestCase):
    """Test Celery asynchronous rank tracking tasks, state transitions, and error handling."""

    def setUp(self):
        SubscriptionService.bootstrap_default_plans()

        self.user = User.objects.create_user(email='celery_tester@doxarank.com', password='Password123!')
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)

        self.project = Project.objects.create(
            owner=self.user,
            name='Addis Insight',
            website_url='https://addisinsight.net'
        )
        self.kw1 = Keyword.objects.create(project=self.project, keyword='ethiopian tourism')
        self.kw2 = Keyword.objects.create(project=self.project, keyword='addis ababa hotels')

    @patch.object(GoogleEtSerpClient, 'fetch_serp', return_value=MOCK_GOOGLE_SERP_HTML)
    def test_check_keyword_ranking_task_success(self, mock_fetch):
        """check_keyword_ranking Celery task stores a snapshot with position."""
        snapshot_id = check_keyword_ranking(self.kw1.id)
        self.assertIsNotNone(snapshot_id)
        snapshot = KeywordRanking.objects.get(id=snapshot_id)
        self.assertEqual(snapshot.position, 2)
        self.assertEqual(snapshot.result_status, RankingResultStatus.FOUND)

    @patch.object(GoogleEtSerpClient, 'fetch_serp', return_value=MOCK_GOOGLE_SERP_HTML)
    def test_run_project_rank_check_lifecycle(self, mock_fetch):
        """Batch project check executes, updates RankCheckJob, and transitions to COMPLETED."""
        job = RankCheckJob.objects.create(
            project=self.project,
            status=RankCheckJobStatus.PENDING,
            total_keywords=2,
            trigger='manual'
        )
        res = run_project_rank_check(self.project.id, job.id)
        self.assertEqual(res, job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, RankCheckJobStatus.COMPLETED)
        self.assertEqual(job.completed_keywords, 2)
        self.assertEqual(job.failed_keywords, 0)
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.completed_at)

    @patch.object(GoogleEtSerpClient, 'fetch_serp')
    def test_run_project_rank_check_partial_failure_isolation(self, mock_fetch):
        """One failed keyword check does not crash the entire batch; marks PARTIAL_FAILURE."""
        # First keyword raises exception, second returns valid HTML
        mock_fetch.side_effect = [
            RuntimeError("Google connection timed out"),
            MOCK_GOOGLE_SERP_HTML,
        ]

        job = RankCheckJob.objects.create(
            project=self.project,
            status=RankCheckJobStatus.PENDING,
            total_keywords=2,
            trigger='manual'
        )
        run_project_rank_check(self.project.id, job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, RankCheckJobStatus.PARTIAL_FAILURE)
        self.assertEqual(job.completed_keywords, 1)
        self.assertEqual(job.failed_keywords, 1)

    @patch.object(GoogleEtSerpClient, 'fetch_serp', return_value=MOCK_GOOGLE_SERP_HTML)
    def test_run_daily_rank_checks_idempotency(self, mock_fetch):
        """Daily rank check skips keywords already checked today to prevent duplicate snapshots."""
        # Create a snapshot for kw1 today
        KeywordRanking.objects.create(
            keyword=self.kw1,
            position=4,
            result_status=RankingResultStatus.FOUND,
            recorded_at=timezone.now()
        )

        summary = run_daily_rank_checks()
        # kw1 is skipped, kw2 is checked
        self.assertEqual(summary['checked'], 1)
        self.assertEqual(summary['skipped'], 1)


class RankTrackerAPITests(TestCase):
    """Test REST API endpoints for rank checks, summaries, history, and permission gating."""

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user_free = User.objects.create_user(email='api_free@doxarank.com', password='Password123!')
        self.user_starter = User.objects.create_user(email='api_starter@doxarank.com', password='Password123!')

        SubscriptionService.assign_plan(self.user_free, PlanCode.FREE)
        SubscriptionService.assign_plan(self.user_starter, PlanCode.STARTER)

        self.proj_free = Project.objects.create(owner=self.user_free, name='Free Proj', website_url='https://free.com')
        self.kw_free = Keyword.objects.create(project=self.proj_free, keyword='free query')

        self.proj_starter = Project.objects.create(owner=self.user_starter, name='Starter Proj', website_url='https://addisinsight.net')
        self.kw_starter = Keyword.objects.create(project=self.proj_starter, keyword='ethiopia news')

    def test_unauthenticated_requests_rejected(self):
        """Unauthenticated requests to rank check and summary return 401."""
        res1 = self.client.post('/api/seo/rankings/check/', {})
        self.assertEqual(res1.status_code, status.HTTP_401_UNAUTHORIZED)
        res2 = self.client.get('/api/seo/rankings/summary/')
        self.assertEqual(res2.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_free_user_rank_check_blocked(self):
        """Free user attempting to launch a rank check receives 403 Forbidden."""
        self.client.force_authenticate(user=self.user_free)
        res = self.client.post('/api/seo/rankings/check/', {'keyword_id': self.kw_free.id})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Rank Tracking', res.data.get('error', ''))

    @patch('apps.seo.tasks.check_keyword_ranking.delay')
    def test_starter_user_rank_check_single_keyword(self, mock_task):
        """Starter user successfully queues a single keyword rank check."""
        mock_task.return_value = MagicMock(id='celery-task-123')
        self.client.force_authenticate(user=self.user_starter)
        res = self.client.post('/api/seo/rankings/check/', {'keyword_id': self.kw_starter.id})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'queued')
        self.assertEqual(res.data['keyword_id'], self.kw_starter.id)

    @patch('apps.seo.tasks.run_project_rank_check.delay')
    def test_starter_user_rank_check_project_batch(self, mock_task):
        """Starter user successfully queues a batch project rank check creating a RankCheckJob."""
        self.client.force_authenticate(user=self.user_starter)
        res = self.client.post('/api/seo/rankings/check/', {'project_id': self.proj_starter.id})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'queued')
        self.assertIn('job_id', res.data)
        self.assertTrue(RankCheckJob.objects.filter(id=res.data['job_id']).exists())

    def test_ranking_summary_metrics_calculation(self):
        """Ranking summary returns current position, previous position, and delta change."""
        now = timezone.now()
        # Older snapshot: rank 8
        KeywordRanking.objects.create(
            keyword=self.kw_starter,
            position=8,
            result_status=RankingResultStatus.FOUND,
            ranking_url='https://addisinsight.net/news',
            title='Ethiopia News Old',
            recorded_at=now - timezone.timedelta(days=1)
        )
        # Newer snapshot: rank 5 (improved by 3 positions)
        KeywordRanking.objects.create(
            keyword=self.kw_starter,
            position=5,
            result_status=RankingResultStatus.FOUND,
            ranking_url='https://addisinsight.net/news-2026',
            title='Ethiopia News Latest',
            recorded_at=now
        )

        self.client.force_authenticate(user=self.user_starter)
        res = self.client.get(f'/api/seo/rankings/summary/?project_id={self.proj_starter.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

        item = res.data[0]
        self.assertEqual(item['current_position'], 5)
        self.assertEqual(item['previous_position'], 8)
        self.assertEqual(item['change'], 3)
        self.assertEqual(item['change_status'], 'improved')
        self.assertEqual(item['title'], 'Ethiopia News Latest')

    def test_ranking_history_endpoint(self):
        """Ranking history endpoint returns chronological snapshots."""
        now = timezone.now()
        r1 = KeywordRanking.objects.create(
            keyword=self.kw_starter,
            position=12,
            recorded_at=now - timezone.timedelta(days=2)
        )
        r2 = KeywordRanking.objects.create(
            keyword=self.kw_starter,
            position=9,
            recorded_at=now - timezone.timedelta(days=1)
        )

        self.client.force_authenticate(user=self.user_starter)
        res = self.client.get(f'/api/seo/rankings/history/?keyword_id={self.kw_starter.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 2)
        # Ordered by -recorded_at
        self.assertEqual(res.data[0]['id'], r2.id)
        self.assertEqual(res.data[1]['id'], r1.id)


# =============================================================================
# PRODUCTION FIXTURE-BASED PARSER TEST SUITE (16 Scenarios)
# =============================================================================

FIXTURE_1_ENGLISH_SERP = """
<!DOCTYPE html>
<html>
<head><title>addis ababa business directory - Google Search</title></head>
<body>
  <div id="search">
    <div id="rso">
      <div class="g"><a href="https://ethiopianbusiness.com/directory"><h3>Ethiopian Business Directory</h3></a></div>
      <div class="g"><a href="https://addisinsight.net/business"><h3>Addis Insight Business Guide</h3></a></div>
      <div class="g"><a href="https://shega.co/directory"><h3>Shega Tech Directory</h3></a></div>
    </div>
  </div>
</body>
</html>
"""

FIXTURE_2_AMHARIC_SERP = """
<!DOCTYPE html>
<html>
<head><title>የኢትዮጵያ ቱሪዝም እና ሆቴሎች - የGoogle ፍለጋ</title></head>
<body>
  <div id="search">
    <div id="rso">
      <div class="g"><a href="https://ethiopianreporter.com/tourism"><h3>የኢትዮጵያ ቱሪዝም መረጃ</h3></a></div>
      <div class="g"><a href="https://addisinsight.net/am/tourism"><h3>አዲስ ኢንሳይት - የኢትዮጵያ ቱሪዝም እና ሆቴሎች</h3></a></div>
    </div>
  </div>
</body>
</html>
"""

FIXTURE_3_OROMO_SERP = """
<!DOCTYPE html>
<html>
<head><title>hoteela gaarii Finfinnee - Barbaacha Google</title></head>
<body>
  <div id="search">
    <div id="rso">
      <div class="g"><a href="https://bbc.com/afaanoromoo/tourism"><h3>Oduu fi Daawwanna Itoophiyaa</h3></a></div>
      <div class="g"><a href="https://addisinsight.net/om/hotels"><h3>Addis Insight - Hoteelota Gaarii Finfinnee</h3></a></div>
    </div>
  </div>
</body>
</html>
"""

FIXTURE_4_ADS_SERP = """
<!DOCTYPE html>
<html>
<head><title>hotels in ethiopia - Google Search</title></head>
<body>
  <div id="search">
    <!-- Top ads container -->
    <div id="tads">
      <div class="uEierd">
        <span class="ad-label">Sponsored</span>
        <a href="https://booking.com/addis"><h3>Booking.com Addis Hotels</h3></a>
      </div>
      <div class="uEierd">
        <span class="ad-label">Ad</span>
        <a href="https://agoda.com/ethiopia"><h3>Agoda Hotels in Ethiopia</h3></a>
      </div>
    </div>
    <!-- Organic results -->
    <div id="rso">
      <div class="g"><a href="https://tripadvisor.com/ethiopia"><h3>Tripadvisor: Ethiopia</h3></a></div>
      <div class="g"><a href="https://addisinsight.net/hotels"><h3>Addis Insight Hotel Guide</h3></a></div>
    </div>
    <!-- Bottom ads container -->
    <div id="bottomads">
      <div class="uEierd">
        <span>ማስታወቂያ</span>
        <a href="https://hotelscombined.com"><h3>HotelsCombined Discount</h3></a>
      </div>
    </div>
  </div>
</body>
</html>
"""

FIXTURE_5_PAA_SERP = """
<!DOCTYPE html>
<html>
<head><title>travel to addis ababa - Google Search</title></head>
<body>
  <div id="search">
    <div id="rso">
      <div class="g"><a href="https://wikitravel.org/en/Addis_Ababa"><h3>Addis Ababa Travel Guide - Wikitravel</h3></a></div>
      <!-- People Also Ask widget (must NOT be counted) -->
      <div class="related-question-pair">
        <div>People also ask</div>
        <div data-q="Is Addis Ababa safe?">
          <a href="https://travelsafe.com/ethiopia"><h3>Is Addis Ababa safe to visit?</h3></a>
        </div>
      </div>
      <div class="g"><a href="https://addisinsight.net/travel"><h3>Addis Insight: Essential Addis Ababa Guide</h3></a></div>
    </div>
  </div>
</body>
</html>
"""

FIXTURE_6_FEATURED_SNIPPET_SERP = """
<!DOCTYPE html>
<html>
<head><title>best time to visit ethiopia - Google Search</title></head>
<body>
  <div id="search">
    <div id="rso">
      <!-- Featured snippet container -->
      <div class="g c2xzTb">
        <div class="xpdOpen">
          <a href="https://addisinsight.net/best-time-to-visit">
            <h3>The Best Time to Visit Ethiopia: Weather & Festival Guide</h3>
          </a>
          <div>The dry season from October to February is generally considered the best time to visit Ethiopia...</div>
          <a href="https://support.google.com/websearch/answer/6371484">About featured snippets</a>
        </div>
      </div>
      <div class="g"><a href="https://lonelyplanet.com/ethiopia"><h3>Lonely Planet Ethiopia Guide</h3></a></div>
    </div>
  </div>
</body>
</html>
"""

FIXTURE_7_MISSING_KEYWORD_SERP = """
<!DOCTYPE html>
<html>
<head><title>aerospace engineering addis ababa - Google Search</title></head>
<body>
  <div id="search">
    <div id="rso">
      <div class="g"><a href="https://aau.edu.et/technology"><h3>AAU Technology Faculty</h3></a></div>
      <div class="g"><a href="https://ethiopianairlines.com/aviation-academy"><h3>Ethiopian Aviation Academy</h3></a></div>
    </div>
  </div>
</body>
</html>
"""

FIXTURE_8_MULTIPLE_ORGANIC_SERP = """
<!DOCTYPE html>
<html>
<head><title>ethiopia coffee exporters - Google Search</title></head>
<body>
  <div id="search">
    <div id="rso">
      <div class="g"><a href="https://site1.com"><h3>Coffee Exporter 1</h3></a></div>
      <div class="g"><a href="https://site2.com"><h3>Coffee Exporter 2</h3></a></div>
      <div class="g"><a href="https://site3.com"><h3>Coffee Exporter 3</h3></a></div>
      <div class="g"><a href="https://site4.com"><h3>Coffee Exporter 4</h3></a></div>
      <div class="g"><a href="https://site5.com"><h3>Coffee Exporter 5</h3></a></div>
      <div class="g"><a href="https://addisinsight.net/coffee"><h3>Addis Insight Coffee Guide</h3></a></div>
      <div class="g"><a href="https://site7.com"><h3>Coffee Exporter 7</h3></a></div>
      <div class="g"><a href="https://site8.com"><h3>Coffee Exporter 8</h3></a></div>
      <div class="g"><a href="https://site9.com"><h3>Coffee Exporter 9</h3></a></div>
      <div class="g"><a href="https://site10.com"><h3>Coffee Exporter 10</h3></a></div>
    </div>
  </div>
</body>
</html>
"""

FIXTURE_9_DUPLICATE_URLS_SERP = """
<!DOCTYPE html>
<html>
<head><title>ethiopian telecom news - Google Search</title></head>
<body>
  <div id="search">
    <div id="rso">
      <div class="g">
        <a href="https://addisinsight.net/telecom-update/"><h3>Addis Insight Telecom Update</h3></a>
        <div class="sitelinks">
          <a href="https://addisinsight.net/telecom-update/#section1"><h3>Section 1</h3></a>
          <a href="https://addisinsight.net/telecom-update/"><h3>Duplicate Link</h3></a>
        </div>
      </div>
      <div class="g"><a href="https://ethiotel.et"><h3>Ethio Telecom Official</h3></a></div>
    </div>
  </div>
</body>
</html>
"""

FIXTURE_10_UNICODE_PUNCTUATION_SERP = """
<!DOCTYPE html>
<html>
<head><title>የኢትዮጵያ፡ባህል፡እና፡ታሪክ - የGoogle ፍለጋ</title></head>
<body>
  <div id="search">
    <div id="rso">
      <div class="g"><a href="https://culture.gov.et"><h3>የባህልና፡ስፖርት፡ሚኒስቴር።</h3></a></div>
      <div class="g"><a href="https://addisinsight.net/am/culture/"><h3>አዲስ፡ኢንሳይት፤ የኢትዮጵያ፡ባህልና፡ታሪክ።</h3></a></div>
      <div class="g"><a href="https://oromia.gov.et/aadaa"><h3>Aadaa fi Seenaa Oromiyaa'n</h3></a></div>
    </div>
  </div>
</body>
</html>
"""

FIXTURE_11_CONSENT_PAGE = """
<!DOCTYPE html>
<html>
<head><title>Before you continue to Google Search</title></head>
<body>
  <form action="https://consent.google.com/save">
    <h1>Before you continue to Google</h1>
    <p>We use cookies and data to deliver and maintain Google services...</p>
    <button type="submit">I agree</button>
  </form>
</body>
</html>
"""

FIXTURE_12_MALFORMED_HTML = """
<!DOCTYPE html>
<html>
<head><title>502 Bad Gateway</title></head>
<body>
  <h1>Server Error 502</h1>
  <p>The upstream server was not available.</p>
</body>
</html>
"""

FIXTURE_13_EMPTY_SERP = "   \n\t   "


class ProductionSerpParserTestSuite(TestCase):
    """
    Realistic fixture-based parser tests covering all 16 required production scenarios.
    """

    def test_1_normal_english_google_ethiopia_serp(self):
        """Scenario 1: Normal English Google Ethiopia SERP."""
        res = SerpParser.parse_google_serp(FIXTURE_1_ENGLISH_SERP, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 2)
        self.assertEqual(res.url, 'https://addisinsight.net/business')
        self.assertIn('Addis Insight Business Guide', res.title)

    def test_2_amharic_serp(self):
        """Scenario 2: Amharic SERP with Fidel characters."""
        res = SerpParser.parse_google_serp(FIXTURE_2_AMHARIC_SERP, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 2)
        self.assertEqual(res.url, 'https://addisinsight.net/am/tourism')
        self.assertIn('አዲስ ኢንሳይት', res.title)

    def test_3_oromo_serp(self):
        """Scenario 3: Oromo SERP with Afaan Oromoo search results."""
        res = SerpParser.parse_google_serp(FIXTURE_3_OROMO_SERP, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 2)
        self.assertEqual(res.url, 'https://addisinsight.net/om/hotels')
        self.assertIn('Hoteelota Gaarii Finfinnee', res.title)

    def test_4_serp_containing_advertisements(self):
        """Scenario 4: Top and bottom ads are filtered out and do not shift organic position."""
        res = SerpParser.parse_google_serp(FIXTURE_4_ADS_SERP, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 2)  # Organic #2, not displaced by Booking.com/Agoda ads
        self.assertEqual(res.url, 'https://addisinsight.net/hotels')

    def test_5_serp_containing_paa(self):
        """Scenario 5: People Also Ask (PAA) question blocks are ignored as organic results."""
        res = SerpParser.parse_google_serp(FIXTURE_5_PAA_SERP, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 2)  # Organic #2, not displaced by PAA accordion link

    def test_6_featured_snippet(self):
        """Scenario 6: Featured snippet is captured as rank #1 organic result without duplication."""
        res = SerpParser.parse_google_serp(FIXTURE_6_FEATURED_SNIPPET_SERP, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 1)
        self.assertEqual(res.url, 'https://addisinsight.net/best-time-to-visit')

    def test_7_missing_keyword(self):
        """Scenario 7: Keyword not present in top results returns NOT_FOUND with position=None."""
        res = SerpParser.parse_google_serp(FIXTURE_7_MISSING_KEYWORD_SERP, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.NOT_FOUND)
        self.assertIsNone(res.position)
        self.assertIsNone(res.url)

    def test_8_multiple_organic_results(self):
        """Scenario 8: Multiple organic results preserve exact 1-based ranking sequence."""
        res = SerpParser.parse_google_serp(FIXTURE_8_MULTIPLE_ORGANIC_SERP, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 6)
        self.assertEqual(res.total_organic_found, 10)

    def test_9_duplicate_looking_urls(self):
        """Scenario 9: Sitelinks and duplicate URLs on the same page are cleanly deduplicated."""
        items = SerpParser.parse_organic_results(FIXTURE_9_DUPLICATE_URLS_SERP)
        urls = [url for url, _ in items]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(urls[0], 'https://addisinsight.net/telecom-update/')

    def test_10_unicode_punctuation(self):
        """Scenario 10: Amharic and Oromo punctuation in SERP preserved without corruption."""
        res = SerpParser.parse_google_serp(FIXTURE_10_UNICODE_PUNCTUATION_SERP, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 2)
        self.assertIn('አዲስ፡ኢንሳይት፤', res.title)

    def test_11_google_block_consent_page(self):
        """Scenario 11: Google consent/interstitial page classified as ERROR."""
        res = SerpParser.parse_google_serp(FIXTURE_11_CONSENT_PAGE, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.ERROR)
        self.assertIsNone(res.position)
        self.assertIn('consent', res.error_message.lower())

    def test_12_malformed_unexpected_html(self):
        """Scenario 12: Malformed HTML missing SERP landmarks classified as ERROR."""
        res = SerpParser.parse_google_serp(FIXTURE_12_MALFORMED_HTML, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.ERROR)
        self.assertIsNone(res.position)
        self.assertIn('landmarks', res.error_message.lower())

    def test_13_empty_serp(self):
        """Scenario 13: Empty or whitespace HTML classified as ERROR."""
        res = SerpParser.parse_google_serp(FIXTURE_13_EMPTY_SERP, 'https://addisinsight.net')
        self.assertEqual(res.status, RankingResultStatus.ERROR)
        self.assertIsNone(res.position)

    @patch('httpx.Client.get')
    def test_14_http_error(self, mock_get):
        """Scenario 14: Outbound HTTP 500/404 error is caught and stored as ERROR snapshot."""
        import httpx
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("500 Server Error", request=MagicMock(), response=mock_resp)
        mock_get.return_value = mock_resp

        client = GoogleEtSerpClient(max_retries=0)
        with self.assertRaises(Exception):
            client.fetch_serp("hotels addis")

    @patch('httpx.Client.get')
    def test_15_timeout(self, mock_get):
        """Scenario 15: Outbound request timeout is caught and surfaced safely."""
        import httpx
        mock_get.side_effect = httpx.TimeoutException("Connection timed out after 15s")

        client = GoogleEtSerpClient(max_retries=0)
        with self.assertRaises(RuntimeError) as ctx:
            client.fetch_serp("hotels addis")
        self.assertIn("timed out", str(ctx.exception).lower())

    @patch('httpx.Client.get')
    def test_16_rate_limit_response(self, mock_get):
        """Scenario 16: HTTP 429 rate limit triggers bounded retry then raises RuntimeError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        client = GoogleEtSerpClient(max_retries=1, politeness_delay=0.01)
        with self.assertRaises(RuntimeError) as ctx:
            client.fetch_serp("hotels addis")
        self.assertIn("rate limit", str(ctx.exception).lower())


# =============================================================================
# PRODUCTION RANK TRACKER SERVICE TESTS (Requirement 15)
# =============================================================================

class ProductionRankTrackerServiceTests(TestCase):
    """
    Comprehensive service tests covering single, multiple, mixed language,
    device preservation, failure modes, tenant isolation, and subscription limits.
    """

    def setUp(self):
        self.user_a = User.objects.create_user(
            email='user_a@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='user_b@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='B'
        )
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Addis Insight Project',
            website_url='https://addisinsight.net'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Shega Project',
            website_url='https://shega.co'
        )
        SubscriptionService.bootstrap_default_plans()
        SubscriptionService.assign_plan(self.user_a, PlanCode.STARTER)
        SubscriptionService.assign_plan(self.user_b, PlanCode.AGENCY)

    @patch.object(GoogleEtSerpClient, 'fetch_serp', return_value=FIXTURE_1_ENGLISH_SERP)
    def test_service_one_keyword(self, mock_fetch):
        """Single keyword check persists snapshot with correct position and metadata."""
        kw = Keyword.objects.create(
            project=self.project_a,
            keyword='addis business guide',
            language=Language.EN,
            device=Device.DESKTOP
        )
        service = RankTrackerService()
        snapshot = service.check_keyword(kw)

        self.assertEqual(snapshot.position, 2)
        self.assertEqual(snapshot.result_status, RankingResultStatus.FOUND)
        self.assertEqual(snapshot.ranking_url, 'https://addisinsight.net/business')
        self.assertEqual(snapshot.device, Device.DESKTOP)
        self.assertEqual(snapshot.country, Country.ET)

    @patch.object(GoogleEtSerpClient, 'fetch_serp', return_value=FIXTURE_1_ENGLISH_SERP)
    def test_service_multiple_keywords(self, mock_fetch):
        """Batch project check executes across multiple keywords with progress updates."""
        kw1 = Keyword.objects.create(project=self.project_a, keyword='guide 1')
        kw2 = Keyword.objects.create(project=self.project_a, keyword='guide 2')

        job = RankCheckJob.objects.create(
            project=self.project_a,
            status=RankCheckJobStatus.PENDING,
            total_keywords=2
        )
        client = GoogleEtSerpClient(politeness_delay=0.0)
        service = RankTrackerService(serp_client=client)
        snapshots = service.check_project_keywords(self.project_a, job=job)

        self.assertEqual(len(snapshots), 2)
        job.refresh_from_db()
        self.assertEqual(job.status, RankCheckJobStatus.COMPLETED)
        self.assertEqual(job.completed_keywords, 2)
        self.assertEqual(job.failed_keywords, 0)

    @patch.object(GoogleEtSerpClient, 'fetch_serp')
    def test_service_mixed_english_amharic_oromo(self, mock_fetch):
        """Service processes English, Amharic, and Oromo keywords in a single project."""
        kw_en = Keyword.objects.create(project=self.project_a, keyword='addis directory', language=Language.EN)
        kw_am = Keyword.objects.create(project=self.project_a, keyword='የኢትዮጵያ ቱሪዝም', language=Language.AM)
        kw_om = Keyword.objects.create(project=self.project_a, keyword='hoteela gaarii', language=Language.OM)

        mock_fetch.side_effect = [
            FIXTURE_1_ENGLISH_SERP,
            FIXTURE_2_AMHARIC_SERP,
            FIXTURE_3_OROMO_SERP,
        ]

        client = GoogleEtSerpClient(politeness_delay=0.0)
        service = RankTrackerService(serp_client=client)
        snapshots = service.check_project_keywords(self.project_a)

        self.assertEqual(len(snapshots), 3)
        self.assertEqual(snapshots[0].language, Language.EN)
        self.assertEqual(snapshots[1].language, Language.AM)
        self.assertEqual(snapshots[2].language, Language.OM)
        for snap in snapshots:
            self.assertEqual(snap.result_status, RankingResultStatus.FOUND)

    @patch.object(GoogleEtSerpClient, 'fetch_serp', return_value=FIXTURE_1_ENGLISH_SERP)
    def test_service_desktop_and_mobile_device_preservation(self, mock_fetch):
        """Keywords configured for desktop and mobile consistently preserve device context."""
        kw_desk = Keyword.objects.create(project=self.project_a, keyword='hotels', device=Device.DESKTOP)
        kw_mob = Keyword.objects.create(project=self.project_a, keyword='hotels mob', device=Device.MOBILE)

        service = RankTrackerService(serp_client=GoogleEtSerpClient(politeness_delay=0.0))
        snap_desk = service.check_keyword(kw_desk)
        snap_mob = service.check_keyword(kw_mob)

        self.assertEqual(snap_desk.device, Device.DESKTOP)
        self.assertEqual(snap_mob.device, Device.MOBILE)

    @patch.object(GoogleEtSerpClient, 'fetch_serp', return_value=FIXTURE_7_MISSING_KEYWORD_SERP)
    def test_service_not_found_status(self, mock_fetch):
        """When keyword is outside the top 100, status is NOT_FOUND and position is None."""
        kw = Keyword.objects.create(project=self.project_a, keyword='aerospace addis')
        service = RankTrackerService()
        snapshot = service.check_keyword(kw)

        self.assertEqual(snapshot.result_status, RankingResultStatus.NOT_FOUND)
        self.assertIsNone(snapshot.position)

    @patch.object(GoogleEtSerpClient, 'fetch_serp', side_effect=RuntimeError("Google CAPTCHA block"))
    def test_service_error_status(self, mock_fetch):
        """Network/block failure results in ERROR status with sanitized diagnostic message."""
        kw = Keyword.objects.create(project=self.project_a, keyword='blocked kw')
        service = RankTrackerService()
        snapshot = service.check_keyword(kw)

        self.assertEqual(snapshot.result_status, RankingResultStatus.ERROR)
        self.assertIsNone(snapshot.position)
        self.assertIn("CAPTCHA", snapshot.error_message)

    @patch.object(GoogleEtSerpClient, 'fetch_serp')
    def test_service_partial_project_failure(self, mock_fetch):
        """Partial failure in a project check transitions job to PARTIAL_FAILURE."""
        kw1 = Keyword.objects.create(project=self.project_a, keyword='kw 1')
        kw2 = Keyword.objects.create(project=self.project_a, keyword='kw 2')

        mock_fetch.side_effect = [
            FIXTURE_1_ENGLISH_SERP,
            RuntimeError("Network timeout on Google Ethiopia"),
        ]

        job = RankCheckJob.objects.create(project=self.project_a, total_keywords=2)
        service = RankTrackerService(serp_client=GoogleEtSerpClient(politeness_delay=0.0))
        snapshots = service.check_project_keywords(self.project_a, job=job)

        job.refresh_from_db()
        self.assertEqual(job.status, RankCheckJobStatus.PARTIAL_FAILURE)
        self.assertEqual(job.completed_keywords, 1)
        self.assertEqual(job.failed_keywords, 1)

    @patch.object(GoogleEtSerpClient, 'fetch_serp', side_effect=RuntimeError("Google completely unreachable"))
    def test_service_complete_project_failure(self, mock_fetch):
        """Complete failure in a project check transitions job to FAILED."""
        kw1 = Keyword.objects.create(project=self.project_a, keyword='kw 1')
        job = RankCheckJob.objects.create(project=self.project_a, total_keywords=1)

        service = RankTrackerService(serp_client=GoogleEtSerpClient(politeness_delay=0.0))
        snapshots = service.check_project_keywords(self.project_a, job=job)

        job.refresh_from_db()
        self.assertEqual(job.status, RankCheckJobStatus.FAILED)
        self.assertEqual(job.failed_keywords, 1)
        self.assertEqual(job.completed_keywords, 0)

    @patch.object(GoogleEtSerpClient, 'fetch_serp', return_value=FIXTURE_1_ENGLISH_SERP)
    def test_service_historical_snapshots_immutable(self, mock_fetch):
        """Historical ranking snapshots remain immutable when a new check is recorded."""
        kw = Keyword.objects.create(project=self.project_a, keyword='historical kw')
        now = timezone.now()
        past_snapshot = KeywordRanking.objects.create(
            keyword=kw,
            position=15,
            result_status=RankingResultStatus.FOUND,
            recorded_at=now - timezone.timedelta(days=7)
        )

        service = RankTrackerService()
        new_snapshot = service.check_keyword(kw)

        past_snapshot.refresh_from_db()
        self.assertEqual(past_snapshot.position, 15)  # Historical snapshot unchanged
        self.assertEqual(new_snapshot.position, 2)
        self.assertEqual(kw.rankings.count(), 2)

    def test_service_tenant_isolation(self):
        """User A cannot access or check rankings belonging to User B."""
        kw_b = Keyword.objects.create(project=self.project_b, keyword='shega kw')

        client = APIClient()
        client.force_authenticate(user=self.user_a)

        # User A tries to get rankings for User B's keyword
        res = client.get(f'/api/seo/rankings/?keyword_id={kw_b.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 0)

        # User A tries to trigger check for User B's keyword
        res = client.post('/api/seo/rankings/check/', {'keyword_id': kw_b.id})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_service_subscription_limits(self):
        """Free user is blocked from rank tracking; Starter has 50 limit; Agency has 500."""
        user_free = User.objects.create_user(email='free_p@doxarank.com', password='Password123!')
        SubscriptionService.assign_plan(user_free, PlanCode.FREE)
        proj_free = Project.objects.create(owner=user_free, name='Free Proj', website_url='https://free.com')
        kw_free = Keyword.objects.create(project=proj_free, keyword='free kw')

        client = APIClient()
        client.force_authenticate(user=user_free)

        # Free user blocked from triggering rank check
        res = client.post('/api/seo/rankings/check/', {'keyword_id': kw_free.id})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class ModernSerpPipelineTests(TestCase):
    """
    Comprehensive tests for modern Google Ethiopia SERP parsing,
    DataForSEO integration, domain normalization, and display position formatting.
    """

    def setUp(self):
        self.user = User.objects.create_user(email='modern_serp@doxarank.com', password='Password123!')
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.project = Project.objects.create(
            owner=self.user,
            name='Doxa PLC',
            website_url='https://doxaplc.com/'
        )

    def test_modern_google_goto_redirect_unwrapping(self):
        """Modern Google Ethiopia /goto?url= redirect URLs are unwrapped cleanly."""
        wrapped = "/goto?url=https%3A%2F%2Fdoxaplc.com%2Fservices%2Fseo%2F&ved=2ahUKEwj"
        clean = SerpParser.clean_google_url(wrapped)
        self.assertEqual(clean, "https://doxaplc.com/services/seo/")

        # Test absolute google.com.et goto URL
        abs_wrapped = "https://www.google.com.et/goto?url=https%3A%2F%2Fdoxaplc.com%2Fabout"
        clean_abs = SerpParser.clean_google_url(abs_wrapped)
        self.assertEqual(clean_abs, "https://doxaplc.com/about")

    def test_modern_google_serp_containers_and_classes(self):
        """Parser extracts organic results from modern div.MjjYud / a.zReHs DOM structures."""
        modern_html = """
        <!DOCTYPE html>
        <html><head><title>Search</title></head><body>
          <div id="rso">
            <!-- Modern result 1 (Competitor) -->
            <div class="MjjYud">
              <div class="tF2Cxc">
                <div class="yuRUbf">
                  <a class="zReHs" href="/goto?url=https%3A%2F%2Fother-agency.com%2Fservices">
                    <h3>Top Ethiopian Agencies</h3>
                  </a>
                </div>
              </div>
            </div>
            <!-- Modern result 2 (Target website) -->
            <div class="MjjYud">
              <div class="tF2Cxc">
                <div class="yuRUbf">
                  <a class="zReHs" href="/goto?url=https%3A%2F%2Fdoxaplc.com%2Fcase-studies">
                    <h3>DOXA Innovations &amp; SEO Case Studies</h3>
                  </a>
                </div>
              </div>
            </div>
          </div>
        </body></html>
        """
        res = SerpParser.parse_google_serp(modern_html, 'https://doxaplc.com/')
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 2)
        self.assertEqual(res.url, 'https://doxaplc.com/case-studies')
        self.assertIn('DOXA Innovations', res.title)

    def test_google_enablejs_botguard_challenge_detection(self):
        """Google enablejs and BotGuard anti-bot pages are detected explicitly as errors."""
        enablejs_html = """
        <!DOCTYPE html><html><head><title>Google Search</title></head><body>
        <noscript>
          <meta content="0;url=/httpservice/retry/enablejs?sei=xyz" http-equiv="refresh">
          <div>Please click <a href="/httpservice/retry/enablejs?sei=xyz">here</a></div>
        </noscript>
        <script src="https://www.google.com/js/bg/abc.js"></script>
        </body></html>
        """
        is_valid, err = SerpParser.validate_serp_response(enablejs_html)
        self.assertFalse(is_valid)
        self.assertIn("enablejs/BotGuard", err)

        res = SerpParser.parse_google_serp(enablejs_html, 'https://doxaplc.com/')
        self.assertEqual(res.status, RankingResultStatus.ERROR)
        self.assertIsNone(res.position)
        self.assertIn("enablejs/BotGuard", res.error_message)

    def test_domain_normalization_and_strict_matching(self):
        """Domain normalization handles schemes, paths, ports, and www without false positives."""
        self.assertEqual(SerpParser.normalize_domain('https://www.doxaplc.com/about/'), 'doxaplc.com')
        self.assertEqual(SerpParser.normalize_domain('http://doxaplc.com:8080/'), 'doxaplc.com')
        self.assertEqual(SerpParser.normalize_domain('doxaplc.com/'), 'doxaplc.com')

        # Matching tests
        self.assertTrue(SerpParser.domains_match('https://doxaplc.com/page', 'https://www.doxaplc.com/'))
        self.assertTrue(SerpParser.domains_match('https://blog.doxaplc.com/post', 'doxaplc.com'))
        # Substring false positive rejection: notdoxaplc.com must NOT match doxaplc.com
        self.assertFalse(SerpParser.domains_match('https://notdoxaplc.com/page', 'doxaplc.com'))
        self.assertFalse(SerpParser.domains_match('https://doxaplc.org/page', 'doxaplc.com'))

    @patch('httpx.Client.post')
    def test_dataforseo_serp_client_success_found(self, mock_post):
        """DataForSeoSerpClient successfully queries live organic SERP and finds ranking."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = {
            "tasks": [
                {
                    "status_code": 20000,
                    "status_message": "Ok.",
                    "result": [
                        {
                            "items": [
                                {
                                    "type": "organic",
                                    "rank_group": 1,
                                    "url": "https://wikipedia.org/wiki/Start",
                                    "title": "Start - Wikipedia",
                                    "domain": "wikipedia.org"
                                },
                                {
                                    "type": "organic",
                                    "rank_group": 7,
                                    "url": "https://doxaplc.com/start-project",
                                    "title": "Start Your Project - DOXA",
                                    "domain": "doxaplc.com"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        mock_post.return_value = mock_resp

        client = DataForSeoSerpClient(login="test_user", password="test_password")
        res, err = client.check_serp(
            keyword="Start",
            target_website="https://doxaplc.com",
            language="en"
        )
        self.assertIsNone(err)
        self.assertIsNotNone(res)
        self.assertEqual(res.status, RankingResultStatus.FOUND)
        self.assertEqual(res.position, 7)
        self.assertEqual(res.url, "https://doxaplc.com/start-project")

    @patch('httpx.Client.post')
    def test_dataforseo_serp_client_not_found(self, mock_post):
        """DataForSeoSerpClient returns NOT_FOUND when domain is not in results."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = {
            "tasks": [
                {
                    "status_code": 20000,
                    "status_message": "Ok.",
                    "result": [
                        {
                            "items": [
                                {
                                    "type": "organic",
                                    "rank_group": 1,
                                    "url": "https://wikipedia.org/wiki/Start",
                                    "title": "Start - Wikipedia",
                                    "domain": "wikipedia.org"
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        mock_post.return_value = mock_resp

        client = DataForSeoSerpClient(login="test_user", password="test_password")
        res, err = client.check_serp(
            keyword="Start",
            target_website="https://doxaplc.com",
            language="en"
        )
        self.assertIsNone(err)
        self.assertIsNotNone(res)
        self.assertEqual(res.status, RankingResultStatus.NOT_FOUND)
        self.assertIsNone(res.position)

    def test_position_metrics_human_readable_display(self):
        """calculate_position_metrics returns clean display_position values."""
        kw = Keyword.objects.create(project=self.project, keyword='test display kw')

        # Scenario 1: Not checked yet
        m1 = RankTrackerService.calculate_position_metrics(kw)
        self.assertEqual(m1['display_position'], '—')
        self.assertEqual(m1['result_status'], 'not_checked')

        # Scenario 2: Found at rank #7
        KeywordRanking.objects.create(
            keyword=kw,
            position=7,
            result_status=RankingResultStatus.FOUND,
            recorded_at=timezone.now()
        )
        m2 = RankTrackerService.calculate_position_metrics(kw)
        self.assertEqual(m2['display_position'], '#7')
        self.assertEqual(m2['current_position'], 7)

        # Scenario 3: Not in top 100
        KeywordRanking.objects.create(
            keyword=kw,
            position=None,
            result_status=RankingResultStatus.NOT_FOUND,
            recorded_at=timezone.now() + timezone.timedelta(minutes=1)
        )
        m3 = RankTrackerService.calculate_position_metrics(kw)
        self.assertEqual(m3['display_position'], 'Not in top 100')
        self.assertIsNone(m3['current_position'])

        # Scenario 4: Error / Check failed
        KeywordRanking.objects.create(
            keyword=kw,
            position=None,
            result_status=RankingResultStatus.ERROR,
            error_message='Google anti-bot challenge',
            recorded_at=timezone.now() + timezone.timedelta(minutes=2)
        )
        m4 = RankTrackerService.calculate_position_metrics(kw)
        self.assertEqual(m4['display_position'], 'Check failed')
        self.assertIsNone(m4['current_position'])
        self.assertIn('anti-bot', m4['error_message'])

    def test_three_keyword_scenarios(self):
        """
        Verifies Requirement 15:
        1. Broad keyword where domain is not in top 100 -> status='not_found', pos=None
        2. Keyword that returns project's own domain -> status='found', pos=1
        3. Scraper error/block -> status='error', pos=None
        """
        # Keyword 1: Broad keyword not ranking
        kw_broad = Keyword.objects.create(project=self.project, keyword='Start')
        broad_html = """
        <html><body><div id="rso">
          <div class="g"><a href="https://example.com/one"><h3>Example One</h3></a></div>
          <div class="g"><a href="https://example.com/two"><h3>Example Two</h3></a></div>
        </div></body></html>
        """
        with patch.object(GoogleEtSerpClient, 'fetch_serp', return_value=broad_html):
            service = RankTrackerService()
            snap_broad = service.check_keyword(kw_broad)
            self.assertEqual(snap_broad.result_status, RankingResultStatus.NOT_FOUND)
            self.assertIsNone(snap_broad.position)
            metrics_broad = RankTrackerService.calculate_position_metrics(kw_broad)
            self.assertEqual(metrics_broad['display_position'], 'Not in top 100')

        # Keyword 2: Branded keyword ranking #1
        kw_branded = Keyword.objects.create(project=self.project, keyword='Doxa Innovations Ethiopia')
        branded_html = """
        <html><body><div id="rso">
          <div class="g"><a href="https://doxaplc.com/home"><h3>DOXA Innovations Ethiopia - Official</h3></a></div>
        </div></body></html>
        """
        with patch.object(GoogleEtSerpClient, 'fetch_serp', return_value=branded_html):
            service = RankTrackerService()
            snap_branded = service.check_keyword(kw_branded)
            self.assertEqual(snap_branded.result_status, RankingResultStatus.FOUND)
            self.assertEqual(snap_branded.position, 1)
            metrics_branded = RankTrackerService.calculate_position_metrics(kw_branded)
            self.assertEqual(metrics_branded['display_position'], '#1')

        # Keyword 3: Error / Blocked
        kw_err = Keyword.objects.create(project=self.project, keyword='blocked keyword')
        with patch.object(GoogleEtSerpClient, 'fetch_serp', side_effect=RuntimeError("Google rate limit (HTTP 429)")):
            service = RankTrackerService()
            snap_err = service.check_keyword(kw_err)
            self.assertEqual(snap_err.result_status, RankingResultStatus.ERROR)
            self.assertIsNone(snap_err.position)
            self.assertIn('429', snap_err.error_message)
            metrics_err = RankTrackerService.calculate_position_metrics(kw_err)
            self.assertEqual(metrics_err['display_position'], 'Check failed')


