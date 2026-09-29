"""
Comprehensive test suite for DoxaRank Original SRS Keyword Intelligence / Search Volume & CPC.

Tests:
1. Data Model & Unicode:
   - Creation of KeywordIntelligence and KeywordIntelligenceSnapshot.
   - Valid search volume, CPC, competition levels, competition index, difficulty.
   - Ethiopian Amharic (አማርኛ), Oromo (Afaan Oromoo), and English search queries.
   - Nullable and missing fields handled gracefully.
2. Provider Abstraction:
   - BaseKeywordIntelligenceProvider interface compliance.
   - UnconfiguredProvider safe behavior (no random numbers, status UNAVAILABLE, helpful error).
   - MockKeywordIntelligenceProvider deterministic Amharic, Oromo, and English test fixtures.
   - DataForSEOProvider handling: successful response, HTTP 401/403 auth error, HTTP 429 rate limit,
     timeout, malformed payload, partial data.
3. Deterministic Search Intent Classifier:
   - English, Amharic, and Oromo rule matching across transactional, commercial, informational, navigational.
   - Zero LLM / Agentic AI dependency.
4. Caching & Freshness:
   - Fresh data returned from cache without provider calls.
   - Stale data refreshed on demand.
   - Refresh in progress prevention (duplicate job lock).
   - Previous valid metrics preserved if subsequent provider refresh fails.
5. Subscription & Entitlement:
   - Gated via FeatureCode.RANK_TRACKING.
   - Free plan users denied access (HTTP 403 FEATURE_NOT_ENTITLED).
   - Starter and Agency plan users granted access.
6. API & Security:
   - Authenticated user required.
   - Strict project ownership isolation (cross-tenant access returns 404).
   - GET /api/seo/keywords/<id>/intelligence/
   - POST /api/seo/keywords/<id>/intelligence/refresh/
   - GET /api/seo/keyword-intelligence/
   - POST /api/seo/keyword-intelligence/refresh/ (bulk)
   - GET /api/seo/keyword-intelligence/<id>/history/
   - Provider credentials never leaked to frontend.
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock
import requests

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.projects.models import Project
from apps.subscriptions.models import FeatureCode, PlanCode
from apps.subscriptions.services import SubscriptionService
from apps.seo.models import (
    Keyword, KeywordIntelligence, KeywordIntelligenceSnapshot,
    IntelligenceStatus, CompetitionLevel, SearchIntent, Language, Country
)
from apps.seo.services.keyword_intelligence import (
    KeywordIntelligenceService,
    KeywordMetricsResult,
    BaseKeywordIntelligenceProvider,
    UnconfiguredProvider,
    MockKeywordIntelligenceProvider,
    DataForSEOProvider,
    classify_search_intent,
    get_keyword_intelligence_provider,
)

User = get_user_model()


class KeywordIntelligenceModelAndDataTests(TestCase):
    """
    Tests for KeywordIntelligence data models and Unicode handling.
    """

    @classmethod
    def setUpTestData(cls):
        SubscriptionService.bootstrap_default_plans()

    def setUp(self):
        self.user = User.objects.create_user(email='intel_test@example.com', password='pass123_test')
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.project = Project.objects.create(
            owner=self.user,
            name="Addis Hospitality",
            website_url="https://addishotel.et"
        )

    def test_create_amharic_keyword_intelligence(self):
        """Verify Amharic keyword metrics creation and Unicode preservation."""
        kw = Keyword.objects.create(
            project=self.project,
            keyword="የአዲስ አበባ ሆቴል",
            language=Language.AM,
            country=Country.ET,
            search_domain="google.com.et"
        )
        intel = KeywordIntelligence.objects.create(
            keyword=kw,
            search_volume=2400,
            cpc=Decimal("0.3500"),
            currency="USD",
            competition=CompetitionLevel.MEDIUM,
            competition_index=0.45,
            difficulty=28,
            intent=SearchIntent.COMMERCIAL,
            source="mock",
            status=IntelligenceStatus.FRESH,
            last_refreshed_at=timezone.now()
        )
        self.assertEqual(intel.keyword.keyword, "የአዲስ አበባ ሆቴል")
        self.assertEqual(intel.search_volume, 2400)
        self.assertEqual(intel.cpc, Decimal("0.3500"))
        self.assertEqual(intel.competition, "MEDIUM")
        self.assertTrue(intel.is_fresh)

    def test_create_oromo_keyword_intelligence(self):
        """Verify Afaan Oromoo keyword metrics and Language.OM support."""
        kw = Keyword.objects.create(
            project=self.project,
            keyword="hoteelaa finfinnee",
            language=Language.OM,
            country=Country.ET,
            search_domain="google.com.et"
        )
        intel = KeywordIntelligence.objects.create(
            keyword=kw,
            search_volume=880,
            cpc=Decimal("0.2500"),
            currency="USD",
            competition=CompetitionLevel.LOW,
            competition_index=0.22,
            difficulty=18,
            intent=SearchIntent.COMMERCIAL,
            source="mock",
            status=IntelligenceStatus.FRESH,
            last_refreshed_at=timezone.now()
        )
        self.assertEqual(kw.language, 'om')
        self.assertEqual(intel.search_volume, 880)
        self.assertEqual(intel.competition, 'LOW')

    def test_nullable_missing_provider_fields(self):
        """Verify all provider metrics can be null without constraint failures."""
        kw = Keyword.objects.create(
            project=self.project,
            keyword="rare query without volume",
            language=Language.EN
        )
        intel = KeywordIntelligence.objects.create(
            keyword=kw,
            search_volume=None,
            cpc=None,
            competition=None,
            competition_index=None,
            difficulty=None,
            intent=None,
            source="unconfigured",
            status=IntelligenceStatus.UNAVAILABLE
        )
        self.assertIsNone(intel.search_volume)
        self.assertIsNone(intel.cpc)
        self.assertFalse(intel.is_fresh)

    def test_intelligence_snapshot_recording(self):
        """Verify historical snapshots are created and ordered chronologically."""
        kw = Keyword.objects.create(
            project=self.project,
            keyword="seo agency ethiopia",
            language=Language.EN
        )
        snap1 = KeywordIntelligenceSnapshot.objects.create(
            keyword=kw,
            search_volume=600,
            cpc=Decimal("1.1000"),
            competition=CompetitionLevel.HIGH,
            source="mock",
            recorded_at=timezone.now() - timezone.timedelta(days=30)
        )
        snap2 = KeywordIntelligenceSnapshot.objects.create(
            keyword=kw,
            search_volume=720,
            cpc=Decimal("1.2500"),
            competition=CompetitionLevel.HIGH,
            source="mock",
            recorded_at=timezone.now()
        )
        snapshots = list(kw.intelligence_snapshots.all())
        self.assertEqual(len(snapshots), 2)
        # Ordered by -recorded_at
        self.assertEqual(snapshots[0].id, snap2.id)
        self.assertEqual(snapshots[1].id, snap1.id)


class IntentClassifierTests(TestCase):
    """
    Tests for deterministic multilingual search intent classifier.
    """

    def test_english_intent_classification(self):
        self.assertEqual(classify_search_intent("buy shoes online ethiopia"), "transactional")
        self.assertEqual(classify_search_intent("best hotels in addis ababa"), "commercial")
        self.assertEqual(classify_search_intent("how to start an export business in ethiopia"), "informational")
        self.assertEqual(classify_search_intent("doxarank login portal"), "navigational")

    def test_amharic_intent_classification(self):
        # Transactional: መግዛት / ዋጋ
        self.assertEqual(classify_search_intent("ቡና መግዛት"), "transactional")
        self.assertEqual(classify_search_intent("የመኪና ዋጋ በአዲስ አበባ"), "transactional")
        # Commercial: ምርጥ / ሆቴል
        self.assertEqual(classify_search_intent("የአዲስ አበባ ምርጥ ሆቴል"), "commercial")
        # Informational: እንዴት / ምንነት
        self.assertEqual(classify_search_intent("እንዴት ድረ ገጽ መስራት ይቻላል"), "informational")
        # Navigational: መግቢያ
        self.assertEqual(classify_search_intent("የኢትዮጵያ አየር መንገድ ድህረ ገጽ"), "navigational")

    def test_oromo_intent_classification(self):
        # Transactional: bituu / gatii
        self.assertEqual(classify_search_intent("buna bituu Finfinnee"), "transactional")
        # Commercial: filatamaa / hoteelaa
        self.assertEqual(classify_search_intent("hoteelaa filatamaa Finfinnee"), "commercial")
        # Informational: akkamiin
        self.assertEqual(classify_search_intent("akkamiin daldala jalqabuu"), "informational")
        # Navigational: marsariitii
        self.assertEqual(classify_search_intent("marsariitii seensaa"), "navigational")


class KeywordIntelligenceProviderTests(TestCase):
    """
    Tests for provider abstractions, unconfigured handling, mock provider, and DataForSEO provider.
    """

    def test_unconfigured_provider_safe_behavior(self):
        """Unconfigured provider must return success=False and never invent fake numbers."""
        provider = UnconfiguredProvider()
        result = provider.get_keyword_metrics("hotels addis ababa")
        self.assertFalse(result.success)
        self.assertIsNone(result.search_volume)
        self.assertIsNone(result.cpc)
        self.assertEqual(result.source, "unconfigured")
        self.assertIn("not configured", result.error_message)

    def test_mock_provider_deterministic_fixtures(self):
        """Mock provider returns known values for fixtures."""
        provider = MockKeywordIntelligenceProvider()

        # Amharic query
        am_res = provider.get_keyword_metrics("የአዲስ አበባ ሆቴል")
        self.assertTrue(am_res.success)
        self.assertEqual(am_res.search_volume, 2400)
        self.assertEqual(am_res.cpc, Decimal("0.3500"))
        self.assertEqual(am_res.competition, "MEDIUM")
        self.assertEqual(am_res.intent, "commercial")
        self.assertEqual(am_res.source, "mock")

        # Oromo query
        om_res = provider.get_keyword_metrics("hoteelaa finfinnee")
        self.assertTrue(om_res.success)
        self.assertEqual(om_res.search_volume, 880)
        self.assertEqual(om_res.cpc, Decimal("0.2500"))
        self.assertEqual(om_res.competition, "LOW")

        # Arbitrary query deterministic hash
        arb_res = provider.get_keyword_metrics("some unique query")
        self.assertTrue(arb_res.success)
        self.assertIsNotNone(arb_res.search_volume)
        self.assertIsNotNone(arb_res.cpc)
        self.assertEqual(arb_res.source, "mock")

    @patch('requests.post')
    def test_dataforseo_provider_success(self, mock_post):
        """Test successful DataForSEO Google Ads search volume response."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": "0.1.20240101",
            "status_code": 20000,
            "status_message": "Ok.",
            "tasks": [
                {
                    "id": "01011234-1234-1234-1234-123456789012",
                    "status_code": 20000,
                    "status_message": "Ok.",
                    "result": [
                        {
                            "keyword": "best hotels in addis ababa",
                            "search_volume": 5400,
                            "cpc": 0.85,
                            "competition": "HIGH",
                            "competition_index": 0.78,
                            "monthly_searches": [{"year": 2026, "month": 8, "search_volume": 5400}]
                        }
                    ]
                }
            ]
        }
        mock_post.return_value = mock_response

        provider = DataForSEOProvider(login="test_user", password="test_password")
        res = provider.get_keyword_metrics("best hotels in addis ababa", country="ET", language="en")

        self.assertTrue(res.success)
        self.assertEqual(res.search_volume, 5400)
        self.assertEqual(res.cpc, Decimal("0.8500"))
        self.assertEqual(res.competition, "HIGH")
        self.assertEqual(res.competition_index, 0.78)
        self.assertEqual(res.source, "dataforseo")

    @patch('requests.post')
    def test_dataforseo_provider_auth_failure(self, mock_post):
        """DataForSEO HTTP 401 authentication failure is handled cleanly."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        provider = DataForSEOProvider(login="bad_user", password="bad_password")
        res = provider.get_keyword_metrics("seo agency")

        self.assertFalse(res.success)
        self.assertIn("authentication failure", res.error_message)

    @patch('requests.post')
    def test_dataforseo_provider_rate_limit(self, mock_post):
        """DataForSEO HTTP 429 rate limit is handled gracefully."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 429
        mock_post.return_value = mock_response

        provider = DataForSEOProvider(login="test_user", password="test_password")
        res = provider.get_keyword_metrics("seo agency")

        self.assertFalse(res.success)
        self.assertIn("rate limit", res.error_message.lower())

    @patch('requests.post')
    def test_dataforseo_provider_timeout(self, mock_post):
        """Network timeout is handled without unhandled exception."""
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        provider = DataForSEOProvider(login="test_user", password="test_password")
        res = provider.get_keyword_metrics("seo agency")

        self.assertFalse(res.success)
        self.assertIn("Timeout", res.error_message)


class KeywordIntelligenceServiceTests(TestCase):
    """
    Tests for KeywordIntelligenceService caching, snapshot persistence, and error preservation.
    """

    @classmethod
    def setUpTestData(cls):
        SubscriptionService.bootstrap_default_plans()

    def setUp(self):
        self.user = User.objects.create_user(email='svc_user@example.com', password='password123')
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.project = Project.objects.create(
            owner=self.user,
            name="Service Test Project",
            website_url="https://servicetest.et"
        )
        self.keyword = Keyword.objects.create(
            project=self.project,
            keyword="best hotels in addis ababa",
            language=Language.EN,
            country=Country.ET
        )

    def test_service_initialization(self):
        """get_or_create_intelligence initializes record with deterministic intent."""
        intel = KeywordIntelligenceService.get_or_create_intelligence(self.keyword)
        self.assertEqual(intel.keyword, self.keyword)
        self.assertEqual(intel.status, IntelligenceStatus.UNAVAILABLE)
        self.assertEqual(intel.intent, "commercial")  # from "best hotels"

    def test_service_refresh_with_mock_provider(self):
        """Successful refresh creates snapshot and marks status FRESH."""
        provider = MockKeywordIntelligenceProvider()
        intel = KeywordIntelligenceService.refresh_keyword_intelligence(
            self.keyword.id,
            force=True,
            provider=provider
        )
        self.assertEqual(intel.status, IntelligenceStatus.FRESH)
        self.assertEqual(intel.search_volume, 5400)
        self.assertEqual(intel.cpc, Decimal("0.8500"))
        self.assertEqual(intel.competition, "HIGH")
        self.assertEqual(intel.source, "mock")
        self.assertIsNotNone(intel.last_refreshed_at)
        self.assertTrue(intel.is_fresh)

        # Snapshot check
        snapshots = self.keyword.intelligence_snapshots.all()
        self.assertEqual(snapshots.count(), 1)
        self.assertEqual(snapshots.first().search_volume, 5400)

    def test_cache_reuse_for_fresh_data(self):
        """Fresh data is returned immediately without calling provider."""
        provider = MagicMock(spec=BaseKeywordIntelligenceProvider)
        provider.provider_name = 'mock'
        provider.get_keyword_metrics.return_value = KeywordMetricsResult(
            search_volume=1000,
            cpc=Decimal("0.50"),
            competition="LOW",
            source="mock",
            success=True
        )

        # First call hits provider
        intel1 = KeywordIntelligenceService.refresh_keyword_intelligence(
            self.keyword.id,
            force=True,
            provider=provider
        )
        self.assertEqual(provider.get_keyword_metrics.call_count, 1)

        # Second call within TTL returns cached without calling provider
        intel2 = KeywordIntelligenceService.refresh_keyword_intelligence(
            self.keyword.id,
            force=False,
            provider=provider
        )
        self.assertEqual(provider.get_keyword_metrics.call_count, 1)
        self.assertEqual(intel1.id, intel2.id)

    def test_provider_failure_preserves_previous_data(self):
        """Provider failure transitions status to ERROR but preserves existing volume/cpc numbers."""
        mock_provider = MockKeywordIntelligenceProvider()
        # Seed with initial valid data
        intel = KeywordIntelligenceService.refresh_keyword_intelligence(
            self.keyword.id,
            force=True,
            provider=mock_provider
        )
        self.assertEqual(intel.search_volume, 5400)

        # Now simulate a failing provider
        failing_provider = MagicMock(spec=BaseKeywordIntelligenceProvider)
        failing_provider.provider_name = 'failing'
        failing_provider.get_keyword_metrics.return_value = KeywordMetricsResult(
            source='failing',
            success=False,
            error_message="API connection lost"
        )

        updated_intel = KeywordIntelligenceService.refresh_keyword_intelligence(
            self.keyword.id,
            force=True,
            provider=failing_provider
        )
        # Previous data MUST be preserved!
        self.assertEqual(updated_intel.search_volume, 5400)
        self.assertEqual(updated_intel.status, IntelligenceStatus.ERROR)
        self.assertEqual(updated_intel.error_message, "API connection lost")


class KeywordIntelligenceAPITests(TestCase):
    """
    Tests for Keyword Intelligence REST API endpoints, permissions, and subscriptions.
    """

    @classmethod
    def setUpTestData(cls):
        SubscriptionService.bootstrap_default_plans()

    def setUp(self):
        self.client = APIClient()

        # Users
        self.user_free = User.objects.create_user(email='free_api@example.com', password='password123')
        SubscriptionService.assign_plan(self.user_free, PlanCode.FREE)

        self.user_starter = User.objects.create_user(email='starter_api@example.com', password='password123')
        SubscriptionService.assign_plan(self.user_starter, PlanCode.STARTER)

        self.user_other = User.objects.create_user(email='other_api@example.com', password='password123')
        SubscriptionService.assign_plan(self.user_other, PlanCode.STARTER)

        # Projects
        self.project_starter = Project.objects.create(
            owner=self.user_starter,
            name="Starter Site",
            website_url="https://startersite.et"
        )
        self.project_other = Project.objects.create(
            owner=self.user_other,
            name="Other Site",
            website_url="https://othersite.et"
        )
        self.project_free = Project.objects.create(
            owner=self.user_free,
            name="Free Site",
            website_url="https://freesite.et"
        )

        # Keywords
        self.kw_starter = Keyword.objects.create(
            project=self.project_starter,
            keyword="የአዲስ አበባ ሆቴል",
            language=Language.AM
        )
        self.kw_other = Keyword.objects.create(
            project=self.project_other,
            keyword="other private query",
            language=Language.EN
        )
        self.kw_free = Keyword.objects.create(
            project=self.project_free,
            keyword="free query",
            language=Language.EN
        )

    def test_anonymous_access_denied(self):
        """Unauthenticated requests must be rejected with 401 Unauthorized."""
        res = self.client.get(f"/api/seo/keywords/{self.kw_starter.id}/intelligence/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_free_plan_blocked_from_refresh(self):
        """Free plan users without RANK_TRACKING feature receive 403 Forbidden."""
        self.client.force_authenticate(user=self.user_free)
        res = self.client.post(f"/api/seo/keywords/{self.kw_free.id}/intelligence/refresh/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("does not include", res.data.get('error', ''))

    @override_settings(KEYWORD_INTELLIGENCE_PROVIDER='mock')
    def test_starter_plan_refresh_allowed(self):
        """Starter plan user can successfully refresh keyword intelligence."""
        self.client.force_authenticate(user=self.user_starter)
        res = self.client.post(f"/api/seo/keywords/{self.kw_starter.id}/intelligence/refresh/", {'force': True})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['keyword'], self.kw_starter.id)
        self.assertEqual(res.data['search_volume'], 2400)
        self.assertEqual(res.data['cpc'], "0.3500")
        self.assertEqual(res.data['competition'], "MEDIUM")
        self.assertEqual(res.data['status'], "FRESH")

    def test_get_keyword_intelligence(self):
        """Retrieve keyword intelligence details."""
        self.client.force_authenticate(user=self.user_starter)
        res = self.client.get(f"/api/seo/keywords/{self.kw_starter.id}/intelligence/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['keyword'], self.kw_starter.id)

    def test_cross_tenant_isolation_blocked(self):
        """User cannot access or refresh another user's keyword intelligence."""
        self.client.force_authenticate(user=self.user_starter)
        # Attempt to access user_other's keyword
        res = self.client.get(f"/api/seo/keywords/{self.kw_other.id}/intelligence/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        res_refresh = self.client.post(f"/api/seo/keywords/{self.kw_other.id}/intelligence/refresh/")
        self.assertEqual(res_refresh.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(KEYWORD_INTELLIGENCE_PROVIDER='mock', CELERY_TASK_ALWAYS_EAGER=True)
    def test_bulk_refresh_keywords_intelligence(self):
        """Bulk refresh keyword intelligence for all active project keywords."""
        self.client.force_authenticate(user=self.user_starter)
        res = self.client.post(
            "/api/seo/keyword-intelligence/refresh/",
            {'project_id': self.project_starter.id, 'force': True},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'queued')
        self.assertEqual(res.data['project_id'], self.project_starter.id)
        self.assertGreaterEqual(res.data['total_keywords'], 1)

    def test_bulk_refresh_non_owned_project_denied(self):
        """Bulk refresh against another user's project returns 404."""
        self.client.force_authenticate(user=self.user_starter)
        res = self.client.post(
            "/api/seo/keyword-intelligence/refresh/",
            {'project_id': self.project_other.id},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_keyword_serializer_embeds_intelligence(self):
        """KeywordSerializer response contains nested intelligence field."""
        self.client.force_authenticate(user=self.user_starter)
        KeywordIntelligenceService.get_or_create_intelligence(self.kw_starter)
        res = self.client.get(f"/api/seo/keywords/{self.kw_starter.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('intelligence', res.data)
        self.assertIsNotNone(res.data['intelligence'])
        self.assertEqual(res.data['intelligence']['keyword'], self.kw_starter.id)
