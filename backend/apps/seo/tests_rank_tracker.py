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
