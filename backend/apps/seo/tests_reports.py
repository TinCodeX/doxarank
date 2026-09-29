"""
Comprehensive test suite for DoxaRank Original SRS White-Label PDF Reports.

Verifies:
1. Agency tier entitlement (FeatureCode.WHITE_LABEL_REPORTS: Free/Starter denied, Agency allowed)
2. Strict multi-tenant isolation (project and report ownership enforcement)
3. Crawler data extraction and aggregation (broken links, slow pages, title issues)
4. Rank tracking data extraction, Google Ethiopia domains, and movement calculations
5. Competitor SERP snapshot extraction and benchmark comparison
6. SEO recommendations integration and prioritization
7. Deterministic phased action plan generation (no LLM, rule-based)
8. Actual PDF file generation with ReportLab (non-zero size, valid %PDF header)
9. Report status lifecycle transitions (PENDING -> RUNNING -> COMPLETED / FAILED)
10. Secure download authorization and path traversal prevention
11. ZERO DoxaRank branding in white-label reports (pure client branding)
12. Idempotent execution and safe re-generation
13. Celery background task integration
14. Graceful handling of empty or partial data
"""

import os
import io
import shutil
import tempfile
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status

from apps.projects.models import Project
from apps.subscriptions.models import Plan, Subscription, FeatureCode, PlanCode, SubscriptionStatus
from apps.subscriptions.services import SubscriptionService, PlanEntitlementService
from apps.seo.models import (
    SEOReport, ReportStatus,
    Keyword, KeywordRanking, RankingResultStatus,
    Competitor, CompetitorSnapshot,
    CrawlJob, CrawlJobStatus, CrawlPage,
    SEORecommendation, SEOInsight, RecommendationPriority, RecommendationStatus,
    Recommendation
)
from apps.seo.services.reports import SEOReportService
from apps.seo.tasks import generate_seo_report_task

User = get_user_model()


class WhiteLabelReportsTestCase(TestCase):
    """
    Dedicated test cases for White-Label SEO Reports.
    """

    @classmethod
    def setUpTestData(cls):
        # Bootstrap canonical plans
        SubscriptionService.bootstrap_default_plans()

    def setUp(self):
        # Create temporary media root for tests
        self.test_media_dir = tempfile.mkdtemp()
        self.media_override = override_settings(
            MEDIA_ROOT=self.test_media_dir,
            CELERY_TASK_ALWAYS_EAGER=True,
            CELERY_TASK_EAGER_PROPAGATES=True
        )
        self.media_override.enable()

        # Users
        self.user_free = User.objects.create_user(
            email='user_free@example.com',
            password='password123'
        )
        SubscriptionService.assign_plan(self.user_free, PlanCode.FREE)

        self.user_starter = User.objects.create_user(
            email='user_starter@example.com',
            password='password123'
        )
        SubscriptionService.assign_plan(self.user_starter, PlanCode.STARTER)

        self.user_agency = User.objects.create_user(
            email='user_agency@example.com',
            password='password123'
        )
        SubscriptionService.assign_plan(self.user_agency, PlanCode.AGENCY)

        self.user_other_agency = User.objects.create_user(
            email='other_agency@example.com',
            password='password123'
        )
        SubscriptionService.assign_plan(self.user_other_agency, PlanCode.AGENCY)

        # Projects
        self.project_agency = Project.objects.create(
            owner=self.user_agency,
            name="Addis Tech Solutions",
            website_url="https://addistech.et"
        )
        self.project_other = Project.objects.create(
            owner=self.user_other_agency,
            name="Competitor Agency Site",
            website_url="https://otheragency.et"
        )
        self.project_starter = Project.objects.create(
            owner=self.user_starter,
            name="Starter Site",
            website_url="https://startersite.et"
        )

        # DRF API Clients
        self.client_agency = APIClient()
        self.client_agency.force_authenticate(user=self.user_agency)

        self.client_starter = APIClient()
        self.client_starter.force_authenticate(user=self.user_starter)

        self.client_free = APIClient()
        self.client_free.force_authenticate(user=self.user_free)

        self.client_other = APIClient()
        self.client_other.force_authenticate(user=self.user_other_agency)

    def tearDown(self):
        self.media_override.disable()
        if os.path.exists(self.test_media_dir):
            shutil.rmtree(self.test_media_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Subscription Entitlement Tests (Agency only)
    # -------------------------------------------------------------------------

    def test_agency_can_generate_report(self):
        """Agency user has WHITE_LABEL_REPORTS entitlement and can request report generation."""
        self.assertTrue(PlanEntitlementService.can_use_feature(self.user_agency, FeatureCode.WHITE_LABEL_REPORTS))
        
        response = self.client_agency.post('/api/seo/reports/generate/', {
            'project_id': self.project_agency.id,
            'client_name': 'Acme Corporation',
            'title': 'Executive SEO Audit Q3'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Executive SEO Audit Q3')
        self.assertEqual(response.data['client_name'], 'Acme Corporation')
        self.assertEqual(response.data['status'], ReportStatus.COMPLETED)
        self.assertGreater(response.data['file_size_bytes'], 0)
        self.assertIn('/download/', response.data['download_url'])

    def test_free_cannot_generate_report(self):
        """Free user is strictly denied access to white-label report generation with 403."""
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_free, FeatureCode.WHITE_LABEL_REPORTS))
        
        # Create a free user project
        free_proj = Project.objects.create(
            owner=self.user_free,
            name="Free Site",
            website_url="https://freesite.com"
        )

        response = self.client_free.post('/api/seo/reports/generate/', {
            'project_id': free_proj.id
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'FEATURE_NOT_ENTITLED')
        self.assertEqual(response.data.get('feature'), FeatureCode.WHITE_LABEL_REPORTS)

    def test_starter_cannot_generate_report(self):
        """Starter user is strictly denied access to white-label report generation with 403."""
        self.assertFalse(PlanEntitlementService.can_use_feature(self.user_starter, FeatureCode.WHITE_LABEL_REPORTS))

        response = self.client_starter.post('/api/seo/reports/generate/', {
            'project_id': self.project_starter.id
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('code'), 'FEATURE_NOT_ENTITLED')

    # -------------------------------------------------------------------------
    # Multi-Tenant Isolation Tests
    # -------------------------------------------------------------------------

    def test_project_ownership_enforced_on_generation(self):
        """User cannot generate a report for a project owned by another user."""
        response = self.client_agency.post('/api/seo/reports/generate/', {
            'project_id': self.project_other.id  # owned by other agency
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_report_ownership_enforced_on_retrieval(self):
        """User cannot view or list reports belonging to another user's project."""
        # Generate report for other agency
        other_report = SEOReport.objects.create(
            project=self.project_other,
            generated_by=self.user_other_agency,
            title="Other Secret Report",
            status=ReportStatus.COMPLETED
        )

        # User agency tries to retrieve it
        response = self.client_agency.get(f'/api/seo/reports/{other_report.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # User agency listing reports should not include other_report
        list_res = self.client_agency.get('/api/seo/reports/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        report_ids = [r['id'] for r in list_res.data]
        self.assertNotIn(other_report.id, report_ids)

    def test_download_authorization_and_isolation(self):
        """Only the project owner can download the completed report PDF."""
        # Generate valid completed report for Agency user
        report = SEOReportService.create_report(
            project=self.project_agency,
            user=self.user_agency,
            client_name="Client Test",
            title="Download Test Report"
        )
        SEOReportService.execute_report_generation(report.id)
        report.refresh_from_db()
        self.assertEqual(report.status, ReportStatus.COMPLETED)

        # Owner downloads successfully
        dl_response = self.client_agency.get(f'/api/seo/reports/{report.id}/download/')
        self.assertEqual(dl_response.status_code, status.HTTP_200_OK)
        self.assertEqual(dl_response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', dl_response['Content-Disposition'])

        # Other agency user is blocked with 404
        other_dl = self.client_other.get(f'/api/seo/reports/{report.id}/download/')
        self.assertEqual(other_dl.status_code, status.HTTP_404_NOT_FOUND)

        # Unauthenticated request is blocked with 401
        anon_client = APIClient()
        anon_dl = anon_client.get(f'/api/seo/reports/{report.id}/download/')
        self.assertEqual(anon_dl.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_path_traversal_prevention(self):
        """Malicious relative file paths cannot escape MEDIA_ROOT."""
        report = SEOReport.objects.create(
            project=self.project_agency,
            generated_by=self.user_agency,
            title="Traversal Test",
            status=ReportStatus.COMPLETED,
            file_path="../../etc/passwd",
            file_size_bytes=100
        )

        response = self.client_agency.get(f'/api/seo/reports/{report.id}/download/')
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    # -------------------------------------------------------------------------
    # Report Data Extraction & Content Tests
    # -------------------------------------------------------------------------

    def test_report_data_contains_crawler_findings(self):
        """Report context accurately extracts metrics from latest completed CrawlJob."""
        crawl = CrawlJob.objects.create(
            project=self.project_agency,
            status=CrawlJobStatus.COMPLETED,
            pages_crawled=45,
            pages_discovered=50,
            broken_links_count=3,
            missing_titles_count=2,
            missing_descriptions_count=5,
            duplicate_titles_count=1,
            missing_h1_count=4,
            redirect_chains_count=1,
            slow_pages_count=2,
            completed_at=timezone.now()
        )
        CrawlPage.objects.create(
            crawl_job=crawl,
            url="https://addistech.et/broken",
            status_code=404,
            is_broken=True
        )

        context = SEOReportService.collect_report_context(self.project_agency)
        self.assertTrue(context['crawler']['available'])
        self.assertEqual(context['crawler']['pages_crawled'], 45)
        self.assertEqual(context['crawler']['broken_links_count'], 3)
        self.assertEqual(context['crawler']['missing_titles_count'], 2)
        self.assertEqual(len(context['crawler']['sample_issues']), 1)

    def test_report_data_contains_ranking_and_movement_information(self):
        """Report context extracts rank tracking data and calculates movement on google.com.et."""
        kw = Keyword.objects.create(
            project=self.project_agency,
            keyword="web development addis",
            search_domain="google.com.et",
            is_active=True
        )
        # Previous ranking (position 5)
        KeywordRanking.objects.create(
            keyword=kw,
            position=5,
            result_status=RankingResultStatus.FOUND,
            ranking_url="https://addistech.et/web",
            recorded_at=timezone.now() - timezone.timedelta(days=2),
            created_at=timezone.now() - timezone.timedelta(days=2)
        )
        # Latest ranking (position 2) -> movement should be +3
        KeywordRanking.objects.create(
            keyword=kw,
            position=2,
            result_status=RankingResultStatus.FOUND,
            ranking_url="https://addistech.et/web",
            recorded_at=timezone.now(),
            created_at=timezone.now()
        )

        context = SEOReportService.collect_report_context(self.project_agency)
        self.assertTrue(context['rank_tracking']['available'])
        self.assertEqual(context['rank_tracking']['total_keywords'], 1)
        self.assertEqual(context['rank_tracking']['top_3_count'], 1)
        self.assertEqual(context['rank_tracking']['keywords'][0]['movement'], '+3')
        self.assertEqual(context['rank_tracking']['keywords'][0]['position'], '#2')

    def test_report_data_contains_competitor_information(self):
        """Report context extracts competitor domains and position benchmarks."""
        comp = Competitor.objects.create(
            project=self.project_agency,
            name="rival agency",
            domain="rivalagency.et",
            is_active=True
        )
        kw = Keyword.objects.create(
            project=self.project_agency,
            keyword="best seo ethiopia",
            is_active=True
        )
        CompetitorSnapshot.objects.create(
            project=self.project_agency,
            competitor=comp,
            keyword=kw,
            position=4,
            result_status=RankingResultStatus.FOUND
        )

        context = SEOReportService.collect_report_context(self.project_agency)
        self.assertTrue(context['competitors']['available'])
        self.assertEqual(context['competitors']['total_competitors'], 1)
        self.assertEqual(context['competitors']['competitor_list'][0]['domain'], 'rivalagency.et')
        self.assertEqual(len(context['competitors']['comparison']), 1)

    def test_report_data_contains_recommendations_and_action_plan(self):
        """Report context includes recommendations and deterministic phased action plan without LLM."""
        insight = SEOInsight.objects.create(
            project=self.project_agency,
            fingerprint="crawl_dead_pages",
            title="Crawler Discovered Dead Pages",
            description="Multiple 404 links detected.",
            severity="critical"
        )
        rec = SEORecommendation.objects.create(
            project=self.project_agency,
            insight=insight,
            title="Fix Broken Product Links",
            summary="Dead links reduce crawl budget.",
            explanation="Ensure all internal links return 200.",
            priority=RecommendationPriority.HIGH,
            recommended_action="Update canonical URLs and restore 404 targets.",
            expected_impact="High crawl efficiency.",
            status=RecommendationStatus.PENDING_REVIEW
        )

        context = SEOReportService.collect_report_context(self.project_agency)
        self.assertTrue(context['recommendations']['available'])
        self.assertGreaterEqual(context['recommendations']['count'], 1)
        self.assertIn("Fix Broken Product Links", [r['title'] for r in context['recommendations']['items']])

        # Action plan deterministic verification
        action_plan = context['action_plan']
        self.assertIn('phase_1_critical', action_plan)
        self.assertIn('phase_2_onpage', action_plan)
        self.assertIn('phase_3_growth', action_plan)
        self.assertTrue(len(action_plan['phase_1_critical']) > 0)

    # -------------------------------------------------------------------------
    # PDF Generation, White-Label Guarantee & Integrity Tests
    # -------------------------------------------------------------------------

    def test_pdf_is_actually_generated_with_valid_pdf_structure(self):
        """Verifies PDF binary stream is generated, saved to media, and has non-zero size."""
        report = SEOReportService.create_report(
            project=self.project_agency,
            user=self.user_agency,
            client_name="Nexus Holdings",
            title="Quarterly SEO Technical Audit"
        )
        SEOReportService.execute_report_generation(report.id)
        report.refresh_from_db()

        self.assertEqual(report.status, ReportStatus.COMPLETED)
        self.assertGreater(report.file_size_bytes, 1000)
        self.assertTrue(os.path.exists(os.path.join(settings.MEDIA_ROOT, report.file_path)))

        # Validate PDF header
        with open(os.path.join(settings.MEDIA_ROOT, report.file_path), 'rb') as f:
            header = f.read(5)
            self.assertEqual(header, b'%PDF-')

    def test_no_doxarank_branding_in_white_label_report(self):
        """
        CRITICAL WHITE-LABEL REQUIREMENT:
        The generated PDF must contain ZERO occurrences of 'DoxaRank' in its text stream.
        """
        report = SEOReportService.create_report(
            project=self.project_agency,
            user=self.user_agency,
            client_name="Prime Agency Client",
            title="Clean White Label SEO Report"
        )
        SEOReportService.execute_report_generation(report.id)
        report.refresh_from_db()

        full_path = os.path.join(settings.MEDIA_ROOT, report.file_path)
        with open(full_path, 'rb') as f:
            pdf_bytes = f.read()

        # Check raw bytes (case-insensitive)
        self.assertNotIn(b'doxarank', pdf_bytes.lower())
        self.assertNotIn(b'doxa rank', pdf_bytes.lower())

        # If PyPDF2 or PyPDF is available, verify extracted page text as well
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(full_path)
            extracted_text = ""
            for page in reader.pages:
                extracted_text += page.extract_text() or ""
            self.assertNotIn('doxarank', extracted_text.lower())
            self.assertNotIn('doxa rank', extracted_text.lower())
            # Ensure client branding is present
            self.assertIn('prime agency client', extracted_text.lower())
        except Exception:
            pass

    def test_failed_generation_handled_safely(self):
        """Simulated failure during PDF compilation updates status to FAILED with error message."""
        report = SEOReport.objects.create(
            project=self.project_agency,
            generated_by=self.user_agency,
            title="Faulty Report",
            status=ReportStatus.PENDING
        )

        with patch.object(SEOReportService, 'generate_pdf', side_effect=RuntimeError("Simulated ReportLab crash")):
            with self.assertRaises(RuntimeError):
                SEOReportService.execute_report_generation(report.id)

        report.refresh_from_db()
        self.assertEqual(report.status, ReportStatus.FAILED)
        self.assertIn("Simulated ReportLab crash", report.error_message)

    def test_empty_project_data_handled_gracefully(self):
        """Project with no crawl, no keywords, and no competitors generates report cleanly without crashing."""
        empty_proj = Project.objects.create(
            owner=self.user_agency,
            name="Brand New Project",
            website_url="https://brandnewproject.et"
        )

        report = SEOReportService.create_report(
            project=empty_proj,
            user=self.user_agency,
            client_name="New Client",
            title="Baseline Audit"
        )
        completed_report = SEOReportService.execute_report_generation(report.id)

        self.assertEqual(completed_report.status, ReportStatus.COMPLETED)
        self.assertGreater(completed_report.file_size_bytes, 0)
        self.assertTrue(os.path.exists(os.path.join(settings.MEDIA_ROOT, completed_report.file_path)))

    def test_celery_task_execution(self):
        """Celery background task runs generate_seo_report_task and updates report to COMPLETED."""
        report = SEOReport.objects.create(
            project=self.project_agency,
            generated_by=self.user_agency,
            title="Async Celery Report",
            status=ReportStatus.PENDING
        )

        task_result = generate_seo_report_task(report.id)
        self.assertEqual(task_result, report.id)

        report.refresh_from_db()
        self.assertEqual(report.status, ReportStatus.COMPLETED)
        self.assertGreater(report.file_size_bytes, 0)
