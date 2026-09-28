"""
Comprehensive test suite for DoxaRank Weekly Competitor SERP Snapshots.
Adheres strictly to the original SRS requirements:
- Competitor management associated with projects
- Weekly and manual SERP snapshots against Google Ethiopia (google.com.et)
- Exact Unicode Amharic preservation
- Strict subscription gating (FeatureCode.COMPETITOR_SNAPSHOTS: Free & Starter blocked, Agency allowed)
- Strict tenant isolation (cross-user access blocked)
- Robust SSRF and domain validation
- Resilient organic result parsing (ads, PAA, knowledge panels ignored)
- Celery task state transitions, error isolation, and idempotency
- 100% mocked external Google network requests
"""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient
from rest_framework import status

from apps.projects.models import Project
from apps.subscriptions.models import Plan, Subscription, FeatureCode, PlanCode
from apps.subscriptions.services import SubscriptionService
from apps.seo.models import (
    Keyword,
    Device,
    Language,
    RankingResultStatus,
    Competitor,
    CompetitorSnapshot,
    CompetitorSnapshotJob,
    CompetitorSnapshotJobStatus,
)
from apps.seo.services.competitor_service import (
    validate_and_normalize_competitor_domain,
    CompetitorSnapshotService,
)
from apps.seo.services.rank_tracker import SerpParser, GoogleEtSerpClient

User = get_user_model()


# Sample mock Google Ethiopia SERP HTML with organic, ads, PAA, and redirects
MOCK_SERP_HTML = """
<!DOCTYPE html>
<html>
<head><title>best hotel addis ababa - Google Search</title></head>
<body>
  <!-- Ad Unit Top (should be ignored) -->
  <div id="tads">
    <div class="ad-unit">
      <span class="ad-badge">Sponsored</span>
      <a href="https://booking.com/ad-hotel"><h3>Booking.com: Addis Hotels</h3></a>
    </div>
  </div>

  <!-- Organic Result 1: Target Project (addisinsight.net) -->
  <div class="g">
    <a href="/url?q=https://www.addisinsight.net/best-hotels-addis/&sa=U">
      <h3>10 Best Luxury Hotels in Addis Ababa - Addis Insight</h3>
    </a>
  </div>

  <!-- Organic Result 2: Competitor A (shega.co) -->
  <div class="MjjYud">
    <a href="https://shega.co/post/top-addis-hotels-hospitality/">
      <h3>Top Hospitality and Hotels in Addis - Shega</h3>
    </a>
  </div>

  <!-- People Also Ask / Knowledge Unit (should be ignored) -->
  <div class="related-question-pair">
    <h3>People also ask</h3>
    <a href="https://tripadvisor.com/faq">Where to stay in Addis?</a>
  </div>

  <!-- Organic Result 3: Competitor B (ethiopianbusinessreview.net) -->
  <div class="g">
    <a href="https://ethiopianbusinessreview.net/hospitality-addis-hotels/">
      <h3>Addis Hotel Sector Overview - EBR</h3>
    </a>
  </div>

  <!-- Amharic Ad Unit (should be ignored) -->
  <div class="g">
    <div>ማስታወቂያ</div>
    <a href="https://ad-network.com/promo"><h3>Special Promo Hotel</h3></a>
  </div>

  <!-- Organic Result 4: General site (travelethiopia.com) -->
  <div class="g">
    <a href="https://travelethiopia.com/hotels/">
      <h3>Travel Ethiopia Hotels Guide</h3>
    </a>
  </div>
</body>
</html>
"""


class CompetitorDomainValidationTests(TestCase):
    """Test domain normalization and SSRF security controls."""

    def setUp(self):
        self.user = User.objects.create_user(email='sec@example.com', password='password123')
        self.project = Project.objects.create(
            owner=self.user,
            name='My Addis Business',
            website_url='https://myaddisbiz.com'
        )

    def test_normalize_valid_domain(self):
        domain, url = validate_and_normalize_competitor_domain("https://www.addisinsight.net/page/", self.project)
        self.assertEqual(domain, "addisinsight.net")
        self.assertEqual(url, "https://addisinsight.net")

    def test_normalize_bare_domain(self):
        domain, url = validate_and_normalize_competitor_domain("shega.co", self.project)
        self.assertEqual(domain, "shega.co")
        self.assertEqual(url, "https://shega.co")

    def test_reject_localhost(self):
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("localhost", self.project)

        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("http://127.0.0.1:8000", self.project)

    def test_reject_private_ip_ranges(self):
        # 10.x.x.x
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("10.0.1.5", self.project)
        # 192.168.x.x
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("192.168.0.1", self.project)
        # 172.16.x.x
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("172.20.0.10", self.project)

    def test_reject_cloud_metadata(self):
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("http://169.254.169.254/latest/meta-data", self.project)
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("metadata.google.internal", self.project)

    def test_reject_dangerous_schemes(self):
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("file:///etc/passwd", self.project)
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("ftp://competitor.com", self.project)
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("javascript:alert(1)", self.project)

    def test_reject_single_word_hostname(self):
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("intranet", self.project)

    def test_reject_project_own_domain(self):
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("https://myaddisbiz.com/about", self.project)
        with self.assertRaises(ValidationError):
            validate_and_normalize_competitor_domain("www.myaddisbiz.com", self.project)


class CompetitorSnapshotModelTests(TestCase):
    """Test Competitor, CompetitorSnapshot, and CompetitorSnapshotJob models."""

    def setUp(self):
        self.user = User.objects.create_user(email='m@example.com', password='password123')
        self.project = Project.objects.create(
            owner=self.user,
            name='Addis Tour Portal',
            website_url='https://addistours.com'
        )
        self.keyword = Keyword.objects.create(
            project=self.project,
            keyword='በአዲስ አበባ ምርጥ ሆቴል',  # Amharic query
            language=Language.AM,
            search_domain='google.com.et'
        )
        self.competitor = Competitor.objects.create(
            project=self.project,
            name='Shega Media',
            domain='shega.co',
            website_url='https://shega.co'
        )

    def test_create_competitor(self):
        self.assertEqual(self.competitor.name, 'Shega Media')
        self.assertEqual(self.competitor.domain, 'shega.co')
        self.assertTrue(self.competitor.is_active)
        self.assertEqual(str(self.competitor), "Shega Media (shega.co) - Addis Tour Portal")

    def test_create_snapshot_found(self):
        snapshot = CompetitorSnapshot.objects.create(
            competitor=self.competitor,
            project=self.project,
            keyword=self.keyword,
            position=3,
            ranking_url='https://shega.co/addis-hotels',
            title='Top Addis Hotels - Shega',
            result_status=RankingResultStatus.FOUND,
            search_domain='google.com.et',
        )
        self.assertEqual(snapshot.position, 3)
        self.assertEqual(snapshot.result_status, RankingResultStatus.FOUND)
        self.assertIn("#3", str(snapshot))

    def test_create_snapshot_not_found(self):
        snapshot = CompetitorSnapshot.objects.create(
            competitor=self.competitor,
            project=self.project,
            keyword=self.keyword,
            position=None,
            result_status=RankingResultStatus.NOT_FOUND,
            search_domain='google.com.et',
        )
        self.assertIsNone(snapshot.position)
        self.assertEqual(snapshot.result_status, RankingResultStatus.NOT_FOUND)
        self.assertIn("Not Found", str(snapshot))

    def test_historical_snapshots_preserved(self):
        # Week 1 snapshot
        s1 = CompetitorSnapshot.objects.create(
            competitor=self.competitor,
            project=self.project,
            keyword=self.keyword,
            position=5,
            result_status=RankingResultStatus.FOUND
        )
        # Week 2 snapshot
        s2 = CompetitorSnapshot.objects.create(
            competitor=self.competitor,
            project=self.project,
            keyword=self.keyword,
            position=8,
            result_status=RankingResultStatus.FOUND
        )
        snapshots = CompetitorSnapshot.objects.filter(competitor=self.competitor, keyword=self.keyword)
        self.assertEqual(snapshots.count(), 2)
        self.assertEqual(snapshots.first().position, 8)  # ordering is -recorded_at


class CompetitorSubscriptionGatingTests(TestCase):
    """Verify subscription gating for Competitor Snapshots (Agency tier required)."""

    def setUp(self):
        self.client = APIClient()

        SubscriptionService.bootstrap_default_plans()

        # Users
        self.user_free = User.objects.create_user(email='f@example.com', password='p123')
        self.user_starter = User.objects.create_user(email='s@example.com', password='p123')
        self.user_agency = User.objects.create_user(email='a@example.com', password='p123')

        SubscriptionService.assign_plan(self.user_free, PlanCode.FREE)
        SubscriptionService.assign_plan(self.user_starter, PlanCode.STARTER)
        SubscriptionService.assign_plan(self.user_agency, PlanCode.AGENCY)

        self.project_free = Project.objects.create(owner=self.user_free, name='Free Proj', website_url='https://free.com')
        self.project_starter = Project.objects.create(owner=self.user_starter, name='Starter Proj', website_url='https://starter.com')
        self.project_agency = Project.objects.create(owner=self.user_agency, name='Agency Proj', website_url='https://agency.com')

    def test_free_user_blocked_from_competitors(self):
        self.client.force_authenticate(user=self.user_free)
        res = self.client.get('/api/seo/competitors/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res_post = self.client.post('/api/seo/competitors/', {
            'project': self.project_free.id,
            'name': 'Competitor A',
            'domain': 'competitor.com'
        })
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)

    def test_starter_user_blocked_from_competitors(self):
        self.client.force_authenticate(user=self.user_starter)
        res = self.client.get('/api/seo/competitors/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res_check = self.client.post('/api/seo/competitor-snapshots/check/', {'project_id': self.project_starter.id})
        self.assertEqual(res_check.status_code, status.HTTP_403_FORBIDDEN)

    def test_agency_user_allowed(self):
        self.client.force_authenticate(user=self.user_agency)
        res = self.client.get('/api/seo/competitors/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        res_post = self.client.post('/api/seo/competitors/', {
            'project': self.project_agency.id,
            'name': 'Shega Media',
            'domain': 'shega.co'
        })
        self.assertEqual(res_post.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_post.data['domain'], 'shega.co')


class CompetitorTenantIsolationTests(TestCase):
    """Verify complete tenant isolation between users."""

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user_a = User.objects.create_user(email='a@example.com', password='p123')
        self.user_b = User.objects.create_user(email='b@example.com', password='p123')

        SubscriptionService.assign_plan(self.user_a, PlanCode.AGENCY)
        SubscriptionService.assign_plan(self.user_b, PlanCode.AGENCY)

        self.proj_a = Project.objects.create(owner=self.user_a, name='Proj A', website_url='https://proja.com')
        self.proj_b = Project.objects.create(owner=self.user_b, name='Proj B', website_url='https://projb.com')

        self.comp_a = Competitor.objects.create(project=self.proj_a, name='Comp A', domain='compa.com')
        self.comp_b = Competitor.objects.create(project=self.proj_b, name='Comp B', domain='compb.com')

    def test_user_a_cannot_view_user_b_competitors(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get('/api/seo/competitors/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        domains = [item['domain'] for item in res.data]
        self.assertIn('compa.com', domains)
        self.assertNotIn('compb.com', domains)

    def test_user_a_cannot_view_user_b_competitor_detail(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'/api/seo/competitors/{self.comp_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_modify_user_b_competitor(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(f'/api/seo/competitors/{self.comp_b.id}/', {'name': 'Hacked'})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_add_competitor_to_user_b_project(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post('/api/seo/competitors/', {
            'project': self.proj_b.id,
            'name': 'Malicious',
            'domain': 'malicious.com'
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_a_cannot_launch_snapshot_on_user_b_project(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post('/api/seo/competitor-snapshots/check/', {'project_id': self.proj_b.id})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class CompetitorSerpServiceTests(TestCase):
    """Test SERP fetching, parsing, and competitor matching against mock google.com.et responses."""

    def setUp(self):
        self.user = User.objects.create_user(email='serp@example.com', password='p123')
        self.project = Project.objects.create(
            owner=self.user,
            name='Addis Insight',
            website_url='https://addisinsight.net'
        )
        self.kw_en = Keyword.objects.create(
            project=self.project,
            keyword='best hotel addis ababa',
            language=Language.EN,
            search_domain='google.com.et'
        )
        self.kw_am = Keyword.objects.create(
            project=self.project,
            keyword='በአዲስ አበባ ምርጥ ሆቴል',
            language=Language.AM,
            search_domain='google.com.et'
        )
        self.comp_shega = Competitor.objects.create(
            project=self.project,
            name='Shega Media',
            domain='shega.co'
        )
        self.comp_ebr = Competitor.objects.create(
            project=self.project,
            name='Ethiopian Business Review',
            domain='ethiopianbusinessreview.net'
        )
        self.comp_missing = Competitor.objects.create(
            project=self.project,
            name='Unranked Competitor',
            domain='notfoundcompetitor.com'
        )

    @patch.object(GoogleEtSerpClient, 'fetch_serp')
    def test_run_snapshot_for_project_success(self, mock_fetch):
        mock_fetch.return_value = MOCK_SERP_HTML

        service = CompetitorSnapshotService()
        job = service.run_snapshot_for_project(project_id=self.project.id)

        self.assertEqual(job.status, CompetitorSnapshotJobStatus.COMPLETED)
        self.assertEqual(job.total_keywords, 2)
        self.assertEqual(job.completed_keywords, 2)
        self.assertEqual(job.failed_keywords, 0)

        # Check snapshots created
        # Shega: organic result 2
        snap_shega = CompetitorSnapshot.objects.filter(
            competitor=self.comp_shega, keyword=self.kw_en
        ).first()
        self.assertIsNotNone(snap_shega)
        self.assertEqual(snap_shega.position, 2)
        self.assertEqual(snap_shega.result_status, RankingResultStatus.FOUND)
        self.assertIn("shega.co", snap_shega.ranking_url)

        # EBR: organic result 3 (ignoring the PAA box)
        snap_ebr = CompetitorSnapshot.objects.filter(
            competitor=self.comp_ebr, keyword=self.kw_en
        ).first()
        self.assertIsNotNone(snap_ebr)
        self.assertEqual(snap_ebr.position, 3)
        self.assertEqual(snap_ebr.result_status, RankingResultStatus.FOUND)

        # Missing competitor: not found in top 100
        snap_missing = CompetitorSnapshot.objects.filter(
            competitor=self.comp_missing, keyword=self.kw_en
        ).first()
        self.assertIsNotNone(snap_missing)
        self.assertIsNone(snap_missing.position)
        self.assertEqual(snap_missing.result_status, RankingResultStatus.NOT_FOUND)

        # Amharic query snapshots also created
        snap_am = CompetitorSnapshot.objects.filter(
            competitor=self.comp_shega, keyword=self.kw_am
        ).first()
        self.assertIsNotNone(snap_am)
        self.assertEqual(snap_am.keyword.keyword, 'በአዲስ አበባ ምርጥ ሆቴል')

    @patch.object(GoogleEtSerpClient, 'fetch_serp')
    def test_run_snapshot_partial_failure_isolation(self, mock_fetch):
        # First keyword succeeds, second keyword fails
        def side_effect(keyword, language, device):
            if 'ምርጥ' in keyword:
                raise RuntimeError("Google connection timeout")
            return MOCK_SERP_HTML

        mock_fetch.side_effect = side_effect

        service = CompetitorSnapshotService()
        job = service.run_snapshot_for_project(project_id=self.project.id)

        self.assertEqual(job.status, CompetitorSnapshotJobStatus.PARTIAL_FAILURE)
        self.assertEqual(job.completed_keywords, 1)
        self.assertEqual(job.failed_keywords, 1)

        # Failed keyword should have ERROR snapshots recorded
        error_snaps = CompetitorSnapshot.objects.filter(keyword=self.kw_am)
        self.assertEqual(error_snaps.count(), 3)
        for s in error_snaps:
            self.assertEqual(s.result_status, RankingResultStatus.ERROR)
            self.assertIn("timeout", s.error_message)


class CompetitorCeleryTaskTests(TestCase):
    """Test Celery async task execution, error isolation, and weekly schedule idempotency."""

    def setUp(self):
        SubscriptionService.bootstrap_default_plans()
        self.user = User.objects.create_user(email='celery@example.com', password='p123')
        SubscriptionService.assign_plan(self.user, PlanCode.AGENCY)

        self.project = Project.objects.create(
            owner=self.user,
            name='Addis Tour',
            website_url='https://addistour.com'
        )
        self.keyword = Keyword.objects.create(
            project=self.project,
            keyword='addis ababa tours'
        )
        self.competitor = Competitor.objects.create(
            project=self.project,
            name='Competitor X',
            domain='compx.com'
        )

    @patch('apps.seo.services.competitor_service.CompetitorSnapshotService.run_snapshot_for_project')
    def test_run_project_competitor_snapshot_task(self, mock_run):
        job = CompetitorSnapshotJob.objects.create(
            project=self.project,
            trigger='manual',
            status=CompetitorSnapshotJobStatus.PENDING
        )
        mock_run.return_value = job

        from apps.seo.tasks import run_project_competitor_snapshot
        res = run_project_competitor_snapshot(self.project.id, job.id)
        self.assertEqual(res, job.id)
        mock_run.assert_called_once_with(project_id=self.project.id, job_id=job.id)

    @patch('apps.seo.tasks.run_project_competitor_snapshot.delay')
    def test_run_weekly_competitor_snapshots_schedule_idempotency(self, mock_delay):
        from apps.seo.tasks import run_weekly_competitor_snapshots

        # First run: should enqueue job
        summary1 = run_weekly_competitor_snapshots()
        self.assertEqual(summary1['enqueued'], 1)
        self.assertEqual(mock_delay.call_count, 1)

        # Complete the created job
        job = CompetitorSnapshotJob.objects.filter(project=self.project).first()
        job.status = CompetitorSnapshotJobStatus.COMPLETED
        job.save()

        # Second run immediately: should skip due to weekly idempotency (checked within last 6 days)
        summary2 = run_weekly_competitor_snapshots()
        self.assertEqual(summary2['enqueued'], 0)
        self.assertEqual(summary2['skipped'], 1)
        self.assertEqual(mock_delay.call_count, 1)  # No extra delay calls


class CompetitorAPITests(TestCase):
    """Test REST API endpoints for competitors, snapshots, and jobs."""

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()
        self.user = User.objects.create_user(email='api@example.com', password='p123')
        SubscriptionService.assign_plan(self.user, PlanCode.AGENCY)
        self.client.force_authenticate(user=self.user)

        self.project = Project.objects.create(
            owner=self.user,
            name='API Proj',
            website_url='https://apiproj.com'
        )
        self.keyword = Keyword.objects.create(
            project=self.project,
            keyword='best addis restaurants'
        )

    def test_competitor_crud_workflow(self):
        # 1. Create competitor
        res = self.client.post('/api/seo/competitors/', {
            'project': self.project.id,
            'name': 'Shega Media',
            'domain': 'https://www.shega.co/news'
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        comp_id = res.data['id']
        self.assertEqual(res.data['domain'], 'shega.co')
        self.assertEqual(res.data['website_url'], 'https://shega.co')

        # 2. List competitors
        res_list = self.client.get(f'/api/seo/competitors/?project_id={self.project.id}')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data), 1)

        # 3. Update competitor
        res_update = self.client.patch(f'/api/seo/competitors/{comp_id}/', {'name': 'Shega Updated'})
        self.assertEqual(res_update.status_code, status.HTTP_200_OK)
        self.assertEqual(res_update.data['name'], 'Shega Updated')

        # 4. Delete competitor
        res_del = self.client.delete(f'/api/seo/competitors/{comp_id}/')
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Competitor.objects.count(), 0)

    @patch('apps.seo.tasks.run_project_competitor_snapshot.delay')
    def test_launch_snapshot_endpoint(self, mock_delay):
        comp = Competitor.objects.create(project=self.project, name='Comp', domain='comp.com')
        res = self.client.post('/api/seo/competitor-snapshots/check/', {'project_id': self.project.id})
        self.assertEqual(res.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(res.data['status'], 'pending')
        self.assertIn('job_id', res.data)
        self.assertEqual(mock_delay.call_count, 1)

    @patch('apps.seo.tasks.run_project_competitor_snapshot.delay')
    def test_launch_snapshot_alias_endpoint(self, mock_delay):
        # Tests the explicit path /api/seo/competitors/snapshots/check/
        res = self.client.post('/api/seo/competitors/snapshots/check/', {'project_id': self.project.id})
        self.assertEqual(res.status_code, status.HTTP_202_ACCEPTED)

    def test_latest_matrix_endpoint(self):
        comp = Competitor.objects.create(project=self.project, name='Comp', domain='comp.com')
        snap = CompetitorSnapshot.objects.create(
            competitor=comp,
            project=self.project,
            keyword=self.keyword,
            position=7,
            result_status=RankingResultStatus.FOUND
        )
        res = self.client.get(f'/api/seo/competitor-snapshots/latest/?project_id={self.project.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['position'], 7)
        self.assertEqual(res.data[0]['competitor_domain'], 'comp.com')
