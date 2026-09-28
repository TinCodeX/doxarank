"""
Tests for SEO Recommendations Feed (Original SRS Task).

Covers:
- Models: creation, priority, status transitions, resolution timestamps, string representation
- Recommendation Engine:
  - Technical Crawler: broken internal page, missing title, duplicate title, missing meta description,
    missing H1, multiple H1s, missing canonical, slow page, image missing alt, redirect chain
  - Rank Tracker: keyword not found in top 100, ranking decline, page 2 striking distance, low ranking
  - Competitor SERP Snapshots: competitor outranking, competitor found while project unranked, competitor top 3
- Deduplication & Idempotency: multiple generation runs do not duplicate recommendations
- Tenant Isolation: User A cannot list, view, modify, or generate recommendations for User B
- Celery Task: async execution, failure handling, project context verification
- REST API: list, filter (status, severity, category, source_type), detail, patch lifecycle, generate endpoint
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.projects.models import Project
from apps.subscriptions.models import PlanCode
from apps.subscriptions.services import SubscriptionService
from apps.seo.models import (
    CrawlJob,
    CrawlJobStatus,
    CrawlPage,
    Keyword,
    KeywordRanking,
    RankingResultStatus,
    Competitor,
    CompetitorSnapshot,
    Recommendation,
    RecommendationSource,
    RecommendationCategory,
    RecommendationSeverity,
    RecommendationState,
)
from apps.seo.services.recommendations import (
    RecommendationEngine,
    calculate_recommendation_priority,
)

User = get_user_model()


class RecommendationModelTests(TestCase):
    """Test Recommendation model creation, ordering, and status transitions."""

    def setUp(self):
        SubscriptionService.bootstrap_default_plans()
        self.user = User.objects.create_user(email='rec_model@example.com', password='password123')
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.project = Project.objects.create(
            owner=self.user,
            name='Addis Insight',
            website_url='https://addisinsight.net'
        )

    def test_create_recommendation(self):
        rec = Recommendation.objects.create(
            project=self.project,
            source_type=RecommendationSource.CRAWLER,
            source_id='101',
            category=RecommendationCategory.INDEXING,
            severity=RecommendationSeverity.CRITICAL,
            title='Fix broken internal page (HTTP 404)',
            description='Problem: HTTP 404. Why it matters: Broken link.',
            recommended_action='Restore page or set up 301 redirect.',
            affected_url='https://addisinsight.net/missing-page',
            status=RecommendationState.OPEN,
            priority=95,
            fingerprint='crawler_broken:https://addisinsight.net/missing-page',
        )
        self.assertEqual(rec.priority, 95)
        self.assertEqual(rec.status, RecommendationState.OPEN)
        self.assertIsNone(rec.resolved_at)
        self.assertIn("CRITICAL", str(rec))
        self.assertIn("Addis Insight", str(rec))

    def test_status_lifecycle(self):
        rec = Recommendation.objects.create(
            project=self.project,
            source_type=RecommendationSource.RANK_TRACKER,
            title='Rank Decline',
            description='Dropped 5 spots',
            recommended_action='Update copy',
            status=RecommendationState.OPEN,
            priority=75,
            fingerprint='rank_decline:1',
        )
        self.assertEqual(rec.status, RecommendationState.OPEN)

        # Transition to acknowledged
        rec.status = RecommendationState.ACKNOWLEDGED
        rec.save()
        self.assertEqual(rec.status, RecommendationState.ACKNOWLEDGED)

        # Transition to resolved
        rec.status = RecommendationState.RESOLVED
        rec.resolved_at = timezone.now()
        rec.save()
        self.assertEqual(rec.status, RecommendationState.RESOLVED)
        self.assertIsNotNone(rec.resolved_at)

    def test_priority_calculation(self):
        p_crit = calculate_recommendation_priority(RecommendationSeverity.CRITICAL, RecommendationCategory.INDEXING, is_broken=True)
        self.assertEqual(p_crit, 100)  # 90 base + 10 broken = 100

        p_high = calculate_recommendation_priority(RecommendationSeverity.HIGH, RecommendationCategory.RANKINGS, is_ranking_drop=True)
        self.assertEqual(p_high, 78)  # 70 base + 8 drop = 78

        p_multi = calculate_recommendation_priority(RecommendationSeverity.MEDIUM, RecommendationCategory.ON_PAGE_SEO, count_affected=4)
        self.assertEqual(p_multi, 58)  # 50 base + min(10, 8) = 58


class RecommendationEngineCrawlerTests(TestCase):
    """Test deterministic recommendation rules for Technical SEO Crawler findings."""

    def setUp(self):
        SubscriptionService.bootstrap_default_plans()
        self.user = User.objects.create_user(email='crawler_rec@example.com', password='p123')
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.project = Project.objects.create(
            owner=self.user,
            name='Bole Hotel',
            website_url='https://bolehotel.et'
        )
        self.crawl_job = CrawlJob.objects.create(
            project=self.project,
            status=CrawlJobStatus.COMPLETED,
            completed_at=timezone.now(),
        )

    def test_broken_page_rule(self):
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://bolehotel.et/missing-room',
            status_code=404,
            is_broken=True,
            title='404 Not Found'
        )
        recs = RecommendationEngine.evaluate_crawler_findings(self.project)
        broken_rec = next((r for r in recs if 'crawler_broken' in r['fingerprint']), None)
        self.assertIsNotNone(broken_rec)
        self.assertEqual(broken_rec['severity'], RecommendationSeverity.CRITICAL)
        self.assertEqual(broken_rec['category'], RecommendationCategory.INDEXING)
        self.assertIn("HTTP 404", broken_rec['title'])

    def test_missing_title_rule(self):
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://bolehotel.et/about',
            status_code=200,
            title=''
        )
        recs = RecommendationEngine.evaluate_crawler_findings(self.project)
        title_rec = next((r for r in recs if 'crawler_missing_title' in r['fingerprint']), None)
        self.assertIsNotNone(title_rec)
        self.assertEqual(title_rec['severity'], RecommendationSeverity.HIGH)
        self.assertEqual(title_rec['category'], RecommendationCategory.ON_PAGE_SEO)

    def test_duplicate_title_rule(self):
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://bolehotel.et/rooms/1',
            status_code=200,
            title='Deluxe Rooms - Bole Hotel'
        )
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://bolehotel.et/rooms/2',
            status_code=200,
            title='Deluxe Rooms - Bole Hotel'
        )
        recs = RecommendationEngine.evaluate_crawler_findings(self.project)
        dup_rec = next((r for r in recs if 'crawler_duplicate_title' in r['fingerprint']), None)
        self.assertIsNotNone(dup_rec)
        self.assertEqual(dup_rec['category'], RecommendationCategory.ON_PAGE_SEO)
        self.assertIn("2 pages", dup_rec['title'])

    def test_missing_meta_description_rule(self):
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://bolehotel.et/contact',
            status_code=200,
            title='Contact Us',
            meta_description=''
        )
        recs = RecommendationEngine.evaluate_crawler_findings(self.project)
        meta_rec = next((r for r in recs if 'crawler_missing_meta_desc' in r['fingerprint']), None)
        self.assertIsNotNone(meta_rec)
        self.assertEqual(meta_rec['severity'], RecommendationSeverity.MEDIUM)

    def test_missing_and_multiple_h1_rules(self):
        # Missing H1
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://bolehotel.et/no-h1',
            status_code=200,
            title='No H1 Page',
            h1_count=0
        )
        # Multiple H1
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://bolehotel.et/multi-h1',
            status_code=200,
            title='Multi H1 Page',
            h1_count=3
        )
        recs = RecommendationEngine.evaluate_crawler_findings(self.project)
        missing_h1 = next((r for r in recs if 'crawler_missing_h1' in r['fingerprint']), None)
        multi_h1 = next((r for r in recs if 'crawler_multiple_h1' in r['fingerprint']), None)

        self.assertIsNotNone(missing_h1)
        self.assertEqual(missing_h1['severity'], RecommendationSeverity.MEDIUM)
        self.assertIsNotNone(multi_h1)
        self.assertEqual(multi_h1['severity'], RecommendationSeverity.LOW)

    def test_missing_canonical_rule(self):
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://bolehotel.et/gallery',
            status_code=200,
            title='Gallery',
            canonical_url=''
        )
        recs = RecommendationEngine.evaluate_crawler_findings(self.project)
        can_rec = next((r for r in recs if 'crawler_missing_canonical' in r['fingerprint']), None)
        self.assertIsNotNone(can_rec)
        self.assertEqual(can_rec['category'], RecommendationCategory.TECHNICAL_SEO)

    def test_slow_page_rule(self):
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://bolehotel.et/slow-page',
            status_code=200,
            title='Slow Page',
            response_time_ms=4500,
            is_slow=True
        )
        recs = RecommendationEngine.evaluate_crawler_findings(self.project)
        slow_rec = next((r for r in recs if 'crawler_slow_page' in r['fingerprint']), None)
        self.assertIsNotNone(slow_rec)
        self.assertEqual(slow_rec['category'], RecommendationCategory.PERFORMANCE)
        self.assertIn("4500ms", slow_rec['title'])

    def test_missing_image_alt_rule(self):
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://bolehotel.et/dining',
            status_code=200,
            title='Dining',
            images_missing_alt_count=5
        )
        recs = RecommendationEngine.evaluate_crawler_findings(self.project)
        alt_rec = next((r for r in recs if 'crawler_missing_alt' in r['fingerprint']), None)
        self.assertIsNotNone(alt_rec)
        self.assertEqual(alt_rec['category'], RecommendationCategory.CONTENT)
        self.assertIn("5 image(s)", alt_rec['title'])

    def test_redirect_chain_rule(self):
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://bolehotel.et/old-link',
            final_url='https://bolehotel.et/final-link',
            status_code=200,
            title='Redirected',
            has_redirect=True,
            redirect_chain=['https://bolehotel.et/hop1', 'https://bolehotel.et/hop2']
        )
        recs = RecommendationEngine.evaluate_crawler_findings(self.project)
        chain_rec = next((r for r in recs if 'crawler_redirect_chain' in r['fingerprint']), None)
        self.assertIsNotNone(chain_rec)
        self.assertEqual(chain_rec['category'], RecommendationCategory.TECHNICAL_SEO)
        self.assertIn("2 hops", chain_rec['title'])


class RecommendationEngineRankTrackerTests(TestCase):
    """Test deterministic recommendation rules for Rank Tracker findings."""

    def setUp(self):
        SubscriptionService.bootstrap_default_plans()
        self.user = User.objects.create_user(email='rank_rec@example.com', password='p123')
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.project = Project.objects.create(
            owner=self.user,
            name='Ethiopian Coffee Co',
            website_url='https://ethiopiancoffee.com'
        )

    def test_keyword_not_found_rule(self):
        kw = Keyword.objects.create(
            project=self.project,
            keyword='sidama specialty coffee'
        )
        KeywordRanking.objects.create(
            keyword=kw,
            position=None,
            result_status=RankingResultStatus.NOT_FOUND,
            recorded_at=timezone.now()
        )
        recs = RecommendationEngine.evaluate_rank_tracker_findings(self.project)
        rec = next((r for r in recs if f"rank_not_found:{kw.id}" in r['fingerprint']), None)
        self.assertIsNotNone(rec)
        self.assertEqual(rec['severity'], RecommendationSeverity.HIGH)
        self.assertEqual(rec['category'], RecommendationCategory.RANKINGS)
        self.assertIn("Top 100", rec['title'])

    def test_ranking_decline_rule(self):
        kw = Keyword.objects.create(
            project=self.project,
            keyword='yirgacheffe beans'
        )
        # Previous observation: rank #4
        KeywordRanking.objects.create(
            keyword=kw,
            position=4,
            result_status=RankingResultStatus.FOUND,
            recorded_at=timezone.now() - timezone.timedelta(days=1)
        )
        # Latest observation: rank #12 (dropped 8 positions)
        KeywordRanking.objects.create(
            keyword=kw,
            position=12,
            result_status=RankingResultStatus.FOUND,
            recorded_at=timezone.now()
        )
        recs = RecommendationEngine.evaluate_rank_tracker_findings(self.project)
        rec = next((r for r in recs if f"rank_decline:{kw.id}" in r['fingerprint']), None)
        self.assertIsNotNone(rec)
        self.assertEqual(rec['severity'], RecommendationSeverity.HIGH)
        self.assertIn("dropped 8 positions to #12", rec['title'])

    def test_page_two_opportunity_rule(self):
        kw = Keyword.objects.create(
            project=self.project,
            keyword='addis ababa roastery'
        )
        KeywordRanking.objects.create(
            keyword=kw,
            position=14,
            result_status=RankingResultStatus.FOUND,
            recorded_at=timezone.now()
        )
        recs = RecommendationEngine.evaluate_rank_tracker_findings(self.project)
        rec = next((r for r in recs if f"rank_page_two:{kw.id}" in r['fingerprint']), None)
        self.assertIsNotNone(rec)
        self.assertEqual(rec['severity'], RecommendationSeverity.MEDIUM)
        self.assertIn("Striking distance", rec['title'])

    def test_low_ranking_rule(self):
        kw = Keyword.objects.create(
            project=self.project,
            keyword='ethiopian espresso blend'
        )
        KeywordRanking.objects.create(
            keyword=kw,
            position=45,
            result_status=RankingResultStatus.FOUND,
            recorded_at=timezone.now()
        )
        recs = RecommendationEngine.evaluate_rank_tracker_findings(self.project)
        rec = next((r for r in recs if f"rank_low_position:{kw.id}" in r['fingerprint']), None)
        self.assertIsNotNone(rec)
        self.assertEqual(rec['severity'], RecommendationSeverity.LOW)
        self.assertIn("#45", rec['title'])


class RecommendationEngineCompetitorTests(TestCase):
    """Test deterministic recommendation rules for Competitor SERP Snapshots findings."""

    def setUp(self):
        SubscriptionService.bootstrap_default_plans()
        self.user = User.objects.create_user(email='comp_rec@example.com', password='p123')
        SubscriptionService.assign_plan(self.user, PlanCode.AGENCY)
        self.project = Project.objects.create(
            owner=self.user,
            name='Addis Tour Portal',
            website_url='https://addistour.et'
        )
        self.competitor = Competitor.objects.create(
            project=self.project,
            name='Rival Tours',
            domain='rivaltours.com'
        )
        self.keyword = Keyword.objects.create(
            project=self.project,
            keyword='ethiopian historic route tour'
        )

    def test_competitor_outranking_project_rule(self):
        # Project is ranking at position 15
        KeywordRanking.objects.create(
            keyword=self.keyword,
            position=15,
            result_status=RankingResultStatus.FOUND,
            recorded_at=timezone.now()
        )
        # Competitor is ranking ahead at position 4
        CompetitorSnapshot.objects.create(
            competitor=self.competitor,
            project=self.project,
            keyword=self.keyword,
            position=4,
            result_status=RankingResultStatus.FOUND,
            ranking_url='https://rivaltours.com/historic-route'
        )
        recs = RecommendationEngine.evaluate_competitor_findings(self.project)
        rec = next((r for r in recs if f"comp_outranks:{self.competitor.id}:{self.keyword.id}" in r['fingerprint']), None)
        self.assertIsNotNone(rec)
        self.assertEqual(rec['severity'], RecommendationSeverity.HIGH)
        self.assertEqual(rec['category'], RecommendationCategory.COMPETITORS)
        self.assertIn("outranks your website", rec['title'])

    def test_competitor_found_project_unranked_rule(self):
        # Project is unranked
        KeywordRanking.objects.create(
            keyword=self.keyword,
            position=None,
            result_status=RankingResultStatus.NOT_FOUND,
            recorded_at=timezone.now()
        )
        # Competitor is ranking at position 6
        CompetitorSnapshot.objects.create(
            competitor=self.competitor,
            project=self.project,
            keyword=self.keyword,
            position=6,
            result_status=RankingResultStatus.FOUND,
        )
        recs = RecommendationEngine.evaluate_competitor_findings(self.project)
        rec = next((r for r in recs if f"comp_proj_not_found:{self.competitor.id}:{self.keyword.id}" in r['fingerprint']), None)
        self.assertIsNotNone(rec)
        self.assertEqual(rec['severity'], RecommendationSeverity.HIGH)
        self.assertIn("ranks (#6) while your site is unranked", rec['title'])

    def test_competitor_top_three_rule(self):
        # Competitor holds position #2
        CompetitorSnapshot.objects.create(
            competitor=self.competitor,
            project=self.project,
            keyword=self.keyword,
            position=2,
            result_status=RankingResultStatus.FOUND,
        )
        recs = RecommendationEngine.evaluate_competitor_findings(self.project)
        rec = next((r for r in recs if f"comp_top_three:{self.competitor.id}:{self.keyword.id}" in r['fingerprint']), None)
        self.assertIsNotNone(rec)
        self.assertEqual(rec['severity'], RecommendationSeverity.MEDIUM)
        self.assertIn("Top 3 rank (#2)", rec['title'])


class RecommendationDeduplicationAndIdempotencyTests(TestCase):
    """Verify that repeated generation runs are strictly idempotent and do not duplicate open recommendations."""

    def setUp(self):
        SubscriptionService.bootstrap_default_plans()
        self.user = User.objects.create_user(email='dedup@example.com', password='p123')
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.project = Project.objects.create(
            owner=self.user,
            name='Dedup Test Proj',
            website_url='https://deduptest.com'
        )
        self.crawl_job = CrawlJob.objects.create(
            project=self.project,
            status=CrawlJobStatus.COMPLETED,
            completed_at=timezone.now(),
        )
        CrawlPage.objects.create(
            crawl_job=self.crawl_job,
            url='https://deduptest.com/broken',
            status_code=404,
            is_broken=True,
            title='Valid Title',
            meta_description='Valid Meta Description',
            h1_count=1,
            canonical_url='https://deduptest.com/broken',
        )

    def test_idempotent_repeated_generation(self):
        # Run 1: Creates recommendation
        recs1 = RecommendationEngine.generate_project_recommendations(self.project)
        self.assertEqual(len(recs1), 1)
        self.assertEqual(Recommendation.objects.filter(project=self.project).count(), 1)
        first_id = recs1[0].id

        # Run 2: Does not create a duplicate
        recs2 = RecommendationEngine.generate_project_recommendations(self.project)
        self.assertEqual(len(recs2), 1)
        self.assertEqual(Recommendation.objects.filter(project=self.project).count(), 1)
        self.assertEqual(recs2[0].id, first_id)

    def test_acknowledged_recommendation_is_updated_not_duplicated(self):
        recs1 = RecommendationEngine.generate_project_recommendations(self.project)
        rec = recs1[0]
        rec.status = RecommendationState.ACKNOWLEDGED
        rec.save()

        # Run again
        recs2 = RecommendationEngine.generate_project_recommendations(self.project)
        self.assertEqual(len(recs2), 1)
        self.assertEqual(Recommendation.objects.filter(project=self.project).count(), 1)
        self.assertEqual(recs2[0].status, RecommendationState.ACKNOWLEDGED)


class RecommendationTenantIsolationTests(TestCase):
    """Verify complete tenant isolation between users."""

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()

        self.user_a = User.objects.create_user(email='user_a@example.com', password='p123')
        self.user_b = User.objects.create_user(email='user_b@example.com', password='p123')
        SubscriptionService.assign_plan(self.user_a, PlanCode.STARTER)
        SubscriptionService.assign_plan(self.user_b, PlanCode.STARTER)

        self.proj_a = Project.objects.create(owner=self.user_a, name='Proj A', website_url='https://proja.com')
        self.proj_b = Project.objects.create(owner=self.user_b, name='Proj B', website_url='https://projb.com')

        self.rec_a = Recommendation.objects.create(
            project=self.proj_a,
            title='Rec A',
            description='Issue A',
            recommended_action='Action A',
            fingerprint='test:a'
        )
        self.rec_b = Recommendation.objects.create(
            project=self.proj_b,
            title='Rec B',
            description='Issue B',
            recommended_action='Action B',
            fingerprint='test:b'
        )

    def test_user_a_cannot_see_user_b_recommendations(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get('/api/seo/recommendations/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in res.data]
        self.assertIn(self.rec_a.id, ids)
        self.assertNotIn(self.rec_b.id, ids)

    def test_user_a_cannot_view_user_b_recommendation_detail(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'/api/seo/recommendations/{self.rec_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_modify_user_b_recommendation(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(f'/api/seo/recommendations/{self.rec_b.id}/', {'status': 'resolved'})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_generate_for_user_b_project(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post('/api/seo/recommendations/generate/', {'project_id': self.proj_b.id})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class RecommendationCeleryTaskTests(TestCase):
    """Test Celery async task execution, error handling, and summary return."""

    def setUp(self):
        SubscriptionService.bootstrap_default_plans()
        self.user = User.objects.create_user(email='celery_rec@example.com', password='p123')
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.project = Project.objects.create(
            owner=self.user,
            name='Celery Project',
            website_url='https://celeryproject.com'
        )

    @patch('apps.seo.services.recommendations.RecommendationEngine.generate_project_recommendations')
    def test_generate_project_recommendations_task_success(self, mock_generate):
        mock_rec = MagicMock()
        mock_generate.return_value = [mock_rec]

        from apps.seo.tasks import generate_project_recommendations_task
        summary = generate_project_recommendations_task(self.project.id)

        self.assertEqual(summary['status'], 'success')
        self.assertEqual(summary['project_id'], self.project.id)
        self.assertEqual(summary['total_generated'], 1)
        mock_generate.assert_called_once_with(self.project)

    def test_generate_task_nonexistent_project_handles_cleanly(self):
        from apps.seo.tasks import generate_project_recommendations_task
        summary = generate_project_recommendations_task(999999)
        self.assertEqual(summary['status'], 'error')
        self.assertIn("not found", summary['message'])


class RecommendationAPITests(TestCase):
    """Test REST API endpoints for recommendations list, filtering, updates, and generation."""

    def setUp(self):
        self.client = APIClient()
        SubscriptionService.bootstrap_default_plans()
        self.user = User.objects.create_user(email='api_rec@example.com', password='p123')
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.client.force_authenticate(user=self.user)

        self.project = Project.objects.create(
            owner=self.user,
            name='API Test Project',
            website_url='https://apitest.com'
        )
        self.rec_crit = Recommendation.objects.create(
            project=self.project,
            source_type=RecommendationSource.CRAWLER,
            category=RecommendationCategory.INDEXING,
            severity=RecommendationSeverity.CRITICAL,
            title='Critical Broken Page',
            description='404 on page',
            recommended_action='Fix link',
            status=RecommendationState.OPEN,
            priority=95,
            fingerprint='fp:1'
        )
        self.rec_high = Recommendation.objects.create(
            project=self.project,
            source_type=RecommendationSource.RANK_TRACKER,
            category=RecommendationCategory.RANKINGS,
            severity=RecommendationSeverity.HIGH,
            title='Ranking Drop',
            description='Dropped 4 spots',
            recommended_action='Improve copy',
            status=RecommendationState.OPEN,
            priority=78,
            fingerprint='fp:2'
        )

    def test_list_and_filter_recommendations(self):
        # List all
        res = self.client.get(f'/api/seo/recommendations/?project_id={self.project.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 2)

        # Filter by severity
        res_sev = self.client.get(f'/api/seo/recommendations/?project_id={self.project.id}&severity=critical')
        self.assertEqual(res_sev.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_sev.data), 1)
        self.assertEqual(res_sev.data[0]['id'], self.rec_crit.id)

        # Filter by category
        res_cat = self.client.get(f'/api/seo/recommendations/?project_id={self.project.id}&category=rankings')
        self.assertEqual(res_cat.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_cat.data), 1)
        self.assertEqual(res_cat.data[0]['id'], self.rec_high.id)

        # Filter by source_type
        res_src = self.client.get(f'/api/seo/recommendations/?project_id={self.project.id}&source_type=crawler')
        self.assertEqual(res_src.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_src.data), 1)
        self.assertEqual(res_src.data[0]['id'], self.rec_crit.id)

    def test_patch_status_lifecycle_and_actions(self):
        # 1. Acknowledge via patch
        res_ack = self.client.patch(f'/api/seo/recommendations/{self.rec_crit.id}/', {'status': 'acknowledged'})
        self.assertEqual(res_ack.status_code, status.HTTP_200_OK)
        self.rec_crit.refresh_from_db()
        self.assertEqual(self.rec_crit.status, RecommendationState.ACKNOWLEDGED)

        # 2. Resolve via custom action
        res_res = self.client.post(f'/api/seo/recommendations/{self.rec_crit.id}/resolve/')
        self.assertEqual(res_res.status_code, status.HTTP_200_OK)
        self.rec_crit.refresh_from_db()
        self.assertEqual(self.rec_crit.status, RecommendationState.RESOLVED)
        self.assertIsNotNone(self.rec_crit.resolved_at)

        # 3. Dismiss via custom action
        res_dis = self.client.post(f'/api/seo/recommendations/{self.rec_high.id}/dismiss/')
        self.assertEqual(res_dis.status_code, status.HTTP_200_OK)
        self.rec_high.refresh_from_db()
        self.assertEqual(self.rec_high.status, RecommendationState.DISMISSED)

    def test_generate_endpoint_synchronous(self):
        res = self.client.post('/api/seo/recommendations/generate/', {'project_id': self.project.id})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data, list)

    @patch('apps.seo.tasks.generate_project_recommendations_task.delay')
    def test_generate_endpoint_async(self, mock_delay):
        res = self.client.post('/api/seo/recommendations/generate/', {
            'project_id': self.project.id,
            'async': True
        })
        self.assertEqual(res.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(res.data['status'], 'queued')
        self.assertEqual(mock_delay.call_count, 1)
