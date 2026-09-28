"""
Technical SEO Crawler — Comprehensive Test Suite
=================================================

Covers:
  - Models: CrawlJob lifecycle, CrawlPage creation, ownership, relationships
  - Subscription: Free blocked, Starter allowed, Agency allowed
  - API: authentication, project ownership, launch, list, detail, pages, cross-tenant
  - Crawler service: URL normalization, SSRF protection, issue detection
  - Celery task: enqueue, completion, failure handling
  - Security: localhost, RFC1918, metadata, IPv6, redirect-to-private blocked

All external network calls are mocked via unittest.mock.
Authentication follows the project pattern: APIClient.force_authenticate().
"""

import socket
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.seo.models import CrawlJob, CrawlJobStatus, CrawlPage
from apps.seo.services.technical_crawler import (
    TechnicalCrawlerService,
    _is_ip_blocked,
    _is_hostname_safe,
    detect_page_issues,
    extract_page_data,
    normalize_url,
    is_same_domain,
    has_crawlable_extension,
    validate_crawl_target,
)
from apps.subscriptions.services import SubscriptionService

User = get_user_model()


# =============================================================================
# MODEL TESTS
# =============================================================================

class CrawlJobModelTests(TestCase):
    """Tests for the CrawlJob model — creation, lifecycle, ownership."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='crawlmodel@doxarank.com',
            password='TestPass123!',
            first_name='Crawl',
            last_name='Tester',
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Test Site',
            website_url='https://test.example.com',
        )

    def test_crawl_job_creation_defaults(self):
        """CrawlJob is created with correct default field values."""
        job = CrawlJob.objects.create(project=self.project)
        self.assertEqual(job.status, CrawlJobStatus.PENDING)
        self.assertEqual(job.max_pages, 100)
        self.assertEqual(job.max_depth, 3)
        self.assertTrue(job.respect_robots_txt)
        self.assertEqual(job.pages_crawled, 0)
        self.assertEqual(job.broken_links_count, 0)
        self.assertIsNone(job.started_at)
        self.assertIsNone(job.completed_at)
        self.assertIsNone(job.celery_task_id)
        self.assertIsNone(job.error_message)
        self.assertEqual(job.crawl_metadata, {})

    def test_crawl_job_ownership_chain(self):
        """CrawlJob is linked to the correct project and owner."""
        job = CrawlJob.objects.create(project=self.project)
        self.assertEqual(job.project, self.project)
        self.assertEqual(job.project.owner, self.user)

    def test_crawl_job_status_transitions(self):
        """Manual status transitions work correctly."""
        job = CrawlJob.objects.create(project=self.project)
        self.assertEqual(job.status, CrawlJobStatus.PENDING)

        job.status = CrawlJobStatus.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=['status', 'started_at', 'updated_at'])
        job.refresh_from_db()
        self.assertEqual(job.status, CrawlJobStatus.RUNNING)

        job.status = CrawlJobStatus.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'completed_at', 'updated_at'])
        job.refresh_from_db()
        self.assertEqual(job.status, CrawlJobStatus.COMPLETED)

    def test_crawl_job_duration_seconds_property(self):
        """duration_seconds returns correct value when both timestamps are set."""
        job = CrawlJob.objects.create(project=self.project)
        self.assertIsNone(job.duration_seconds)  # No timestamps yet

        from datetime import timedelta
        now = timezone.now()
        job.started_at = now - timedelta(seconds=42)
        job.completed_at = now
        job.save(update_fields=['started_at', 'completed_at', 'updated_at'])
        self.assertAlmostEqual(job.duration_seconds, 42, delta=1)

    def test_crawl_job_str(self):
        """CrawlJob __str__ returns a meaningful representation."""
        job = CrawlJob.objects.create(project=self.project)
        s = str(job)
        self.assertIn('CrawlJob', s)
        self.assertIn('Test Site', s)

    def test_crawl_page_creation_and_relationship(self):
        """CrawlPage can be created and is linked to its parent CrawlJob."""
        job = CrawlJob.objects.create(project=self.project, status=CrawlJobStatus.RUNNING)
        page = CrawlPage.objects.create(
            crawl_job=job,
            url='https://test.example.com/page',
            status_code=200,
            depth=1,
        )
        self.assertEqual(page.crawl_job, job)
        self.assertEqual(job.pages.count(), 1)
        self.assertFalse(page.is_broken)
        self.assertFalse(page.is_slow)
        self.assertEqual(page.issues, [])

    def test_crawl_page_is_broken_flag(self):
        """CrawlPage is_broken can be set correctly."""
        job = CrawlJob.objects.create(project=self.project)
        page = CrawlPage.objects.create(
            crawl_job=job,
            url='https://test.example.com/missing',
            status_code=404,
            is_broken=True,
            depth=0,
        )
        self.assertTrue(page.is_broken)

    def test_crawl_job_cascade_delete(self):
        """Deleting a CrawlJob cascades and deletes associated CrawlPages."""
        job = CrawlJob.objects.create(project=self.project)
        CrawlPage.objects.create(crawl_job=job, url='https://test.example.com/', status_code=200, depth=0)
        self.assertEqual(CrawlPage.objects.count(), 1)
        job.delete()
        self.assertEqual(CrawlPage.objects.count(), 0)

    def test_project_cascade_deletes_crawl_jobs(self):
        """Deleting a Project cascades and deletes all associated CrawlJobs."""
        CrawlJob.objects.create(project=self.project)
        self.assertEqual(CrawlJob.objects.count(), 1)
        self.project.delete()
        self.assertEqual(CrawlJob.objects.count(), 0)


# =============================================================================
# SUBSCRIPTION / ENTITLEMENT TESTS
# =============================================================================

class CrawlSubscriptionTests(TestCase):
    """
    Verify that the TECHNICAL_CRAWLER feature gate works correctly.
    Free users are blocked. Starter and Agency users are allowed.
    """

    def setUp(self):
        self.client = APIClient()

        # Create three users — Free, Starter, Agency
        self.free_user = User.objects.create_user(
            email='crawl_free@doxarank.com', password='Pass123!',
            first_name='Free', last_name='User',
        )
        self.starter_user = User.objects.create_user(
            email='crawl_starter@doxarank.com', password='Pass123!',
            first_name='Starter', last_name='User',
        )
        self.agency_user = User.objects.create_user(
            email='crawl_agency@doxarank.com', password='Pass123!',
            first_name='Agency', last_name='User',
        )

        SubscriptionService.bootstrap_default_plans()
        SubscriptionService.assign_plan(self.free_user, 'FREE')
        SubscriptionService.assign_plan(self.starter_user, 'STARTER')
        SubscriptionService.assign_plan(self.agency_user, 'AGENCY')

        self.free_project = Project.objects.create(
            owner=self.free_user, name='Free Site', website_url='https://free.example.com'
        )
        self.starter_project = Project.objects.create(
            owner=self.starter_user, name='Starter Site', website_url='https://starter.example.com'
        )
        self.agency_project = Project.objects.create(
            owner=self.agency_user, name='Agency Site', website_url='https://agency.example.com'
        )

    def test_free_user_cannot_launch_crawl(self):
        """Free plan users receive 403 when launching a crawl."""
        self.client.force_authenticate(user=self.free_user)
        r = self.client.post('/api/seo/crawler/launch/', {
            'project_id': self.free_project.id,
        }, format='json')
        self.assertEqual(r.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_starter_user_can_launch_crawl(self):
        """Starter plan users can launch a crawl (response is 202 Accepted)."""
        self.client.force_authenticate(user=self.starter_user)
        with patch('apps.seo.tasks.run_technical_crawl.delay') as mock_task:
            mock_task.return_value = MagicMock(id='mock-task-id')
            r = self.client.post('/api/seo/crawler/launch/', {
                'project_id': self.starter_project.id,
            }, format='json')
        self.assertIn(r.status_code, [http_status.HTTP_202_ACCEPTED, http_status.HTTP_200_OK])

    def test_agency_user_can_launch_crawl(self):
        """Agency plan users can launch a crawl."""
        self.client.force_authenticate(user=self.agency_user)
        with patch('apps.seo.tasks.run_technical_crawl.delay') as mock_task:
            mock_task.return_value = MagicMock(id='mock-task-id')
            r = self.client.post('/api/seo/crawler/launch/', {
                'project_id': self.agency_project.id,
            }, format='json')
        self.assertIn(r.status_code, [http_status.HTTP_202_ACCEPTED, http_status.HTTP_200_OK])


# =============================================================================
# API ENDPOINT TESTS
# =============================================================================

class CrawlJobAPITests(TestCase):
    """Tests for /api/seo/crawler/ and /api/seo/crawler-pages/ endpoints."""

    def setUp(self):
        self.client = APIClient()

        self.user_a = User.objects.create_user(
            email='crawlapi_a@doxarank.com', password='Pass123!',
            first_name='A', last_name='User',
        )
        self.user_b = User.objects.create_user(
            email='crawlapi_b@doxarank.com', password='Pass123!',
            first_name='B', last_name='User',
        )

        SubscriptionService.bootstrap_default_plans()
        SubscriptionService.assign_plan(self.user_a, 'STARTER')
        SubscriptionService.assign_plan(self.user_b, 'STARTER')

        self.project_a = Project.objects.create(
            owner=self.user_a, name='Site A', website_url='https://sitea.example.com'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b, name='Site B', website_url='https://siteb.example.com'
        )

        self.job_a = CrawlJob.objects.create(
            project=self.project_a,
            status=CrawlJobStatus.COMPLETED,
            pages_crawled=5,
        )
        CrawlPage.objects.create(
            crawl_job=self.job_a,
            url='https://sitea.example.com/',
            status_code=200,
            depth=0,
        )
        CrawlPage.objects.create(
            crawl_job=self.job_a,
            url='https://sitea.example.com/broken',
            status_code=404,
            is_broken=True,
            depth=1,
        )

        self.job_b = CrawlJob.objects.create(
            project=self.project_b,
            status=CrawlJobStatus.COMPLETED,
        )

    # --- Authentication ---

    def test_list_crawl_jobs_requires_authentication(self):
        """Unauthenticated requests to /api/seo/crawler/ return 401."""
        r = self.client.get('/api/seo/crawler/')
        self.assertEqual(r.status_code, http_status.HTTP_401_UNAUTHORIZED)

    def test_list_crawl_pages_requires_authentication(self):
        """Unauthenticated requests to /api/seo/crawler-pages/ return 401."""
        r = self.client.get('/api/seo/crawler-pages/')
        self.assertEqual(r.status_code, http_status.HTTP_401_UNAUTHORIZED)

    # --- List / Retrieve ---

    def test_authenticated_user_sees_only_own_crawl_jobs(self):
        """User A sees only their own crawl jobs."""
        self.client.force_authenticate(user=self.user_a)
        r = self.client.get('/api/seo/crawler/')
        self.assertEqual(r.status_code, http_status.HTTP_200_OK)
        ids = [j['id'] for j in r.data]
        self.assertIn(self.job_a.id, ids)
        self.assertNotIn(self.job_b.id, ids)

    def test_retrieve_own_crawl_job(self):
        """User A can retrieve their own crawl job detail."""
        self.client.force_authenticate(user=self.user_a)
        r = self.client.get(f'/api/seo/crawler/{self.job_a.id}/')
        self.assertEqual(r.status_code, http_status.HTTP_200_OK)
        self.assertEqual(r.data['id'], self.job_a.id)

    def test_cannot_retrieve_other_users_crawl_job(self):
        """User A cannot access User B's crawl job — returns 404."""
        self.client.force_authenticate(user=self.user_a)
        r = self.client.get(f'/api/seo/crawler/{self.job_b.id}/')
        self.assertEqual(r.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_filter_crawl_jobs_by_project_id(self):
        """Filtering by project_id only returns jobs for that project."""
        self.client.force_authenticate(user=self.user_a)
        r = self.client.get(f'/api/seo/crawler/?project_id={self.project_a.id}')
        self.assertEqual(r.status_code, http_status.HTTP_200_OK)
        self.assertTrue(all(j['project'] == self.project_a.id for j in r.data))

    # --- Pages endpoint ---

    def test_crawl_pages_endpoint_filters_by_job(self):
        """Pages endpoint with crawl_job_id returns only that job's pages."""
        self.client.force_authenticate(user=self.user_a)
        r = self.client.get(f'/api/seo/crawler-pages/?crawl_job_id={self.job_a.id}')
        self.assertEqual(r.status_code, http_status.HTTP_200_OK)
        self.assertEqual(len(r.data), 2)

    def test_crawl_pages_endpoint_filter_broken(self):
        """is_broken=true filter returns only broken pages."""
        self.client.force_authenticate(user=self.user_a)
        r = self.client.get(f'/api/seo/crawler-pages/?crawl_job_id={self.job_a.id}&is_broken=true')
        self.assertEqual(r.status_code, http_status.HTTP_200_OK)
        self.assertTrue(all(p['is_broken'] for p in r.data))

    def test_cannot_see_other_users_pages(self):
        """User A cannot see pages from User B's crawl job."""
        self.client.force_authenticate(user=self.user_a)
        r = self.client.get(f'/api/seo/crawler-pages/?crawl_job_id={self.job_b.id}')
        self.assertEqual(r.status_code, http_status.HTTP_200_OK)
        # Queryset filters by owner — should return empty
        self.assertEqual(len(r.data), 0)

    # --- Launch endpoint ---

    def test_launch_crawl_creates_crawl_job(self):
        """POST /api/seo/crawler/launch/ creates a CrawlJob and returns 202."""
        self.client.force_authenticate(user=self.user_a)
        with patch('apps.seo.tasks.run_technical_crawl.delay') as mock_task:
            mock_task.return_value = MagicMock(id='abc-123')
            r = self.client.post('/api/seo/crawler/launch/', {
                'project_id': self.project_a.id,
                'max_pages': 50,
                'max_depth': 2,
            }, format='json')
        self.assertIn(r.status_code, [http_status.HTTP_202_ACCEPTED, http_status.HTTP_200_OK])
        self.assertIn('crawl_job', r.data)

    def test_launch_crawl_for_other_users_project_returns_404(self):
        """Cannot launch a crawl for another user's project."""
        self.client.force_authenticate(user=self.user_a)
        with patch('apps.seo.tasks.run_technical_crawl.delay'):
            r = self.client.post('/api/seo/crawler/launch/', {
                'project_id': self.project_b.id,
            }, format='json')
        self.assertEqual(r.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_launch_crawl_blocked_when_already_running(self):
        """Returns 409 if there is already a PENDING/RUNNING crawl for the project."""
        self.client.force_authenticate(user=self.user_a)
        # Mark job_a as RUNNING (simulating an active crawl)
        self.job_a.status = CrawlJobStatus.RUNNING
        self.job_a.save(update_fields=['status', 'updated_at'])
        r = self.client.post('/api/seo/crawler/launch/', {
            'project_id': self.project_a.id,
        }, format='json')
        self.assertEqual(r.status_code, http_status.HTTP_409_CONFLICT)

    def test_launch_max_pages_validation(self):
        """max_pages of 0 is rejected by the serializer."""
        self.client.force_authenticate(user=self.user_a)
        r = self.client.post('/api/seo/crawler/launch/', {
            'project_id': self.project_a.id,
            'max_pages': 0,
        }, format='json')
        self.assertEqual(r.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_serializer_returns_project_name_and_url(self):
        """CrawlJob serializer includes project_name and project_website_url."""
        self.client.force_authenticate(user=self.user_a)
        r = self.client.get(f'/api/seo/crawler/{self.job_a.id}/')
        self.assertEqual(r.status_code, http_status.HTTP_200_OK)
        self.assertIn('project_name', r.data)
        self.assertIn('project_website_url', r.data)
        self.assertEqual(r.data['project_name'], 'Site A')


# =============================================================================
# SSRF SECURITY TESTS
# =============================================================================

class SSRFSecurityTests(TestCase):
    """
    Tests that the SSRF protection layer in TechnicalCrawlerService
    correctly blocks all private / reserved network targets.
    """

    def test_localhost_ipv4_is_blocked(self):
        """127.0.0.1 is always blocked."""
        self.assertTrue(_is_ip_blocked('127.0.0.1'))

    def test_localhost_range_is_blocked(self):
        """Full 127.0.0.0/8 loopback range is blocked."""
        self.assertTrue(_is_ip_blocked('127.255.255.255'))

    def test_rfc1918_10x_is_blocked(self):
        """10.0.0.0/8 private network is blocked."""
        self.assertTrue(_is_ip_blocked('10.0.0.1'))
        self.assertTrue(_is_ip_blocked('10.255.255.255'))

    def test_rfc1918_172_is_blocked(self):
        """172.16.0.0/12 private network is blocked."""
        self.assertTrue(_is_ip_blocked('172.16.0.1'))
        self.assertTrue(_is_ip_blocked('172.31.255.255'))

    def test_rfc1918_192_is_blocked(self):
        """192.168.0.0/16 private network is blocked."""
        self.assertTrue(_is_ip_blocked('192.168.0.1'))
        self.assertTrue(_is_ip_blocked('192.168.255.255'))

    def test_link_local_is_blocked(self):
        """169.254.0.0/16 link-local range is blocked."""
        self.assertTrue(_is_ip_blocked('169.254.0.1'))
        self.assertTrue(_is_ip_blocked('169.254.169.254'))  # Cloud metadata

    def test_ipv6_loopback_is_blocked(self):
        """IPv6 loopback ::1 is blocked."""
        self.assertTrue(_is_ip_blocked('::1'))

    def test_ipv6_link_local_is_blocked(self):
        """IPv6 link-local fe80::/10 is blocked."""
        self.assertTrue(_is_ip_blocked('fe80::1'))

    def test_ipv6_ula_is_blocked(self):
        """IPv6 unique-local fc00::/7 is blocked."""
        self.assertTrue(_is_ip_blocked('fc00::1'))

    def test_ipv4_mapped_loopback_is_blocked(self):
        """IPv4-mapped IPv6 loopback ::ffff:127.0.0.1 is blocked."""
        self.assertTrue(_is_ip_blocked('::ffff:127.0.0.1'))

    def test_public_ip_is_allowed(self):
        """A real public IP address is not blocked."""
        self.assertFalse(_is_ip_blocked('8.8.8.8'))
        self.assertFalse(_is_ip_blocked('1.1.1.1'))

    def test_validate_crawl_target_blocks_non_http_scheme(self):
        """Only http/https schemes are allowed; file://, ftp://, etc. are rejected."""
        with self.assertRaises(ValueError):
            validate_crawl_target('file:///etc/passwd')
        with self.assertRaises(ValueError):
            validate_crawl_target('ftp://example.com')

    def test_validate_crawl_target_blocks_localhost_url(self):
        """localhost URL is rejected at validate_crawl_target."""
        with patch('apps.seo.services.technical_crawler.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, None, None, None, ('127.0.0.1', 0))]
            with self.assertRaises(ValueError):
                validate_crawl_target('http://localhost/')

    def test_validate_crawl_target_blocks_private_ip_url(self):
        """Private IP URL is rejected at validate_crawl_target."""
        with patch('apps.seo.services.technical_crawler.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, None, None, None, ('192.168.1.1', 0))]
            with self.assertRaises(ValueError):
                validate_crawl_target('http://internal.corp/')

    def test_validate_crawl_target_blocks_metadata_endpoint(self):
        """Cloud metadata IP URL is rejected."""
        with self.assertRaises(ValueError):
            validate_crawl_target('http://169.254.169.254/latest/meta-data/')

    def test_redirect_to_private_ip_blocked(self):
        """DNS resolving to a private IP raises ValueError."""
        with patch('apps.seo.services.technical_crawler.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, None, None, None, ('10.0.0.1', 0))]
            with self.assertRaises(ValueError):
                _is_hostname_safe('internal.evil.com')

    def test_invalid_url_is_rejected(self):
        """Malformed URL is rejected cleanly."""
        with self.assertRaises(ValueError):
            validate_crawl_target('not_a_url_at_all')


# =============================================================================
# URL NORMALIZATION TESTS
# =============================================================================

class URLNormalizationTests(TestCase):
    """Tests for normalize_url, is_same_domain, has_crawlable_extension."""

    def test_normalize_url_strips_fragment(self):
        """URL fragments are stripped."""
        result = normalize_url('https://example.com/page#anchor', 'https://example.com/')
        self.assertEqual(result, 'https://example.com/page')

    def test_normalize_url_resolves_relative(self):
        """Relative URLs are resolved against the base."""
        result = normalize_url('/about', 'https://example.com/')
        self.assertEqual(result, 'https://example.com/about')

    def test_normalize_url_rejects_javascript_scheme(self):
        """javascript: URLs return None."""
        result = normalize_url('javascript:void(0)', 'https://example.com/')
        self.assertIsNone(result)

    def test_normalize_url_rejects_mailto(self):
        """mailto: URLs return None."""
        result = normalize_url('mailto:test@example.com', 'https://example.com/')
        self.assertIsNone(result)

    def test_normalize_url_returns_none_for_empty(self):
        """Empty input returns None."""
        result = normalize_url('', 'https://example.com/')
        self.assertIsNone(result)

    def test_is_same_domain_matches_exact(self):
        """Exact same domain matches."""
        self.assertTrue(is_same_domain('https://example.com/page', 'https://example.com/'))

    def test_is_same_domain_www_equivalence(self):
        """www.example.com and example.com are treated as the same domain."""
        self.assertTrue(is_same_domain('https://www.example.com/page', 'https://example.com/'))
        self.assertTrue(is_same_domain('https://example.com/page', 'https://www.example.com/'))

    def test_is_same_domain_different_domains(self):
        """Different domains do not match."""
        self.assertFalse(is_same_domain('https://external.com/page', 'https://example.com/'))

    def test_has_crawlable_extension_html(self):
        """HTML pages (no extension or .html) are crawlable."""
        self.assertTrue(has_crawlable_extension('https://example.com/page'))
        self.assertTrue(has_crawlable_extension('https://example.com/page.html'))

    def test_has_crawlable_extension_images(self):
        """Image files are not crawlable."""
        self.assertFalse(has_crawlable_extension('https://example.com/image.jpg'))
        self.assertFalse(has_crawlable_extension('https://example.com/image.png'))

    def test_has_crawlable_extension_css_js(self):
        """CSS and JS files are not crawlable."""
        self.assertFalse(has_crawlable_extension('https://example.com/style.css'))
        self.assertFalse(has_crawlable_extension('https://example.com/app.js'))


# =============================================================================
# SEO DATA EXTRACTION TESTS
# =============================================================================

class SEOExtractionTests(TestCase):
    """Tests for extract_page_data and detect_page_issues functions."""

    BASE = 'https://example.com/'

    def _make_page(self, html: str, status: int = 200, time_ms: float = 500.0):
        return extract_page_data(
            url=self.BASE,
            final_url=self.BASE,
            status_code=status,
            response_time_ms=time_ms,
            depth=0,
            redirect_chain=[],
            html_text=html,
            base_domain=self.BASE,
        )

    def test_extract_title(self):
        """Title tag is extracted."""
        page = self._make_page('<html><head><title>Hello World</title></head><body></body></html>')
        self.assertEqual(page.title, 'Hello World')

    def test_missing_title_detected(self):
        """Missing title is detected and flagged."""
        page = self._make_page('<html><head></head><body><h1>Test</h1></body></html>')
        self.assertIsNone(page.title)
        issues = detect_page_issues(page)
        types = [i.issue_type for i in issues]
        self.assertIn('missing_title', types)

    def test_extract_meta_description(self):
        """Meta description is extracted."""
        html = '<html><head><meta name="description" content="My description"></head><body></body></html>'
        page = self._make_page(html)
        self.assertEqual(page.meta_description, 'My description')

    def test_missing_meta_description_detected(self):
        """Missing meta description is flagged."""
        page = self._make_page('<html><head><title>Test</title></head><body><h1>Hi</h1></body></html>')
        issues = detect_page_issues(page)
        types = [i.issue_type for i in issues]
        self.assertIn('missing_meta_description', types)

    def test_extract_h1_count(self):
        """H1 count is extracted correctly."""
        page = self._make_page('<html><body><h1>First</h1><h1>Second</h1></body></html>')
        self.assertEqual(page.h1_count, 2)

    def test_missing_h1_detected(self):
        """Missing H1 is flagged."""
        page = self._make_page('<html><head><title>Test</title></head><body></body></html>')
        issues = detect_page_issues(page)
        types = [i.issue_type for i in issues]
        self.assertIn('missing_h1', types)

    def test_multiple_h1_detected(self):
        """Multiple H1s are flagged as a notice."""
        page = self._make_page('<html><body><h1>A</h1><h1>B</h1></body></html>')
        issues = detect_page_issues(page)
        types = [i.issue_type for i in issues]
        self.assertIn('multiple_h1', types)

    def test_image_alt_missing_detected(self):
        """Images missing alt attributes are counted."""
        html = '<html><body><img src="a.jpg"><img src="b.jpg" alt="ok"></body></html>'
        page = self._make_page(html)
        self.assertEqual(page.images_count, 2)
        self.assertEqual(page.images_missing_alt_count, 1)
        issues = detect_page_issues(page)
        types = [i.issue_type for i in issues]
        self.assertIn('images_missing_alt', types)

    def test_broken_page_detected(self):
        """4xx pages are flagged as broken."""
        page = self._make_page('', status=404)
        self.assertTrue(page.is_broken)
        issues = detect_page_issues(page)
        types = [i.issue_type for i in issues]
        self.assertIn('broken_page', types)

    def test_slow_page_detected(self):
        """Pages over 3000ms threshold are flagged as slow."""
        page = self._make_page(
            '<html><body><h1>Slow</h1></body></html>',
            time_ms=3500.0
        )
        self.assertTrue(page.is_slow)
        issues = detect_page_issues(page)
        types = [i.issue_type for i in issues]
        self.assertIn('slow_page', types)

    def test_redirect_chain_flagged(self):
        """Redirect chains are detected and flagged."""
        page = extract_page_data(
            url='http://example.com/',
            final_url='https://example.com/',
            status_code=200,
            response_time_ms=300,
            depth=0,
            redirect_chain=['http://example.com/'],
            html_text='<html><body><h1>OK</h1></body></html>',
            base_domain='https://example.com/',
        )
        self.assertTrue(page.has_redirect)
        issues = detect_page_issues(page)
        types = [i.issue_type for i in issues]
        self.assertIn('redirect_chain', types)

    def test_internal_and_external_link_count(self):
        """Internal and external links are discovered and counted separately."""
        html = '''
        <html><body>
          <a href="/page1">Page 1</a>
          <a href="/page2">Page 2</a>
          <a href="https://external.com">External</a>
        </body></html>
        '''
        page = self._make_page(html)
        self.assertEqual(page.internal_links_count, 2)
        self.assertEqual(page.external_links_count, 1)

    def test_no_critical_issues_on_healthy_page(self):
        """A page with all required SEO elements has no critical issues."""
        html = '''
        <html>
          <head>
            <title>Great Page</title>
            <meta name="description" content="This is a great page">
            <link rel="canonical" href="https://example.com/">
          </head>
          <body>
            <h1>Great Page</h1>
            <p>Content here</p>
          </body>
        </html>
        '''
        page = self._make_page(html)
        issues = detect_page_issues(page)
        critical = [i for i in issues if i.severity == 'critical']
        self.assertEqual(len(critical), 0)


# =============================================================================
# CELERY TASK TESTS
# =============================================================================

class CrawlCeleryTaskTests(TestCase):
    """Tests for the run_technical_crawl Celery task."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='crawltask@doxarank.com', password='Pass123!',
            first_name='Crawl', last_name='Task',
        )
        self.project = Project.objects.create(
            owner=self.user, name='Task Test Site',
            website_url='https://task-test.example.com',
        )
        self.crawl_job = CrawlJob.objects.create(
            project=self.project,
            status=CrawlJobStatus.PENDING,
        )

    def _make_mock_page(self, url='https://task-test.example.com/', status_code=200):
        page = MagicMock()
        page.url = url
        page.final_url = url
        page.status_code = status_code
        page.response_time_ms = 300.0
        page.depth = 0
        page.title = 'Home'
        page.meta_description = 'Desc'
        page.h1_count = 1
        page.word_count = 50
        page.canonical_url = None
        page.has_redirect = False
        page.redirect_chain = []
        page.internal_links_count = 1
        page.external_links_count = 0
        page.images_count = 0
        page.images_missing_alt_count = 0
        page.is_broken = (status_code >= 400)
        page.is_slow = False
        page.findings = []
        return page

    def _make_mock_summary(self, pages_crawled=1):
        summary = MagicMock()
        summary.pages_crawled = pages_crawled
        summary.pages_discovered = pages_crawled
        summary.broken_links_count = 0
        summary.missing_titles_count = 0
        summary.missing_descriptions_count = 0
        summary.duplicate_titles_count = 0
        summary.missing_h1_count = 0
        summary.redirect_chains_count = 0
        summary.slow_pages_count = 0
        summary.metadata = {}
        return summary

    def test_task_transitions_to_running_and_completes(self):
        """
        Task transitions CrawlJob PENDING → RUNNING → COMPLETED and
        persists CrawlPage records.
        """
        mock_page = self._make_mock_page()
        mock_summary = self._make_mock_summary(pages_crawled=1)

        with patch('apps.seo.tasks.TechnicalCrawlerService') as MockCrawler:
            instance = MockCrawler.return_value
            instance.crawl.return_value = (mock_summary, [mock_page])

            from apps.seo.tasks import run_technical_crawl
            run_technical_crawl.run(
                crawl_job_id=self.crawl_job.id,
                max_pages=10,
                max_depth=2,
                respect_robots_txt=True,
            )

        self.crawl_job.refresh_from_db()
        self.assertEqual(self.crawl_job.status, CrawlJobStatus.COMPLETED)
        self.assertIsNotNone(self.crawl_job.completed_at)
        self.assertEqual(CrawlPage.objects.filter(crawl_job=self.crawl_job).count(), 1)

    def test_task_marks_failed_on_ssrf_error(self):
        """ValueError from SSRF check causes CrawlJob to transition to FAILED."""
        with patch('apps.seo.tasks.TechnicalCrawlerService') as MockCrawler:
            instance = MockCrawler.return_value
            instance.crawl.side_effect = ValueError('SSRF: blocked IP detected')

            from apps.seo.tasks import run_technical_crawl
            run_technical_crawl.run(
                crawl_job_id=self.crawl_job.id,
                max_pages=10,
                max_depth=2,
            )

        self.crawl_job.refresh_from_db()
        self.assertEqual(self.crawl_job.status, CrawlJobStatus.FAILED)
        self.assertIsNotNone(self.crawl_job.error_message)

    def test_task_skips_already_running_job(self):
        """If a CrawlJob is already RUNNING, the task skips re-executing it."""
        self.crawl_job.status = CrawlJobStatus.RUNNING
        self.crawl_job.save(update_fields=['status', 'updated_at'])

        with patch('apps.seo.tasks.TechnicalCrawlerService') as MockCrawler:
            from apps.seo.tasks import run_technical_crawl
            run_technical_crawl.run(
                crawl_job_id=self.crawl_job.id,
                max_pages=10,
                max_depth=2,
            )
            # Crawler should never be instantiated or called
            MockCrawler.assert_not_called()

    def test_task_handles_missing_crawl_job(self):
        """Task with a non-existent crawl_job_id returns None gracefully."""
        from apps.seo.tasks import run_technical_crawl
        result = run_technical_crawl.run(
            crawl_job_id=999999,
            max_pages=10,
            max_depth=2,
        )
        self.assertIsNone(result)
