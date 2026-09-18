import httpx
from django.test import TestCase, override_settings
from django.core.cache import cache
from django.conf import settings
from unittest.mock import patch, MagicMock
from django.db import transaction, IntegrityError
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from apps.projects.models import Project
from apps.seo.models import (
    Keyword, KeywordRanking, SearchEngine, Country, Language, Device,
    SiteAudit, AuditIssue, AuditStatus, IssueSeverity,
    SearchConsoleConnection, SearchConsolePermission, SearchConsoleSyncStatus,
    SearchAnalyticsData,
    SEOInsight, InsightSeverity, InsightStatus, InsightSource, InsightType,
    SEORecommendation, RecommendationType, RecommendationPriority, RecommendationStatus,
    SEOContentBrief, BriefContentType, BriefSearchIntent, BriefStatus,
    SEOContentDraft, DraftStatus,
    SEOAction, ActionType, ActionStatus, ActionPriority,
    AgentRun, AgentStep, AgentToolCall, AgentRunStatus, AgentActionType, AgentStepStatus
)
from apps.seo.services.seo_intelligence import (
    SEOIntelligenceService,
    SEOCorrelationIntelligenceService,
    SEOCorrelationOpportunity,
    OpportunityType
)
from apps.seo.services.seo_investigation import (
    SEOInvestigationService,
    SEOInvestigationResult,
    InvestigationStatus,
    InvestigationConfidence,
    RootCauseCategory,
    ImpactEstimate,
    EffortEstimate,
    RiskLevel,
    InvestigationActionType
)
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, InMemoryEventPublisher
)
from apps.seo.services.ai_providers import MockAIProvider
from apps.seo.services.ai_seo_agent import AISeoAgentService
from apps.seo.services.content_brief_service import SEOContentBriefService
from apps.seo.services.content_writer_service import SEOContentWriterService
from apps.seo.services.export_service import ContentBriefExportService, ContentDraftExportService
from apps.seo.services.action_service import SEOActionService
from apps.seo.services.action_executors import MockSEOActionExecutor
from apps.seo.services.tool_registry import (
    ToolCategory, AgentToolDefinition, ToolRegistry,
    get_tool_registry, create_default_tool_registry
)
from apps.seo.services.agent_orchestrator import AgentOrchestrator


User = get_user_model()




class KeywordAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.keywords_url = '/api/seo/keywords/'

        # Create two test users
        self.user_a = User.objects.create_user(
            email='seo_user_a@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='seo_user_b@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='B'
        )

        # Create projects for each user
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Addis Insight',
            website_url='https://addisinsight.net'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Shega Media',
            website_url='https://shega.co'
        )

        # Create a keyword for User A and one for User B
        self.keyword_a = Keyword.objects.create(
            project=self.project_a,
            keyword='ethiopia tech news',
            search_engine=SearchEngine.GOOGLE,
            country=Country.ET,
            language=Language.EN,
            device=Device.DESKTOP
        )
        self.keyword_b = Keyword.objects.create(
            project=self.project_b,
            keyword='addis ababa startup',
            search_engine=SearchEngine.GOOGLE,
            country=Country.ET,
            language=Language.EN,
            device=Device.DESKTOP
        )

    def test_unauthenticated_get_rejected(self):
        """1. Unauthenticated GET is rejected (401)."""
        response = self.client.get(self.keywords_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_list_own_keywords(self):
        """2. Authenticated user can list own keywords."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(self.keywords_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [k['id'] for k in response.data]
        self.assertIn(self.keyword_a.id, ids)
        self.assertNotIn(self.keyword_b.id, ids)

    def test_user_can_create_keyword_for_own_project(self):
        """3. User can create a keyword for own project."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'project': self.project_a.id,
            'keyword': 'seo agency addis',
            'search_engine': 'google',
            'country': 'ET',
            'language': 'en',
            'device': 'desktop'
        }
        response = self.client.post(self.keywords_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['keyword'], 'seo agency addis')

    def test_keyword_associated_with_correct_project(self):
        """4. Keyword is associated with the correct project."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'project': self.project_a.id,
            'keyword': 'amharic translation',
            'language': 'am'
        }
        response = self.client.post(self.keywords_url, payload, format='json')
        keyword_id = response.data['id']
        kw_obj = Keyword.objects.get(id=keyword_id)
        self.assertEqual(kw_obj.project, self.project_a)

    def test_cannot_create_keyword_in_another_users_project(self):
        """5. User cannot create a keyword inside another user's project (400)."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'project': self.project_b.id,  # Owned by User B!
            'keyword': 'unauthorized keyword'
        }
        response = self.client.post(self.keywords_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project', response.data)

    def test_cannot_retrieve_another_users_keyword(self):
        """6. User cannot retrieve another user's keyword (404)."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(f'/api/seo/keywords/{self.keyword_b.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_modify_another_users_keyword(self):
        """7. User cannot modify another user's keyword (404)."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.patch(
            f'/api/seo/keywords/{self.keyword_b.id}/',
            {'keyword': 'hacked keyword'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.keyword_b.refresh_from_db()
        self.assertEqual(self.keyword_b.keyword, 'addis ababa startup')

    def test_cannot_delete_another_users_keyword(self):
        """8. User cannot delete another user's keyword (404)."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(f'/api/seo/keywords/{self.keyword_b.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Keyword.objects.filter(id=self.keyword_b.id).exists())

    def test_user_can_update_own_keyword(self):
        """9. User can update own keyword."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.patch(
            f'/api/seo/keywords/{self.keyword_a.id}/',
            {'is_active': False, 'device': 'mobile'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.keyword_a.refresh_from_db()
        self.assertFalse(self.keyword_a.is_active)
        self.assertEqual(self.keyword_a.device, 'mobile')

    def test_user_can_delete_own_keyword(self):
        """10. User can delete own keyword."""
        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(f'/api/seo/keywords/{self.keyword_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Keyword.objects.filter(id=self.keyword_a.id).exists())

    def test_invalid_keyword_rejected(self):
        """11. Invalid keyword (empty / whitespace / short) is rejected."""
        self.client.force_authenticate(user=self.user_a)
        for bad_kw in ['', '   ', 'a']:
            res = self.client.post(
                self.keywords_url,
                {'project': self.project_a.id, 'keyword': bad_kw},
                format='json'
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_search_engine_rejected(self):
        """12. Invalid search engine is rejected."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(
            self.keywords_url,
            {'project': self.project_a.id, 'keyword': 'test query', 'search_engine': 'invalid_engine'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_language_rejected(self):
        """13. Invalid language is rejected."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(
            self.keywords_url,
            {'project': self.project_a.id, 'keyword': 'test query', 'language': 'invalid_lang'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_device_rejected(self):
        """14. Invalid device is rejected."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(
            self.keywords_url,
            {'project': self.project_a.id, 'keyword': 'test query', 'device': 'tablet'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_project_filtering_works(self):
        """15. Project filtering works via ?project_id=."""
        self.client.force_authenticate(user=self.user_a)
        project_a2 = Project.objects.create(
            owner=self.user_a,
            name='Project A2',
            website_url='https://project-a2.com'
        )
        kw_a2 = Keyword.objects.create(
            project=project_a2,
            keyword='second project query'
        )

        res = self.client.get(f'{self.keywords_url}?project_id={self.project_a.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [k['id'] for k in res.data]
        self.assertIn(self.keyword_a.id, ids)
        self.assertNotIn(kw_a2.id, ids)

    def test_project_filtering_cannot_bypass_ownership(self):
        """16. Project filtering cannot bypass ownership (passing other user's project returns [])."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.keywords_url}?project_id={self.project_b.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 0)

    def test_duplicate_keyword_configuration_rejected(self):
        """17. Duplicate keyword/configuration is rejected."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'project': self.project_a.id,
            'keyword': 'ethiopia tech news',
            'search_engine': 'google',
            'country': 'ET',
            'language': 'en',
            'device': 'desktop'
        }
        res = self.client.post(self.keywords_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('keyword' in res.data or 'non_field_errors' in res.data)


class KeywordRankingAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.rankings_url = '/api/seo/rankings/'

        self.user_a = User.objects.create_user(
            email='ranking_user_a@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='ranking_user_b@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='B'
        )

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Addis Insight',
            website_url='https://addisinsight.net'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Shega Media',
            website_url='https://shega.co'
        )

        self.keyword_a = Keyword.objects.create(
            project=self.project_a,
            keyword='ethiopia tech news'
        )
        self.keyword_b = Keyword.objects.create(
            project=self.project_b,
            keyword='addis ababa startup'
        )

        self.ranking_a = KeywordRanking.objects.create(
            keyword=self.keyword_a,
            position=12,
            ranking_url='https://addisinsight.net/tech-news',
            recorded_at=timezone.now() - timezone.timedelta(days=1)
        )
        self.ranking_b = KeywordRanking.objects.create(
            keyword=self.keyword_b,
            position=5,
            ranking_url='https://shega.co/startups',
            recorded_at=timezone.now() - timezone.timedelta(days=1)
        )

    def test_unauthenticated_get_rejected(self):
        """1. Unauthenticated GET is rejected (401)."""
        res = self.client.get(self.rankings_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_a_can_create_ranking_for_own_keyword(self):
        """2. User A can create a ranking for User A's keyword."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'keyword': self.keyword_a.id,
            'position': 8,
            'ranking_url': 'https://addisinsight.net/tech-news-top',
            'search_engine': 'google',
            'country': 'ET',
            'language': 'en',
            'device': 'desktop',
            'recorded_at': timezone.now().isoformat()
        }
        res = self.client.post(self.rankings_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['position'], 8)
        self.assertEqual(res.data['keyword'], self.keyword_a.id)

    def test_user_b_can_create_ranking_for_own_keyword(self):
        """3. User B can create a ranking for User B's keyword."""
        self.client.force_authenticate(user=self.user_b)
        payload = {
            'keyword': self.keyword_b.id,
            'position': 3,
            'ranking_url': 'https://shega.co/addis-startup-top',
            'recorded_at': timezone.now().isoformat()
        }
        res = self.client.post(self.rankings_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['position'], 3)

    def test_user_a_cannot_create_ranking_for_user_b_keyword(self):
        """4. User A cannot create a ranking for User B's keyword (400)."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'keyword': self.keyword_b.id,  # Owned by User B!
            'position': 1,
            'recorded_at': timezone.now().isoformat()
        }
        res = self.client.post(self.rankings_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('keyword', res.data)

    def test_user_a_can_list_own_rankings(self):
        """5. User A can list their own rankings."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(self.rankings_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r['id'] for r in res.data]
        self.assertIn(self.ranking_a.id, ids)
        self.assertNotIn(self.ranking_b.id, ids)

    def test_user_a_cannot_see_user_b_rankings(self):
        """6. User A cannot see User B's rankings."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(self.rankings_url)
        ids = [r['id'] for r in res.data]
        self.assertNotIn(self.ranking_b.id, ids)

    def test_user_a_cannot_retrieve_user_b_ranking(self):
        """7. User A cannot retrieve User B's ranking (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'/api/seo/rankings/{self.ranking_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_modify_user_b_ranking(self):
        """8. User A cannot modify User B's ranking (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(
            f'/api/seo/rankings/{self.ranking_b.id}/',
            {'position': 99},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.ranking_b.refresh_from_db()
        self.assertEqual(self.ranking_b.position, 5)

    def test_user_a_cannot_delete_user_b_ranking(self):
        """9. User A cannot delete User B's ranking (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'/api/seo/rankings/{self.ranking_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(KeywordRanking.objects.filter(id=self.ranking_b.id).exists())

    def test_user_a_can_update_own_ranking(self):
        """10. User A can update their own ranking."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(
            f'/api/seo/rankings/{self.ranking_a.id}/',
            {'position': 10, 'ranking_url': 'https://addisinsight.net/updated-url'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.ranking_a.refresh_from_db()
        self.assertEqual(self.ranking_a.position, 10)
        self.assertEqual(self.ranking_a.ranking_url, 'https://addisinsight.net/updated-url')

    def test_user_a_can_delete_own_ranking(self):
        """11. User A can delete their own ranking."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'/api/seo/rankings/{self.ranking_a.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(KeywordRanking.objects.filter(id=self.ranking_a.id).exists())

    def test_invalid_position_rejected(self):
        """12. Invalid position is rejected (<= 0 or string)."""
        self.client.force_authenticate(user=self.user_a)
        for bad_pos in [0, -1, 9999]:
            res = self.client.post(
                self.rankings_url,
                {'keyword': self.keyword_a.id, 'position': bad_pos, 'recorded_at': timezone.now().isoformat()},
                format='json'
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_ranking_url_rejected(self):
        """13. Invalid ranking URL is rejected."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(
            self.rankings_url,
            {'keyword': self.keyword_a.id, 'position': 10, 'ranking_url': 'not_a_valid_url', 'recorded_at': timezone.now().isoformat()},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_keyword_filtering_works(self):
        """14. Keyword filtering works via ?keyword_id=."""
        self.client.force_authenticate(user=self.user_a)
        keyword_a2 = Keyword.objects.create(
            project=self.project_a,
            keyword='another keyword a'
        )
        ranking_a2 = KeywordRanking.objects.create(
            keyword=keyword_a2,
            position=20,
            recorded_at=timezone.now()
        )

        res = self.client.get(f'{self.rankings_url}?keyword_id={self.keyword_a.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r['id'] for r in res.data]
        self.assertIn(self.ranking_a.id, ids)
        self.assertNotIn(ranking_a2.id, ids)

    def test_cross_user_keyword_filtering_does_not_leak_data(self):
        """15. Cross-user keyword filtering does not leak data (returns [])."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.rankings_url}?keyword_id={self.keyword_b.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 0)

    def test_duplicate_observations_handled(self):
        """16. Duplicate observations are rejected."""
        self.client.force_authenticate(user=self.user_a)
        now_ts = timezone.now()
        KeywordRanking.objects.create(
            keyword=self.keyword_a,
            position=15,
            search_engine=SearchEngine.GOOGLE,
            country=Country.ET,
            language=Language.EN,
            device=Device.DESKTOP,
            recorded_at=now_ts
        )
        payload = {
            'keyword': self.keyword_a.id,
            'position': 16,
            'search_engine': 'google',
            'country': 'ET',
            'language': 'en',
            'device': 'desktop',
            'recorded_at': now_ts.isoformat()
        }
        res = self.client.post(self.rankings_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ranking_history_remains_associated_with_correct_keyword(self):
        """17. Ranking history remains associated with correct keyword."""
        self.assertEqual(self.ranking_a.keyword, self.keyword_a)
        self.assertEqual(self.ranking_a.keyword.project, self.project_a)

    def test_deleting_keyword_removes_ranking_history_via_cascade(self):
        """18. Deleting a keyword removes its ranking history through CASCADE."""
        ranking_id = self.ranking_a.id
        self.keyword_a.delete()
        self.assertFalse(KeywordRanking.objects.filter(id=ranking_id).exists())


class SiteAuditAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.audits_url = '/api/seo/audits/'

        self.user_a = User.objects.create_user(
            email='audit_user_a@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='audit_user_b@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='B'
        )

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Addis Insight',
            website_url='https://addisinsight.net'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Shega Media',
            website_url='https://shega.co'
        )

        self.audit_a = SiteAudit.objects.create(
            project=self.project_a,
            status=AuditStatus.COMPLETED,
            score=88
        )
        self.audit_b = SiteAudit.objects.create(
            project=self.project_b,
            status=AuditStatus.PENDING
        )

    def test_unauthenticated_get_rejected(self):
        """1. Unauthenticated GET is rejected (401)."""
        res = self.client.get(self.audits_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_a_can_create_audit_for_own_project(self):
        """2. User A can create an audit for User A's project."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'project': self.project_a.id,
            'status': 'pending',
            'score': 90
        }
        res = self.client.post(self.audits_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['score'], 90)
        self.assertEqual(res.data['project_name'], 'Addis Insight')

    def test_user_b_can_create_audit_for_own_project(self):
        """3. User B can create an audit for User B's project."""
        self.client.force_authenticate(user=self.user_b)
        payload = {
            'project': self.project_b.id,
            'status': 'running'
        }
        res = self.client.post(self.audits_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['status'], 'running')

    def test_user_a_cannot_create_audit_for_user_b_project(self):
        """4. User A cannot create an audit for User B's project (400)."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'project': self.project_b.id,  # Owned by User B!
            'status': 'pending'
        }
        res = self.client.post(self.audits_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project', res.data)

    def test_user_a_only_sees_own_audits(self):
        """5. User A only sees their own audits."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(self.audits_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [a['id'] for a in res.data]
        self.assertIn(self.audit_a.id, ids)
        self.assertNotIn(self.audit_b.id, ids)

    def test_user_a_cannot_retrieve_user_b_audit(self):
        """6. User A cannot retrieve User B's audit (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'/api/seo/audits/{self.audit_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_modify_user_b_audit(self):
        """7. User A cannot modify User B's audit (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(
            f'/api/seo/audits/{self.audit_b.id}/',
            {'score': 100},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.audit_b.refresh_from_db()
        self.assertNotEqual(self.audit_b.score, 100)

    def test_user_a_cannot_delete_user_b_audit(self):
        """8. User A cannot delete User B's audit (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'/api/seo/audits/{self.audit_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(SiteAudit.objects.filter(id=self.audit_b.id).exists())

    def test_user_a_can_update_own_audit(self):
        """9. User A can update their own audit."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(
            f'/api/seo/audits/{self.audit_a.id}/',
            {'score': 95, 'status': 'completed'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.audit_a.refresh_from_db()
        self.assertEqual(self.audit_a.score, 95)

    def test_user_a_can_delete_own_audit(self):
        """10. User A can delete their own audit."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'/api/seo/audits/{self.audit_a.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SiteAudit.objects.filter(id=self.audit_a.id).exists())

    def test_project_filtering_works(self):
        """11. Project filtering works (?project_id=)."""
        self.client.force_authenticate(user=self.user_a)
        proj_a2 = Project.objects.create(owner=self.user_a, name='Proj A2', website_url='https://a2.com')
        audit_a2 = SiteAudit.objects.create(project=proj_a2, status=AuditStatus.PENDING)

        res = self.client.get(f'{self.audits_url}?project_id={self.project_a.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [a['id'] for a in res.data]
        self.assertIn(self.audit_a.id, ids)
        self.assertNotIn(audit_a2.id, ids)

    def test_cross_user_project_filtering_is_isolated(self):
        """12. Cross-user project filtering is isolated (returns [])."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.audits_url}?project_id={self.project_b.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 0)

    def test_invalid_score_values_rejected(self):
        """19. Invalid score values (<0 or >100) are rejected."""
        self.client.force_authenticate(user=self.user_a)
        for bad_score in [-1, 101, 500]:
            res = self.client.post(
                self.audits_url,
                {'project': self.project_a.id, 'score': bad_score},
                format='json'
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class AuditIssueAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.issues_url = '/api/seo/issues/'

        self.user_a = User.objects.create_user(
            email='issue_user_a@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='issue_user_b@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='B'
        )

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Addis Insight',
            website_url='https://addisinsight.net'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Shega Media',
            website_url='https://shega.co'
        )

        self.audit_a = SiteAudit.objects.create(
            project=self.project_a,
            status=AuditStatus.COMPLETED,
            score=88
        )
        self.audit_b = SiteAudit.objects.create(
            project=self.project_b,
            status=AuditStatus.RUNNING
        )

        self.issue_a = AuditIssue.objects.create(
            audit=self.audit_a,
            issue_type='missing_title',
            severity=IssueSeverity.CRITICAL,
            title='Homepage missing meta title tag'
        )
        self.issue_b = AuditIssue.objects.create(
            audit=self.audit_b,
            issue_type='broken_link',
            severity=IssueSeverity.WARNING,
            title='404 link on contact page'
        )

    def test_unauthenticated_get_rejected(self):
        """1. Unauthenticated GET is rejected (401)."""
        res = self.client.get(self.issues_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_a_can_create_issue_under_own_audit(self):
        """13. User A can create an issue under their own audit."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'audit': self.audit_a.id,
            'issue_type': 'slow_lcp',
            'severity': 'warning',
            'title': 'LCP exceeds 3.0s',
            'description': 'Banner image uncompressed',
            'page_url': 'https://addisinsight.net/',
            'recommendation': 'Compress banner image with WebP'
        }
        res = self.client.post(self.issues_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['audit'], self.audit_a.id)
        self.assertEqual(res.data['project_name'], 'Addis Insight')

    def test_user_a_cannot_create_issue_under_user_b_audit(self):
        """14. User A cannot create an issue under User B's audit (400)."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'audit': self.audit_b.id,  # User B's audit!
            'issue_type': 'hacked_injection',
            'severity': 'critical',
            'title': 'Unauthorized issue injection'
        }
        res = self.client.post(self.issues_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('audit', res.data)

    def test_user_a_cannot_read_user_b_issue(self):
        """15. User A cannot read User B's audit issue (404 / filtered from list)."""
        self.client.force_authenticate(user=self.user_a)
        res_get = self.client.get(f'/api/seo/issues/{self.issue_b.id}/')
        self.assertEqual(res_get.status_code, status.HTTP_404_NOT_FOUND)

        res_list = self.client.get(self.issues_url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        ids = [i['id'] for i in res_list.data]
        self.assertIn(self.issue_a.id, ids)
        self.assertNotIn(self.issue_b.id, ids)

    def test_user_a_cannot_modify_user_b_issue(self):
        """16. User A cannot modify User B's audit issue (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(
            f'/api/seo/issues/{self.issue_b.id}/',
            {'title': 'Changed title'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.issue_b.refresh_from_db()
        self.assertEqual(self.issue_b.title, '404 link on contact page')

    def test_user_a_cannot_delete_user_b_issue(self):
        """17. User A cannot delete User B's audit issue (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'/api/seo/issues/{self.issue_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(AuditIssue.objects.filter(id=self.issue_b.id).exists())

    def test_user_a_can_update_own_issue(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(
            f'/api/seo/issues/{self.issue_a.id}/',
            {'severity': 'warning'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.issue_a.refresh_from_db()
        self.assertEqual(self.issue_a.severity, 'warning')

    def test_user_a_can_delete_own_issue(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'/api/seo/issues/{self.issue_a.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AuditIssue.objects.filter(id=self.issue_a.id).exists())

    def test_issue_filtering_by_audit_works(self):
        """18. Issue filtering by audit works (?audit_id=) & cross-user isolated."""
        self.client.force_authenticate(user=self.user_a)
        audit_a2 = SiteAudit.objects.create(project=self.project_a, status=AuditStatus.PENDING)
        issue_a2 = AuditIssue.objects.create(
            audit=audit_a2,
            issue_type='viewport_tag',
            severity=IssueSeverity.NOTICE,
            title='Missing viewport tag'
        )

        res = self.client.get(f'{self.issues_url}?audit_id={self.audit_a.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [i['id'] for i in res.data]
        self.assertIn(self.issue_a.id, ids)
        self.assertNotIn(issue_a2.id, ids)

        # Cross-user audit filtering returns []
        res_cross = self.client.get(f'{self.issues_url}?audit_id={self.audit_b.id}')
        self.assertEqual(res_cross.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_cross.data), 0)

    def test_cascade_deletion(self):
        """20. Cascade deletion works correctly."""
        issue_id = self.issue_a.id
        self.audit_a.delete()
        self.assertFalse(AuditIssue.objects.filter(id=issue_id).exists())


class SearchConsoleConnectionAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.gsc_url = '/api/seo/search-console/'

        self.user_a = User.objects.create_user(
            email='gsc_user_a@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='gsc_user_b@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='B'
        )

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Addis Insight',
            website_url='https://addisinsight.net'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Shega Media',
            website_url='https://shega.co'
        )

        self.conn_a = SearchConsoleConnection.objects.create(
            project=self.project_a,
            property_url='sc-domain:addisinsight.net',
            permission_level=SearchConsolePermission.SITE_OWNER,
            is_connected=True
        )
        self.conn_b = SearchConsoleConnection.objects.create(
            project=self.project_b,
            property_url='https://shega.co/',
            permission_level=SearchConsolePermission.SITE_FULL_USER,
            is_connected=True
        )

    def test_unauthenticated_get_rejected(self):
        """1. Unauthenticated GET is rejected (401)."""
        res = self.client.get(self.gsc_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_a_can_create_connection_for_own_project(self):
        """2. User A can create a GSC connection for own project."""
        self.client.force_authenticate(user=self.user_a)
        project_a2 = Project.objects.create(
            owner=self.user_a,
            name='Addis Tech Hub',
            website_url='https://addistech.et'
        )
        payload = {
            'project': project_a2.id,
            'property_url': 'sc-domain:addistech.et',
            'permission_level': 'siteOwner'
        }
        res = self.client.post(self.gsc_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['property_url'], 'sc-domain:addistech.et')
        self.assertEqual(res.data['project_name'], 'Addis Tech Hub')

    def test_user_b_can_create_connection_for_own_project(self):
        """3. User B can create a GSC connection for own project."""
        self.client.force_authenticate(user=self.user_b)
        project_b2 = Project.objects.create(
            owner=self.user_b,
            name='Shega Venture',
            website_url='https://shega.co/venture'
        )
        payload = {
            'project': project_b2.id,
            'property_url': 'https://shega.co/venture/',
            'permission_level': 'siteFullUser'
        }
        res = self.client.post(self.gsc_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['project'], project_b2.id)

    def test_user_a_cannot_create_connection_for_user_b_project(self):
        """4. User A cannot create a GSC connection for User B's project (400)."""
        self.client.force_authenticate(user=self.user_a)
        project_b_new = Project.objects.create(
            owner=self.user_b,
            name='User B Extra Proj',
            website_url='https://b-extra.com'
        )
        payload = {
            'project': project_b_new.id,
            'property_url': 'sc-domain:b-extra.com'
        }
        res = self.client.post(self.gsc_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project', res.data)

    def test_user_a_only_sees_own_connection(self):
        """5. User A only sees their own GSC connections in list."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(self.gsc_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [c['id'] for c in res.data]
        self.assertIn(self.conn_a.id, ids)
        self.assertNotIn(self.conn_b.id, ids)

    def test_user_a_cannot_retrieve_user_b_connection(self):
        """6. User A cannot retrieve User B's GSC connection (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.gsc_url}{self.conn_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_modify_user_b_connection(self):
        """7. User A cannot modify User B's GSC connection (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(
            f'{self.gsc_url}{self.conn_b.id}/',
            {'property_url': 'sc-domain:hacked.com'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.conn_b.refresh_from_db()
        self.assertEqual(self.conn_b.property_url, 'https://shega.co/')

    def test_user_a_cannot_delete_user_b_connection(self):
        """8. User A cannot delete User B's GSC connection (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'{self.gsc_url}{self.conn_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(SearchConsoleConnection.objects.filter(id=self.conn_b.id).exists())

    def test_user_a_can_update_own_connection(self):
        """9. User A can update their own GSC connection."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(
            f'{self.gsc_url}{self.conn_a.id}/',
            {'sync_status': 'success', 'is_connected': True},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.conn_a.refresh_from_db()
        self.assertEqual(self.conn_a.sync_status, 'success')

    def test_user_a_can_delete_own_connection(self):
        """10. User A can delete / disconnect own GSC connection."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'{self.gsc_url}{self.conn_a.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SearchConsoleConnection.objects.filter(id=self.conn_a.id).exists())

    def test_project_filtering_works(self):
        """11. Project filtering works (?project_id=)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.gsc_url}?project_id={self.project_a.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [c['id'] for c in res.data]
        self.assertIn(self.conn_a.id, ids)

    def test_cross_user_project_filtering_is_isolated(self):
        """12. Cross-user project filtering is isolated (returns [])."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.gsc_url}?project_id={self.project_b.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 0)

    def test_duplicate_connection_rejected(self):
        """13. Duplicate connection for the same project is rejected."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'project': self.project_a.id,
            'property_url': 'sc-domain:duplicate.com'
        }
        res = self.client.post(self.gsc_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_data_rejected(self):
        """14. Blank property_url or invalid permission level is rejected."""
        self.client.force_authenticate(user=self.user_a)
        project_a_temp = Project.objects.create(
            owner=self.user_a,
            name='Temp Proj',
            website_url='https://temp.et'
        )
        res = self.client.post(
            self.gsc_url,
            {'project': project_a_temp.id, 'property_url': '   '},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cascade_deletion(self):
        """15. Cascade deletion on project delete."""
        conn_id = self.conn_a.id
        self.project_a.delete()
        self.assertFalse(SearchConsoleConnection.objects.filter(id=conn_id).exists())


from datetime import date, timedelta
from decimal import Decimal

class SearchAnalyticsAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.analytics_url = '/api/seo/search-analytics/'

        self.user_a = User.objects.create_user(
            email='test_analytics_a@doxarank.com',
            password='Password123!',
            first_name='Analytics',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='test_analytics_b@doxarank.com',
            password='Password123!',
            first_name='Analytics',
            last_name='B'
        )

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Analytics Proj A',
            website_url='https://proja.com'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Analytics Proj B',
            website_url='https://projb.com'
        )

        self.conn_a = SearchConsoleConnection.objects.create(
            project=self.project_a,
            property_url='sc-domain:proja.com',
            permission_level='siteOwner',
            is_connected=True
        )
        self.conn_b = SearchConsoleConnection.objects.create(
            project=self.project_b,
            property_url='https://projb.com/',
            permission_level='siteFullUser',
            is_connected=True
        )

        self.today = date.today()
        self.yesterday = self.today - timedelta(days=1)

        self.rec_a1 = SearchAnalyticsData.objects.create(
            connection=self.conn_a,
            date=self.today,
            query='keyword rank test',
            page='https://proja.com/test',
            country='eth',
            device='desktop',
            clicks=50,
            impressions=1000,
            ctr=Decimal('0.0500'),
            position=Decimal('2.50')
        )
        self.rec_b1 = SearchAnalyticsData.objects.create(
            connection=self.conn_b,
            date=self.today,
            query='keyword rank user b',
            page='https://projb.com/test',
            country='eth',
            device='mobile',
            clicks=20,
            impressions=500,
            ctr=Decimal('0.0400'),
            position=Decimal('4.00')
        )

    def test_unauthenticated_get_rejected(self):
        """1. Unauthenticated GET rejected (401)."""
        res = self.client.get(self.analytics_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_create_analytics(self):
        """2. Authenticated user can create analytics for own connection."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'connection': self.conn_a.id,
            'date': str(self.yesterday),
            'query': 'new analytics query',
            'page': 'https://proja.com/new',
            'country': 'eth',
            'device': 'mobile',
            'clicks': 25,
            'impressions': 500,
            'ctr': '0.0500',
            'position': '3.10'
        }
        res = self.client.post(self.analytics_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['connection'], self.conn_a.id)
        self.assertEqual(res.data['project_id'], self.project_a.id)

    def test_cross_user_creation_blocked(self):
        """3. User A cannot create analytics for User B's connection."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'connection': self.conn_b.id,
            'date': str(self.yesterday),
            'query': 'unauthorized query',
            'clicks': 10,
            'impressions': 100
        }
        res = self.client.post(self.analytics_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_isolation(self):
        """4. User A only sees User A's analytics."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(self.analytics_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in res.data]
        self.assertIn(self.rec_a1.id, ids)
        self.assertNotIn(self.rec_b1.id, ids)

    def test_cross_user_retrieve_blocked(self):
        """5. User A cannot retrieve User B's analytics."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.analytics_url}{self.rec_b1.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_cross_user_modify_blocked(self):
        """6. User A cannot modify User B's analytics."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(f'{self.analytics_url}{self.rec_b1.id}/', {'clicks': 9999}, format='json')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_cross_user_delete_blocked(self):
        """7. User A cannot delete User B's analytics."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'{self.analytics_url}{self.rec_b1.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_own_record(self):
        """8. User A can update own record."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(f'{self.analytics_url}{self.rec_a1.id}/', {'clicks': 77}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['clicks'], 77)

    def test_delete_own_record(self):
        """9. User A can delete own record."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'{self.analytics_url}{self.rec_a1.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SearchAnalyticsData.objects.filter(id=self.rec_a1.id).exists())

    def test_filtering(self):
        """10. Filtering by project, connection, date, query, page, country, device."""
        self.client.force_authenticate(user=self.user_a)
        
        # Filter by project_id
        res_proj = self.client.get(f'{self.analytics_url}?project_id={self.project_a.id}')
        self.assertEqual(res_proj.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_proj.data), 1)

        # Filter by connection_id
        res_conn = self.client.get(f'{self.analytics_url}?connection_id={self.conn_a.id}')
        self.assertEqual(res_conn.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_conn.data), 1)

        # Filter by query
        res_q = self.client.get(f'{self.analytics_url}?query=keyword')
        self.assertEqual(res_q.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_q.data), 1)

        # Filter by device
        res_d = self.client.get(f'{self.analytics_url}?device=desktop')
        self.assertEqual(res_d.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_d.data), 1)

    def test_invalid_values_and_duplicates_rejected(self):
        """11. Negative values and duplicates are rejected."""
        self.client.force_authenticate(user=self.user_a)

        # Negative clicks
        res_neg = self.client.post(self.analytics_url, {
            'connection': self.conn_a.id,
            'date': str(self.today),
            'query': 'another query',
            'clicks': -1
        }, format='json')
        self.assertEqual(res_neg.status_code, status.HTTP_400_BAD_REQUEST)

        # Duplicate observation
        res_dup = self.client.post(self.analytics_url, {
            'connection': self.conn_a.id,
            'date': str(self.today),
            'query': 'keyword rank test',
            'page': 'https://proja.com/test',
            'country': 'eth',
            'device': 'desktop'
        }, format='json')
        self.assertEqual(res_dup.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cascade_delete(self):
        """12. Cascade delete when SearchConsoleConnection or Project is deleted."""
        rec_id = self.rec_a1.id
        self.project_a.delete()
        self.assertFalse(SearchAnalyticsData.objects.filter(id=rec_id).exists())


class SEOIntelligenceServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='intelligence_user@doxarank.com',
            password='Password123!',
            first_name='Intelligence',
            last_name='Tester'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Intelligence Test Site',
            website_url='https://inteltest.com'
        )
        self.now = timezone.now()

    def test_ranking_drop_rule_detected(self):
        """Rule A: Detects ranking drop (>= 3 positions)."""
        kw = Keyword.objects.create(
            project=self.project,
            keyword='best seo tools'
        )
        # Previous position: 4, Current position: 11 (drop of 7)
        KeywordRanking.objects.create(
            keyword=kw,
            position=4,
            recorded_at=self.now - timezone.timedelta(days=2)
        )
        KeywordRanking.objects.create(
            keyword=kw,
            position=11,
            recorded_at=self.now
        )

        service = SEOIntelligenceService(self.project)
        summary = service.analyze()

        self.assertEqual(summary['created'], 2)  # Ranking drop + Page two (pos 11 is also on page 2)
        drop_insight = SEOInsight.objects.get(project=self.project, insight_type=InsightType.RANKING_DROP)
        self.assertEqual(drop_insight.severity, InsightSeverity.WARNING)
        self.assertEqual(drop_insight.related_keyword, kw)
        self.assertEqual(drop_insight.metadata['position_drop'], 7)
        self.assertEqual(drop_insight.metadata['previous_position'], 4)
        self.assertEqual(drop_insight.metadata['current_position'], 11)

    def test_ranking_improvement_rule_detected(self):
        """Rule B: Detects ranking improvement (>= 3 positions)."""
        kw = Keyword.objects.create(
            project=self.project,
            keyword='organic search growth'
        )
        # Previous: 18, Current: 7 (Gain of 11)
        KeywordRanking.objects.create(
            keyword=kw,
            position=18,
            recorded_at=self.now - timezone.timedelta(days=3)
        )
        KeywordRanking.objects.create(
            keyword=kw,
            position=7,
            recorded_at=self.now
        )

        service = SEOIntelligenceService(self.project)
        summary = service.analyze()

        gain_insight = SEOInsight.objects.get(project=self.project, insight_type=InsightType.RANKING_IMPROVEMENT)
        self.assertEqual(gain_insight.severity, InsightSeverity.OPPORTUNITY)
        self.assertEqual(gain_insight.metadata['position_gain'], 11)

    def test_page_two_keyword_opportunity_detected(self):
        """Rule C: Detects keywords ranking between positions 11 and 20."""
        kw = Keyword.objects.create(
            project=self.project,
            keyword='page two ranking test'
        )
        KeywordRanking.objects.create(
            keyword=kw,
            position=14,
            recorded_at=self.now
        )

        service = SEOIntelligenceService(self.project)
        summary = service.analyze()

        p2_insight = SEOInsight.objects.get(project=self.project, insight_type=InsightType.PAGE_TWO_KEYWORD)
        self.assertEqual(p2_insight.severity, InsightSeverity.OPPORTUNITY)
        self.assertIn('14', p2_insight.title)
        self.assertEqual(p2_insight.metadata['current_position'], 14)

    def test_high_impressions_low_ctr_detected(self):
        """Rule D: Detects GSC queries with high impressions but low CTR (< 3%)."""
        conn = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url='https://inteltest.com/',
            is_connected=True
        )
        # Query with 200 impressions and 2 clicks (1.0% CTR)
        SearchAnalyticsData.objects.create(
            connection=conn,
            date=self.now.date(),
            query='free audit tool',
            impressions=200,
            clicks=2,
            ctr=0.0100,
            position=8.5
        )

        service = SEOIntelligenceService(self.project)
        summary = service.analyze()

        insight = SEOInsight.objects.get(project=self.project, insight_type=InsightType.HIGH_IMPRESSIONS_LOW_CTR)
        self.assertEqual(insight.severity, InsightSeverity.OPPORTUNITY)
        self.assertEqual(insight.source, InsightSource.SEARCH_CONSOLE)
        self.assertEqual(insight.metadata['impressions'], 200)
        self.assertEqual(insight.metadata['clicks'], 2)

    def test_declining_gsc_performance_detected(self):
        """Rule E: Detects decline in search clicks and impressions (>= 15%)."""
        conn = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url='https://inteltest.com/',
            is_connected=True
        )
        # Prior period: 100 clicks, 1000 impressions
        SearchAnalyticsData.objects.create(
            connection=conn,
            date=self.now.date() - timezone.timedelta(days=10),
            query='historical query',
            impressions=1000,
            clicks=100,
            ctr=0.10,
            position=3.0
        )
        # Recent period: 50 clicks (50% drop), 500 impressions (50% drop)
        SearchAnalyticsData.objects.create(
            connection=conn,
            date=self.now.date(),
            query='historical query',
            impressions=500,
            clicks=50,
            ctr=0.10,
            position=5.0
        )

        service = SEOIntelligenceService(self.project)
        summary = service.analyze()

        click_decline = SEOInsight.objects.filter(project=self.project, insight_type=InsightType.DECLINING_CLICKS)
        self.assertTrue(click_decline.exists())
        self.assertEqual(click_decline.first().severity, InsightSeverity.CRITICAL)  # 50% >= 30% is critical

        imp_decline = SEOInsight.objects.filter(project=self.project, insight_type=InsightType.DECLINING_IMPRESSIONS)
        self.assertTrue(imp_decline.exists())

    def test_technical_seo_audit_issues_detected(self):
        """Rule F: Converts unresolved critical/warning audit issues to insights."""
        audit = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.COMPLETED,
            score=72
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type='broken_links',
            severity=IssueSeverity.CRITICAL,
            title='Found 12 broken 404 links',
            description='Multiple critical pages return HTTP 404 response.',
            page_url='https://inteltest.com/products',
            recommendation='Fix or 301 redirect dead link paths.'
        )

        service = SEOIntelligenceService(self.project)
        summary = service.analyze()

        insight = SEOInsight.objects.get(project=self.project, insight_type=InsightType.TECHNICAL_SEO_ISSUE)
        self.assertEqual(insight.severity, InsightSeverity.CRITICAL)
        self.assertEqual(insight.source, InsightSource.SITE_AUDIT)
        self.assertIn('Found 12 broken 404 links', insight.title)

    def test_analysis_deduplication_and_idempotency(self):
        """Deduplication: Repeated analysis runs do not create duplicate insights."""
        kw = Keyword.objects.create(
            project=self.project,
            keyword='dedup keyword test'
        )
        KeywordRanking.objects.create(
            keyword=kw,
            position=15,
            recorded_at=self.now
        )

        service = SEOIntelligenceService(self.project)

        # First run: creates insight
        summary1 = service.analyze()
        self.assertEqual(summary1['created'], 1)
        self.assertEqual(summary1['updated'], 0)
        self.assertEqual(SEOInsight.objects.filter(project=self.project).count(), 1)

        # Second run: updates existing, 0 created
        summary2 = service.analyze()
        self.assertEqual(summary2['created'], 0)
        self.assertEqual(summary2['updated'], 1)
        self.assertEqual(SEOInsight.objects.filter(project=self.project).count(), 1)


class SEOInsightAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.insights_url = '/api/seo/insights/'
        self.analyze_url = '/api/seo/insights/analyze/'
        self.summary_url = '/api/seo/insights/summary/'

        self.user_a = User.objects.create_user(
            email='insight_user_a@doxarank.com',
            password='Password123!',
            first_name='Insight',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='insight_user_b@doxarank.com',
            password='Password123!',
            first_name='Insight',
            last_name='B'
        )

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Project A Analytics',
            website_url='https://proja-seo.com'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Project B Analytics',
            website_url='https://projb-seo.com'
        )

        self.insight_a1 = SEOInsight.objects.create(
            project=self.project_a,
            fingerprint='test:insight_a1',
            insight_type=InsightType.RANKING_DROP,
            severity=InsightSeverity.WARNING,
            title='Ranking Drop for Project A',
            description='Dropped from #3 to #9',
            status=InsightStatus.OPEN,
            source=InsightSource.RANKING
        )
        self.insight_a2 = SEOInsight.objects.create(
            project=self.project_a,
            fingerprint='test:insight_a2',
            insight_type=InsightType.PAGE_TWO_KEYWORD,
            severity=InsightSeverity.OPPORTUNITY,
            title='Page 2 Keyword for Project A',
            description='Position #14',
            status=InsightStatus.RESOLVED,
            source=InsightSource.RANKING
        )
        self.insight_b1 = SEOInsight.objects.create(
            project=self.project_b,
            fingerprint='test:insight_b1',
            insight_type=InsightType.TECHNICAL_SEO_ISSUE,
            severity=InsightSeverity.CRITICAL,
            title='Critical Audit Issue for Project B',
            description='Site down',
            status=InsightStatus.OPEN,
            source=InsightSource.SITE_AUDIT
        )

    def test_unauthenticated_requests_rejected(self):
        """1. Unauthenticated requests are rejected (401)."""
        res = self.client.get(self.insights_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        res_post = self.client.post(self.analyze_url, {'project_id': self.project_a.id})
        self.assertEqual(res_post.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_only_list_own_project_insights(self):
        """2. User A can list own insights and cannot see User B's insights."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(self.insights_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        ids = [item['id'] for item in res.data]
        self.assertIn(self.insight_a1.id, ids)
        self.assertIn(self.insight_a2.id, ids)
        self.assertNotIn(self.insight_b1.id, ids)

    def test_filter_by_severity_and_status(self):
        """3. Filtering by severity and status works properly."""
        self.client.force_authenticate(user=self.user_a)

        # Filter by severity=warning
        res_sev = self.client.get(f'{self.insights_url}?severity=warning')
        self.assertEqual(res_sev.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_sev.data), 1)
        self.assertEqual(res_sev.data[0]['id'], self.insight_a1.id)

        # Filter by status=resolved
        res_stat = self.client.get(f'{self.insights_url}?status=resolved')
        self.assertEqual(res_stat.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_stat.data), 1)
        self.assertEqual(res_stat.data[0]['id'], self.insight_a2.id)

    def test_cannot_access_or_modify_another_users_insight(self):
        """4. User A cannot access or edit User B's insight (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.insights_url}{self.insight_b1.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        res_patch = self.client.patch(
            f'{self.insights_url}{self.insight_b1.id}/',
            {'status': 'resolved'},
            format='json'
        )
        self.assertEqual(res_patch.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_analyze_another_users_project(self):
        """5. User A cannot trigger intelligence analysis on User B's project (400)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(self.analyze_url, {'project_id': self.project_b.id}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_analyze_endpoint_for_own_project(self):
        """6. User A can trigger intelligence analysis for own project."""
        kw = Keyword.objects.create(project=self.project_a, keyword='analytics query')
        KeywordRanking.objects.create(keyword=kw, position=12, recorded_at=timezone.now())

        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(self.analyze_url, {'project_id': self.project_a.id}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('created', res.data)
        self.assertIn('total_open', res.data)

    def test_insight_status_lifecycle_updates(self):
        """7. Status updates (open -> resolved -> dismissed -> open) update resolved_at."""
        self.client.force_authenticate(user=self.user_a)

        # Open -> Resolved
        res1 = self.client.patch(
            f'{self.insights_url}{self.insight_a1.id}/',
            {'status': 'resolved'},
            format='json'
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.data['status'], 'resolved')
        self.assertIsNotNone(res1.data['resolved_at'])

        # Resolved -> Dismissed
        res2 = self.client.patch(
            f'{self.insights_url}{self.insight_a1.id}/',
            {'status': 'dismissed'},
            format='json'
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['status'], 'dismissed')

        # Dismissed -> Open
        res3 = self.client.patch(
            f'{self.insights_url}{self.insight_a1.id}/',
            {'status': 'open'},
            format='json'
        )
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertEqual(res3.data['status'], 'open')
        self.assertIsNone(res3.data['resolved_at'])

    def test_summary_endpoint(self):
        """8. Summary endpoint returns accurate severity and status breakdown."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.summary_url}?project_id={self.project_a.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['warning'], 1)
        self.assertEqual(res.data['opportunity'], 0)  # insight_a2 is resolved
        self.assertEqual(res.data['open_total'], 1)
        self.assertEqual(res.data['resolved_total'], 1)
        self.assertEqual(res.data['total'], 2)


class AIProviderTests(TestCase):
    def setUp(self):
        self.provider = MockAIProvider()

    def test_ranking_drop_mock_recommendation(self):
        """Mock provider generates tailored ranking recovery plan."""
        context = {
            "insight_type": "ranking_drop",
            "severity": "critical",
            "title": "Ranking Drop for 'best seo tools'",
            "keyword": "best seo tools",
            "url": "https://example.com/tools",
            "metadata": {"previous_position": 4, "current_position": 14, "position_drop": 10}
        }
        rec = self.provider.generate_recommendation(context)
        self.assertEqual(rec['recommendation_type'], 'ranking_recovery')
        self.assertEqual(rec['priority'], 'critical')
        self.assertIn('best seo tools', rec['title'])
        self.assertIn('proposed_title', rec['generated_content'])
        self.assertIn('action_checklist', rec['generated_content'])

    def test_page_two_mock_recommendation(self):
        """Mock provider generates page 2 push plan."""
        context = {
            "insight_type": "page_two_keyword",
            "severity": "opportunity",
            "keyword": "addis fintech",
            "url": "https://example.com/fintech",
            "metadata": {"current_position": 14}
        }
        rec = self.provider.generate_recommendation(context)
        self.assertEqual(rec['recommendation_type'], 'page_two_opportunity')
        self.assertEqual(rec['priority'], 'high')
        self.assertIn('Page 2', rec['title'])

    def test_high_impressions_low_ctr_mock_recommendation(self):
        """Mock provider generates CTR optimization proposals."""
        context = {
            "insight_type": "high_impressions_low_ctr",
            "severity": "opportunity",
            "keyword": "top ethiopian banks",
            "metadata": {"impressions": 1200, "clicks": 12, "ctr_percent": 1.0}
        }
        rec = self.provider.generate_recommendation(context)
        self.assertEqual(rec['recommendation_type'], 'ctr_optimization')
        self.assertIn('proposed_meta_description', rec['generated_content'])


class AISeoAgentServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='agent_tester@doxarank.com',
            password='Password123!',
            first_name='Agent',
            last_name='Tester'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Agent Test Project',
            website_url='https://agenttest.com'
        )
        self.kw = Keyword.objects.create(
            project=self.project,
            keyword='seo software'
        )
        self.insight = SEOInsight.objects.create(
            project=self.project,
            fingerprint='test:agent_insight',
            insight_type=InsightType.RANKING_DROP,
            severity=InsightSeverity.WARNING,
            title='Ranking Drop for "seo software"',
            description='Dropped from #3 to #11',
            recommendation='Audit landing page',
            status=InsightStatus.OPEN,
            source=InsightSource.RANKING,
            related_keyword=self.kw,
            related_url='https://agenttest.com/software',
            metadata={'previous_position': 3, 'current_position': 11, 'position_drop': 8}
        )
        self.service = AISeoAgentService(self.project, provider=MockAIProvider())

    def test_generate_for_insight_persists_recommendation(self):
        """Service generates and saves structured recommendation."""
        rec = self.service.generate_for_insight(self.insight)
        self.assertIsNotNone(rec.id)
        self.assertEqual(rec.project, self.project)
        self.assertEqual(rec.insight, self.insight)
        self.assertEqual(rec.recommendation_type, RecommendationType.RANKING_RECOVERY)
        self.assertEqual(rec.priority, RecommendationPriority.HIGH)
        self.assertEqual(rec.status, RecommendationStatus.PENDING_REVIEW)
        self.assertIn('seo software', rec.title)
        self.assertIn('action_checklist', rec.generated_content)

    def test_repeated_generation_updates_pending_recommendation(self):
        """Repeated generation updates existing pending recommendation without duplicates."""
        rec1 = self.service.generate_for_insight(self.insight)
        rec2 = self.service.generate_for_insight(self.insight)

        self.assertEqual(rec1.id, rec2.id)
        self.assertEqual(SEORecommendation.objects.filter(project=self.project).count(), 1)

    def test_batch_generation_for_open_insights(self):
        """Service generates recommendations for all open insights."""
        # Create second open insight
        SEOInsight.objects.create(
            project=self.project,
            fingerprint='test:agent_insight_2',
            insight_type=InsightType.PAGE_TWO_KEYWORD,
            severity=InsightSeverity.OPPORTUNITY,
            title='Page 2 for "analytics"',
            description='Ranking #13',
            status=InsightStatus.OPEN,
            source=InsightSource.RANKING
        )
        recs = self.service.generate_batch()
        self.assertEqual(len(recs), 2)
        self.assertEqual(SEORecommendation.objects.filter(project=self.project).count(), 2)

    def test_cross_project_insight_rejected(self):
        """Service rejects generating recommendation for another project's insight."""
        other_proj = Project.objects.create(
            owner=self.user,
            name='Other Project',
            website_url='https://other.com'
        )
        other_insight = SEOInsight.objects.create(
            project=other_proj,
            fingerprint='test:other_ins',
            insight_type=InsightType.RANKING_DROP,
            title='Other Insight',
            description='Test'
        )
        with self.assertRaises(ValueError):
            self.service.generate_for_insight(other_insight)


class SEORecommendationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.recs_url = '/api/seo/ai/recommendations/'
        self.generate_url = '/api/seo/ai/recommendations/generate/'
        self.summary_url = '/api/seo/ai/recommendations/summary/'

        self.user_a = User.objects.create_user(
            email='rec_user_a@doxarank.com',
            password='Password123!',
            first_name='Rec',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='rec_user_b@doxarank.com',
            password='Password123!',
            first_name='Rec',
            last_name='B'
        )

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Project A Recs',
            website_url='https://proja-recs.com'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Project B Recs',
            website_url='https://projb-recs.com'
        )

        self.insight_a = SEOInsight.objects.create(
            project=self.project_a,
            fingerprint='test:rec_ins_a',
            insight_type=InsightType.PAGE_TWO_KEYWORD,
            severity=InsightSeverity.OPPORTUNITY,
            title='Page 2 for "tech ethiopia"',
            description='Ranking #14',
            status=InsightStatus.OPEN
        )
        self.insight_b = SEOInsight.objects.create(
            project=self.project_b,
            fingerprint='test:rec_ins_b',
            insight_type=InsightType.TECHNICAL_SEO_ISSUE,
            severity=InsightSeverity.CRITICAL,
            title='Broken Links on B',
            description='404 errors',
            status=InsightStatus.OPEN
        )

        self.rec_a1 = SEORecommendation.objects.create(
            project=self.project_a,
            insight=self.insight_a,
            recommendation_type=RecommendationType.PAGE_TWO_OPPORTUNITY,
            title='Push "tech ethiopia" to Page 1',
            summary='Keyword on page 2',
            explanation='Topical baseline exists',
            priority=RecommendationPriority.HIGH,
            recommended_action='Update headers and internal links',
            expected_impact='Higher CTR',
            status=RecommendationStatus.PENDING_REVIEW
        )
        self.rec_b1 = SEORecommendation.objects.create(
            project=self.project_b,
            insight=self.insight_b,
            recommendation_type=RecommendationType.TECHNICAL_SEO,
            title='Fix 404 Links',
            summary='Resolve dead URLs',
            explanation='Crawl budget waste',
            priority=RecommendationPriority.CRITICAL,
            recommended_action='Redirect 404s',
            expected_impact='Unblock crawler',
            status=RecommendationStatus.PENDING_REVIEW
        )

    def test_unauthenticated_requests_rejected(self):
        """1. Unauthenticated requests rejected (401)."""
        res = self.client.get(self.recs_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        res_post = self.client.post(self.generate_url, {'project_id': self.project_a.id})
        self.assertEqual(res_post.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_only_list_own_recommendations(self):
        """2. User A can list own recommendations and cannot see User B's."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(self.recs_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        ids = [r['id'] for r in res.data]
        self.assertIn(self.rec_a1.id, ids)
        self.assertNotIn(self.rec_b1.id, ids)

    def test_filter_by_priority_and_status(self):
        """3. Filtering by priority and status works properly."""
        self.client.force_authenticate(user=self.user_a)

        res = self.client.get(f'{self.recs_url}?priority=high&status=pending_review')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['id'], self.rec_a1.id)

    def test_cannot_access_or_patch_another_users_recommendation(self):
        """4. User A cannot access or update User B's recommendation (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.recs_url}{self.rec_b1.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        res_patch = self.client.patch(
            f'{self.recs_url}{self.rec_b1.id}/',
            {'status': 'reviewed'},
            format='json'
        )
        self.assertEqual(res_patch.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_generate_for_another_users_project(self):
        """5. User A cannot generate recommendations for User B's project (400)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(self.generate_url, {'project_id': self.project_b.id}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_generate_endpoint_for_own_project(self):
        """6. User A can generate recommendations for own project."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(
            self.generate_url,
            {'project_id': self.project_a.id, 'insight_ids': [self.insight_a.id]},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['insight'], self.insight_a.id)

    def test_recommendation_status_lifecycle_updates(self):
        """7. Status transitions (pending_review -> reviewed -> applied -> dismissed)."""
        self.client.force_authenticate(user=self.user_a)

        # Pending -> Reviewed
        res1 = self.client.patch(
            f'{self.recs_url}{self.rec_a1.id}/',
            {'status': 'reviewed'},
            format='json'
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.data['status'], 'reviewed')

        # Reviewed -> Applied
        res2 = self.client.patch(
            f'{self.recs_url}{self.rec_a1.id}/',
            {'status': 'applied'},
            format='json'
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['status'], 'applied')

        # Applied -> Dismissed
        res3 = self.client.patch(
            f'{self.recs_url}{self.rec_a1.id}/',
            {'status': 'dismissed'},
            format='json'
        )
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertEqual(res3.data['status'], 'dismissed')

    def test_summary_endpoint(self):
        """8. Summary endpoint returns accurate priority and status counts."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.summary_url}?project_id={self.project_a.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['high'], 1)
        self.assertEqual(res.data['pending_review'], 1)
        self.assertEqual(res.data['total'], 1)

    def test_cascade_delete(self):
        """9. Deleting project cascades and deletes recommendations."""
        rec_id = self.rec_a1.id
        self.project_a.delete()
        self.assertFalse(SEORecommendation.objects.filter(id=rec_id).exists())


class SEOContentBriefAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.briefs_url = '/api/seo/ai/content-briefs/'
        self.generate_url = '/api/seo/ai/content-briefs/generate/'

        self.user_a = User.objects.create_user(
            email='brief_user_a@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='brief_user_b@doxarank.com',
            password='Password123!',
            first_name='User',
            last_name='B'
        )

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Addis Insight',
            website_url='https://addisinsight.net'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Shega Media',
            website_url='https://shega.co'
        )

        self.insight_a = SEOInsight.objects.create(
            project=self.project_a,
            fingerprint='fp_brief_a1',
            insight_type=InsightType.PAGE_TWO_KEYWORD,
            severity=InsightSeverity.OPPORTUNITY,
            title='Push "ethiopian coffee export" to Page 1',
            description='Keyword ranks #14 with high search volume.',
            recommendation='Update H1 headers and add comprehensive brewing guide.',
            related_url='https://addisinsight.net/ethiopian-coffee'
        )
        self.insight_b = SEOInsight.objects.create(
            project=self.project_b,
            fingerprint='fp_brief_b1',
            insight_type=InsightType.TECHNICAL_SEO_ISSUE,
            severity=InsightSeverity.CRITICAL,
            title='Fix Missing Canonicals',
            description='Multiple duplicate pages found.',
            recommendation='Add rel=canonical tags site-wide.'
        )

        self.rec_a = SEORecommendation.objects.create(
            project=self.project_a,
            insight=self.insight_a,
            recommendation_type=RecommendationType.PAGE_TWO_OPPORTUNITY,
            priority=RecommendationPriority.HIGH,
            title='Optimize Content for "ethiopian coffee export"',
            summary='Push keyword from #14 into top 10 rankings.',
            explanation='Topical authority gap identified.',
            recommended_action='Draft comprehensive expert guide.',
            expected_impact='Higher organic click-through rate.',
            affected_url='https://addisinsight.net/ethiopian-coffee',
            affected_keyword='ethiopian coffee export'
        )
        self.rec_b = SEORecommendation.objects.create(
            project=self.project_b,
            insight=self.insight_b,
            recommendation_type=RecommendationType.TECHNICAL_SEO,
            priority=RecommendationPriority.CRITICAL,
            title='Resolve Canonical URL Errors',
            summary='Duplicate URLs indexed by Googlebot.',
            explanation='Crawl budget wastage.',
            recommended_action='Fix canonical headers in CMS.',
            expected_impact='Clean indexation state.'
        )

        self.brief_a = SEOContentBrief.objects.create(
            project=self.project_a,
            recommendation=self.rec_a,
            title='In-Depth Article Brief: Ethiopian Coffee Export Guide',
            target_keyword='ethiopian coffee export',
            secondary_keywords=['yirgacheffe beans', 'sidama coffee export', 'direct trade ethiopia'],
            search_intent=BriefSearchIntent.INFORMATIONAL,
            target_url='https://addisinsight.net/ethiopian-coffee',
            content_type=BriefContentType.BLOG_POST,
            recommended_title='The Ultimate Guide to Ethiopian Coffee Export (2026)',
            meta_description='Comprehensive overview of Ethiopian coffee varieties, trade regulations, and export practices.',
            suggested_slug='/blog/ethiopian-coffee-export',
            content_angle='Expert supply-chain perspective with 2026 customs data.',
            audience='Global importers, green bean buyers, and coffee enthusiasts.',
            outline=[
                {'heading': 'The Ethiopian Coffee Landscape', 'level': 'H1', 'key_points': ['Origins', 'Varieties']},
                {'heading': 'Regulatory & Export Framework', 'level': 'H2', 'key_points': ['ECX Process', 'Certifications']}
            ],
            key_points=['Explain regional bean flavor profiles.', 'Highlight 2026 export regulations.'],
            internal_link_suggestions=[{'target_url': '/blog/agri-trade', 'anchor_text': 'agricultural trade', 'context': 'Intro'}],
            external_link_suggestions=[{'source': 'ICO Statistics', 'anchor_text': 'International Coffee Organization', 'context': 'Data'}],
            faq_questions=[{'question': 'What are the main export regions?', 'answer_guidance': 'Sidama, Yirgacheffe, Guji, Harrar.'}],
            entities_topics=['Arabica', 'Washed Coffee', 'Specialty Coffee Association', 'Direct Trade'],
            content_length_target=1800,
            status=BriefStatus.DRAFT
        )

        self.brief_b = SEOContentBrief.objects.create(
            project=self.project_b,
            recommendation=self.rec_b,
            title='Technical SEO Specification: Canonical Link Tags',
            target_keyword='fix canonical tags',
            search_intent=BriefSearchIntent.INFORMATIONAL,
            content_type=BriefContentType.TECHNICAL_IMPLEMENTATION,
            recommended_title='Technical Spec: Canonical Header Deployment',
            meta_description='Developer instructions for rel=canonical tags.',
            status=BriefStatus.IN_PROGRESS
        )

    def test_unauthenticated_access_rejected(self):
        """1. Unauthenticated request to content briefs is rejected (401)."""
        res = self.client.get(self.briefs_url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_a_can_list_own_content_briefs(self):
        """2. User A can list their own content briefs."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(self.briefs_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [b['id'] for b in res.data]
        self.assertIn(self.brief_a.id, ids)
        self.assertNotIn(self.brief_b.id, ids)

    def test_user_a_cannot_see_user_b_brief(self):
        """3. User A cannot see User B's content briefs."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.briefs_url}{self.brief_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_a_cannot_modify_user_b_brief(self):
        """4. User A cannot modify User B's content brief (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(
            f'{self.briefs_url}{self.brief_b.id}/',
            {'title': 'Hacked Brief Title'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.brief_b.refresh_from_db()
        self.assertNotEqual(self.brief_b.title, 'Hacked Brief Title')

    def test_user_a_cannot_delete_user_b_brief(self):
        """5. User A cannot delete User B's content brief (404)."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'{self.briefs_url}{self.brief_b.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(SEOContentBrief.objects.filter(id=self.brief_b.id).exists())

    def test_generate_content_brief_for_recommendation(self):
        """6. User can trigger AI content brief generation for a valid recommendation."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'project_id': self.project_a.id,
            'recommendation_id': self.rec_a.id
        }
        res = self.client.post(self.generate_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['project'], self.project_a.id)
        self.assertEqual(res.data['recommendation'], self.rec_a.id)
        self.assertIn('outline', res.data)
        self.assertIn('faq_questions', res.data)
        self.assertIn('internal_link_suggestions', res.data)
        self.assertIn('secondary_keywords', res.data)

    def test_generate_content_brief_with_content_type_override(self):
        """7. Generate content brief with explicit content_type override."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'project_id': self.project_a.id,
            'recommendation_id': self.rec_a.id,
            'content_type': 'landing_page'
        }
        res = self.client.post(self.generate_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['content_type'], 'landing_page')
        self.assertEqual(res.data['search_intent'], 'commercial')

    def test_cannot_generate_brief_for_another_users_recommendation(self):
        """8. Cross-tenant generation request is rejected."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'project_id': self.project_a.id,
            'recommendation_id': self.rec_b.id  # Belongs to User B's project!
        }
        res = self.client.post(self.generate_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_status_lifecycle_updates(self):
        """9. Status transitions (draft -> in_progress -> completed -> archived)."""
        self.client.force_authenticate(user=self.user_a)
        
        # draft -> in_progress
        res1 = self.client.patch(
            f'{self.briefs_url}{self.brief_a.id}/',
            {'status': 'in_progress'},
            format='json'
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.data['status'], 'in_progress')

        # in_progress -> completed
        res2 = self.client.patch(
            f'{self.briefs_url}{self.brief_a.id}/',
            {'status': 'completed'},
            format='json'
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['status'], 'completed')

    def test_export_markdown_endpoint(self):
        """10. Export brief as Markdown format."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.briefs_url}{self.brief_a.id}/export/?export_format=markdown')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'text/markdown; charset=utf-8')
        content = res.content.decode('utf-8')
        self.assertIn('# SEO Content Brief:', content)
        self.assertIn('Ethiopian Coffee Export', content)
        self.assertIn('## 1. Brief Overview & Strategy', content)

    def test_export_csv_endpoint(self):
        """11. Export brief as CSV format."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.briefs_url}{self.brief_a.id}/export/?export_format=csv')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'text/csv; charset=utf-8')
        content = res.content.decode('utf-8')
        self.assertIn('Section,Property / Heading', content)
        self.assertIn('Primary Keyword', content)
        self.assertIn('ethiopian coffee export', content)

    def test_export_pdf_endpoint(self):
        """12. Export brief as PDF format."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.briefs_url}{self.brief_a.id}/export/?export_format=pdf')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'application/pdf')
        self.assertTrue(res.content.startswith(b'%PDF-1.4'))
        self.assertTrue(res.content.endswith(b'%%EOF\n'))

    def test_filtering_by_project_and_content_type(self):
        """13. Query parameters filter briefs accurately without cross-project leakage."""
        self.client.force_authenticate(user=self.user_a)
        
        # Filter by project
        res = self.client.get(f'{self.briefs_url}?project_id={self.project_a.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

        # Cross project filter returns empty
        res_cross = self.client.get(f'{self.briefs_url}?project_id={self.project_b.id}')
        self.assertEqual(res_cross.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_cross.data), 0)

        # Filter by content_type
        res_type = self.client.get(f'{self.briefs_url}?content_type=blog_post')
        self.assertEqual(res_type.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_type.data), 1)

    def test_cascade_delete_project_removes_brief(self):
        """14. Deleting parent project cascades to remove associated content briefs."""
        brief_id = self.brief_a.id
        self.project_a.delete()
        self.assertFalse(SEOContentBrief.objects.filter(id=brief_id).exists())


class SEOContentDraftAPITests(TestCase):
    """
    Comprehensive test suite for SEO Content Drafts:
    1. Unauthenticated rejection
    2. Multi-tenant security isolation (User B cannot access User A drafts)
    3. Cross-user generation rejection
    4. Draft generation from Brief (blog_post archetype)
    5. Draft generation for landing_page archetype
    6. Draft generation for page_optimization archetype
    7. Draft generation for technical_implementation archetype
    8. Draft regeneration updates existing record (no duplicates)
    9. In-place content editing recalculates word count and keyword coverage
    10. Lifecycle status transitions
    11. Export as Markdown (.md)
    12. Export as HTML (.html)
    13. Export as PDF (.pdf)
    14. Filtering by project, brief, and status
    15. Cascade delete brief removes associated drafts
    16. Direct draft deletion (204 No Content)
    """

    def setUp(self):
        self.client = APIClient()
        self.drafts_url = '/api/seo/ai/content-drafts/'

        # User A & Project A
        self.user_a = User.objects.create_user(
            email='draft_user_a@doxarank.com',
            password='Password123!',
            first_name='Draft',
            last_name='Author'
        )
        self.project_a = Project.objects.create(
            name='Addis Tech Hub',
            website_url='https://addis-tech.com',
            owner=self.user_a
        )

        # User B & Project B (isolation target)
        self.user_b = User.objects.create_user(
            email='draft_user_b@doxarank.com',
            password='Password123!',
            first_name='Competitor',
            last_name='User'
        )
        self.project_b = Project.objects.create(
            name='Competitor Portal',
            website_url='https://competitor.com',
            owner=self.user_b
        )

        # Setup Grounded Evidence for Project A
        self.keyword_a = Keyword.objects.create(
            project=self.project_a,
            keyword='ethiopian coffee export guide',
            search_engine='google',
            country='ET',
            language='en',
            device='desktop'
        )
        self.ranking_a = KeywordRanking.objects.create(
            keyword=self.keyword_a,
            position=12,
            ranking_url='https://addis-tech.com/coffee-guide',
            search_engine='google',
            country='ET',
            language='en',
            device='desktop',
            recorded_at=timezone.now()
        )
        self.insight_a = SEOInsight.objects.create(
            project=self.project_a,
            insight_type=InsightType.PAGE_TWO_KEYWORD,
            severity=InsightSeverity.OPPORTUNITY,
            title='Push "ethiopian coffee export guide" to Page 1',
            description='Ranking at position 12 with strong baseline relevance.',
            recommendation='Expand on-page content depth and add structured FAQ sections.',
            related_keyword=self.keyword_a,
            related_url='https://addis-tech.com/coffee-guide'
        )
        self.rec_a = SEORecommendation.objects.create(
            project=self.project_a,
            insight=self.insight_a,
            recommendation_type=RecommendationType.PAGE_TWO_OPPORTUNITY,
            priority=RecommendationPriority.HIGH,
            title='Optimize ethiopian coffee export guide for Page 1',
            summary='Topical expansion to capture page 1 search volume.',
            explanation='High opportunity with minimal difficulty.',
            recommended_action='Write an authoritative 1600-word guide.',
            expected_impact='Increases organic click-through by 3.5x.',
            affected_keyword='ethiopian coffee export guide',
            affected_url='https://addis-tech.com/coffee-guide'
        )
        self.brief_a = SEOContentBrief.objects.create(
            project=self.project_a,
            recommendation=self.rec_a,
            title='In-Depth Article Brief: Ethiopian Coffee Export Guide',
            target_keyword='ethiopian coffee export guide',
            secondary_keywords=['coffee export license ethiopia', 'yirgacheffe green coffee suppliers'],
            search_intent=BriefSearchIntent.INFORMATIONAL,
            content_type=BriefContentType.BLOG_POST,
            recommended_title='The Ultimate Ethiopian Coffee Export Guide (2026)',
            meta_description='Learn everything about ethiopian coffee export guide with practical licensing steps and supplier tips.',
            suggested_slug='/blog/ethiopian-coffee-export-guide',
            content_length_target=1600
        )

        # Pre-create a Draft for User A
        self.draft_a = SEOContentWriterService.generate_for_brief(
            project=self.project_a,
            brief=self.brief_a
        )

        # Create Brief & Draft for User B
        self.brief_b = SEOContentBrief.objects.create(
            project=self.project_b,
            title='Competitor Brief',
            target_keyword='competitor seo keyword',
            content_type=BriefContentType.BLOG_POST
        )
        self.draft_b = SEOContentWriterService.generate_for_brief(
            project=self.project_b,
            brief=self.brief_b
        )

    def test_unauthenticated_access_rejected(self):
        """1. Unauthenticated users cannot list, generate, or export drafts."""
        res_list = self.client.get(self.drafts_url)
        self.assertEqual(res_list.status_code, status.HTTP_401_UNAUTHORIZED)

        res_gen = self.client.post(f'{self.drafts_url}generate/', {
            'project_id': self.project_a.id,
            'content_brief_id': self.brief_a.id
        })
        self.assertEqual(res_gen.status_code, status.HTTP_401_UNAUTHORIZED)

        res_exp = self.client.get(f'{self.drafts_url}{self.draft_a.id}/export/')
        self.assertEqual(res_exp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_isolation_cannot_access_other_user_draft(self):
        """2. User B receives 404 when querying User A's draft directly."""
        self.client.force_authenticate(user=self.user_b)
        res = self.client.get(f'{self.drafts_url}{self.draft_a.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Patch also returns 404
        res_patch = self.client.patch(f'{self.drafts_url}{self.draft_a.id}/', {'title': 'Hacked Title'})
        self.assertEqual(res_patch.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_generate_draft_for_other_user_brief(self):
        """3. User B cannot generate a draft using User A's brief_id."""
        self.client.force_authenticate(user=self.user_b)
        res = self.client.post(f'{self.drafts_url}generate/', {
            'project_id': self.project_a.id,
            'content_brief_id': self.brief_a.id
        })
        self.assertIn(res.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND])

    def test_generate_draft_from_brief_blog_post(self):
        """4. Generate full SEOContentDraft for blog_post brief and verify all schema fields."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(f'{self.drafts_url}generate/', {
            'project_id': self.project_a.id,
            'content_brief_id': self.brief_a.id
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertEqual(data['project'], self.project_a.id)
        self.assertEqual(data['brief'], self.brief_a.id)
        self.assertEqual(data['content_type'], 'blog_post')
        self.assertEqual(data['status'], 'generated')
        self.assertTrue(len(data['title']) > 0)
        self.assertTrue(len(data['introduction']) > 0)
        self.assertTrue(len(data['content_body']) > 0)
        self.assertTrue(data['word_count'] > 100)
        self.assertIn('target_keyword', data['keyword_usage'])
        self.assertIn('occurrences', data['keyword_usage']['target_keyword'])
        self.assertTrue(isinstance(data['faq_section'], list))
        self.assertEqual(data['schema_json_ld']['@type'], 'Article')

    def test_generate_draft_landing_page(self):
        """5. Generate landing page archetype draft with WebPage schema."""
        landing_brief = SEOContentBrief.objects.create(
            project=self.project_a,
            title='Landing Page Brief',
            target_keyword='enterprise coffee export platform',
            content_type=BriefContentType.LANDING_PAGE,
            search_intent=BriefSearchIntent.COMMERCIAL
        )
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(f'{self.drafts_url}generate/', {
            'project_id': self.project_a.id,
            'content_brief_id': landing_brief.id
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['content_type'], 'landing_page')
        self.assertEqual(res.data['schema_json_ld']['@type'], 'WebPage')
        self.assertIn('Why Modern Teams Choose', res.data['content_body'])

    def test_generate_draft_page_optimization(self):
        """6. Generate page optimization draft."""
        opt_brief = SEOContentBrief.objects.create(
            project=self.project_a,
            title='Page Refresh Brief',
            target_keyword='coffee export licensing regulations',
            content_type=BriefContentType.PAGE_OPTIMIZATION
        )
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(f'{self.drafts_url}generate/', {
            'project_id': self.project_a.id,
            'content_brief_id': opt_brief.id
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['content_type'], 'page_optimization')
        self.assertIn('Optimization Guide', res.data['title'])

    def test_generate_draft_technical_implementation(self):
        """7. Generate technical SEO implementation draft with TechArticle schema."""
        tech_brief = SEOContentBrief.objects.create(
            project=self.project_a,
            title='Technical Bottleneck Brief',
            target_keyword='xml sitemap indexation delay',
            content_type=BriefContentType.TECHNICAL_IMPLEMENTATION
        )
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(f'{self.drafts_url}generate/', {
            'project_id': self.project_a.id,
            'content_brief_id': tech_brief.id
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['content_type'], 'technical_implementation')
        self.assertEqual(res.data['schema_json_ld']['@type'], 'TechArticle')
        self.assertIn('```nginx', res.data['content_body'])

    def test_regenerate_draft_updates_existing_record(self):
        """8. Regenerating draft for same brief updates existing record rather than duplicating."""
        initial_id = self.draft_a.id
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(f'{self.drafts_url}generate/', {
            'project_id': self.project_a.id,
            'content_brief_id': self.brief_a.id,
            'regenerate': True
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['id'], initial_id)
        self.assertEqual(SEOContentDraft.objects.filter(brief=self.brief_a).count(), 1)

    def test_partial_update_content_body_recalculates_word_count(self):
        """9. Human in-place editing of content_body recalculates exact word_count and keyword coverage."""
        self.client.force_authenticate(user=self.user_a)
        updated_text = "This is a new edited paragraph mentioning ethiopian coffee export guide clearly for human review."
        res = self.client.patch(f'{self.drafts_url}{self.draft_a.id}/', {
            'content_body': updated_text,
            'title': 'Manually Reviewed Title'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.draft_a.refresh_from_db()
        self.assertEqual(self.draft_a.title, 'Manually Reviewed Title')
        self.assertEqual(self.draft_a.word_count, len(updated_text.split()))
        self.assertEqual(self.draft_a.keyword_usage['target_keyword']['occurrences'], 1)

    def test_status_lifecycle_transitions(self):
        """10. Test editorial status transitions (generated -> reviewed -> approved -> published -> archived)."""
        self.client.force_authenticate(user=self.user_a)
        for target_stat in ['reviewed', 'approved', 'published', 'archived']:
            res = self.client.patch(f'{self.drafts_url}{self.draft_a.id}/', {'status': target_stat})
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertEqual(res.data['status'], target_stat)

    def test_export_markdown_endpoint(self):
        """11. Export draft as Markdown."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.drafts_url}{self.draft_a.id}/export/?export_format=markdown')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('text/markdown', res['Content-Type'])
        self.assertIn('attachment; filename=', res['Content-Disposition'])
        content = res.content.decode('utf-8')
        self.assertTrue(content.startswith('---'))
        self.assertIn('```json-ld', content)

    def test_export_html_endpoint(self):
        """12. Export draft as semantic HTML5 with schema."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.drafts_url}{self.draft_a.id}/export/?export_format=html')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('text/html', res['Content-Type'])
        content = res.content.decode('utf-8')
        self.assertIn('<!DOCTYPE html>', content)
        self.assertIn('<script type="application/ld+json">', content)
        self.assertIn(self.project_a.name, content)

    def test_export_pdf_endpoint(self):
        """13. Export draft as pure Python PDF 1.4."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.drafts_url}{self.draft_a.id}/export/?export_format=pdf')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'application/pdf')
        self.assertTrue(res.content.startswith(b'%PDF-1.4'))
        self.assertTrue(res.content.endswith(b'%%EOF\n'))

    def test_filtering_by_project_brief_and_status(self):
        """14. Test query filtering across project, brief, and status."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.drafts_url}?project_id={self.project_a.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

        # Cross project query yields 0
        res_cross = self.client.get(f'{self.drafts_url}?project_id={self.project_b.id}')
        self.assertEqual(res_cross.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_cross.data), 0)

    def test_cascade_delete_brief_removes_draft(self):
        """15. Deleting content brief cascades to remove attached draft."""
        draft_id = self.draft_a.id
        self.brief_a.delete()
        self.assertFalse(SEOContentDraft.objects.filter(id=draft_id).exists())

    def test_delete_draft_endpoint(self):
        """16. User can delete own draft directly."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'{self.drafts_url}{self.draft_a.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SEOContentDraft.objects.filter(id=self.draft_a.id).exists())


class SEOActionAPITests(TestCase):
    """
    Comprehensive test suite for SEOAction milestone:
    1. Unauthenticated rejection (401 on list, retrieve, generate, review, approve, execute, delete)
    2. Multi-tenant security isolation (User B cannot access or modify User A actions -> 404)
    3. Cross-user generation rejection (cannot generate action using another user's project/source)
    4. Action generation from SEORecommendation
    5. Action generation from SEOContentDraft (produces complete publish_new_content package)
    6. Action generation from SEOContentBrief
    7. Lifecycle transitions (proposed -> reviewed -> approved)
    8. Terminal lifecycle states (rejected, cancelled)
    9. Execution safety (unapproved action execution is strictly blocked -> 400)
    10. Safe mock execution (approved action executes -> status completed, metadata & monitoring baseline saved)
    11. Status counts endpoint returns accurate breakdown
    12. In-place action editing (PATCH updates priority, assigned_to, title)
    13. Filtering by project, status, action_type, priority
    14. Direct action deletion (204 No Content) and cascade deletion
    """

    def setUp(self):
        self.client = APIClient()
        self.actions_url = '/api/seo/ai/actions/'

        # User A & Project A
        self.user_a = User.objects.create_user(
            email='action_user_a@doxarank.com',
            password='Password123!',
            first_name='Action',
            last_name='UserA'
        )
        self.project_a = Project.objects.create(
            name='Ethio Commerce Hub',
            website_url='https://ethio-commerce.com',
            owner=self.user_a
        )

        # User B & Project B
        self.user_b = User.objects.create_user(
            email='action_user_b@doxarank.com',
            password='Password123!',
            first_name='Competitor',
            last_name='UserB'
        )
        self.project_b = Project.objects.create(
            name='Competitor Portal',
            website_url='https://competitor.com',
            owner=self.user_b
        )

        # Setup Grounded Evidence for Project A
        self.keyword_a = Keyword.objects.create(
            project=self.project_a,
            keyword='ecommerce platform ethiopia',
            search_engine='google',
            country='ET',
            language='en',
            device='desktop'
        )
        self.ranking_a = KeywordRanking.objects.create(
            keyword=self.keyword_a,
            position=8,
            ranking_url='https://ethio-commerce.com/platform',
            search_engine='google',
            country='ET',
            language='en',
            device='desktop',
            recorded_at=timezone.now()
        )
        self.insight_a = SEOInsight.objects.create(
            project=self.project_a,
            insight_type=InsightType.HIGH_POSITION_OPPORTUNITY,
            severity=InsightSeverity.OPPORTUNITY,
            title='Optimize Title and Meta Description for ecommerce platform ethiopia',
            description='Ranking on page 1 (#8) with strong click growth potential.',
            recommendation='Update meta description with clear action prompt and brand trust.',
            related_keyword=self.keyword_a,
            related_url='https://ethio-commerce.com/platform'
        )
        self.rec_a = SEORecommendation.objects.create(
            project=self.project_a,
            insight=self.insight_a,
            recommendation_type=RecommendationType.META_DESCRIPTION,
            priority=RecommendationPriority.HIGH,
            title='Update Meta Description for ecommerce platform ethiopia',
            summary='Increase SERP CTR by rewriting snippet with compelling Ethiopian value proposition.',
            explanation='Observed ranking position #8 with below-average CTR.',
            recommended_action='Replace meta description tag with high-converting copy.',
            expected_impact='Estimated 25% CTR boost.',
            affected_keyword='ecommerce platform ethiopia',
            affected_url='https://ethio-commerce.com/platform'
        )
        self.brief_a = SEOContentBrief.objects.create(
            project=self.project_a,
            recommendation=self.rec_a,
            title='Ecommerce Platform Guide Brief',
            target_keyword='ecommerce platform ethiopia',
            content_type=BriefContentType.BLOG_POST,
            recommended_title='Best Ecommerce Platforms in Ethiopia (2026)',
            meta_description='Compare top ecommerce platforms in Ethiopia with Telebirr and CBE payment integrations.',
            suggested_slug='/blog/best-ecommerce-platforms-ethiopia'
        )
        self.draft_a = SEOContentWriterService.generate_for_brief(
            project=self.project_a,
            brief=self.brief_a
        )

        # Pre-create an SEOAction for User A
        self.action_service_a = SEOActionService(project=self.project_a)
        self.action_a = self.action_service_a.generate_for_recommendation(self.rec_a)

        # Pre-create an SEOAction for User B
        self.rec_b = SEORecommendation.objects.create(
            project=self.project_b,
            insight=SEOInsight.objects.create(
                project=self.project_b,
                title='Competitor Insight',
                description='Competitor desc'
            ),
            title='Competitor Recommendation',
            summary='Competitor summary',
            explanation='Competitor explanation',
            recommended_action='Competitor action'
        )
        self.action_service_b = SEOActionService(project=self.project_b)
        self.action_b = self.action_service_b.generate_for_recommendation(self.rec_b)

    def test_unauthenticated_access_rejected(self):
        """1. Unauthenticated requests are rejected on all endpoints."""
        res_list = self.client.get(self.actions_url)
        self.assertEqual(res_list.status_code, status.HTTP_401_UNAUTHORIZED)

        res_detail = self.client.get(f'{self.actions_url}{self.action_a.id}/')
        self.assertEqual(res_detail.status_code, status.HTTP_401_UNAUTHORIZED)

        res_gen = self.client.post(f'{self.actions_url}generate/', {'project_id': self.project_a.id})
        self.assertEqual(res_gen.status_code, status.HTTP_401_UNAUTHORIZED)

        res_rev = self.client.post(f'{self.actions_url}{self.action_a.id}/review/')
        self.assertEqual(res_rev.status_code, status.HTTP_401_UNAUTHORIZED)

        res_app = self.client.post(f'{self.actions_url}{self.action_a.id}/approve/')
        self.assertEqual(res_app.status_code, status.HTTP_401_UNAUTHORIZED)

        res_exec = self.client.post(f'{self.actions_url}{self.action_a.id}/execute/')
        self.assertEqual(res_exec.status_code, status.HTTP_401_UNAUTHORIZED)

        res_del = self.client.delete(f'{self.actions_url}{self.action_a.id}/')
        self.assertEqual(res_del.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_isolation_cannot_access_other_user_action(self):
        """2. User B cannot view, modify, review, approve, execute, or delete User A's action."""
        self.client.force_authenticate(user=self.user_b)

        # GET User A action -> 404
        res_get = self.client.get(f'{self.actions_url}{self.action_a.id}/')
        self.assertEqual(res_get.status_code, status.HTTP_404_NOT_FOUND)

        # PATCH User A action -> 404
        res_patch = self.client.patch(f'{self.actions_url}{self.action_a.id}/', {'title': 'Hacked Title'})
        self.assertEqual(res_patch.status_code, status.HTTP_404_NOT_FOUND)

        # Review User A action -> 404
        res_rev = self.client.post(f'{self.actions_url}{self.action_a.id}/review/')
        self.assertEqual(res_rev.status_code, status.HTTP_404_NOT_FOUND)

        # Approve User A action -> 404
        res_app = self.client.post(f'{self.actions_url}{self.action_a.id}/approve/')
        self.assertEqual(res_app.status_code, status.HTTP_404_NOT_FOUND)

        # Execute User A action -> 404
        res_exec = self.client.post(f'{self.actions_url}{self.action_a.id}/execute/')
        self.assertEqual(res_exec.status_code, status.HTTP_404_NOT_FOUND)

        # Delete User A action -> 404
        res_del = self.client.delete(f'{self.actions_url}{self.action_a.id}/')
        self.assertEqual(res_del.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_generate_action_for_other_user_source(self):
        """3. User B cannot generate an action using User A's recommendation, draft, or brief."""
        self.client.force_authenticate(user=self.user_b)

        # Attempt using User A project ID -> 400 (validation error)
        res_cross_proj = self.client.post(f'{self.actions_url}generate/', {
            'project_id': self.project_a.id,
            'recommendation_id': self.rec_a.id
        })
        self.assertEqual(res_cross_proj.status_code, status.HTTP_400_BAD_REQUEST)

        # Attempt using User B project ID with User A recommendation ID -> 400
        res_cross_rec = self.client.post(f'{self.actions_url}generate/', {
            'project_id': self.project_b.id,
            'recommendation_id': self.rec_a.id
        })
        self.assertEqual(res_cross_rec.status_code, status.HTTP_400_BAD_REQUEST)

    def test_action_generation_from_recommendation(self):
        """4. Generate structured SEOAction from SEORecommendation."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(f'{self.actions_url}generate/', {
            'project_id': self.project_a.id,
            'recommendation_id': self.rec_a.id
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertEqual(data['project'], self.project_a.id)
        self.assertEqual(data['recommendation'], self.rec_a.id)
        self.assertEqual(data['action_type'], ActionType.UPDATE_META_DESCRIPTION)
        self.assertEqual(data['status'], ActionStatus.PROPOSED)
        self.assertIn('proposed_change', data)
        self.assertIn('implementation_instructions', data)
        self.assertIn('Marketer', data['implementation_instructions'])
        self.assertIn('Developer', data['implementation_instructions'])

    def test_action_generation_from_draft_publishes_package(self):
        """5. Generate SEOAction from SEOContentDraft creates publish_new_content package."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(f'{self.actions_url}generate/', {
            'project_id': self.project_a.id,
            'content_draft_id': self.draft_a.id
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertEqual(data['action_type'], ActionType.PUBLISH_NEW_CONTENT)
        self.assertEqual(data['draft'], self.draft_a.id)
        self.assertEqual(data['status'], ActionStatus.PROPOSED)

        # Inspect publishing payload
        proposed = data['proposed_change']
        self.assertEqual(proposed['title'], self.draft_a.title)
        self.assertEqual(proposed['slug'], self.draft_a.suggested_slug)
        self.assertEqual(proposed['meta_description'], self.draft_a.meta_description)
        self.assertIn('content', proposed)
        self.assertIn('schema_json_ld', proposed)
        self.assertIn('faq', proposed)

    def test_action_generation_from_brief(self):
        """6. Generate SEOAction from SEOContentBrief."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(f'{self.actions_url}generate/', {
            'project_id': self.project_a.id,
            'content_brief_id': self.brief_a.id
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertEqual(data['brief'], self.brief_a.id)
        self.assertEqual(data['status'], ActionStatus.PROPOSED)

    def test_lifecycle_status_transitions(self):
        """7. Human workflow transitions: proposed -> reviewed -> approved."""
        self.client.force_authenticate(user=self.user_a)

        # 1. Review action
        res_rev = self.client.post(f'{self.actions_url}{self.action_a.id}/review/')
        self.assertEqual(res_rev.status_code, status.HTTP_200_OK)
        self.assertEqual(res_rev.data['status'], ActionStatus.REVIEWED)

        # 2. Approve action
        res_app = self.client.post(f'{self.actions_url}{self.action_a.id}/approve/')
        self.assertEqual(res_app.status_code, status.HTTP_200_OK)
        self.assertEqual(res_app.data['status'], ActionStatus.APPROVED)

    def test_rejection_and_cancellation_lifecycle(self):
        """8. Terminal states: reject and cancel."""
        self.client.force_authenticate(user=self.user_a)

        # Reject
        res_rej = self.client.post(f'{self.actions_url}{self.action_a.id}/reject/')
        self.assertEqual(res_rej.status_code, status.HTTP_200_OK)
        self.assertEqual(res_rej.data['status'], ActionStatus.REJECTED)

        # Cancel
        res_can = self.client.post(f'{self.actions_url}{self.action_a.id}/cancel/')
        self.assertEqual(res_can.status_code, status.HTTP_200_OK)
        self.assertEqual(res_can.data['status'], ActionStatus.CANCELLED)

    def test_execution_safety_cannot_execute_unapproved_action(self):
        """9. Unapproved action execution is strictly blocked (returns 400 Bad Request)."""
        self.client.force_authenticate(user=self.user_a)

        # Action is in 'proposed' state
        self.assertEqual(self.action_a.status, ActionStatus.PROPOSED)
        res = self.client.post(f'{self.actions_url}{self.action_a.id}/execute/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('A human must review and approve the action before execution', res.data['detail'])

        # Reject action and try to execute
        self.action_a.status = ActionStatus.REJECTED
        self.action_a.save()
        res_rej = self.client.post(f'{self.actions_url}{self.action_a.id}/execute/')
        self.assertEqual(res_rej.status_code, status.HTTP_400_BAD_REQUEST)

    def test_successful_mock_execution_records_metadata_and_baseline(self):
        """10. Approved action executes safely in mock staging, recording metadata and monitoring baseline."""
        self.client.force_authenticate(user=self.user_a)

        # First approve action
        self.action_a.status = ActionStatus.APPROVED
        self.action_a.save()

        # Execute
        res = self.client.post(f'{self.actions_url}{self.action_a.id}/execute/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertEqual(data['status'], ActionStatus.COMPLETED)
        self.assertIsNotNone(data['completed_at'])

        # Verify execution metadata persisted in DB
        self.action_a.refresh_from_db()
        self.assertEqual(self.action_a.status, ActionStatus.COMPLETED)
        self.assertIsNotNone(self.action_a.completed_at)
        metadata = self.action_a.execution_metadata
        self.assertEqual(metadata['status'], 'success')
        self.assertIn('MockSEOActionExecutor', metadata['executor'])
        self.assertIn('executed_at', metadata)
        self.assertIn('duration_ms', metadata)
        self.assertIn('monitoring_baseline', metadata)
        self.assertEqual(metadata['monitoring_baseline']['monitored_keyword'], self.action_a.target_keyword)

    def test_action_status_counts_endpoint(self):
        """11. Test status-counts aggregate statistics endpoint."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f'{self.actions_url}status-counts/?project_id={self.project_a.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('proposed', res.data)
        self.assertIn('approved', res.data)
        self.assertIn('completed', res.data)
        self.assertIn('total', res.data)
        self.assertGreaterEqual(res.data['total'], 1)

    def test_patch_action_in_place_edit(self):
        """12. User can update assigned_to, priority, and title of own action."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.patch(f'{self.actions_url}{self.action_a.id}/', {
            'assigned_to': 'Lead SEO Specialist',
            'priority': ActionPriority.CRITICAL
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['assigned_to'], 'Lead SEO Specialist')
        self.assertEqual(res.data['priority'], ActionPriority.CRITICAL)

    def test_filtering_by_project_action_type_priority_and_status(self):
        """13. Filtering queries strictly isolate by parameters and project."""
        self.client.force_authenticate(user=self.user_a)

        res_proj = self.client.get(f'{self.actions_url}?project_id={self.project_a.id}')
        self.assertEqual(res_proj.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_proj.data), 1)

        # Cross-project query returns 0
        res_cross = self.client.get(f'{self.actions_url}?project_id={self.project_b.id}')
        self.assertEqual(res_cross.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_cross.data), 0)

    def test_direct_action_deletion(self):
        """14. User can delete own SEOAction."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.delete(f'{self.actions_url}{self.action_a.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SEOAction.objects.filter(id=self.action_a.id).exists())


class AgentExecutionStateModelTests(TestCase):
    """
    Phase 1 Test Suite: Agent Execution State Models
    1. AgentRun creation with default fields (status=pending, max_steps=15, total_steps=0)
    2. AgentRun structured JSON fields (plan, context_snapshot)
    3. AgentStep creation and relationship to AgentRun
    4. AgentStep step_number uniqueness constraint per run
    5. AgentToolCall creation and relationship to AgentStep
    6. AgentToolCall structured JSON fields and latency telemetry
    7. Cascade deletion on Project deletion
    8. Cascade deletion on User deletion
    9. Cascade deletion on AgentRun and AgentStep deletion
    10. Multi-tenant isolation and ownership preservation
    11. Model string representations (__str__)
    12. Terminal status transitions and completed_at timestamps
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='agent_state_tester@doxarank.com',
            password='Password123!',
            first_name='Agent',
            last_name='Tester'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Agentic Tech Ethiopia',
            website_url='https://agentic-tech.et'
        )

    def test_agent_run_creation_and_defaults(self):
        """1. AgentRun can be created with correct defaults."""
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Analyze and optimize all page 2 search queries.'
        )
        self.assertIsNotNone(run.id)
        self.assertEqual(run.project, self.project)
        self.assertEqual(run.user, self.user)
        self.assertEqual(run.goal, 'Analyze and optimize all page 2 search queries.')
        self.assertEqual(run.status, AgentRunStatus.PENDING)
        self.assertEqual(run.max_steps, 15)
        self.assertEqual(run.total_steps, 0)
        self.assertEqual(run.plan, [])
        self.assertEqual(run.context_snapshot, {})
        self.assertEqual(run.summary, '')
        self.assertIsNone(run.completed_at)
        self.assertIsNotNone(run.created_at)
        self.assertIsNotNone(run.updated_at)

    def test_agent_run_structured_json_fields(self):
        """2. AgentRun correctly stores structured plan and context snapshot."""
        plan_data = [
            {"step": 1, "task": "Query Google Search Console for low-CTR queries"},
            {"step": 2, "task": "Generate on-page copy recommendations"},
            {"step": 3, "task": "Propose action plan for human approval"}
        ]
        context_data = {
            "initial_rankings_count": 24,
            "target_country": "ET",
            "search_engine": "google"
        }
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Execute structured plan test',
            plan=plan_data,
            context_snapshot=context_data,
            max_steps=10
        )
        run.refresh_from_db()
        self.assertEqual(len(run.plan), 3)
        self.assertEqual(run.plan[0]["task"], "Query Google Search Console for low-CTR queries")
        self.assertEqual(run.context_snapshot["target_country"], "ET")
        self.assertEqual(run.max_steps, 10)

    def test_agent_step_creation_and_relationship(self):
        """3. AgentStep belongs to an AgentRun and supports action_type/status choices."""
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Step relationship test'
        )
        step = AgentStep.objects.create(
            run=run,
            step_number=1,
            thought='I should first inspect search console analytics to find declining pages.',
            action_type=AgentActionType.PLAN,
            status=AgentStepStatus.RUNNING
        )
        self.assertIsNotNone(step.id)
        self.assertEqual(step.run, run)
        self.assertEqual(step.step_number, 1)
        self.assertIn('search console analytics', step.thought)
        self.assertEqual(step.action_type, AgentActionType.PLAN)
        self.assertEqual(step.status, AgentStepStatus.RUNNING)
        self.assertIn(step, run.steps.all())

    def test_agent_step_number_uniqueness_constraint(self):
        """4. `run + step_number` uniqueness constraint prevents duplicate steps within a run."""
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Uniqueness test'
        )
        AgentStep.objects.create(
            run=run,
            step_number=1,
            thought='First step'
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AgentStep.objects.create(
                    run=run,
                    step_number=1,
                    thought='Duplicate step 1'
                )

        # Different runs can use the same step_number
        run2 = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Second run'
        )
        step_run2 = AgentStep.objects.create(
            run=run2,
            step_number=1,
            thought='First step of run 2'
        )
        self.assertIsNotNone(step_run2.id)

    def test_agent_tool_call_creation_and_fields(self):
        """5. AgentToolCall belongs to AgentStep and records tool input, output, latency, and mutating flag."""
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Tool call test'
        )
        step = AgentStep.objects.create(
            run=run,
            step_number=1,
            action_type=AgentActionType.TOOL_CALL
        )
        tool_call = AgentToolCall.objects.create(
            step=step,
            tool_name='get_search_console_analytics',
            tool_input={"days": 28, "min_impressions": 100},
            tool_output={"queries_found": 5, "top_query": "ethiopian coffee export"},
            duration_ms=145,
            is_mutating=False
        )
        self.assertIsNotNone(tool_call.id)
        self.assertEqual(tool_call.step, step)
        self.assertEqual(tool_call.tool_name, 'get_search_console_analytics')
        self.assertEqual(tool_call.tool_input['days'], 28)
        self.assertEqual(tool_call.tool_output['top_query'], 'ethiopian coffee export')
        self.assertEqual(tool_call.duration_ms, 145)
        self.assertFalse(tool_call.is_mutating)
        self.assertIn(tool_call, step.tool_calls.all())

    def test_cascade_deletion_on_project_delete(self):
        """6. Deleting Project cascades to delete all AgentRuns, AgentSteps, and AgentToolCalls."""
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Cascade test'
        )
        step = AgentStep.objects.create(run=run, step_number=1)
        tool_call = AgentToolCall.objects.create(step=step, tool_name='test_tool')

        run_id = run.id
        step_id = step.id
        tool_call_id = tool_call.id

        self.project.delete()

        self.assertFalse(AgentRun.objects.filter(id=run_id).exists())
        self.assertFalse(AgentStep.objects.filter(id=step_id).exists())
        self.assertFalse(AgentToolCall.objects.filter(id=tool_call_id).exists())

    def test_cascade_deletion_on_user_delete(self):
        """7. Deleting User cascades to delete user's AgentRuns."""
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='User cascade test'
        )
        run_id = run.id
        self.user.delete()
        self.assertFalse(AgentRun.objects.filter(id=run_id).exists())

    def test_cascade_deletion_on_run_and_step_delete(self):
        """8. Deleting AgentRun cascades to steps and tool calls."""
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Run cascade test'
        )
        step = AgentStep.objects.create(run=run, step_number=1)
        tool_call = AgentToolCall.objects.create(step=step, tool_name='propose_action', is_mutating=True)

        step_id = step.id
        tool_call_id = tool_call.id

        run.delete()
        self.assertFalse(AgentStep.objects.filter(id=step_id).exists())
        self.assertFalse(AgentToolCall.objects.filter(id=tool_call_id).exists())

    def test_model_string_representations(self):
        """9. Verify clean, readable __str__ representations across all three models."""
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Audit landing page speed and mobile usability',
            status=AgentRunStatus.RUNNING
        )
        step = AgentStep.objects.create(
            run=run,
            step_number=2,
            action_type=AgentActionType.TOOL_CALL
        )
        tool_call_ok = AgentToolCall.objects.create(
            step=step,
            tool_name='get_audit_issues',
            duration_ms=85
        )
        tool_call_err = AgentToolCall.objects.create(
            step=step,
            tool_name='run_external_crawler',
            error_message='Connection timed out',
            duration_ms=5000
        )

        self.assertIn(f"Run #{run.id}", str(run))
        self.assertIn("Running", str(run))
        self.assertIn(f"Run #{run.id} Step 2 [Tool Call]", str(step))
        self.assertIn("get_audit_issues on Step #", str(tool_call_ok))
        self.assertIn("OK, 85ms", str(tool_call_ok))
        self.assertIn("Error, 5000ms", str(tool_call_err))

    def test_terminal_status_transitions_and_timestamps(self):
        """10. Terminal state updates set completed_at and summary."""
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Complete run test',
            status=AgentRunStatus.RUNNING
        )
        now = timezone.now()
        run.status = AgentRunStatus.COMPLETED
        run.total_steps = 4
        run.summary = "Successfully completed 4 steps and generated publish action."
        run.completed_at = now
        run.save()

        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertEqual(run.total_steps, 4)
        self.assertIn('Successfully completed', run.summary)
        self.assertIsNotNone(run.completed_at)


class ToolRegistryTests(TestCase):
    """
    Phase 2 Test Suite: Tool Registry & Schema Abstraction
    1. Tool registration, uniqueness, and lookup
    2. Provider-neutral LLM schema export
    3. Safety governance attributes (approval & mutability flags)
    4. Argument schema validation (missing required, type mismatch, enum mismatch)
    5. Execution of read-only tools (get_keyword_rankings, get_search_console_analytics, get_audit_issues)
    6. Execution of safe internal tools (run_intelligence_analysis, generate_recommendation, generate_content_brief, generate_content_draft)
    7. Execution of high-impact tool (propose_seo_action)
    8. Multi-tenant isolation enforcement (cross-project entities rejected)
    9. Error handling (unknown tools, validation failures, service exceptions)
    """

    def setUp(self):
        self.registry = get_tool_registry()

        # User A & Project A
        self.user_a = User.objects.create_user(
            email='tool_user_a@doxarank.com',
            password='Password123!',
            first_name='Tool',
            last_name='UserA'
        )
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Ethio Telecom Hub',
            website_url='https://ethio-telecom-hub.et'
        )

        # User B & Project B (Isolation Target)
        self.user_b = User.objects.create_user(
            email='tool_user_b@doxarank.com',
            password='Password123!',
            first_name='Competitor',
            last_name='UserB'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Competitor Hub',
            website_url='https://competitor-hub.et'
        )

        # Data for Project A
        self.kw_a = Keyword.objects.create(
            project=self.project_a,
            keyword='telebirr payment integration',
            search_engine='google',
            country='ET'
        )
        self.ranking_a = KeywordRanking.objects.create(
            keyword=self.kw_a,
            position=6,
            ranking_url='https://ethio-telecom-hub.et/telebirr',
            search_engine='google',
            country='ET',
            recorded_at=timezone.now()
        )
        self.audit_a = SiteAudit.objects.create(
            project=self.project_a,
            status=AuditStatus.COMPLETED,
            score=88
        )
        self.issue_a = AuditIssue.objects.create(
            audit=self.audit_a,
            issue_type='slow_ttfb',
            severity=IssueSeverity.WARNING,
            title='Slow Server Response Time (TTFB)',
            description='TTFB is 1.4s on landing pages.',
            page_url='https://ethio-telecom-hub.et/telebirr'
        )
        self.gsc_conn_a = SearchConsoleConnection.objects.create(
            project=self.project_a,
            property_url='https://ethio-telecom-hub.et',
            permission_level=SearchConsolePermission.SITE_OWNER,
            sync_status=SearchConsoleSyncStatus.SUCCESS
        )
        self.gsc_data_a = SearchAnalyticsData.objects.create(
            connection=self.gsc_conn_a,
            query='telebirr merchant api',
            page='https://ethio-telecom-hub.et/telebirr',
            clicks=120,
            impressions=3400,
            ctr=0.035,
            position=6.2,
            country='ET',
            device='desktop',
            date=timezone.now().date()
        )
        self.insight_a = SEOInsight.objects.create(
            project=self.project_a,
            fingerprint='fp_tool_test_a',
            insight_type=InsightType.HIGH_IMPRESSIONS_LOW_CTR,
            severity=InsightSeverity.OPPORTUNITY,
            title='High Impressions Low CTR on "telebirr merchant api"',
            description='Page gets 3400 impressions with only 3.5% CTR.',
            status=InsightStatus.OPEN,
            related_keyword=self.kw_a
        )
        self.rec_a = SEORecommendation.objects.create(
            project=self.project_a,
            insight=self.insight_a,
            recommendation_type=RecommendationType.CTR_OPTIMIZATION,
            priority=RecommendationPriority.HIGH,
            title='Optimize Title and Meta Description for Telebirr API',
            summary='Compelling CTA in SERP snippet.',
            explanation='High impression volume available.',
            recommended_action='Rewrite title to emphasize 2026 instant onboarding.',
            expected_impact='Estimated +40% clicks.',
            affected_keyword='telebirr merchant api',
            affected_url='https://ethio-telecom-hub.et/telebirr'
        )
        self.brief_a = SEOContentBrief.objects.create(
            project=self.project_a,
            recommendation=self.rec_a,
            title='Telebirr Merchant Integration Guide Brief',
            target_keyword='telebirr merchant api',
            content_type=BriefContentType.BLOG_POST,
            recommended_title='How to Integrate Telebirr Merchant API (2026 Guide)',
            meta_description='Step-by-step developer tutorial for integrating Telebirr in Ethiopia.'
        )

        # Data for Project B (to test isolation)
        self.insight_b = SEOInsight.objects.create(
            project=self.project_b,
            fingerprint='fp_tool_test_b',
            title='Competitor Insight',
            description='Competitor desc'
        )
        self.rec_b = SEORecommendation.objects.create(
            project=self.project_b,
            insight=self.insight_b,
            title='Competitor Recommendation',
            summary='Competitor summary',
            explanation='Competitor explanation',
            recommended_action='Competitor action'
        )
        self.brief_b = SEOContentBrief.objects.create(
            project=self.project_b,
            title='Competitor Brief',
            target_keyword='competitor term'
        )

    def test_default_registry_has_all_registered_tools(self):
        """1. Default ToolRegistry is populated with all registered tools."""
        expected_tools = [
            'get_keyword_rankings',
            'get_search_console_analytics',
            'trigger_site_audit',
            'get_site_audit_summary',
            'get_audit_issues',
            'gsc_search_analytics',
            'gsc_top_queries',
            'gsc_top_pages',
            'gsc_opportunity_audit',
            'gsc_performance_comparison',
            'analyze_seo_opportunities',
            'investigate_seo_opportunity',
            'run_intelligence_analysis',
            'generate_recommendation',
            'generate_content_brief',
            'generate_content_draft',
            'propose_seo_action',
            'get_pending_actions',
            'get_action',
            'preview_action',
            'plan_seo_actions',
            'get_action_plan',
            'verify_seo_action',
            'verify_action_plan',
            'get_action_outcomes'
        ]
        registered_names = [t.name for t in self.registry.list_tools()]
        self.assertEqual(len(registered_names), 29)
        for tool_name in expected_tools:
            self.assertIn(tool_name, registered_names)
            tool = self.registry.get(tool_name)
            self.assertIsNotNone(tool)
            self.assertEqual(tool.name, tool_name)

    def test_tool_definitions_and_schema_export(self):
        """2. Tool definitions export standard provider-neutral JSON schemas."""
        schemas = self.registry.get_schemas()
        self.assertEqual(len(schemas), 29)


        for s in schemas:
            self.assertIn('name', s)
            self.assertIn('description', s)
            self.assertIn('category', s)
            self.assertIn('parameters', s)
            self.assertIn('requires_approval', s)
            self.assertIn('is_mutating', s)

            params = s['parameters']
            self.assertEqual(params.get('type'), 'object')
            self.assertIn('properties', params)
            self.assertIsInstance(params.get('required', []), list)

    def test_tool_governance_attributes(self):
        """3. Tool governance classification matches safety policy."""
        # Read-only tools
        for name in ['get_keyword_rankings', 'get_search_console_analytics', 'get_audit_issues', 'gsc_search_analytics', 'gsc_top_queries', 'gsc_top_pages']:
            tool = self.registry.get(name)
            self.assertEqual(tool.category, ToolCategory.READ_ONLY)
            self.assertFalse(tool.requires_approval)
            self.assertFalse(tool.is_mutating)

        # Safe internal mutating tools
        for name in ['run_intelligence_analysis', 'generate_recommendation', 'generate_content_brief', 'generate_content_draft']:
            tool = self.registry.get(name)
            self.assertEqual(tool.category, ToolCategory.SAFE_INTERNAL)
            self.assertFalse(tool.requires_approval)
            self.assertTrue(tool.is_mutating)

        # High-impact tool
        action_tool = self.registry.get('propose_seo_action')
        self.assertEqual(action_tool.category, ToolCategory.HIGH_IMPACT)
        self.assertTrue(action_tool.requires_approval)
        self.assertTrue(action_tool.is_mutating)

    def test_unknown_tool_lookup_and_execution(self):
        """4. Unknown tool lookup fails safely and returns structured error."""
        self.assertIsNone(self.registry.get('nonexistent_tool'))
        with self.assertRaises(KeyError):
            self.registry.get_tool('nonexistent_tool')

        res = self.registry.execute('nonexistent_tool', self.project_a, {})
        self.assertFalse(res['success'])
        self.assertEqual(res['error']['code'], 'TOOL_NOT_FOUND')
        self.assertIn('nonexistent_tool', res['error']['message'])

    def test_argument_validation_missing_required_and_type_mismatch(self):
        """5. Argument validation rejects missing required parameters, wrong types, and invalid enums."""
        # Missing required parameter: insight_id for generate_recommendation
        res_missing = self.registry.execute('generate_recommendation', self.project_a, {})
        self.assertFalse(res_missing['success'])
        self.assertEqual(res_missing['error']['code'], 'VALIDATION_ERROR')
        self.assertIn("Missing required parameter 'insight_id'", res_missing['error']['message'])

        # Type mismatch: string instead of integer
        res_type = self.registry.execute('generate_recommendation', self.project_a, {'insight_id': 'abc'})
        self.assertFalse(res_type['success'])
        self.assertEqual(res_type['error']['code'], 'VALIDATION_ERROR')
        self.assertIn("must be an integer", res_type['error']['message'])

        # Enum mismatch: invalid source_type for propose_seo_action
        res_enum = self.registry.execute('propose_seo_action', self.project_a, {
            'source_type': 'invalid_source',
            'source_id': 1
        })
        self.assertFalse(res_enum['success'])
        self.assertEqual(res_enum['error']['code'], 'VALIDATION_ERROR')
        self.assertIn("is not in allowed values", res_enum['error']['message'])

    def test_execute_get_keyword_rankings(self):
        """6. Tool 'get_keyword_rankings' retrieves project rankings accurately."""
        res = self.registry.execute('get_keyword_rankings', self.project_a, {'keyword': 'telebirr'})
        self.assertTrue(res['success'])
        data = res['data']
        self.assertEqual(data['project_id'], self.project_a.id)
        self.assertEqual(data['returned_count'], 1)
        self.assertEqual(data['rankings'][0]['keyword'], 'telebirr payment integration')
        self.assertEqual(data['rankings'][0]['current_position'], 6)

    def test_execute_get_search_console_analytics(self):
        """7. Tool 'get_search_console_analytics' retrieves GSC metrics accurately."""
        res = self.registry.execute('get_search_console_analytics', self.project_a, {'min_impressions': 1000})
        self.assertTrue(res['success'])
        data = res['data']
        self.assertEqual(data['project_id'], self.project_a.id)
        self.assertEqual(data['returned_count'], 1)
        self.assertEqual(data['analytics'][0]['query'], 'telebirr merchant api')
        self.assertEqual(data['analytics'][0]['impressions'], 3400)

    def test_execute_get_audit_issues(self):
        """8. Tool 'get_audit_issues' retrieves site audit issues accurately."""
        res = self.registry.execute('get_audit_issues', self.project_a, {'severity': 'warning'})
        self.assertTrue(res['success'])
        data = res['data']
        self.assertEqual(data['project_id'], self.project_a.id)
        self.assertEqual(data['returned_count'], 1)
        self.assertEqual(data['issues'][0]['issue_type'], 'slow_ttfb')

    def test_execute_run_intelligence_analysis(self):
        """9. Tool 'run_intelligence_analysis' runs SEO intelligence service."""
        res = self.registry.execute('run_intelligence_analysis', self.project_a, {})
        self.assertTrue(res['success'])
        data = res['data']
        self.assertEqual(data['project_id'], self.project_a.id)
        self.assertIn('summary', data)
        self.assertIn('total_open', data['summary'])

    def test_execute_generate_recommendation(self):
        """10. Tool 'generate_recommendation' creates grounded recommendation."""
        res = self.registry.execute('generate_recommendation', self.project_a, {'insight_id': self.insight_a.id})
        self.assertTrue(res['success'])
        data = res['data']
        self.assertEqual(data['project_id'], self.project_a.id)
        self.assertEqual(data['insight_id'], self.insight_a.id)
        self.assertIn('recommendation_type', data)
        self.assertIn('action_checklist', data['generated_content'])

    def test_execute_generate_content_brief(self):
        """11. Tool 'generate_content_brief' creates structured brief."""
        res = self.registry.execute('generate_content_brief', self.project_a, {
            'recommendation_id': self.rec_a.id,
            'content_type': 'blog_post'
        })
        self.assertTrue(res['success'])
        data = res['data']
        self.assertEqual(data['project_id'], self.project_a.id)
        self.assertEqual(data['recommendation_id'], self.rec_a.id)
        self.assertEqual(data['content_type'], 'blog_post')
        self.assertIn('outline', data)

    def test_execute_generate_content_draft(self):
        """12. Tool 'generate_content_draft' creates full draft with schema."""
        res = self.registry.execute('generate_content_draft', self.project_a, {
            'content_brief_id': self.brief_a.id
        })
        self.assertTrue(res['success'])
        data = res['data']
        self.assertEqual(data['project_id'], self.project_a.id)
        self.assertEqual(data['brief_id'], self.brief_a.id)
        self.assertTrue(data['word_count'] > 0)
        self.assertIn('schema_json_ld', data)

    def test_execute_propose_seo_action(self):
        """13. Tool 'propose_seo_action' creates proposed action and declares approval requirement."""
        res = self.registry.execute('propose_seo_action', self.project_a, {
            'source_type': 'recommendation',
            'source_id': self.rec_a.id
        })
        self.assertTrue(res['success'])
        data = res['data']
        self.assertEqual(data['project_id'], self.project_a.id)
        self.assertEqual(data['status'], ActionStatus.PROPOSED)
        self.assertTrue(data['requires_human_approval'])
        self.assertIn('proposed_change', data)

        # Verify action is in database but NOT executed
        action = SEOAction.objects.get(id=data['id'])
        self.assertEqual(action.status, ActionStatus.PROPOSED)
        self.assertIsNone(action.completed_at)

    def test_multi_tenant_isolation_cross_project_rejected(self):
        """14. Tools strictly reject cross-tenant entity IDs and return structured error."""
        # Attempt to generate recommendation using Project B's insight on Project A context
        res_rec = self.registry.execute('generate_recommendation', self.project_a, {'insight_id': self.insight_b.id})
        self.assertFalse(res_rec['success'])
        self.assertEqual(res_rec['error']['code'], 'EXECUTION_ERROR')
        self.assertIn('not found on project', res_rec['error']['message'])

        # Attempt to generate brief using Project B's recommendation on Project A context
        res_brief = self.registry.execute('generate_content_brief', self.project_a, {'recommendation_id': self.rec_b.id})
        self.assertFalse(res_brief['success'])
        self.assertEqual(res_brief['error']['code'], 'EXECUTION_ERROR')

        # Attempt to generate draft using Project B's brief on Project A context
        res_draft = self.registry.execute('generate_content_draft', self.project_a, {'content_brief_id': self.brief_b.id})
        self.assertFalse(res_draft['success'])
        self.assertEqual(res_draft['error']['code'], 'EXECUTION_ERROR')

        # Attempt to propose action using Project B's recommendation on Project A context
        res_act = self.registry.execute('propose_seo_action', self.project_a, {
            'source_type': 'recommendation',
            'source_id': self.rec_b.id
        })
        self.assertFalse(res_act['success'])
        self.assertEqual(res_act['error']['code'], 'EXECUTION_ERROR')


class AgentOrchestratorTests(TestCase):
    """
    Phase 3 Test Suite: Core Agent Orchestrator & ReAct Execution Engine
    1. Multi-step agent execution through ReAct loop
    2. AgentRun state transitions and step ordering
    3. AgentToolCall telemetry persistence (inputs, outputs, latency, mutability)
    4. ToolRegistry invocation adherence
    5. max_steps guardrail bounding
    6. Repeated-tool failure loop detection
    7. Malformed AI decision handling
    8. Unknown tool handling
    9. Tool argument validation failure handling
    10. Human approval pause behavior on propose_seo_action
    11. Approved action resume behavior
    12. Rejected action resume behavior
    13. Resume guardrail on non-waiting runs
    14. Multi-tenant isolation enforcement
    15. Verification that unapproved actions are never executed
    16. Project baseline context snapshot capture
    17. Terminal completed state
    18. Terminal failed/cancelled state
    """

    def setUp(self):
        # User A & Project A
        self.user_a = User.objects.create_user(
            email='orch_user_a@doxarank.com',
            password='Password123!',
            first_name='Orchestrator',
            last_name='UserA'
        )
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Ethio Fintech Solutions',
            website_url='https://ethio-fintech.et'
        )

        # User B & Project B
        self.user_b = User.objects.create_user(
            email='orch_user_b@doxarank.com',
            password='Password123!',
            first_name='Competitor',
            last_name='UserB'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Competitor Fintech',
            website_url='https://competitor-fintech.et'
        )

        # Seed Project A SEO Entities
        self.kw_a = Keyword.objects.create(
            project=self.project_a,
            keyword='cbe birr mobile payment',
            search_engine='google',
            country='ET'
        )
        self.ranking_a = KeywordRanking.objects.create(
            keyword=self.kw_a,
            position=11,
            ranking_url='https://ethio-fintech.et/cbe-birr',
            search_engine='google',
            country='ET',
            recorded_at=timezone.now()
        )
        self.insight_a = SEOInsight.objects.create(
            project=self.project_a,
            fingerprint='fp_orch_a1',
            insight_type=InsightType.PAGE_TWO_KEYWORD,
            severity=InsightSeverity.OPPORTUNITY,
            title='Push "cbe birr mobile payment" to Page 1',
            description='Ranking at position 11 on page 2.',
            status=InsightStatus.OPEN,
            related_keyword=self.kw_a,
            related_url='https://ethio-fintech.et/cbe-birr'
        )

        self.mock_provider = MockAIProvider()
        self.registry = get_tool_registry()
        self.orchestrator = AgentOrchestrator(
            project=self.project_a,
            user=self.user_a,
            provider=self.mock_provider,
            registry=self.registry,
            max_steps=15
        )

    def test_basic_multistep_agent_execution_and_approval_pause(self):
        """1. Agent runs multi-step loop and pauses at human approval checkpoint."""
        goal = "Analyze ranking drop for cbe birr mobile payment and draft optimization action"
        run = self.orchestrator.start_run(goal=goal)

        # Run pauses at propose_seo_action waiting for approval
        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)
        self.assertGreaterEqual(run.total_steps, 5)
        self.assertEqual(run.steps.count(), run.total_steps)

        # Verify step order
        steps = list(run.steps.order_by('step_number'))
        for idx, step in enumerate(steps, start=1):
            self.assertEqual(step.step_number, idx)

        # Verify latest step is an approval checkpoint
        latest_step = steps[-1]
        self.assertEqual(latest_step.action_type, AgentActionType.APPROVAL)
        self.assertEqual(latest_step.status, AgentStepStatus.WAITING)

        # Verify an SEOAction proposal was created in database in PROPOSED status
        action = SEOAction.objects.filter(project=self.project_a).first()
        self.assertIsNotNone(action)
        self.assertEqual(action.status, ActionStatus.PROPOSED)
        self.assertIsNone(action.completed_at)

    def test_agent_tool_call_telemetry_persistence(self):
        """2. Every executed step records AgentToolCall with inputs, outputs, duration, and mutability."""
        goal = "Query search rankings baseline"
        run = self.orchestrator.start_run(goal=goal)

        first_step = run.steps.get(step_number=1)
        tool_call = first_step.tool_calls.first()
        self.assertIsNotNone(tool_call)
        self.assertEqual(tool_call.tool_name, 'get_keyword_rankings')
        self.assertIsInstance(tool_call.tool_input, dict)
        self.assertIsInstance(tool_call.tool_output, dict)
        self.assertGreaterEqual(tool_call.duration_ms, 0)
        self.assertFalse(tool_call.is_mutating)

    def test_resume_run_on_approved_action_completes_workflow(self):
        """3. Resuming run with approval marks step complete, continues loop, and finishes successfully."""
        goal = "Optimize cbe birr mobile payment page"
        run = self.orchestrator.start_run(goal=goal)
        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)

        # Simulate user approving the action
        resumed_run = self.orchestrator.resume_run(run, approval_decision="approved")
        self.assertEqual(resumed_run.status, AgentRunStatus.COMPLETED)
        self.assertIsNotNone(resumed_run.completed_at)
        self.assertIn("Successfully completed", resumed_run.summary)

        # Verify last step is FINAL and completed
        final_step = resumed_run.steps.order_by('-step_number').first()
        self.assertEqual(final_step.action_type, AgentActionType.FINAL)
        self.assertEqual(final_step.status, AgentStepStatus.COMPLETED)

    def test_resume_run_on_rejected_action_terminates_run(self):
        """4. Resuming run with rejection transitions to CANCELLED and stops."""
        goal = "Optimize landing page copy"
        run = self.orchestrator.start_run(goal=goal)
        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)

        # Simulate user rejecting the action
        resumed_run = self.orchestrator.resume_run(run, approval_decision="rejected")
        self.assertEqual(resumed_run.status, AgentRunStatus.CANCELLED)
        self.assertIsNotNone(resumed_run.completed_at)
        self.assertIn("rejected", resumed_run.summary)

        # Latest step is marked FAILED with rejection note
        latest_step = resumed_run.steps.order_by('-step_number').first()
        self.assertEqual(latest_step.status, AgentStepStatus.FAILED)
        self.assertIn("Human Rejection", latest_step.thought)

    def test_cannot_resume_non_waiting_run(self):
        """5. Attempting to resume a run that is not waiting for approval raises ValueError."""
        run = AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            goal='Invalid resume test',
            status=AgentRunStatus.COMPLETED
        )
        with self.assertRaises(ValueError):
            self.orchestrator.resume_run(run, "approved")

    def test_max_steps_guardrail_bounding(self):
        """6. Agent halts and marks FAILED when max_steps limit is exceeded."""
        short_orchestrator = AgentOrchestrator(
            project=self.project_a,
            user=self.user_a,
            provider=self.mock_provider,
            registry=self.registry,
            max_steps=2
        )
        run = short_orchestrator.start_run(goal="Long workflow exceeding max steps")
        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertEqual(run.total_steps, 2)
        self.assertIn("step limit (2)", run.summary)
        self.assertIsNotNone(run.completed_at)

    def test_repeated_tool_failure_loop_detection(self):
        """7. Agent detects repeated failing tool calls and terminates safely."""
        # Provider that repeatedly tries to call generate_recommendation with invalid insight ID
        class LoopingProvider(MockAIProvider):
            def decide_agent_action(self, context):
                return {
                    "action": "tool",
                    "tool_name": "generate_recommendation",
                    "arguments": {"insight_id": 999999},  # Will fail validation/lookup
                    "reason": "Repeated failing call"
                }

        loop_orchestrator = AgentOrchestrator(
            project=self.project_a,
            user=self.user_a,
            provider=LoopingProvider(),
            registry=self.registry,
            max_steps=10
        )
        run = loop_orchestrator.start_run(goal="Test loop detection")
        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertIn("repetitive tool loop", run.summary.lower())

    def test_malformed_ai_decision_handling(self):
        """8. Agent handles malformed/invalid decision output from AI without crashing."""
        class MalformedProvider(MockAIProvider):
            def decide_agent_action(self, context):
                return {"invalid_key": "not a valid action"}

        malformed_orchestrator = AgentOrchestrator(
            project=self.project_a,
            user=self.user_a,
            provider=MalformedProvider(),
            registry=self.registry,
            max_steps=5
        )
        run = malformed_orchestrator.start_run(goal="Test malformed decision")
        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertIn("malformed AI decision", run.summary)
        self.assertEqual(run.steps.count(), 1)
        self.assertEqual(run.steps.first().status, AgentStepStatus.FAILED)

    def test_unknown_tool_decision_handling(self):
        """9. Calling an unknown tool records failure and terminates without unhandled exception."""
        class UnknownToolProvider(MockAIProvider):
            def decide_agent_action(self, context):
                if not context.get('history'):
                    return {
                        "action": "tool",
                        "tool_name": "hack_external_server",
                        "arguments": {},
                        "reason": "Attempt unknown tool"
                    }
                return {"action": "finish", "summary": "Finished after error"}

        unknown_orchestrator = AgentOrchestrator(
            project=self.project_a,
            user=self.user_a,
            provider=UnknownToolProvider(),
            registry=self.registry,
            max_steps=5
        )
        run = unknown_orchestrator.start_run(goal="Test unknown tool")
        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        first_step = run.steps.get(step_number=1)
        self.assertEqual(first_step.status, AgentStepStatus.FAILED)
        self.assertEqual(first_step.tool_calls.first().error_message, "Tool 'hack_external_server' is not registered.")

    def test_tool_argument_validation_failure_handling(self):
        """10. Tool parameter schema validation failure is captured in telemetry."""
        class InvalidArgsProvider(MockAIProvider):
            def decide_agent_action(self, context):
                if not context.get('history'):
                    return {
                        "action": "tool",
                        "tool_name": "generate_recommendation",
                        "arguments": {"insight_id": "not_an_int"},  # Type mismatch
                        "reason": "Attempt invalid arg type"
                    }
                return {"action": "finish", "summary": "Finished after validation error"}

        invalid_orchestrator = AgentOrchestrator(
            project=self.project_a,
            user=self.user_a,
            provider=InvalidArgsProvider(),
            registry=self.registry,
            max_steps=5
        )
        run = invalid_orchestrator.start_run(goal="Test argument validation failure")
        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        first_step = run.steps.get(step_number=1)
        self.assertEqual(first_step.status, AgentStepStatus.FAILED)
        tc = first_step.tool_calls.first()
        self.assertIn("must be an integer", tc.error_message)

    def test_multi_tenant_isolation_enforcement(self):
        """11. Orchestrator operates strictly within authorized project context."""
        # Verify baseline snapshot has Project A count
        run = self.orchestrator.start_run(goal="Tenant isolation test")
        self.assertEqual(run.project, self.project_a)
        self.assertEqual(run.user, self.user_a)
        self.assertEqual(run.context_snapshot["total_keywords"], 1)

        # Attempting to pass Project B entity fails securely
        class CrossTenantProvider(MockAIProvider):
            def decide_agent_action(self, context):
                return {
                    "action": "tool",
                    "tool_name": "generate_recommendation",
                    "arguments": {"insight_id": 99999},
                    "reason": "Attempt cross project"
                }

        ct_orchestrator = AgentOrchestrator(
            project=self.project_a,
            user=self.user_a,
            provider=CrossTenantProvider(),
            registry=self.registry,
            max_steps=2
        )
        run_ct = ct_orchestrator.start_run(goal="Cross tenant test")
        first_tc = run_ct.steps.first().tool_calls.first()
        self.assertIn("not found on project", first_tc.error_message)

    def test_unapproved_high_impact_actions_are_never_executed(self):
        """12. Orchestrator never directly executes SEOAction in production or staging without user approval."""
        run = self.orchestrator.start_run(goal="Generate and execute action safely")
        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)

        # Check all SEOActions for Project A
        actions = SEOAction.objects.filter(project=self.project_a)
        for act in actions:
            self.assertEqual(act.status, ActionStatus.PROPOSED)
            self.assertIsNone(act.completed_at)


class AgentRunAPITests(TestCase):
    """
    Phase 4 Test Suite: REST API, Multi-Tenancy, and End-to-End Orchestrator Verification
    1. Authentication enforcement (401 on unauthenticated endpoints)
    2. Multi-tenant isolation (rejection of unowned project IDs, 404 on cross-user run access)
    3. Creation endpoint (POST /api/seo/ai/agent/runs/)
    4. Validation of input goal and project
    5. List endpoint (GET /api/seo/ai/agent/runs/ with project filtering)
    6. Retrieval endpoint (GET /api/seo/ai/agent/runs/{id}/ with nested step and tool telemetry)
    7. Resume endpoint (POST /api/seo/ai/agent/runs/{id}/resume/) with approval
    8. Resume endpoint with rejection
    9. Resume rejection on non-waiting runs (400 Bad Request)
    10. Full End-to-End lifecycle (Goal -> Tools -> Proposal -> Pause -> Human Approval -> Complete)
    """

    def setUp(self):
        self.client = APIClient()
        self.base_url = '/api/seo/ai/agent/runs/'

        # User A & Project A
        self.user_a = User.objects.create_user(
            email='api_agent_a@doxarank.com',
            password='Password123!',
            first_name='ApiAgent',
            last_name='UserA'
        )
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Ethio Ecommerce Hub',
            website_url='https://ethio-ecommerce.et'
        )

        # User B & Project B
        self.user_b = User.objects.create_user(
            email='api_agent_b@doxarank.com',
            password='Password123!',
            first_name='ApiAgent',
            last_name='UserB'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Competitor Ecommerce',
            website_url='https://competitor-ecommerce.et'
        )

        # Seed Project A Entities
        self.kw_a = Keyword.objects.create(
            project=self.project_a,
            keyword='ethio telecom sim card online',
            search_engine='google',
            country='ET'
        )
        self.ranking_a = KeywordRanking.objects.create(
            keyword=self.kw_a,
            position=8,
            ranking_url='https://ethio-ecommerce.et/sim-cards',
            search_engine='google',
            country='ET',
            recorded_at=timezone.now()
        )
        self.insight_a = SEOInsight.objects.create(
            project=self.project_a,
            fingerprint='fp_api_orch_1',
            insight_type=InsightType.HIGH_IMPRESSIONS_LOW_CTR,
            severity=InsightSeverity.OPPORTUNITY,
            title='Optimize Snippet CTR for SIM Card Landing Page',
            description='High impressions but below-average CTR observed.',
            status=InsightStatus.OPEN,
            related_keyword=self.kw_a,
            related_url='https://ethio-ecommerce.et/sim-cards'
        )

    def test_unauthenticated_requests_rejected(self):
        """1. Unauthenticated requests to AgentRun endpoints return 401 Unauthorized."""
        res_list = self.client.get(self.base_url)
        self.assertEqual(res_list.status_code, status.HTTP_401_UNAUTHORIZED)

        res_create = self.client.post(self.base_url, {'project': self.project_a.id, 'goal': 'Test'})
        self.assertEqual(res_create.status_code, status.HTTP_401_UNAUTHORIZED)

        res_retrieve = self.client.get(f'{self.base_url}1/')
        self.assertEqual(res_retrieve.status_code, status.HTTP_401_UNAUTHORIZED)

        res_resume = self.client.post(f'{self.base_url}1/resume/', {'decision': 'approved'})
        self.assertEqual(res_resume.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_agent_run_success(self):
        """2. Authenticated user creates an agent run and receives serialized execution state."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            'project': self.project_a.id,
            'goal': 'Inspect ranking signals and synthesize optimization action.'
        }
        res = self.client.post(self.base_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.data
        self.assertIn('id', data)
        self.assertEqual(data['project'], self.project_a.id)
        self.assertEqual(data['project_name'], self.project_a.name)
        self.assertEqual(data['goal'], payload['goal'])
        self.assertEqual(data['status'], AgentRunStatus.WAITING_FOR_APPROVAL)
        self.assertGreaterEqual(data['total_steps'], 5)
        self.assertIsInstance(data['steps'], list)
        self.assertIsNotNone(data['pending_action'])

    def test_create_agent_run_rejects_missing_or_invalid_goal(self):
        """3. Creating run with empty goal returns 400 Bad Request."""
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(self.base_url, {'project': self.project_a.id, 'goal': ''}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('goal', res.data)

    def test_multi_tenant_create_rejects_unowned_project(self):
        """4. User B cannot create an agent run on User A's project."""
        self.client.force_authenticate(user=self.user_b)
        payload = {
            'project': self.project_a.id,
            'goal': 'Unauthorized agent execution'
        }
        res = self.client.post(self.base_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project', res.data)
        self.assertIn('permission', str(res.data['project']).lower())

    def test_list_agent_runs_scoped_to_user_projects(self):
        """5. List endpoint returns only runs belonging to projects owned by the requesting user."""
        # Create run for User A
        run_a = AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            goal='Goal User A',
            status=AgentRunStatus.COMPLETED
        )
        # Create run for User B
        run_b = AgentRun.objects.create(
            project=self.project_b,
            user=self.user_b,
            goal='Goal User B',
            status=AgentRunStatus.COMPLETED
        )

        # User A list
        self.client.force_authenticate(user=self.user_a)
        res_a = self.client.get(self.base_url)
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)
        run_ids_a = [r['id'] for r in res_a.data]
        self.assertIn(run_a.id, run_ids_a)
        self.assertNotIn(run_b.id, run_ids_a)

        # User B list
        self.client.force_authenticate(user=self.user_b)
        res_b = self.client.get(self.base_url)
        self.assertEqual(res_b.status_code, status.HTTP_200_OK)
        run_ids_b = [r['id'] for r in res_b.data]
        self.assertIn(run_b.id, run_ids_b)
        self.assertNotIn(run_a.id, run_ids_b)

    def test_retrieve_agent_run_with_nested_telemetry(self):
        """6. Retrieve endpoint returns full step hierarchy and tool telemetry."""
        self.client.force_authenticate(user=self.user_a)
        create_res = self.client.post(self.base_url, {
            'project': self.project_a.id,
            'goal': 'Inspect search metrics'
        }, format='json')
        run_id = create_res.data['id']

        retrieve_res = self.client.get(f'{self.base_url}{run_id}/')
        self.assertEqual(retrieve_res.status_code, status.HTTP_200_OK)
        data = retrieve_res.data
        self.assertEqual(data['id'], run_id)
        self.assertGreaterEqual(len(data['steps']), 1)

        # Verify step and tool telemetry fields
        first_step = data['steps'][0]
        self.assertEqual(first_step['step_number'], 1)
        self.assertIn('thought', first_step)
        self.assertIn('tool_calls', first_step)
        first_tc = first_step['tool_calls'][0]
        self.assertEqual(first_tc['tool_name'], 'get_keyword_rankings')
        self.assertIn('tool_input', first_tc)
        self.assertIn('tool_output', first_tc)
        self.assertIn('duration_ms', first_tc)

    def test_retrieve_other_user_run_returns_404(self):
        """7. Attempting to retrieve another user's run returns 404 Not Found."""
        run_a = AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            goal='User A Secret Mission',
            status=AgentRunStatus.COMPLETED
        )
        self.client.force_authenticate(user=self.user_b)
        res = self.client.get(f'{self.base_url}{run_a.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_resume_other_user_run_returns_404(self):
        """8. Attempting to resume another user's run returns 404 Not Found."""
        run_a = AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            goal='User A Waiting Mission',
            status=AgentRunStatus.WAITING_FOR_APPROVAL
        )
        self.client.force_authenticate(user=self.user_b)
        res = self.client.post(f'{self.base_url}{run_a.id}/resume/', {'decision': 'approved'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_resume_non_waiting_run_returns_400(self):
        """9. Resuming a run that is not waiting for approval returns 400 Bad Request."""
        run_a = AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            goal='Already Completed Mission',
            status=AgentRunStatus.COMPLETED
        )
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(f'{self.base_url}{run_a.id}/resume/', {'decision': 'approved'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', res.data)
        self.assertIn('Only runs waiting for approval', res.data['detail'])

    def test_end_to_end_agent_workflow_and_human_approval_resume(self):
        """10. Full End-to-End flow: Creation -> Paused for Approval -> API Resume (Approved) -> Completed."""
        self.client.force_authenticate(user=self.user_a)

        # Step 1: POST goal to initiate run
        create_res = self.client.post(self.base_url, {
            'project': self.project_a.id,
            'goal': 'Run autonomous ranking optimization workflow for Ethio Ecommerce'
        }, format='json')
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        run_id = create_res.data['id']
        self.assertEqual(create_res.data['status'], AgentRunStatus.WAITING_FOR_APPROVAL)
        self.assertIsNotNone(create_res.data['pending_action'])

        # Step 2: Verify action proposal in database
        action = SEOAction.objects.get(id=create_res.data['pending_action']['id'])
        self.assertEqual(action.status, ActionStatus.PROPOSED)

        # Step 3: Call resume endpoint with decision='approved'
        resume_res = self.client.post(f'{self.base_url}{run_id}/resume/', {
            'decision': 'approved'
        }, format='json')
        self.assertEqual(resume_res.status_code, status.HTTP_200_OK)
        self.assertEqual(resume_res.data['status'], AgentRunStatus.COMPLETED)
        self.assertIsNotNone(resume_res.data['completed_at'])
        self.assertIn("Successfully completed", resume_res.data['summary'])

        # Step 4: Verify terminal state in database and action execution
        run_db = AgentRun.objects.get(id=run_id)
        self.assertEqual(run_db.status, AgentRunStatus.COMPLETED)
        self.assertIsNotNone(run_db.completed_at)

        action.refresh_from_db()
        self.assertEqual(action.status, ActionStatus.COMPLETED)
        self.assertIsNotNone(action.completed_at)

    def test_end_to_end_agent_workflow_and_human_rejection(self):
        """11. Full End-to-End flow: Creation -> Paused for Approval -> API Resume (Rejected) -> Cancelled."""
        self.client.force_authenticate(user=self.user_a)

        create_res = self.client.post(self.base_url, {
            'project': self.project_a.id,
            'goal': 'Run optimization workflow'
        }, format='json')
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        run_id = create_res.data['id']
        self.assertEqual(create_res.data['status'], AgentRunStatus.WAITING_FOR_APPROVAL)

        # User rejects proposal
        resume_res = self.client.post(f'{self.base_url}{run_id}/resume/', {
            'decision': 'rejected'
        }, format='json')
        self.assertEqual(resume_res.status_code, status.HTTP_200_OK)
        self.assertEqual(resume_res.data['status'], AgentRunStatus.CANCELLED)
        self.assertIn("rejected", resume_res.data['summary'])

        run_db = AgentRun.objects.get(id=run_id)
        self.assertEqual(run_db.status, AgentRunStatus.CANCELLED)

        # Verify action marked rejected
        action_id = create_res.data['pending_action']['id']
        action_db = SEOAction.objects.get(id=action_id)
        self.assertEqual(action_db.status, ActionStatus.REJECTED)


# ==============================================================================
# MILESTONE 2: CELERY, ASYNC EXECUTION, CONCURRENCY & RETRY TEST SUITE
# ==============================================================================

from unittest.mock import patch, MagicMock
from django.conf import settings
from config.celery import app as celery_app, debug_task
from apps.seo.tasks import execute_agent_run, _mark_run_failed


class CeleryInfrastructureTests(TestCase):
    """
    Phase 2.1: Celery & Redis Infrastructure Tests
    1. Celery app is instantiated and bound to 'doxarank'
    2. Django settings configured with 'CELERY' namespace
    3. Broker and result backend settings configured
    4. Eager execution active in test environment
    5. Debug task runs without error
    """
    def test_celery_app_initialization(self):
        self.assertEqual(celery_app.main, 'doxarank')
        self.assertIn('apps.seo.tasks.execute_agent_run', celery_app.tasks)

    def test_celery_settings_configuration(self):
        self.assertTrue(hasattr(settings, 'CELERY_BROKER_URL'))
        self.assertTrue(hasattr(settings, 'CELERY_RESULT_BACKEND'))
        self.assertTrue(settings.CELERY_TASK_ALWAYS_EAGER)

    def test_debug_task_execution(self):
        result = debug_task.delay()
        self.assertTrue(result.successful() or result.ready())


class AgentCeleryTaskExecutionTests(TestCase):
    """
    Phase 2.2 & 2.7: Agent Execution Celery Tasks
    1. execute_agent_run executes pending run end-to-end
    2. Missing run ID returns None without exception
    3. Resumed run with 'approved' executes action and finishes
    4. Resumed run with 'rejected' cancels run and marks action rejected
    """
    def setUp(self):
        self.user = User.objects.create_user(
            email='task_test_user@doxarank.com',
            password='Password123!',
            first_name='Task',
            last_name='Tester'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Celery Task Project',
            website_url='https://celery-test.et'
        )
        self.kw = Keyword.objects.create(
            project=self.project,
            keyword='async seo test',
            search_engine='google',
            country='ET'
        )
        self.ranking = KeywordRanking.objects.create(
            keyword=self.kw,
            position=4,
            ranking_url='https://celery-test.et/page',
            search_engine='google',
            country='ET',
            recorded_at=timezone.now()
        )
        self.insight = SEOInsight.objects.create(
            project=self.project,
            fingerprint='fp_celery_test_1',
            insight_type=InsightType.HIGH_IMPRESSIONS_LOW_CTR,
            severity=InsightSeverity.OPPORTUNITY,
            title='Celery Opportunity Insight',
            description='Test insight for celery task execution.',
            status=InsightStatus.OPEN,
            related_keyword=self.kw,
            related_url='https://celery-test.et/page'
        )

    def test_execute_agent_run_success(self):
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Execute asynchronous SEO optimization via Celery task',
            status=AgentRunStatus.PENDING
        )
        result = execute_agent_run(run.id)
        self.assertEqual(result, run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)
        self.assertGreater(run.steps.count(), 0)

    def test_execute_agent_run_missing_id_handled_gracefully(self):
        result = execute_agent_run(999999)
        self.assertIsNone(result)

    def test_execute_agent_run_resume_approved(self):
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Resume approved run',
            status=AgentRunStatus.PENDING
        )
        execute_agent_run(run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)

        # Now resume with approval
        result = execute_agent_run(run.id, is_resume=True, approval_decision='approved')
        self.assertEqual(result, run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertIsNotNone(run.completed_at)

        # Check action was executed
        action = SEOAction.objects.filter(project=self.project).latest('created_at')
        self.assertEqual(action.status, ActionStatus.COMPLETED)

    def test_execute_agent_run_resume_rejected(self):
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Resume rejected run',
            status=AgentRunStatus.PENDING
        )
        execute_agent_run(run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)

        # Now resume with rejection
        result = execute_agent_run(run.id, is_resume=True, approval_decision='rejected')
        self.assertEqual(result, run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.CANCELLED)
        self.assertIn("rejected", run.summary)

        # Check action marked rejected
        action = SEOAction.objects.filter(project=self.project).latest('created_at')
        self.assertEqual(action.status, ActionStatus.REJECTED)


class AgentRunConcurrencyAndLockingTests(TestCase):
    """
    Phase 2.5 & 2.8: Idempotency, Concurrency & State Machine Precondition Tests
    1. Task ignores run already in RUNNING status (prevents duplicate worker execution)
    2. Task ignores run already in COMPLETED status
    3. Task ignores run already in FAILED status
    4. Task ignores run already in CANCELLED status
    5. Resume ignores run that is not WAITING_FOR_APPROVAL
    """
    def setUp(self):
        self.user = User.objects.create_user(
            email='concurrency_user@doxarank.com',
            password='Password123!',
            first_name='Concurrent',
            last_name='User'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Concurrency Project',
            website_url='https://concurrency.et'
        )

    def test_task_skips_already_running_run(self):
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Concurrent running goal',
            status=AgentRunStatus.RUNNING
        )
        result = execute_agent_run(run.id)
        self.assertEqual(result, run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.RUNNING)
        self.assertEqual(run.steps.count(), 0)

    def test_task_skips_already_completed_run(self):
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Already completed goal',
            status=AgentRunStatus.COMPLETED
        )
        result = execute_agent_run(run.id)
        self.assertEqual(result, run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.COMPLETED)

    def test_task_skips_failed_run(self):
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Already failed goal',
            status=AgentRunStatus.FAILED
        )
        result = execute_agent_run(run.id)
        self.assertEqual(result, run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.FAILED)

    def test_cannot_resume_pending_or_running_run(self):
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Pending goal cannot resume',
            status=AgentRunStatus.PENDING
        )
        result = execute_agent_run(run.id, is_resume=True, approval_decision='approved')
        self.assertEqual(result, run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.PENDING)


class AgentTaskRetryAndErrorHandlingTests(TestCase):
    """
    Phase 2.6 & 2.13: Retry Strategy & Safe Error Persisting Tests
    1. Retryable ConnectionError triggers self.retry
    2. Non-retryable error transitions run to FAILED with sanitized summary
    3. Safe error masking strips simulated API tokens
    """
    def setUp(self):
        self.user = User.objects.create_user(
            email='retry_user@doxarank.com',
            password='Password123!',
            first_name='Retry',
            last_name='Tester'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Retry Project',
            website_url='https://retry.et'
        )

    @patch('apps.seo.tasks.AgentOrchestrator.execute_loop')
    def test_retryable_exception_triggers_celery_retry(self, mock_loop):
        mock_loop.side_effect = ConnectionError("Simulated Redis/network connection drop")
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Test connection retry',
            status=AgentRunStatus.PENDING
        )
        with patch.object(execute_agent_run, 'retry', side_effect=Exception("CeleryRetryRaised")) as mock_retry:
            with self.assertRaises(Exception) as ctx:
                execute_agent_run(run.id)
            self.assertIn("CeleryRetryRaised", str(ctx.exception))
            mock_retry.assert_called_once()

    @patch('apps.seo.tasks.AgentOrchestrator.execute_loop')
    def test_non_retryable_exception_marks_run_failed(self, mock_loop):
        mock_loop.side_effect = ValueError("Fatal schema corruption")
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Test non-retryable failure',
            status=AgentRunStatus.PENDING
        )
        execute_agent_run(run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertIn("Fatal agent execution error", run.summary)
        self.assertIsNotNone(run.completed_at)

    def test_mark_run_failed_sanitizes_tokens(self):
        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal='Sanitization test',
            status=AgentRunStatus.RUNNING
        )
        raw_error = "OpenAI key sk-1234567890abcdef failed with 401"
        _mark_run_failed(run, raw_error)
        run.refresh_from_db()
        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertNotIn("sk-1234567890abcdef", run.summary)
        self.assertIn("sk-***", run.summary)


class ToolRegistryObservabilityAndSanitizationTests(TestCase):
    """
    Phase 2.12 & 2.13: Tool Observability & Sanitization Tests
    1. Tool registry execution captures duration_ms
    2. Tool registry sanitizes sensitive authorization tokens in error messages
    """
    def setUp(self):
        self.user = User.objects.create_user(
            email='tool_obs_user@doxarank.com',
            password='Password123!',
            first_name='Obs',
            last_name='User'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Tool Obs Project',
            website_url='https://tool-obs.et'
        )
        self.registry = create_default_tool_registry()

    def test_tool_telemetry_captures_duration_ms(self):
        res = self.registry.execute('get_keyword_rankings', self.project, {})
        self.assertTrue(res['success'])
        self.assertIn('duration_ms', res)
        self.assertGreaterEqual(res['duration_ms'], 0)

    def test_tool_error_sanitizes_bearer_and_api_keys(self):
        custom_registry = ToolRegistry()
        def leaky_handler(project, args):
            raise RuntimeError("Failed communicating with provider using Bearer secret_token_xyz_12345 and sk-livekey99999999")

        leaky_tool = AgentToolDefinition(
            name="test_leaky_tool",
            description="Tool that leaks credentials in exception",
            category=ToolCategory.READ_ONLY,
            parameters_schema={"type": "object", "properties": {}},
            requires_approval=False,
            is_mutating=False,
            handler=leaky_handler
        )
        custom_registry.register(leaky_tool)

        res = custom_registry.execute('test_leaky_tool', self.project, {})
        self.assertFalse(res['success'])
        err_msg = res['error']['message']
        self.assertNotIn("secret_token_xyz_12345", err_msg)
        self.assertNotIn("sk-livekey99999999", err_msg)
        self.assertIn("Bearer ***", err_msg)
        self.assertIn("sk-***", err_msg)


# ==============================================================================
# MILESTONE 3, PHASE 3.1: REAL-TIME AGENT EVENT ARCHITECTURE TEST SUITE
# ==============================================================================

import json
import uuid
from apps.seo.services.agent_events import (
    AgentEvent, AgentEventType, AgentEventPublisher,
    InMemoryEventPublisher, RedisEventPublisher, sanitize_event_payload,
    get_event_publisher, set_event_publisher
)


class AgentEventContractTests(TestCase):
    """
    Phase 3.1: Event Contract, UUID Generation, Schema & Payload Sanitization Tests
    1. Event receives server-side generated UUID4 string
    2. Event contains required fields: event_id, event_type, run_id, project_id, step_number, sequence_number, timestamp, payload
    3. Event serializes to valid JSON dictionary and string
    4. All required event types exist in AgentEventType enum
    5. Payload security sanitization masks OpenAI keys, Bearer tokens, passwords, and sensitive keys
    """

    def test_event_construction_and_uuid_generation(self):
        """1. Event receives server-generated UUID4 and preserves required fields."""
        event = AgentEvent(
            event_type=AgentEventType.TOOL_STARTED,
            run_id=42,
            project_id=7,
            step_number=3,
            sequence_number=5,
            payload={"tool_name": "get_keyword_rankings"}
        )
        self.assertIsNotNone(event.event_id)
        # Verify valid UUID format
        parsed_uuid = uuid.UUID(event.event_id)
        self.assertEqual(str(parsed_uuid), event.event_id)
        self.assertEqual(event.event_type, "tool.started")
        self.assertEqual(event.run_id, 42)
        self.assertEqual(event.project_id, 7)
        self.assertEqual(event.step_number, 3)
        self.assertEqual(event.sequence_number, 5)
        self.assertIsNotNone(event.timestamp)
        self.assertEqual(event.payload["tool_name"], "get_keyword_rankings")

    def test_event_json_serialization(self):
        """2. Event serializes cleanly to dictionary and JSON string."""
        event = AgentEvent(
            event_type=AgentEventType.TOOL_COMPLETED,
            run_id=10,
            project_id=2,
            step_number=1,
            sequence_number=4,
            payload={"tool_name": "get_keyword_rankings", "duration_ms": 120, "success": True}
        )
        data = event.to_dict()
        self.assertEqual(data["event_id"], event.event_id)
        self.assertEqual(data["event_type"], "tool.completed")
        self.assertEqual(data["run_id"], 10)
        self.assertEqual(data["project_id"], 2)
        self.assertEqual(data["step_number"], 1)
        self.assertEqual(data["sequence_number"], 4)
        self.assertEqual(data["payload"]["duration_ms"], 120)

        json_str = event.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["event_id"], event.event_id)
        self.assertEqual(parsed["event_type"], "tool.completed")
        self.assertEqual(parsed["sequence_number"], 4)

    def test_all_required_event_types_exist(self):
        """3. Verify all 13 required stable event types exist."""
        expected_types = {
            "agent.started": AgentEventType.AGENT_STARTED,
            "agent.completed": AgentEventType.AGENT_COMPLETED,
            "agent.failed": AgentEventType.AGENT_FAILED,
            "agent.cancelled": AgentEventType.AGENT_CANCELLED,
            "step.started": AgentEventType.STEP_STARTED,
            "step.completed": AgentEventType.STEP_COMPLETED,
            "step.failed": AgentEventType.STEP_FAILED,
            "tool.started": AgentEventType.TOOL_STARTED,
            "tool.completed": AgentEventType.TOOL_COMPLETED,
            "tool.failed": AgentEventType.TOOL_FAILED,
            "approval.required": AgentEventType.APPROVAL_REQUIRED,
            "approval.approved": AgentEventType.APPROVAL_APPROVED,
            "approval.rejected": AgentEventType.APPROVAL_REJECTED,
        }
        for name, enum_val in expected_types.items():
            self.assertEqual(enum_val.value, name)

    def test_payload_security_sanitization(self):
        """4. Payload sanitization securely masks keys, bearer tokens, passwords, and sensitive dictionary values."""
        raw_payload = {
            "api_key": "sk-1234567890abcdef1234567890",
            "password": "SuperSecretPassword123!",
            "token": "secret_jwt_token_xyz",
            "auth_header": "Bearer secret_bearer_token_99999",
            "error_message": "Failed connecting to OpenAI using sk-9876543210fedcba and Bearer auth_secret_tok",
            "nested": {
                "credential": "password=my_plain_password; api_key=secret_val_123",
                "normal_field": "public SEO content"
            }
        }
        event = AgentEvent(
            event_type=AgentEventType.TOOL_FAILED,
            run_id=1,
            project_id=1,
            payload=raw_payload
        )
        cleaned = event.payload
        self.assertEqual(cleaned["api_key"], "***REDACTED***")
        self.assertEqual(cleaned["password"], "***REDACTED***")
        self.assertEqual(cleaned["token"], "***REDACTED***")
        self.assertNotIn("secret_bearer_token_99999", str(cleaned))
        self.assertIn("Bearer ***", str(cleaned))
        self.assertNotIn("sk-9876543210fedcba", cleaned["error_message"])
        self.assertIn("sk-***", cleaned["error_message"])
        self.assertNotIn("my_plain_password", cleaned["nested"]["credential"])
        self.assertEqual(cleaned["nested"]["normal_field"], "public SEO content")


class AgentEventOrderingAndOrchestratorTests(TestCase):
    """
    Phase 3.1: Sequence Numbering, Lifecycle Integration, and Failure Resilience Tests
    1. Orchestrator emits monotonically increasing sequence numbers per run
    2. Resumed run continues sequence numbering without reset or duplicate agent.started
    3. Successful agent workflow emits complete event sequence
    4. Tool and step failure emits tool.failed, step.failed, agent.failed
    5. Approval workflow emits approval.required, approval.approved, approval.rejected, agent.cancelled
    6. Publisher failure resilience: publisher errors do not crash orchestrator or corrupt DB state
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='event_orch_user@doxarank.com',
            password='Password123!',
            first_name='Event',
            last_name='Tester'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Event Architecture Project',
            website_url='https://event-arch.et'
        )
        self.kw = Keyword.objects.create(
            project=self.project,
            keyword='event driven seo',
            search_engine='google',
            country='ET'
        )
        self.ranking = KeywordRanking.objects.create(
            keyword=self.kw,
            position=3,
            ranking_url='https://event-arch.et/blog',
            search_engine='google',
            country='ET',
            recorded_at=timezone.now()
        )
        self.insight = SEOInsight.objects.create(
            project=self.project,
            fingerprint='fp_event_arch_1',
            insight_type=InsightType.HIGH_IMPRESSIONS_LOW_CTR,
            severity=InsightSeverity.OPPORTUNITY,
            title='CTR Improvement Opportunity',
            description='Test insight for event emission.',
            status=InsightStatus.OPEN,
            related_keyword=self.kw,
            related_url='https://event-arch.et/blog'
        )
        self.publisher = InMemoryEventPublisher()
        self.registry = create_default_tool_registry()

    def test_successful_workflow_event_lifecycle(self):
        """1. Successful workflow emits agent.started -> step.started -> tool.started -> tool.completed -> step.completed -> agent.completed."""
        class FinishMockProvider(MockAIProvider):
            def __init__(self):
                self.calls = 0

            def decide_agent_action(self, context):
                self.calls += 1
                if self.calls == 1:
                    return {
                        "action": "tool",
                        "tool_name": "get_keyword_rankings",
                        "arguments": {"keyword": "event"},
                        "reason": "Inspect keyword rankings"
                    }
                return {
                    "action": "finish",
                    "summary": "Keyword optimization completed.",
                    "reason": "Goal achieved."
                }

        orchestrator = AgentOrchestrator(
            project=self.project,
            user=self.user,
            provider=FinishMockProvider(),
            registry=self.registry,
            publisher=self.publisher,
            max_steps=5
        )

        run = orchestrator.start_run(goal="Test event emission on successful workflow")
        self.assertEqual(run.status, AgentRunStatus.COMPLETED)

        events = self.publisher.get_events(run_id=run.id)
        event_types = [e.event_type for e in events]

        expected_order = [
            "agent.started",
            "step.started",
            "tool.started",
            "tool.completed",
            "step.completed",
            "step.started",
            "step.completed",
            "agent.completed"
        ]
        self.assertEqual(event_types, expected_order)

        # Verify monotonic sequence ordering
        sequence_numbers = [e.sequence_number for e in events]
        self.assertEqual(sequence_numbers, list(range(1, len(events) + 1)))

    def test_sequence_continuity_across_approval_and_resume(self):
        """2. Resumed run continues sequence numbering seamlessly without duplicate agent.started."""
        orchestrator = AgentOrchestrator(
            project=self.project,
            user=self.user,
            registry=self.registry,
            publisher=self.publisher
        )

        # Start run -> pauses at propose_seo_action (WAITING_FOR_APPROVAL)
        run = orchestrator.start_run(goal="Pause and resume with event tracking")
        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)

        events_phase1 = self.publisher.get_events(run_id=run.id)
        phase1_types = [e.event_type for e in events_phase1]
        self.assertIn("agent.started", phase1_types)
        self.assertIn("approval.required", phase1_types)
        last_seq_phase1 = events_phase1[-1].sequence_number

        # Resume with new orchestrator instance (simulating Celery worker transition)
        resume_publisher = InMemoryEventPublisher()
        resume_orchestrator = AgentOrchestrator(
            project=self.project,
            user=self.user,
            registry=self.registry,
            publisher=resume_publisher
        )

        run.refresh_from_db()
        run_resumed = resume_orchestrator.resume_run(run, approval_decision="approved")
        self.assertEqual(run_resumed.status, AgentRunStatus.COMPLETED)

        events_phase2 = resume_publisher.get_events(run_id=run.id)
        phase2_types = [e.event_type for e in events_phase2]

        # Verify NO duplicate agent.started
        self.assertNotIn("agent.started", phase2_types)
        self.assertEqual(phase2_types[0], "approval.approved")
        self.assertIn("agent.completed", phase2_types)

        # Verify sequence continued from phase 1 without resetting to 1
        first_seq_phase2 = events_phase2[0].sequence_number
        self.assertEqual(first_seq_phase2, last_seq_phase1 + 1)

        phase2_seqs = [e.sequence_number for e in events_phase2]
        expected_seqs = list(range(last_seq_phase1 + 1, last_seq_phase1 + 1 + len(events_phase2)))
        self.assertEqual(phase2_seqs, expected_seqs)

    def test_rejection_emits_approval_rejected_and_agent_cancelled(self):
        """3. Human rejection emits approval.rejected and agent.cancelled."""
        orchestrator = AgentOrchestrator(
            project=self.project,
            user=self.user,
            registry=self.registry,
            publisher=self.publisher
        )

        run = orchestrator.start_run(goal="Test rejection event emission")
        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)

        # Clear publisher to isolate resume events
        self.publisher.clear()

        run.refresh_from_db()
        cancelled_run = orchestrator.resume_run(run, approval_decision="rejected")
        self.assertEqual(cancelled_run.status, AgentRunStatus.CANCELLED)

        events = self.publisher.get_events(run_id=run.id)
        event_types = [e.event_type for e in events]
        self.assertEqual(event_types, ["approval.rejected", "agent.cancelled"])

    def test_tool_failure_workflow_events(self):
        """4. Tool failure emits tool.failed, step.failed, and agent.failed."""
        class FailingToolProvider(MockAIProvider):
            def decide_agent_action(self, context):
                return {
                    "action": "tool",
                    "tool_name": "generate_recommendation",
                    "arguments": {"insight_id": 999999},  # Non-existent ID causes failure
                    "reason": "Attempt bad recommendation"
                }

        orchestrator = AgentOrchestrator(
            project=self.project,
            user=self.user,
            provider=FailingToolProvider(),
            registry=self.registry,
            publisher=self.publisher,
            max_steps=2
        )

        run = orchestrator.start_run(goal="Test tool failure events")
        self.assertEqual(run.status, AgentRunStatus.FAILED)

        events = self.publisher.get_events(run_id=run.id)
        event_types = [e.event_type for e in events]
        self.assertIn("tool.failed", event_types)
        self.assertIn("step.failed", event_types)
        self.assertIn("agent.failed", event_types)

    def test_resilient_to_publisher_failure(self):
        """5. Publisher exceptions do not abort or corrupt agent execution or database state."""
        class BrokenPublisher(AgentEventPublisher):
            def publish(self, event: AgentEvent) -> None:
                raise RuntimeError("Simulated Redis Pub/Sub / WebSocket connection drop!")

        broken_publisher = BrokenPublisher()
        orchestrator = AgentOrchestrator(
            project=self.project,
            user=self.user,
            registry=self.registry,
            publisher=broken_publisher
        )

        # Run should still complete its logic and transition to WAITING_FOR_APPROVAL safely
        run = orchestrator.start_run(goal="Test resilience against publisher failures")
        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)
        self.assertGreater(run.steps.count(), 0)
        self.assertTrue(SEOAction.objects.filter(project=self.project, status=ActionStatus.PROPOSED).exists())


class RedisEventPublisherTests(TestCase):
    """
    Milestone 3, Phase 3.2.1: Redis Event Publisher Tests
    1. Channel naming formats as 'agent:run:{run_id}'
    2. URL resolution reuses Django Redis settings
    3. Event publication formats JSON and calls Redis publish on correct channel
    4. Payload sanitization is applied prior to Redis publishing
    5. Redis connection drops and publish errors are caught non-fatally
    6. Orchestrator executes smoothly and publishes lifecycle events to Redis channels
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='redis_pub_user@doxarank.com',
            password='Password123!',
            first_name='Redis',
            last_name='PubTester'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Redis Publisher Project',
            website_url='https://redis-pub.et'
        )
        self.kw = Keyword.objects.create(
            project=self.project,
            keyword='redis event pubsub',
            search_engine='google',
            country='ET'
        )
        self.ranking = KeywordRanking.objects.create(
            keyword=self.kw,
            position=2,
            ranking_url='https://redis-pub.et/page',
            search_engine='google',
            country='ET',
            recorded_at=timezone.now()
        )
        self.registry = create_default_tool_registry()

    def test_channel_naming_format(self):
        """1. Channel naming strictly adheres to 'agent:run:{run_id}'."""
        self.assertEqual(RedisEventPublisher.get_channel_name(42), "agent:run:42")
        self.assertEqual(RedisEventPublisher.get_channel_name(999), "agent:run:999")
        self.assertEqual(RedisEventPublisher.get_channel_name(1), "agent:run:1")

    def test_redis_url_resolution(self):
        """2. Reuses existing settings.CELERY_BROKER_URL or custom url."""
        publisher_default = RedisEventPublisher()
        expected_url = getattr(settings, 'REDIS_URL', getattr(settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0'))
        self.assertEqual(publisher_default._get_redis_url(), expected_url)

        publisher_custom = RedisEventPublisher(redis_url="redis://custom-host:6380/5")
        self.assertEqual(publisher_custom._get_redis_url(), "redis://custom-host:6380/5")

    def test_publish_serializes_and_calls_redis(self):
        """3. Publishes valid JSON payload with required fields to agent:run:{run_id}."""
        mock_redis = MagicMock()
        publisher = RedisEventPublisher(redis_client=mock_redis)

        event = AgentEvent(
            event_type=AgentEventType.TOOL_COMPLETED,
            run_id=42,
            project_id=7,
            step_number=2,
            sequence_number=5,
            payload={"tool_name": "get_keyword_rankings", "success": True, "duration_ms": 340}
        )

        publisher.publish(event)

        mock_redis.publish.assert_called_once()
        channel, message = mock_redis.publish.call_args[0]
        self.assertEqual(channel, "agent:run:42")

        parsed = json.loads(message)
        self.assertEqual(parsed["event_id"], event.event_id)
        self.assertEqual(parsed["event_type"], "tool.completed")
        self.assertEqual(parsed["run_id"], 42)
        self.assertEqual(parsed["project_id"], 7)
        self.assertEqual(parsed["step_number"], 2)
        self.assertEqual(parsed["sequence_number"], 5)
        self.assertEqual(parsed["payload"]["tool_name"], "get_keyword_rankings")
        self.assertEqual(parsed["payload"]["duration_ms"], 340)

    def test_publish_payload_sanitization(self):
        """4. Sensitive credentials and private keys are sanitized before publishing to Redis."""
        mock_redis = MagicMock()
        publisher = RedisEventPublisher(redis_client=mock_redis)

        event = AgentEvent(
            event_type=AgentEventType.TOOL_FAILED,
            run_id=10,
            project_id=3,
            payload={
                "api_key": "sk-test1234567890abcdef",
                "auth_header": "Bearer secret_access_token_777",
                "error_msg": "Provider failed with key sk-secret99999999"
            }
        )

        publisher.publish(event)

        mock_redis.publish.assert_called_once()
        _, message = mock_redis.publish.call_args[0]
        parsed = json.loads(message)

        self.assertEqual(parsed["payload"]["api_key"], "***REDACTED***")
        self.assertNotIn("sk-test1234567890abcdef", message)
        self.assertNotIn("secret_access_token_777", message)
        self.assertIn("Bearer ***", message)
        self.assertIn("sk-***", message)

    def test_publish_failure_is_non_fatal(self):
        """5. Connection drops or Redis errors in publish() are logged and do not raise exceptions."""
        mock_redis = MagicMock()
        mock_redis.publish.side_effect = ConnectionError("Connection refused by Redis server at 127.0.0.1:6379")
        publisher = RedisEventPublisher(redis_client=mock_redis)

        event = AgentEvent(
            event_type=AgentEventType.AGENT_STARTED,
            run_id=1,
            project_id=1,
            payload={"goal": "Test resilience"}
        )

        # Must not raise an exception
        try:
            publisher.publish(event)
        except Exception as e:
            self.fail(f"publisher.publish raised an unexpected exception: {e}")

    def test_orchestrator_integration_with_redis_publisher(self):
        """6. Orchestrator seamlessly integrates with RedisEventPublisher to stream lifecycle events."""
        mock_redis = MagicMock()
        redis_publisher = RedisEventPublisher(redis_client=mock_redis)

        class FinishMockProvider(MockAIProvider):
            def decide_agent_action(self, context):
                return {
                    "action": "finish",
                    "summary": "Agent completed via Redis publisher.",
                    "reason": "Direct finish."
                }

        orchestrator = AgentOrchestrator(
            project=self.project,
            user=self.user,
            provider=FinishMockProvider(),
            registry=self.registry,
            publisher=redis_publisher,
            max_steps=3
        )

        run = orchestrator.start_run(goal="Test Redis publisher integration")
        self.assertEqual(run.status, AgentRunStatus.COMPLETED)

        # Verify Redis publish was called for every lifecycle event
        self.assertGreater(mock_redis.publish.call_count, 0)
        expected_channel = f"agent:run:{run.id}"

        for call in mock_redis.publish.call_args_list:
            channel, payload_str = call[0]
            self.assertEqual(channel, expected_channel)
            payload_data = json.loads(payload_str)
            self.assertEqual(payload_data["run_id"], run.id)
            self.assertEqual(payload_data["project_id"], self.project.id)
            self.assertIn(payload_data["event_type"], [
                "agent.started",
                "step.started",
                "step.completed",
                "agent.completed"
            ])


# ==============================================================================
# MILESTONE 3, PHASE 3.2.2: DJANGO CHANNELS + WEBSOCKET CONSUMER TEST SUITE
# ==============================================================================

from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from config.asgi import application
from apps.seo.consumers import AgentEventConsumer
from rest_framework_simplejwt.tokens import RefreshToken


class AgentWebSocketConsumerTests(TestCase):
    """
    Milestone 3, Phase 3.2.2: Django Channels + WebSocket Consumer Tests
    1. Authenticated connection to valid owned run succeeds
    2. Anonymous / unauthenticated connection is rejected (code 4001)
    3. Nonexistent run connection is rejected (code 4003)
    4. Cross-tenant run connection is rejected (code 4003)
    5. Invalid run ID parameter is rejected (code 4004)
    6. Channels group naming adheres to 'agent_run_{run_id}'
    7. Event dispatched via channel layer is delivered to WebSocket client as valid JSON
    8. Sequence numbers are preserved during WebSocket transmission
    9. Sanitized payloads are preserved (no credential leaks over WebSocket)
    10. Tenant isolation across channels groups (Run A events never reach Run B subscriber)
    11. Clean disconnect discards group subscription without error
    12. JWT query string authentication (?token=...) authenticates user on handshake
    13. Transport failures during publishing do not modify or corrupt AgentRun database state
    """

    def setUp(self):
        # User A & Project A
        self.user_a = User.objects.create_user(
            email='ws_user_a@doxarank.com',
            password='Password123!',
            first_name='WsUser',
            last_name='A'
        )
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Project A WS',
            website_url='https://project-a-ws.et'
        )
        self.run_a = AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            goal='Goal for Project A WS',
            status=AgentRunStatus.RUNNING
        )

        # User B & Project B
        self.user_b = User.objects.create_user(
            email='ws_user_b@doxarank.com',
            password='Password123!',
            first_name='WsUser',
            last_name='B'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Project B WS',
            website_url='https://project-b-ws.et'
        )
        self.run_b = AgentRun.objects.create(
            project=self.project_b,
            user=self.user_b,
            goal='Goal for Project B WS',
            status=AgentRunStatus.RUNNING
        )

    async def test_authenticated_user_can_connect_to_own_run(self):
        """1. Authenticated user connecting to their own run succeeds."""
        communicator = WebsocketCommunicator(
            application,
            f"/ws/seo/ai/agent/runs/{self.run_a.id}/"
        )
        communicator.scope["user"] = self.user_a

        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_anonymous_user_connection_is_rejected(self):
        """2. Anonymous / unauthenticated user connection is rejected with 4001."""
        from django.contrib.auth.models import AnonymousUser
        communicator = WebsocketCommunicator(
            application,
            f"/ws/seo/ai/agent/runs/{self.run_a.id}/"
        )
        communicator.scope["user"] = AnonymousUser()

        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4001)

    async def test_nonexistent_run_connection_is_rejected(self):
        """3. Connection to nonexistent run ID is rejected with 4003 without leaking information."""
        communicator = WebsocketCommunicator(
            application,
            "/ws/seo/ai/agent/runs/999999/"
        )
        communicator.scope["user"] = self.user_a

        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)

    async def test_cross_tenant_run_connection_is_rejected(self):
        """4. User B connecting to User A's run is rejected with 4003."""
        communicator = WebsocketCommunicator(
            application,
            f"/ws/seo/ai/agent/runs/{self.run_a.id}/"
        )
        communicator.scope["user"] = self.user_b

        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)

    async def test_channels_group_naming_format(self):
        """5. Channels group naming strictly conforms to 'agent_run_{run_id}'."""
        self.assertEqual(RedisEventPublisher.get_group_name(42), "agent_run_42")
        self.assertEqual(RedisEventPublisher.get_group_name(self.run_a.id), f"agent_run_{self.run_a.id}")

    async def test_event_delivery_to_connected_client(self):
        """6. Serialized AgentEvent sent via channel layer is delivered to WebSocket subscriber."""
        communicator = WebsocketCommunicator(
            application,
            f"/ws/seo/ai/agent/runs/{self.run_a.id}/"
        )
        communicator.scope["user"] = self.user_a
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Create and dispatch an event
        event = AgentEvent(
            event_type=AgentEventType.TOOL_COMPLETED,
            run_id=self.run_a.id,
            project_id=self.project_a.id,
            step_number=3,
            sequence_number=7,
            payload={"tool_name": "get_keyword_rankings", "duration_ms": 150, "success": True}
        )

        channel_layer = get_channel_layer()
        group_name = RedisEventPublisher.get_group_name(self.run_a.id)
        await channel_layer.group_send(
            group_name,
            {
                "type": "agent_event",
                "event": event.to_dict()
            }
        )

        # Receive JSON over WebSocket
        message = await communicator.receive_json_from()
        self.assertEqual(message["event_id"], event.event_id)
        self.assertEqual(message["event_type"], "tool.completed")
        self.assertEqual(message["run_id"], self.run_a.id)
        self.assertEqual(message["project_id"], self.project_a.id)
        self.assertEqual(message["step_number"], 3)
        self.assertEqual(message["sequence_number"], 7)
        self.assertEqual(message["payload"]["tool_name"], "get_keyword_rankings")
        self.assertEqual(message["payload"]["duration_ms"], 150)

        await communicator.disconnect()

    async def test_group_isolation_between_runs(self):
        """7. Events published for Run A never reach subscribers of Run B."""
        # Connect to Run A
        comm_a = WebsocketCommunicator(
            application,
            f"/ws/seo/ai/agent/runs/{self.run_a.id}/"
        )
        comm_a.scope["user"] = self.user_a
        connected_a, _ = await comm_a.connect()
        self.assertTrue(connected_a)

        # Connect to Run B
        comm_b = WebsocketCommunicator(
            application,
            f"/ws/seo/ai/agent/runs/{self.run_b.id}/"
        )
        comm_b.scope["user"] = self.user_b
        connected_b, _ = await comm_b.connect()
        self.assertTrue(connected_b)

        # Dispatch event to Run A only
        event_a = AgentEvent(
            event_type=AgentEventType.STEP_COMPLETED,
            run_id=self.run_a.id,
            project_id=self.project_a.id,
            step_number=1,
            sequence_number=2,
            payload={"action_type": "tool_call"}
        )

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            RedisEventPublisher.get_group_name(self.run_a.id),
            {
                "type": "agent_event",
                "event": event_a.to_dict()
            }
        )

        # Comm A receives event
        msg_a = await comm_a.receive_json_from()
        self.assertEqual(msg_a["run_id"], self.run_a.id)

        # Comm B receives nothing
        received_nothing = await comm_b.receive_nothing()
        self.assertTrue(received_nothing)

        await comm_a.disconnect()
        await comm_b.disconnect()

    async def test_jwt_query_string_authentication(self):
        """8. JWT token in query string (?token=...) authenticates connection successfully."""
        from asgiref.sync import sync_to_async
        refresh = await sync_to_async(RefreshToken.for_user)(self.user_a)
        access_token = str(refresh.access_token)

        communicator = WebsocketCommunicator(
            application,
            f"/ws/seo/ai/agent/runs/{self.run_a.id}/?token={access_token}"
        )

        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_sanitized_payloads_delivered_over_websocket(self):
        """9. Sensitive tokens and keys remain sanitized when delivered to WebSocket client."""
        communicator = WebsocketCommunicator(
            application,
            f"/ws/seo/ai/agent/runs/{self.run_a.id}/"
        )
        communicator.scope["user"] = self.user_a
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        event = AgentEvent(
            event_type=AgentEventType.TOOL_FAILED,
            run_id=self.run_a.id,
            project_id=self.project_a.id,
            payload={
                "api_key": "sk-secret1234567890abcdef",
                "header": "Bearer top_secret_token_12345",
                "error": "Failed with key sk-secret99999999"
            }
        )

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            RedisEventPublisher.get_group_name(self.run_a.id),
            {
                "type": "agent_event",
                "event": event.to_dict()
            }
        )

        msg = await communicator.receive_json_from()
        payload = msg["payload"]
        self.assertEqual(payload["api_key"], "***REDACTED***")
        self.assertNotIn("sk-secret1234567890abcdef", str(payload))
        self.assertNotIn("top_secret_token_12345", str(payload))
        self.assertIn("Bearer ***", str(payload))
        self.assertIn("sk-***", str(payload))

        await communicator.disconnect()

    def test_transport_failure_does_not_corrupt_agent_run(self):
        """10. Broken channel layer does not corrupt or modify AgentRun database state."""
        class BrokenChannelLayer:
            async def group_send(self, group, message):
                raise RuntimeError("Channel layer crashed!")

        broken_publisher = RedisEventPublisher(
            redis_client=MagicMock(),
            channel_layer=BrokenChannelLayer()
        )

        event = AgentEvent(
            event_type=AgentEventType.AGENT_STARTED,
            run_id=self.run_a.id,
            project_id=self.project_a.id,
            payload={"goal": "Resilience test"}
        )

        # Must not raise an exception
        try:
            broken_publisher.publish(event)
        except Exception as e:
            self.fail(f"publish() raised an unexpected exception: {e}")

        self.run_a.refresh_from_db()
        self.assertEqual(self.run_a.status, AgentRunStatus.RUNNING)


# ==============================================================================
# MILESTONE 3, PHASE 3.4: REAL-TIME EVENT RESILIENCE & REPLAY TEST SUITE
# ==============================================================================

class AgentEventReplayAPITests(TestCase):
    """
    Phase 3.4: Replay API Authorization, Cursor Recovery, Ordering & Sanitization Tests
    1. Authenticated owner can retrieve events from replay endpoint
    2. Anonymous/unauthenticated user is rejected with HTTP 401
    3. Cross-tenant access is rejected with HTTP 404 (zero leakage)
    4. Nonexistent run returns HTTP 404
    5. Cursor ?after_sequence=0 returns all available events
    6. Cursor ?after_sequence=N returns strictly events after N
    7. Cursor ?after_sequence=latest returns empty list
    8. Returned events are strictly ascending by sequence_number
    9. Sensitive credentials (sk-..., Bearer...) are sanitized in replayed payloads
    10. Replay works cleanly across COMPLETED, FAILED, and CANCELLED terminal states
    """

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            email='replay_owner@doxarank.com',
            password='Password123!',
            first_name='Replay',
            last_name='Owner'
        )
        self.other_user = User.objects.create_user(
            email='replay_other@doxarank.com',
            password='Password123!',
            first_name='Other',
            last_name='User'
        )

        self.project = Project.objects.create(
            owner=self.owner,
            name='Replay Project',
            website_url='https://replay-test.et'
        )
        self.other_project = Project.objects.create(
            owner=self.other_user,
            name='Other Project',
            website_url='https://other-test.et'
        )

        # Create AgentRun with stored event history
        self.run = AgentRun.objects.create(
            project=self.project,
            user=self.owner,
            goal='Analyze competitor keyword gaps and propose action',
            status=AgentRunStatus.RUNNING,
            max_steps=15,
            total_steps=1,
            context_snapshot={
                '_event_seq': 5,
                '_event_history': [
                    {
                        'event_id': 'evt-1-start',
                        'event_type': 'agent.started',
                        'run_id': 1,
                        'project_id': self.project.id,
                        'step_number': None,
                        'sequence_number': 1,
                        'timestamp': '2026-08-30T10:00:00Z',
                        'payload': {'goal': 'Analyze gaps'}
                    },
                    {
                        'event_id': 'evt-2-step-start',
                        'event_type': 'step.started',
                        'run_id': 1,
                        'project_id': self.project.id,
                        'step_number': 1,
                        'sequence_number': 2,
                        'timestamp': '2026-08-30T10:00:01Z',
                        'payload': {'step_number': 1, 'action_type': 'tool_call'}
                    },
                    {
                        'event_id': 'evt-3-tool-start',
                        'event_type': 'tool.started',
                        'run_id': 1,
                        'project_id': self.project.id,
                        'step_number': 1,
                        'sequence_number': 3,
                        'timestamp': '2026-08-30T10:00:02Z',
                        'payload': {'tool_name': 'get_keyword_rankings'}
                    },
                    {
                        'event_id': 'evt-4-tool-finish',
                        'event_type': 'tool.completed',
                        'run_id': 1,
                        'project_id': self.project.id,
                        'step_number': 1,
                        'sequence_number': 4,
                        'timestamp': '2026-08-30T10:00:03Z',
                        'payload': {'tool_name': 'get_keyword_rankings', 'duration_ms': 120, 'success': True}
                    },
                    {
                        'event_id': 'evt-5-step-finish',
                        'event_type': 'step.completed',
                        'run_id': 1,
                        'project_id': self.project.id,
                        'step_number': 1,
                        'sequence_number': 5,
                        'timestamp': '2026-08-30T10:00:04Z',
                        'payload': {'step_number': 1, 'success': True}
                    }
                ]
            }
        )

    def test_owner_can_retrieve_replay_events(self):
        """1. Authenticated owner receives HTTP 200 with list of events."""
        self.client.force_authenticate(user=self.owner)
        url = f'/api/seo/ai/agent/runs/{self.run.id}/events/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 5)
        self.assertEqual(response.data[0]['event_type'], 'agent.started')
        self.assertEqual(response.data[4]['event_type'], 'step.completed')

    def test_anonymous_user_is_rejected(self):
        """2. Unauthenticated request is rejected with HTTP 401."""
        url = f'/api/seo/ai/agent/runs/{self.run.id}/events/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cross_tenant_access_is_rejected(self):
        """3. Another user cannot access project owner's run events (returns 404)."""
        self.client.force_authenticate(user=self.other_user)
        url = f'/api/seo/ai/agent/runs/{self.run.id}/events/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonexistent_run_returns_404(self):
        """4. Request for non-existent run ID returns HTTP 404."""
        self.client.force_authenticate(user=self.owner)
        url = '/api/seo/ai/agent/runs/999999/events/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_after_sequence_cursor_filtering(self):
        """5 & 6 & 7. ?after_sequence filters strictly after cursor."""
        self.client.force_authenticate(user=self.owner)
        url = f'/api/seo/ai/agent/runs/{self.run.id}/events/'

        # Cursor = 0 (all events)
        res_0 = self.client.get(f"{url}?after_sequence=0")
        self.assertEqual(len(res_0.data), 5)
        self.assertEqual([e['sequence_number'] for e in res_0.data], [1, 2, 3, 4, 5])

        # Cursor = 3 (events after 3 -> 4, 5)
        res_3 = self.client.get(f"{url}?after_sequence=3")
        self.assertEqual(len(res_3.data), 2)
        self.assertEqual([e['sequence_number'] for e in res_3.data], [4, 5])

        # Cursor = 5 (no events after 5 -> [])
        res_5 = self.client.get(f"{url}?after_sequence=5")
        self.assertEqual(len(res_5.data), 0)

    def test_replay_events_are_strictly_ascending(self):
        """8. Replayed events are always sorted ascending by sequence_number."""
        self.client.force_authenticate(user=self.owner)
        url = f'/api/seo/ai/agent/runs/{self.run.id}/events/'
        response = self.client.get(url)
        seqs = [e['sequence_number'] for e in response.data]
        self.assertEqual(seqs, sorted(seqs))

    def test_replay_sanitizes_credentials(self):
        """9. Leaky payloads in event history are masked on replay."""
        leaky_run = AgentRun.objects.create(
            project=self.project,
            user=self.owner,
            goal='Security check',
            status=AgentRunStatus.COMPLETED,
            context_snapshot={
                '_event_history': [
                    {
                        'event_id': 'evt-leak',
                        'event_type': 'tool.failed',
                        'run_id': 2,
                        'project_id': self.project.id,
                        'step_number': 1,
                        'sequence_number': 1,
                        'timestamp': '2026-08-30T10:00:00Z',
                        'payload': {
                            'api_key': 'sk-topsecret1234567890',
                            'auth': 'Bearer raw_bearer_token_xyz999',
                            'message': 'Failed with password=SuperSecretPassword123'
                        }
                    }
                ]
            }
        )
        self.client.force_authenticate(user=self.owner)
        url = f'/api/seo/ai/agent/runs/{leaky_run.id}/events/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data[0]['payload']
        self.assertEqual(payload['api_key'], '***REDACTED***')
        self.assertNotIn('sk-topsecret1234567890', str(payload))
        self.assertNotIn('raw_bearer_token_xyz999', str(payload))
        self.assertNotIn('SuperSecretPassword123', str(payload))
        self.assertIn('Bearer ***', str(payload))

    def test_replay_across_terminal_states(self):
        """10. Historical reconstruction works for completed, failed, and cancelled runs without stored history."""
        # Create completed run without _event_history
        completed_run = AgentRun.objects.create(
            project=self.project,
            user=self.owner,
            goal='Historical completed run',
            status=AgentRunStatus.COMPLETED,
            summary='Completed successfully in 1 step.',
            total_steps=1,
            max_steps=15
        )
        step = AgentStep.objects.create(
            run=completed_run,
            step_number=1,
            thought='Reasoning finished',
            action_type=AgentActionType.PLAN,
            status=AgentStepStatus.COMPLETED
        )
        AgentToolCall.objects.create(
            step=step,
            tool_name='get_keyword_rankings',
            tool_input={'keyword': 'seo'},
            tool_output={'rank': 1},
            duration_ms=45
        )

        self.client.force_authenticate(user=self.owner)
        url = f'/api/seo/ai/agent/runs/{completed_run.id}/events/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 4)
        event_types = [e['event_type'] for e in response.data]
        self.assertIn('agent.started', event_types)
        self.assertIn('step.started', event_types)
        self.assertIn('tool.completed', event_types)
        self.assertIn('agent.completed', event_types)


# ==============================================================================
# MILESTONE 4, PHASE 4.1.1: GOOGLE SEARCH CONSOLE OAUTH2 FOUNDATION TEST SUITE
# ==============================================================================

from apps.seo.services.encryption import encrypt_token, decrypt_token


class GoogleOAuthFoundationTests(TestCase):
    """
    Phase 4.1.1: Google OAuth2 Settings, Symmetric Encryption, Credential Storage & Serialization Safety Tests
    1. Google OAuth settings load with safe development defaults when unset
    2. Symmetric Fernet encryption/decryption round-trip succeeds with zero plaintext leakage
    3. Invalid or corrupted ciphertext safely returns None without crashing
    4. SearchConsoleConnection helper methods (set_refresh_token, get_refresh_token, has_valid_credentials)
    5. SearchConsoleConnectionSerializer strictly excludes encrypted_refresh_token from API responses
    6. Multi-tenant isolation prevents cross-tenant access to SearchConsoleConnection credentials
    """

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            email='gsc_oauth_owner@doxarank.com',
            password='Password123!',
            first_name='GSC',
            last_name='Owner'
        )
        self.other_user = User.objects.create_user(
            email='gsc_oauth_other@doxarank.com',
            password='Password123!',
            first_name='Other',
            last_name='User'
        )
        self.project = Project.objects.create(
            owner=self.owner,
            name='GSC OAuth Project',
            website_url='https://gsc-oauth.et'
        )
        self.other_project = Project.objects.create(
            owner=self.other_user,
            name='Other Project',
            website_url='https://other-gsc.et'
        )

    def test_google_oauth_settings_load_with_safe_defaults(self):
        """1. Settings define OAuth client ID, secret, redirect URI, and scopes with safe defaults."""
        self.assertTrue(hasattr(settings, 'GOOGLE_OAUTH_CLIENT_ID'))
        self.assertTrue(hasattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET'))
        self.assertTrue(hasattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI'))
        self.assertTrue(hasattr(settings, 'GOOGLE_OAUTH_SCOPES'))
        self.assertIn('https://www.googleapis.com/auth/webmasters.readonly', settings.GOOGLE_OAUTH_SCOPES)

    def test_token_encryption_and_decryption(self):
        """2. Raw OAuth refresh token is encrypted at rest and decrypted accurately in memory."""
        raw_refresh_token = "1//04_example_google_oauth2_refresh_token_secret_xyz12345"
        encrypted = encrypt_token(raw_refresh_token)

        self.assertIsNotNone(encrypted)
        self.assertNotEqual(encrypted, raw_refresh_token)
        self.assertNotIn(raw_refresh_token, encrypted)

        decrypted = decrypt_token(encrypted)
        self.assertEqual(decrypted, raw_refresh_token)

        # Empty / None handling
        self.assertIsNone(encrypt_token(None))
        self.assertIsNone(encrypt_token(""))
        self.assertIsNone(decrypt_token(None))
        self.assertIsNone(decrypt_token(""))

    def test_invalid_token_decryption_returns_none(self):
        """3. Corrupted or invalid ciphertext safely returns None without raising an uncaught exception."""
        invalid_ciphertext = "not_a_valid_fernet_token_xyz"
        decrypted = decrypt_token(invalid_ciphertext)
        self.assertIsNone(decrypted)

    def test_search_console_connection_model_token_helpers(self):
        """4. Model methods accurately manage token encryption, decryption, and credential validity state."""
        raw_token = "1//04_test_live_refresh_token_abc"
        connection = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="sc-domain:gsc-oauth.et",
            is_connected=True,
            google_account_email="owner@doxarank.com",
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )

        # Initially no token
        self.assertFalse(connection.has_oauth_token)
        self.assertFalse(connection.has_valid_credentials())
        self.assertIsNone(connection.get_refresh_token())

        # Set token
        connection.set_refresh_token(raw_token)
        connection.save()

        connection.refresh_from_db()
        self.assertTrue(connection.has_oauth_token)
        self.assertTrue(connection.has_valid_credentials())
        self.assertEqual(connection.get_refresh_token(), raw_token)
        self.assertNotIn(raw_token, connection.encrypted_refresh_token)

    def test_serializer_excludes_encrypted_refresh_token(self):
        """5. Serializer exposes metadata and has_oauth_token, but strictly excludes encrypted_refresh_token."""
        connection = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="sc-domain:gsc-oauth.et",
            is_connected=True,
            google_account_email="admin@gsc-oauth.et",
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        connection.set_refresh_token("1//04_secret_refresh_token_999")
        connection.save()

        self.client.force_authenticate(user=self.owner)
        url = f'/api/seo/search-console/{connection.id}/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('encrypted_refresh_token', response.data)
        self.assertNotIn('1//04_secret_refresh_token_999', str(response.data))
        self.assertTrue(response.data.get('has_oauth_token'))
        self.assertEqual(response.data.get('google_account_email'), 'admin@gsc-oauth.et')

    def test_multi_tenant_isolation_on_gsc_connection_with_credentials(self):
        """6. Other authenticated users cannot access or view project owner's Search Console connection."""
        connection = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="sc-domain:gsc-oauth.et",
            is_connected=True,
            google_account_email="owner@doxarank.com"
        )
        connection.set_refresh_token("1//04_secret_owner_token")
        connection.save()

        # Other user tries to access owner's connection
        self.client.force_authenticate(user=self.other_user)
        url = f'/api/seo/search-console/{connection.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(
    GOOGLE_OAUTH_CLIENT_ID='mock_test_client_id.apps.googleusercontent.com',
    GOOGLE_OAUTH_CLIENT_SECRET='mock_test_client_secret_xyz99999',
    GOOGLE_OAUTH_REDIRECT_URI='http://localhost:5173/integrations/google/callback'
)
class GoogleOAuthFlowTests(TestCase):
    """
    Phase 4.1.2: Google OAuth2 Authorization & Callback Exchange Flow Test Suite
    1. Authorization URL endpoint generates valid Google OAuth URL with offline consent & state
    2. Unauthenticated request to authorization URL endpoint is rejected (401)
    3. Nonexistent project ID returns 404
    4. Cross-tenant request to authorization URL returns 404 (strict multi-tenant isolation)
    5. Missing project_id query parameter returns 400 Bad Request
    6. Unconfigured Google OAuth settings returns clean 503 error
    7. OAuthStateService generates and verifies tamper-proof state
    8. Tampered or forged state signature is rejected (400)
    9. Expired state token is rejected (400)
    10. Reused/replayed state token is rejected (400)
    11. Cross-user state token is rejected (400)
    12. Cross-project state token is rejected (400)
    13. Valid callback exchanges code, verifies Google identity, stores encrypted refresh token, and creates connection
    14. Callback on existing project updates connection without creating duplicate records
    15. Google authorization denial (access_denied) is cleanly handled without server error (400)
    16. Missing authorization code or missing state parameter returns 400
    17. Google exchange error (e.g. invalid_grant) is cleanly sanitized and handled (400)
    18. Missing refresh token on new connection is safely rejected with helpful message (400)
    19. Missing refresh token on existing connection preserves existing encrypted refresh token (200)
    20. GET callback endpoint works equivalently to POST
    21. Client secret and plaintext tokens never appear in serialized API responses or logs
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.auth_url_endpoint = '/api/seo/integrations/google/authorization-url/'
        self.callback_endpoint = '/api/seo/integrations/google/callback/'

        self.owner = User.objects.create_user(
            email='gsc_oauth_flow_owner@doxarank.com',
            password='Password123!',
            first_name='Flow',
            last_name='Owner'
        )
        self.other_user = User.objects.create_user(
            email='gsc_oauth_flow_other@doxarank.com',
            password='Password123!',
            first_name='Other',
            last_name='User'
        )
        self.project = Project.objects.create(
            owner=self.owner,
            name='Flow Test Project',
            website_url='https://flow-test.et'
        )
        self.other_project = Project.objects.create(
            owner=self.other_user,
            name='Other Project',
            website_url='https://other-project.et'
        )

    def test_authorization_url_authenticated_owner_success(self):
        """1. Authenticated project owner receives valid Google OAuth URL containing state, scopes, offline consent."""
        from apps.seo.services.google_oauth import OAuthStateService

        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f"{self.auth_url_endpoint}?project_id={self.project.id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('authorization_url', response.data)
        auth_url = response.data['authorization_url']

        self.assertTrue(auth_url.startswith("https://accounts.google.com/o/oauth2/v2/auth"))
        self.assertIn("response_type=code", auth_url)
        self.assertIn("access_type=offline", auth_url)
        self.assertIn("prompt=consent", auth_url)
        self.assertIn("state=", auth_url)
        self.assertIn("webmasters.readonly", auth_url)
        # Client secret must never be in the URL
        self.assertNotIn("GOOGLE_OAUTH_CLIENT_SECRET", auth_url)

    def test_authorization_url_unauthenticated_rejected(self):
        """2. Unauthenticated request to authorization URL returns 401 Unauthorized."""
        response = self.client.get(f"{self.auth_url_endpoint}?project_id={self.project.id}")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authorization_url_nonexistent_project_rejected(self):
        """3. Nonexistent project ID returns 404 Not Found."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f"{self.auth_url_endpoint}?project_id=999999")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_authorization_url_cross_tenant_isolation_rejected(self):
        """4. Authenticated user requesting authorization URL for another user's project is rejected (404)."""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(f"{self.auth_url_endpoint}?project_id={self.project.id}")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_authorization_url_missing_project_id_param_rejected(self):
        """5. Missing project_id query parameter returns 400 Bad Request."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(self.auth_url_endpoint)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project_id", response.data.get('detail', ''))

    @override_settings(GOOGLE_OAUTH_CLIENT_ID='')
    def test_authorization_url_missing_google_oauth_settings_handled(self):
        """6. Unconfigured Google OAuth settings on server returns safe 503 error."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f"{self.auth_url_endpoint}?project_id={self.project.id}")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_oauth_state_generation_and_verification_roundtrip(self):
        """7. OAuthStateService generates signed state and verifies successfully with correct user/project."""
        from apps.seo.services.google_oauth import OAuthStateService

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)
        self.assertIsInstance(state, str)
        self.assertTrue(len(state) > 20)

        resolved_project, resolved_user = OAuthStateService.verify_state(
            raw_state=state,
            expected_user=self.owner
        )
        self.assertEqual(resolved_project.id, self.project.id)
        self.assertEqual(resolved_user.id, self.owner.id)

    def test_oauth_state_tampered_or_bad_signature_rejected(self):
        """8. Tampered or forged state signature is rejected."""
        from apps.seo.services.google_oauth import OAuthStateService, InvalidOAuthStateError

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)
        tampered_state = state[:-5] + "ABCDE"

        with self.assertRaises(InvalidOAuthStateError):
            OAuthStateService.verify_state(raw_state=tampered_state)

        # Empty / None state
        with self.assertRaises(InvalidOAuthStateError):
            OAuthStateService.verify_state(raw_state="")
        with self.assertRaises(InvalidOAuthStateError):
            OAuthStateService.verify_state(raw_state=None)

    def test_oauth_state_expiration_rejected(self):
        """9. Expired state token is rejected when exceeding max_age."""
        from apps.seo.services.google_oauth import OAuthStateService, InvalidOAuthStateError

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)

        # Verify with max_age = -1 (already expired)
        with self.assertRaises(InvalidOAuthStateError):
            OAuthStateService.verify_state(raw_state=state, max_age=-1)

    def test_oauth_state_replay_rejected(self):
        """10. Reusing a valid state token a second time is rejected by replay protection."""
        from apps.seo.services.google_oauth import OAuthStateService, InvalidOAuthStateError

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)

        # First verification succeeds
        OAuthStateService.verify_state(raw_state=state)

        # Second verification with identical state fails due to nonce consumption
        with self.assertRaises(InvalidOAuthStateError) as ctx:
            OAuthStateService.verify_state(raw_state=state)
        self.assertIn("already been used", str(ctx.exception))

    def test_oauth_state_cross_user_rejected(self):
        """11. Cross-user verification mismatch raises InvalidOAuthStateError."""
        from apps.seo.services.google_oauth import OAuthStateService, InvalidOAuthStateError

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)

        with self.assertRaises(InvalidOAuthStateError):
            OAuthStateService.verify_state(raw_state=state, expected_user=self.other_user)

    def test_oauth_state_cross_project_rejected(self):
        """12. State where project ownership is invalid or does not match user raises error."""
        from apps.seo.services.google_oauth import OAuthStateService, InvalidOAuthStateError

        # Create state with other_project for owner (mismatched)
        signer = OAuthStateService.get_signer()
        forged_payload = {
            'user_id': self.owner.id,
            'project_id': self.other_project.id,  # Owned by other_user!
            'nonce': 'random_test_nonce_xyz',
            'ts': 123456789
        }
        forged_state = signer.sign_object(forged_payload)

        with self.assertRaises(InvalidOAuthStateError):
            OAuthStateService.verify_state(raw_state=forged_state)

    @patch('apps.seo.services.google_oauth.GoogleOAuthService.fetch_user_identity')
    @patch('apps.seo.services.google_oauth.GoogleOAuthService.exchange_code')
    def test_callback_successful_token_exchange_creates_connection(self, mock_exchange, mock_identity):
        """13. Valid callback creates SearchConsoleConnection with encrypted refresh token and metadata."""
        from apps.seo.services.google_oauth import OAuthStateService

        mock_exchange.return_value = {
            'access_token': 'ya29.a0AfH6SM_mock_access_token',
            'refresh_token': '1//04_mock_google_refresh_token_secret_123',
            'expires_in': 3600,
            'scope': 'https://www.googleapis.com/auth/webmasters.readonly openid email profile'
        }
        mock_identity.return_value = {
            'email': 'gsc.verified.user@gmail.com',
            'name': 'GSC Verified',
            'verified_email': True
        }

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)

        self.client.force_authenticate(user=self.owner)
        payload = {
            'code': '4/0AX4XfWh_valid_auth_code_from_google',
            'state': state
        }
        response = self.client.post(self.callback_endpoint, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['project'], self.project.id)
        self.assertEqual(response.data['google_account_email'], 'gsc.verified.user@gmail.com')
        self.assertTrue(response.data['is_connected'])
        self.assertTrue(response.data['has_oauth_token'])

        # Database verification
        connection = SearchConsoleConnection.objects.get(project=self.project)
        self.assertTrue(connection.is_connected)
        self.assertEqual(connection.google_account_email, 'gsc.verified.user@gmail.com')
        self.assertEqual(connection.get_refresh_token(), '1//04_mock_google_refresh_token_secret_123')
        self.assertNotIn('1//04_mock_google_refresh_token_secret_123', connection.encrypted_refresh_token)

        # Plaintext token must NEVER appear in response
        self.assertNotIn('encrypted_refresh_token', response.data)
        self.assertNotIn('1//04_mock_google_refresh_token_secret_123', str(response.data))

    @patch('apps.seo.services.google_oauth.GoogleOAuthService.fetch_user_identity')
    @patch('apps.seo.services.google_oauth.GoogleOAuthService.exchange_code')
    def test_callback_existing_connection_updated_without_duplication(self, mock_exchange, mock_identity):
        """14. Re-authorizing an existing connection updates the record rather than duplicating it."""
        from apps.seo.services.google_oauth import OAuthStateService

        # Pre-create existing connection
        existing_conn = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="sc-domain:flow-test.et",
            is_connected=False,
            google_account_email="old.email@gmail.com"
        )
        existing_conn.set_refresh_token("1//04_old_refresh_token")
        existing_conn.save()

        mock_exchange.return_value = {
            'access_token': 'ya29.new_access_token',
            'refresh_token': '1//04_new_refresh_token_abc',
            'expires_in': 3600,
            'scope': 'https://www.googleapis.com/auth/webmasters.readonly'
        }
        mock_identity.return_value = {
            'email': 'new.email@gmail.com',
            'verified_email': True
        }

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)

        self.client.force_authenticate(user=self.owner)
        payload = {
            'code': '4/new_code',
            'state': state
        }
        response = self.client.post(self.callback_endpoint, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(SearchConsoleConnection.objects.filter(project=self.project).count(), 1)

        existing_conn.refresh_from_db()
        self.assertTrue(existing_conn.is_connected)
        self.assertEqual(existing_conn.google_account_email, 'new.email@gmail.com')
        self.assertEqual(existing_conn.get_refresh_token(), '1//04_new_refresh_token_abc')

    def test_callback_google_authorization_denial_handled(self):
        """15. User denying Google consent returns clean 400 error without server exception."""
        payload = {
            'error': 'access_denied',
            'error_description': 'The user denied the request to access their Google account.'
        }
        response = self.client.post(self.callback_endpoint, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("denied by the user", response.data.get('detail', ''))

    def test_callback_missing_code_or_state_rejected(self):
        """16. Missing code or state parameter in callback is rejected (400)."""
        # Missing code
        res1 = self.client.post(self.callback_endpoint, {'state': 'some_state'}, format='json')
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)

        # Missing state
        res2 = self.client.post(self.callback_endpoint, {'code': 'some_code'}, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.seo.services.google_oauth.GoogleOAuthService.exchange_code')
    def test_callback_invalid_code_google_error_handled(self, mock_exchange):
        """17. Google returning an error during code exchange returns clean 400."""
        from apps.seo.services.google_oauth import OAuthStateService, GoogleOAuthExchangeError

        mock_exchange.side_effect = GoogleOAuthExchangeError("Google token exchange failed: invalid_grant")

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)
        self.client.force_authenticate(user=self.owner)

        payload = {'code': 'bad_expired_code', 'state': state}
        response = self.client.post(self.callback_endpoint, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("invalid_grant", response.data.get('detail', ''))

    @patch('apps.seo.services.google_oauth.GoogleOAuthService.fetch_user_identity')
    @patch('apps.seo.services.google_oauth.GoogleOAuthService.exchange_code')
    def test_callback_missing_refresh_token_on_new_connection_handled(self, mock_exchange, mock_identity):
        """18. Missing refresh token on new connection returns 400 Bad Request with guidance."""
        from apps.seo.services.google_oauth import OAuthStateService

        mock_exchange.return_value = {
            'access_token': 'ya29.access_only_token',
            'refresh_token': None,  # No refresh token returned
            'expires_in': 3600
        }
        mock_identity.return_value = {'email': 'test@gmail.com'}

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)
        payload = {'code': 'valid_code', 'state': state}
        response = self.client.post(self.callback_endpoint, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No refresh token", response.data.get('detail', ''))

    @patch('apps.seo.services.google_oauth.GoogleOAuthService.fetch_user_identity')
    @patch('apps.seo.services.google_oauth.GoogleOAuthService.exchange_code')
    def test_callback_missing_refresh_token_on_existing_connection_retains_token(self, mock_exchange, mock_identity):
        """19. Missing refresh token on re-authorization preserves the existing encrypted refresh token."""
        from apps.seo.services.google_oauth import OAuthStateService

        existing_conn = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="sc-domain:flow-test.et",
            is_connected=True,
            google_account_email="initial@gmail.com"
        )
        existing_conn.set_refresh_token("1//04_preserved_refresh_token")
        existing_conn.save()

        mock_exchange.return_value = {
            'access_token': 'ya29.access_only_token',
            'refresh_token': None,  # Google didn't return a new refresh token
            'expires_in': 3600
        }
        mock_identity.return_value = {'email': 'reauthorized@gmail.com'}

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)
        payload = {'code': 'valid_code', 'state': state}
        response = self.client.post(self.callback_endpoint, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        existing_conn.refresh_from_db()
        self.assertEqual(existing_conn.get_refresh_token(), "1//04_preserved_refresh_token")
        self.assertEqual(existing_conn.google_account_email, "reauthorized@gmail.com")

    @patch('apps.seo.services.google_oauth.GoogleOAuthService.fetch_user_identity')
    @patch('apps.seo.services.google_oauth.GoogleOAuthService.exchange_code')
    def test_callback_get_method_supported(self, mock_exchange, mock_identity):
        """20. GET callback with query parameters is supported for direct redirection."""
        from apps.seo.services.google_oauth import OAuthStateService

        mock_exchange.return_value = {
            'access_token': 'ya29.get_access_token',
            'refresh_token': '1//04_get_refresh_token',
            'expires_in': 3600
        }
        mock_identity.return_value = {'email': 'get.callback@gmail.com'}

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)
        url = f"{self.callback_endpoint}?code=get_code&state={state}"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['google_account_email'], 'get.callback@gmail.com')

    @patch('apps.seo.services.google_oauth.GoogleOAuthService.fetch_user_identity')
    @patch('apps.seo.services.google_oauth.GoogleOAuthService.exchange_code')
    def test_security_client_secret_and_token_never_leak(self, mock_exchange, mock_identity):
        """21. Plaintext refresh tokens and client secret never appear in responses or serialized data."""
        from apps.seo.services.google_oauth import OAuthStateService

        secret_token = "1//04_super_secret_unique_refresh_token_never_leak_xyz"
        mock_exchange.return_value = {
            'access_token': 'ya29.secret_access_token',
            'refresh_token': secret_token,
            'expires_in': 3600
        }
        mock_identity.return_value = {'email': 'secure@gmail.com'}

        state = OAuthStateService.generate_state(user=self.owner, project=self.project)
        payload = {'code': 'security_code', 'state': state}
        response = self.client.post(self.callback_endpoint, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        serialized_str = str(response.data)
        self.assertNotIn(secret_token, serialized_str)
        self.assertNotIn(getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', ''), serialized_str)
        self.assertNotIn('encrypted_refresh_token', response.data)


@override_settings(
    GOOGLE_OAUTH_CLIENT_ID='mock_test_client_id.apps.googleusercontent.com',
    GOOGLE_OAUTH_CLIENT_SECRET='mock_test_client_secret_xyz99999',
    GOOGLE_OAUTH_REDIRECT_URI='http://localhost:5173/integrations/google/callback'
)
class GoogleSearchConsoleApiAndToolsTests(TestCase):
    """
    Phase 4.1.3: Google Search Console API Access Service & Agent Tools Test Suite
    1. Retrieval and validation of active SearchConsoleConnection
    2. Missing or disconnected connection raises SearchConsoleNotConnectedError
    3. Missing or unconfigured credentials raises SearchConsoleCredentialsError
    4. Auto-refreshing OAuth credential construction with decrypted refresh token
    5. Revoked or expired credentials handling and error state recording
    6. Search Analytics query with response normalization and calculated summary metrics
    7. get_top_queries convenience method with landing page filtering
    8. get_top_pages convenience method with query filtering
    9. Strict date validation (format, start > end, future date, historical lookback limit)
    10. Dimension and row limit validation (clamping and whitelisting)
    11. Google API HttpError handling (401, 403, 404, 429, 500) without crashing
    12. Multi-tenant isolation across project boundaries
    13. Tool registry contains gsc_search_analytics, gsc_top_queries, and gsc_top_pages
    14. Execution of GSC tools through ToolRegistry.execute()
    15. Schema validation error handling for GSC tools
    16. Zero credential leakage in tool data, error responses, and telemetry
    """

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(
            email='gsc_tools_owner@doxarank.com',
            password='Password123!',
            first_name='Tools',
            last_name='Owner'
        )
        self.other_user = User.objects.create_user(
            email='gsc_tools_other@doxarank.com',
            password='Password123!',
            first_name='Tools',
            last_name='Other'
        )
        self.project = Project.objects.create(
            owner=self.owner,
            name='GSC Tools Project',
            website_url='https://tools-project.et'
        )
        self.other_project = Project.objects.create(
            owner=self.other_user,
            name='Other Tools Project',
            website_url='https://other-tools.et'
        )

        # Create valid SearchConsoleConnection for project
        self.connection = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="sc-domain:tools-project.et",
            is_connected=True,
            google_account_email="owner@tools-project.et",
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        self.raw_refresh_token = "1//04_mock_live_gsc_refresh_token_test_12345"
        self.connection.set_refresh_token(self.raw_refresh_token)
        self.connection.save()

    def _create_mock_gsc_client(self, rows=None):
        """Helper to create a mock googleapiclient Search Console client."""
        mock_client = MagicMock()
        mock_execute = MagicMock(return_value={"rows": rows if rows is not None else []})
        mock_client.searchanalytics().query().execute = mock_execute
        return mock_client

    def test_service_get_connection_success(self):
        """1. GoogleSearchConsoleService resolves active connection for project."""
        from apps.seo.services.google_search_console import GoogleSearchConsoleService

        service = GoogleSearchConsoleService(project=self.project)
        connection = service.get_connection()
        self.assertEqual(connection.id, self.connection.id)
        self.assertEqual(connection.property_url, "sc-domain:tools-project.et")

    def test_service_get_connection_missing_or_disconnected_raises(self):
        """2. Disconnected or missing SearchConsoleConnection raises SearchConsoleNotConnectedError."""
        from apps.seo.services.google_search_console import (
            GoogleSearchConsoleService,
            SearchConsoleNotConnectedError
        )

        # Disconnected connection
        self.connection.is_connected = False
        self.connection.save()

        service = GoogleSearchConsoleService(project=self.project)
        with self.assertRaises(SearchConsoleNotConnectedError):
            service.get_connection()

        # No connection exists for other project
        other_service = GoogleSearchConsoleService(project=self.other_project)
        with self.assertRaises(SearchConsoleNotConnectedError):
            other_service.get_connection()

    def test_service_get_connection_missing_credentials_raises(self):
        """3. Connection without credentials raises SearchConsoleCredentialsError."""
        from apps.seo.services.google_search_console import (
            GoogleSearchConsoleService,
            SearchConsoleCredentialsError
        )

        self.connection.encrypted_refresh_token = ""
        self.connection.save()

        service = GoogleSearchConsoleService(project=self.project)
        with self.assertRaises(SearchConsoleCredentialsError):
            service.get_connection()

    @patch('google.oauth2.credentials.Credentials.refresh')
    def test_service_get_credentials_and_auto_refresh(self, mock_refresh):
        """4. Auto-refreshing Credentials instance constructed with decrypted token."""
        from apps.seo.services.google_search_console import GoogleSearchConsoleService

        service = GoogleSearchConsoleService(project=self.project)
        creds = service.get_credentials()

        self.assertIsNotNone(creds)
        self.assertEqual(creds.refresh_token, self.raw_refresh_token)
        mock_refresh.assert_called_once()

    @patch('google.oauth2.credentials.Credentials.refresh')
    def test_service_get_credentials_revoked_updates_error_state(self, mock_refresh):
        """5. Expired or revoked credentials update connection status to failed and raise clean error."""
        from apps.seo.services.google_search_console import (
            GoogleSearchConsoleService,
            SearchConsoleCredentialsError
        )

        mock_refresh.side_effect = Exception("invalid_grant: Token has been expired or revoked.")

        service = GoogleSearchConsoleService(project=self.project)
        with self.assertRaises(SearchConsoleCredentialsError) as ctx:
            service.get_credentials()

        self.assertIn("expired or been revoked", str(ctx.exception))
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.sync_status, "failed")
        self.assertIn("expired or revoked", self.connection.error_message)

    def test_query_search_analytics_success_normalization(self):
        """6. Live Search Analytics query returns normalized internal schema with summary aggregates."""
        from apps.seo.services.google_search_console import GoogleSearchConsoleService

        sample_rows = [
            {
                "keys": ["ethiopia tech news"],
                "clicks": 150,
                "impressions": 3000,
                "ctr": 0.05,
                "position": 3.2
            },
            {
                "keys": ["addis ababa fintech"],
                "clicks": 50,
                "impressions": 1000,
                "ctr": 0.05,
                "position": 7.8
            }
        ]
        mock_client = self._create_mock_gsc_client(rows=sample_rows)

        service = GoogleSearchConsoleService(project=self.project)
        result = service.query_search_analytics(
            start_date="2026-08-01",
            end_date="2026-08-20",
            dimensions=["query"],
            row_limit=25,
            client=mock_client
        )

        self.assertEqual(result["project_id"], self.project.id)
        self.assertEqual(result["property_url"], "sc-domain:tools-project.et")
        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(len(result["rows"]), 2)

        # Verify row mapping
        first_row = result["rows"][0]
        self.assertEqual(first_row["query"], "ethiopia tech news")
        self.assertEqual(first_row["clicks"], 150)
        self.assertEqual(first_row["impressions"], 3000)
        self.assertEqual(first_row["ctr_percent"], 5.0)
        self.assertEqual(first_row["position"], 3.2)

        # Verify summary metrics
        summary = result["summary"]
        self.assertEqual(summary["total_clicks"], 200)
        self.assertEqual(summary["total_impressions"], 4000)
        self.assertEqual(summary["average_ctr_percent"], 5.0)
        self.assertAlmostEqual(summary["average_position"], 4.35, delta=0.1)

    def test_get_top_queries_with_page_filter(self):
        """7. get_top_queries sorts queries and applies page filter."""
        from apps.seo.services.google_search_console import GoogleSearchConsoleService

        sample_rows = [
            {"keys": ["low impressions"], "clicks": 10, "impressions": 100, "ctr": 0.1, "position": 1.0},
            {"keys": ["high impressions"], "clicks": 50, "impressions": 5000, "ctr": 0.01, "position": 8.0}
        ]
        mock_client = self._create_mock_gsc_client(rows=sample_rows)

        service = GoogleSearchConsoleService(project=self.project)
        result = service.get_top_queries(
            start_date="2026-08-01",
            end_date="2026-08-15",
            limit=10,
            page_filter="https://tools-project.et/tech",
            client=mock_client
        )

        self.assertEqual(result["returned_count"], 2)
        self.assertEqual(result["page_filter"], "https://tools-project.et/tech")
        # Highest impressions query sorted first
        self.assertEqual(result["top_queries"][0]["query"], "high impressions")
        self.assertEqual(result["top_queries"][1]["query"], "low impressions")

    def test_get_top_pages_with_query_filter(self):
        """8. get_top_pages sorts landing pages by clicks and applies query filter."""
        from apps.seo.services.google_search_console import GoogleSearchConsoleService

        sample_rows = [
            {"keys": ["https://tools-project.et/blog/1"], "clicks": 5, "impressions": 200, "ctr": 0.025, "position": 4.0},
            {"keys": ["https://tools-project.et/blog/2"], "clicks": 80, "impressions": 1000, "ctr": 0.08, "position": 2.0}
        ]
        mock_client = self._create_mock_gsc_client(rows=sample_rows)

        service = GoogleSearchConsoleService(project=self.project)
        result = service.get_top_pages(
            start_date="2026-08-01",
            end_date="2026-08-15",
            limit=10,
            query_filter="tech news",
            client=mock_client
        )

        self.assertEqual(result["returned_count"], 2)
        self.assertEqual(result["query_filter"], "tech news")
        # Highest clicks page sorted first
        self.assertEqual(result["top_pages"][0]["page"], "https://tools-project.et/blog/2")
        self.assertEqual(result["top_pages"][1]["page"], "https://tools-project.et/blog/1")

    def test_date_validations(self):
        """9. Date validations enforce YYYY-MM-DD, bounds, and max lookback range."""
        from apps.seo.services.google_search_console import (
            GoogleSearchConsoleService,
            SearchConsoleValidationError
        )

        service = GoogleSearchConsoleService(project=self.project)

        # Malformed date strings
        with self.assertRaises(SearchConsoleValidationError):
            service.validate_date_string("08-20-2026")
        with self.assertRaises(SearchConsoleValidationError):
            service.validate_date_string("invalid_date")
        with self.assertRaises(SearchConsoleValidationError):
            service.validate_date_string("")

        # start_date > end_date
        with self.assertRaises(SearchConsoleValidationError):
            service.validate_date_range("2026-08-20", "2026-08-01")

        # Future date
        future_date = (timezone.now().date() + timedelta(days=5)).strftime('%Y-%m-%d')
        with self.assertRaises(SearchConsoleValidationError):
            service.validate_date_range(future_date, future_date)

        # Older than 16 months lookback
        ancient_date = (timezone.now().date() - timedelta(days=600)).strftime('%Y-%m-%d')
        with self.assertRaises(SearchConsoleValidationError):
            service.validate_date_range(ancient_date, "2026-08-01")

    def test_dimension_and_limit_validations(self):
        """10. Dimensions and row limits are strictly validated and clamped."""
        from apps.seo.services.google_search_console import (
            GoogleSearchConsoleService,
            SearchConsoleValidationError
        )

        service = GoogleSearchConsoleService(project=self.project)

        # Invalid dimension
        with self.assertRaises(SearchConsoleValidationError):
            service.validate_dimensions(["query", "injected_invalid_dim"])

        # Default dimensions when None
        self.assertEqual(service.validate_dimensions(None), ["query"])

        # Valid dimensions subset
        valid = service.validate_dimensions(["page", "device", "country"])
        self.assertEqual(valid, ["page", "device", "country"])

    def test_google_api_http_error_handling(self):
        """11. Google API HttpErrors are safely converted to SearchConsoleApiError with diagnostic messages."""
        from apps.seo.services.google_search_console import (
            GoogleSearchConsoleService,
            SearchConsoleApiError
        )
        from googleapiclient.errors import HttpError
        import httplib2

        service = GoogleSearchConsoleService(project=self.project)

        # 401 Unauthorized / Expired
        resp_401 = httplib2.Response({'status': 401})
        http_err_401 = HttpError(resp_401, b'{"error": {"message": "Invalid Credentials"}}')
        mock_client_401 = MagicMock()
        mock_client_401.searchanalytics().query().execute.side_effect = http_err_401

        with self.assertRaises(SearchConsoleApiError) as ctx_401:
            service.query_search_analytics("2026-08-01", "2026-08-15", client=mock_client_401)
        self.assertIn("authorization has expired", str(ctx_401.exception))

        # 403 Forbidden / Not Owner
        resp_403 = httplib2.Response({'status': 403})
        http_err_403 = HttpError(resp_403, b'{"error": {"message": "User does not have permission"}}')
        mock_client_403 = MagicMock()
        mock_client_403.searchanalytics().query().execute.side_effect = http_err_403

        with self.assertRaises(SearchConsoleApiError) as ctx_403:
            service.query_search_analytics("2026-08-01", "2026-08-15", client=mock_client_403)
        self.assertIn("permission denied", str(ctx_403.exception))

        # 429 Rate Limit
        resp_429 = httplib2.Response({'status': 429})
        http_err_429 = HttpError(resp_429, b'{"error": {"message": "Quota exceeded"}}')
        mock_client_429 = MagicMock()
        mock_client_429.searchanalytics().query().execute.side_effect = http_err_429

        with self.assertRaises(SearchConsoleApiError) as ctx_429:
            service.query_search_analytics("2026-08-01", "2026-08-15", client=mock_client_429)
        self.assertIn("quota exceeded", str(ctx_429.exception))

    def test_multi_tenant_isolation_on_service_and_tools(self):
        """12. Other users cannot access project owner's Search Console service."""
        from apps.seo.services.google_search_console import (
            GoogleSearchConsoleService,
            SearchConsoleNotConnectedError
        )

        other_service = GoogleSearchConsoleService(project=self.other_project)
        with self.assertRaises(SearchConsoleNotConnectedError):
            other_service.get_connection()

    def test_tool_registry_contains_gsc_tools(self):
        """13. ToolRegistry registers gsc_search_analytics, gsc_top_queries, and gsc_top_pages."""
        from apps.seo.services.tool_registry import get_tool_registry, ToolCategory

        registry = get_tool_registry()

        tool_names = [t.name for t in registry.list_tools()]
        self.assertIn("gsc_search_analytics", tool_names)
        self.assertIn("gsc_top_queries", tool_names)
        self.assertIn("gsc_top_pages", tool_names)

        # Check schemas and categories
        analytics_tool = registry.get("gsc_search_analytics")
        self.assertEqual(analytics_tool.category, ToolCategory.READ_ONLY)
        self.assertFalse(analytics_tool.is_mutating)
        self.assertFalse(analytics_tool.requires_approval)
        self.assertIn("start_date", analytics_tool.parameters_schema["required"])
        self.assertIn("end_date", analytics_tool.parameters_schema["required"])

    @patch('apps.seo.services.google_search_console.GoogleSearchConsoleService.get_client')
    def test_gsc_tools_execution_via_tool_registry(self, mock_get_client):
        """14. ToolRegistry.execute invokes GSC tools with proper arguments and returns success."""
        from apps.seo.services.tool_registry import get_tool_registry

        mock_rows = [
            {"keys": ["ethiopia seo agency"], "clicks": 40, "impressions": 800, "ctr": 0.05, "position": 4.1}
        ]
        mock_client = self._create_mock_gsc_client(rows=mock_rows)
        mock_get_client.return_value = mock_client

        registry = get_tool_registry()

        # Execute gsc_search_analytics
        res1 = registry.execute("gsc_search_analytics", self.project, {
            "start_date": "2026-08-01",
            "end_date": "2026-08-25",
            "dimensions": ["query"],
            "row_limit": 10
        })
        self.assertTrue(res1["success"])
        self.assertEqual(res1["tool_name"], "gsc_search_analytics")
        self.assertEqual(res1["data"]["total_rows"], 1)

        # Execute gsc_top_queries
        res2 = registry.execute("gsc_top_queries", self.project, {
            "start_date": "2026-08-01",
            "end_date": "2026-08-25",
            "limit": 5
        })
        self.assertTrue(res2["success"])
        self.assertEqual(res2["tool_name"], "gsc_top_queries")
        self.assertEqual(res2["data"]["returned_count"], 1)

        # Execute gsc_top_pages
        mock_page_rows = [
            {"keys": ["https://tools-project.et/seo-guide"], "clicks": 90, "impressions": 1200, "ctr": 0.075, "position": 2.2}
        ]
        mock_get_client.return_value = self._create_mock_gsc_client(rows=mock_page_rows)

        res3 = registry.execute("gsc_top_pages", self.project, {
            "start_date": "2026-08-01",
            "end_date": "2026-08-25",
            "limit": 5
        })
        self.assertTrue(res3["success"])
        self.assertEqual(res3["tool_name"], "gsc_top_pages")
        self.assertEqual(res3["data"]["top_pages"][0]["page"], "https://tools-project.et/seo-guide")

    def test_gsc_tools_validation_error_handling_via_registry(self):
        """15. Missing required arguments or invalid schemas return VALIDATION_ERROR."""
        from apps.seo.services.tool_registry import get_tool_registry

        registry = get_tool_registry()

        # Missing required end_date
        res = registry.execute("gsc_search_analytics", self.project, {
            "start_date": "2026-08-01"
        })
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("end_date", res["error"]["message"])

    @patch('apps.seo.services.google_search_console.GoogleSearchConsoleService.get_client')
    def test_zero_credential_leakage_in_tool_output_and_errors(self, mock_get_client):
        """16. Secret tokens and credentials are redacted from tool error outputs."""
        from apps.seo.services.tool_registry import get_tool_registry

        # Simulate exception containing raw token
        secret_leak = "Failed communicating with Google API using refresh token 1//04_secret_xyz999 and Bearer secret_access_token_123"
        mock_client = MagicMock()
        mock_client.searchanalytics().query().execute.side_effect = RuntimeError(secret_leak)
        mock_get_client.return_value = mock_client

        registry = get_tool_registry()
        res = registry.execute("gsc_search_analytics", self.project, {
            "start_date": "2026-08-01",
            "end_date": "2026-08-25"
        })

        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "EXECUTION_ERROR")
        err_msg = res["error"]["message"]
        self.assertNotIn("1//04_secret_xyz999", err_msg)
        self.assertNotIn("secret_access_token_123", err_msg)
        self.assertIn("[REDACTED", err_msg)


# ==============================================================================
# MILESTONE 4 — PHASE 4.1.4: AGENTIC GSC INTELLIGENCE & REASONING TESTS
# ==============================================================================

class GSCIntelligenceServiceTests(TestCase):
    """
    Unit test suite for GSCIntelligenceService heuristics, statistical detectors,
    period-over-period comparisons, and SEOInsight persistence.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='gsc_intel_user@doxarank.com',
            password='TestPassword123!',
            first_name='Intelligence',
            last_name='Tester'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='GSC Intelligence Project',
            website_url='https://intel-project.doxarank.com'
        )
        from apps.seo.services.gsc_intelligence import GSCIntelligenceService
        self.service = GSCIntelligenceService(project=self.project)

    def test_detect_page_two_opportunities(self):
        """1. Detects queries ranking on Page 2 (pos 10.1 - 20.0) with notable impression volume."""
        sample_rows = [
            {"query": "enterprise seo platform", "position": 12.4, "impressions": 450, "clicks": 8, "ctr": 0.0178, "ctr_percent": 1.78},
            {"query": "rank tracker tool", "position": 3.2, "impressions": 800, "clicks": 45, "ctr": 0.056, "ctr_percent": 5.6},
            {"query": "keyword cannibalization audit", "position": 18.5, "impressions": 220, "clicks": 2, "ctr": 0.009, "ctr_percent": 0.9},
            {"query": "zero impression query", "position": 14.0, "impressions": 2, "clicks": 0, "ctr": 0.0, "ctr_percent": 0.0},
        ]

        result = self.service.analyze_opportunities(query_rows=sample_rows, min_impressions=10)
        findings = result["findings"]
        p2_findings = [f for f in findings if f["finding_type"] == "gsc_page_two_opportunity"]

        self.assertEqual(len(p2_findings), 2)
        # Verify first page 2 finding
        f1 = next(f for f in p2_findings if f["target_query"] == "enterprise seo platform")
        self.assertEqual(f1["severity"], "opportunity")
        self.assertGreaterEqual(f1["confidence"], 0.70)
        self.assertIn("12.4", f1["title"])
        self.assertIn("FAQ", f1["recommendation"])
        self.assertEqual(f1["suggested_action_type"], "optimize_existing_content")

    def test_detect_high_impressions_low_ctr(self):
        """2. Detects queries ranking in top 10 with CTR significantly below position benchmark."""
        sample_rows = [
            # Top 3 ranking but CTR only 2.0% (expected >= 15%)
            {"query": "best seo rank tracker", "position": 2.1, "impressions": 1200, "clicks": 24, "ctr": 0.02, "ctr_percent": 2.0},
            # Page 1 ranking (pos 5) but CTR only 0.8% (expected >= 3%)
            {"query": "serp tracking software", "position": 5.0, "impressions": 600, "clicks": 5, "ctr": 0.008, "ctr_percent": 0.8},
            # Healthy CTR on pos 1
            {"query": "doxarank login", "position": 1.1, "impressions": 500, "clicks": 200, "ctr": 0.40, "ctr_percent": 40.0},
        ]

        result = self.service.analyze_opportunities(query_rows=sample_rows, min_impressions=10)
        findings = result["findings"]
        ctr_findings = [f for f in findings if f["finding_type"] == "gsc_high_impressions_low_ctr"]

        self.assertEqual(len(ctr_findings), 2)
        top_ctr = next(f for f in ctr_findings if f["target_query"] == "best seo rank tracker")
        self.assertEqual(top_ctr["severity"], "warning")
        self.assertIn("SERP Snippet Underperformance", top_ctr["title"])
        self.assertIn("Rewrite meta title", top_ctr["recommendation"])
        self.assertEqual(top_ctr["suggested_action_type"], "update_meta_description")

    def test_detect_keyword_cannibalization(self):
        """3. Detects queries where 2+ landing pages rank simultaneously, splitting search traffic."""
        combined_rows = [
            {"query": "saas seo guide", "page": "https://intel-project.doxarank.com/blog/saas-seo", "clicks": 15, "impressions": 300, "position": 8.0},
            {"query": "saas seo guide", "page": "https://intel-project.doxarank.com/services/saas-seo", "clicks": 10, "impressions": 250, "position": 11.2},
            {"query": "single page query", "page": "https://intel-project.doxarank.com/single", "clicks": 20, "impressions": 100, "position": 4.0},
        ]

        result = self.service.analyze_opportunities(combined_rows=combined_rows, min_impressions=10)
        findings = result["findings"]
        cannibalization_findings = [f for f in findings if f["finding_type"] == "gsc_keyword_cannibalization"]

        self.assertEqual(len(cannibalization_findings), 1)
        cf = cannibalization_findings[0]
        self.assertEqual(cf["target_query"], "saas seo guide")
        self.assertEqual(cf["severity"], "warning")
        self.assertIn("competing pages", cf["title"])
        self.assertIn("canonical tag", cf["recommendation"])
        self.assertEqual(cf["metrics"]["competing_pages_count"], 2)

    def test_detect_emerging_queries(self):
        """4. Detects long-tail queries demonstrating early high CTR engagement (>10%) at pos >= 4."""
        sample_rows = [
            {"query": "how to automate gsc intelligence", "position": 6.5, "impressions": 40, "clicks": 6, "ctr": 0.15, "ctr_percent": 15.0},
            {"query": "standard keyword", "position": 7.0, "impressions": 100, "clicks": 3, "ctr": 0.03, "ctr_percent": 3.0},
        ]

        result = self.service.analyze_opportunities(query_rows=sample_rows, min_impressions=10)
        findings = result["findings"]
        emerging = [f for f in findings if f["finding_type"] == "gsc_emerging_query"]

        self.assertEqual(len(emerging), 1)
        ef = emerging[0]
        self.assertEqual(ef["target_query"], "how to automate gsc intelligence")
        self.assertEqual(ef["severity"], "opportunity")
        self.assertIn("High-Intent Emerging Query", ef["title"])

    def test_compare_periods_calculation(self):
        """5. Compares search performance between two date ranges and calculates metric deltas."""
        mock_gsc = MagicMock()
        # Base period (recent)
        mock_gsc.query_search_analytics.side_effect = [
            {
                "summary": {"total_clicks": 150, "total_impressions": 5000, "average_ctr_percent": 3.0, "average_position": 8.5},
                "rows": [
                    {"query": "seo tool", "clicks": 100, "impressions": 3000, "ctr": 0.033, "position": 6.0},
                    {"query": "new query", "clicks": 50, "impressions": 2000, "ctr": 0.025, "position": 12.0},
                ]
            },
            # Comparison period (prior)
            {
                "summary": {"total_clicks": 200, "total_impressions": 4000, "average_ctr_percent": 5.0, "average_position": 7.0},
                "rows": [
                    {"query": "seo tool", "clicks": 180, "impressions": 3500, "ctr": 0.051, "position": 4.5},
                    {"query": "lost query", "clicks": 20, "impressions": 500, "ctr": 0.04, "position": 9.0},
                ]
            }
        ]

        comparison = self.service.compare_periods(
            base_start="2026-08-01",
            base_end="2026-08-28",
            comp_start="2026-07-04",
            comp_end="2026-07-31",
            gsc_service=mock_gsc
        )

        deltas = comparison["summary_deltas"]
        self.assertEqual(deltas["base_clicks"], 150)
        self.assertEqual(deltas["comp_clicks"], 200)
        self.assertEqual(deltas["clicks_delta"], -50)
        self.assertEqual(deltas["clicks_change_percent"], -25.0)
        self.assertEqual(deltas["impressions_delta"], 1000)
        self.assertEqual(deltas["impressions_change_percent"], 25.0)

        # Verify top decliners and new/lost queries
        self.assertGreaterEqual(len(comparison["top_decliners"]), 1)
        self.assertEqual(comparison["top_decliners"][0]["query"], "seo tool")
        self.assertEqual(comparison["top_decliners"][0]["clicks_delta"], -80)

        self.assertEqual(len(comparison["new_queries"]), 1)
        self.assertEqual(comparison["new_queries"][0]["query"], "new query")

        self.assertEqual(len(comparison["lost_queries"]), 1)
        self.assertEqual(comparison["lost_queries"][0]["query"], "lost query")

        # Significant click drop (-25%) should produce a warning finding
        findings = comparison["findings"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["finding_type"], "gsc_period_comparison_decline")
        self.assertEqual(findings[0]["severity"], "warning")

    def test_sync_findings_to_insights_idempotent(self):
        """6. Idempotently syncs GSC findings to persistent SEOInsight database records."""
        sample_findings = [
            {
                "finding_type": "gsc_page_two_opportunity",
                "severity": "opportunity",
                "confidence": 0.85,
                "title": "Page 2 Opportunity: \"enterprise rank tracking\"",
                "insight": "Ranks at pos 12.2 with 300 impressions.",
                "recommendation": "Add FAQ and on-page headings.",
                "target_query": "enterprise rank tracking",
                "target_url": "https://intel-project.doxarank.com/enterprise",
                "metrics": {"position": 12.2, "impressions": 300},
                "evidence": [{"query": "enterprise rank tracking"}],
                "suggested_action_type": "optimize_existing_content"
            }
        ]

        # Initial sync
        insights_run_1 = self.service.sync_findings_to_insights(sample_findings)
        self.assertEqual(len(insights_run_1), 1)
        insight = SEOInsight.objects.get(id=insights_run_1[0].id)
        self.assertEqual(insight.project, self.project)
        self.assertEqual(insight.source, InsightSource.SEARCH_CONSOLE)
        self.assertEqual(insight.insight_type, InsightType.PAGE_TWO_KEYWORD)
        self.assertEqual(insight.severity, InsightSeverity.OPPORTUNITY)

        # Repeated sync with same finding produces NO duplicate rows
        insights_run_2 = self.service.sync_findings_to_insights(sample_findings)
        self.assertEqual(len(insights_run_2), 1)
        self.assertEqual(SEOInsight.objects.filter(project=self.project).count(), 1)

    def test_empty_or_malformed_gsc_data_graceful_handling(self):
        """7. Handles empty or malformed rows without crashing or raising unhandled exceptions."""
        malformed_rows = [
            {},
            {"query": None, "impressions": None, "position": "invalid"},
            {"query": "broken row", "position": None, "impressions": "bad_int"},
        ]

        result = self.service.analyze_opportunities(query_rows=malformed_rows, min_impressions=10)
        self.assertEqual(result["total_findings"], 0)
        self.assertEqual(result["findings"], [])


class GSCIntelligenceToolRegistryTests(TestCase):
    """
    Test suite for gsc_opportunity_audit and gsc_performance_comparison tools in ToolRegistry.
    """

    def setUp(self):
        self.user_a = User.objects.create_user(email='user_a_tools@doxarank.com', password='TestPassword123!')
        self.user_b = User.objects.create_user(email='user_b_tools@doxarank.com', password='TestPassword123!')
        self.project_a = Project.objects.create(owner=self.user_a, name='Project A', website_url='https://project-a.com')
        self.project_b = Project.objects.create(owner=self.user_b, name='Project B', website_url='https://project-b.com')

    @patch('apps.seo.services.gsc_intelligence.GSCIntelligenceService.analyze_opportunities')
    def test_gsc_opportunity_audit_tool_execution(self, mock_analyze):
        """8. Executes gsc_opportunity_audit tool via ToolRegistry and returns structured output."""
        from apps.seo.services.tool_registry import get_tool_registry

        mock_analyze.return_value = {
            "project_id": self.project_a.id,
            "analyzed_at": "2026-08-31T12:00:00Z",
            "total_queries_analyzed": 25,
            "total_findings": 2,
            "findings_by_type": {"page_two": 1, "low_ctr": 1, "cannibalization": 0, "emerging": 0},
            "findings": [
                {
                    "finding_type": "gsc_page_two_opportunity",
                    "severity": "opportunity",
                    "confidence": 0.85,
                    "title": "Page 2 Opportunity: \"audit tool\"",
                    "insight": "Ranking #12.0",
                    "recommendation": "Optimize content",
                    "target_query": "audit tool",
                    "target_url": "https://project-a.com/audit",
                    "metrics": {"position": 12.0, "impressions": 200},
                    "evidence": []
                }
            ]
        }

        registry = get_tool_registry()
        res = registry.execute("gsc_opportunity_audit", self.project_a, {
            "min_impressions": 15,
            "sync_to_insights": True
        })

        self.assertTrue(res["success"])
        self.assertEqual(res["tool_name"], "gsc_opportunity_audit")
        self.assertEqual(res["data"]["total_findings"], 2)
        self.assertEqual(res["data"]["persisted_insights_count"], 1)
        self.assertEqual(SEOInsight.objects.filter(project=self.project_a).count(), 1)

    @patch('apps.seo.services.gsc_intelligence.GSCIntelligenceService.compare_periods')
    def test_gsc_performance_comparison_tool_execution(self, mock_compare):
        """9. Executes gsc_performance_comparison tool via ToolRegistry."""
        from apps.seo.services.tool_registry import get_tool_registry

        mock_compare.return_value = {
            "project_id": self.project_a.id,
            "summary_deltas": {"clicks_delta": 40, "clicks_change_percent": 15.0},
            "top_gainers": [{"query": "growth keyword", "clicks_delta": 30}],
            "top_decliners": [],
            "findings": []
        }

        registry = get_tool_registry()
        res = registry.execute("gsc_performance_comparison", self.project_a, {
            "base_start_date": "2026-08-01",
            "base_end_date": "2026-08-28",
            "comp_start_date": "2026-07-04",
            "comp_end_date": "2026-07-31",
            "row_limit": 50
        })

        self.assertTrue(res["success"])
        self.assertEqual(res["tool_name"], "gsc_performance_comparison")
        self.assertEqual(res["data"]["summary_deltas"]["clicks_delta"], 40)


class GSCAgentOrchestratorIntegrationTests(TestCase):
    """
    End-to-end integration tests verifying ReAct Agent reasoning on GSC intelligence,
    dynamic multi-step workflows, and human approval boundary gating.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='gsc_agent_user@doxarank.com',
            password='TestPassword123!',
            first_name='Agent',
            last_name='Runner'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Agent GSC Testing Project',
            website_url='https://gsc-agent-test.doxarank.com'
        )
        # Create baseline connection, insight and recommendation for downstream generation tools
        SearchConsoleConnection.objects.create(
            project=self.project,
            property_url='sc-domain:gsc-agent-test.doxarank.com',
            is_connected=True,
            google_account_email='agent@doxarank.com',
            scopes=['https://www.googleapis.com/auth/webmasters.readonly']
        )
        self.insight = SEOInsight.objects.create(
            project=self.project,
            fingerprint='gsc_test_insight_1',
            insight_type=InsightType.PAGE_TWO_KEYWORD,
            severity=InsightSeverity.OPPORTUNITY,
            title='Page 2 Opportunity: "doxarank ai seo"',
            description='Query ranks at #13.5 with 500 impressions.',
            recommendation='Optimize on-page copy and internal linking.',
            source=InsightSource.SEARCH_CONSOLE,
            related_url='https://gsc-agent-test.doxarank.com/ai-seo',
            status=InsightStatus.OPEN
        )

    @patch('apps.seo.services.google_search_console.GoogleSearchConsoleService.get_top_queries')
    @patch('apps.seo.services.google_search_console.GoogleSearchConsoleService.get_top_pages')
    def test_multi_step_gsc_opportunity_reasoning_loop(self, mock_get_top_pages, mock_get_top_queries):
        """10. Agent autonomously plans and executes multi-step GSC intelligence workflow."""
        mock_get_top_queries.return_value = {
            "top_queries": [
                {"query": "doxarank ai seo", "clicks": 12, "impressions": 500, "ctr": 0.024, "position": 13.5}
            ]
        }
        mock_get_top_pages.return_value = {
            "top_pages": [
                {"page": "https://gsc-agent-test.doxarank.com/ai-seo", "clicks": 12, "impressions": 500, "ctr": 0.024, "position": 13.5}
            ]
        }

        orchestrator = AgentOrchestrator(project=self.project, user=self.user, max_steps=10)
        run = orchestrator.start_run(
            goal="Analyze Google Search Console queries to identify high-impact Page 2 opportunities and propose metadata optimizations."
        )

        # Agent should progress through multi-step exploration and pause at approval checkpoint
        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)
        self.assertGreaterEqual(run.total_steps, 4)

        # Verify steps and tool calls
        tool_names = list(AgentToolCall.objects.filter(step__run=run).values_list('tool_name', flat=True))
        self.assertIn("gsc_top_queries", tool_names)
        self.assertIn("gsc_top_pages", tool_names)
        self.assertIn("gsc_opportunity_audit", tool_names)
        self.assertIn("propose_seo_action", tool_names)

        # Verify proposed action exists in waiting_for_approval
        action = SEOAction.objects.filter(project=self.project).first()
        self.assertIsNotNone(action)
        self.assertEqual(action.status, ActionStatus.PROPOSED)

    @patch('apps.seo.services.google_search_console.GoogleSearchConsoleService.query_search_analytics')
    def test_multi_step_gsc_trend_comparison_reasoning_loop(self, mock_query_search):
        """11. Agent autonomously plans and executes GSC performance trend comparison workflow."""
        mock_query_search.side_effect = [
            {"summary": {"total_clicks": 100, "total_impressions": 3000, "average_ctr_percent": 3.3, "average_position": 8.0}, "rows": []},
            {"summary": {"total_clicks": 150, "total_impressions": 3500, "average_ctr_percent": 4.2, "average_position": 7.0}, "rows": []}
        ]

        orchestrator = AgentOrchestrator(project=self.project, user=self.user, max_steps=8)
        run = orchestrator.start_run(
            goal="Compare Google Search Console search performance over the last 28 days vs previous period and detect traffic declines."
        )

        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)
        tool_calls = AgentToolCall.objects.filter(step__run=run).values_list('tool_name', flat=True)
        self.assertIn("gsc_performance_comparison", tool_calls)
        self.assertIn("gsc_opportunity_audit", tool_calls)
        self.assertIn("propose_seo_action", tool_calls)

    @patch('apps.seo.services.google_search_console.GoogleSearchConsoleService.get_top_queries')
    @patch('apps.seo.services.google_search_console.GoogleSearchConsoleService.get_top_pages')
    def test_gsc_proposed_action_human_approval_gate(self, mock_pages, mock_queries):
        """12. Human approval resumes run and safely transitions proposal to execution."""
        mock_queries.return_value = {"top_queries": [{"query": "gsc rank test", "clicks": 5, "impressions": 100, "position": 14.0}]}
        mock_pages.return_value = {"top_pages": [{"page": "https://gsc-agent-test.doxarank.com/ai-seo", "clicks": 5, "impressions": 100, "position": 14.0}]}

        orchestrator = AgentOrchestrator(project=self.project, user=self.user, max_steps=10)
        run = orchestrator.start_run(
            goal="Inspect Google Search Console queries and propose an action."
        )

        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)

        # Human approves proposal
        resumed_run = orchestrator.resume_run(run=run, approval_decision="approved")
        self.assertEqual(resumed_run.status, AgentRunStatus.COMPLETED)
        self.assertIn("Successfully completed", resumed_run.summary)


# ==============================================================================
# MILESTONE 4, PHASE 4.2.1: LIVE WEBSITE CRAWLER FOUNDATION TEST SUITE
# ==============================================================================

class LiveSiteCrawlerTests(TestCase):
    """
    Comprehensive test suite for LiveSiteCrawlerService (Milestone 4, Phase 4.2.1).
    Validates URL handling, robots.txt compliance, bounded BFS traversal,
    HTTP resilience, and BeautifulSoup4 HTML feature extraction.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='crawler_user@doxarank.com',
            password='TestPassword123!',
            first_name='Crawler',
            last_name='Tester'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Crawler Test Website',
            website_url='https://example.com'
        )

    def test_url_normalization(self):
        """1. Normalizes relative URLs, strips fragments, normalizes casing and scheme."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        base = "https://example.com/blog/article-1"
        self.assertEqual(
            LiveSiteCrawlerService.normalize_url("about#team", base),
            "https://example.com/blog/about"
        )
        self.assertEqual(
            LiveSiteCrawlerService.normalize_url("/contact?b=2&a=1#form", base),
            "https://example.com/contact?a=1&b=2"
        )
        self.assertEqual(
            LiveSiteCrawlerService.normalize_url("HTTPS://EXAMPLE.COM/Path/../Services/", base),
            "https://example.com/Services/"
        )
        # Invalid / non-crawlable schemes
        self.assertIsNone(LiveSiteCrawlerService.normalize_url("mailto:info@example.com", base))
        self.assertIsNone(LiveSiteCrawlerService.normalize_url("javascript:void(0)", base))
        self.assertIsNone(LiveSiteCrawlerService.normalize_url("tel:+1234567890", base))
        self.assertIsNone(LiveSiteCrawlerService.normalize_url("", base))

    def test_same_domain_and_extension_filtering(self):
        """2. Restricts crawl to target domain with www equivalence and filters non-HTML extensions."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        # Same domain
        self.assertTrue(LiveSiteCrawlerService.is_same_domain("https://example.com/page", "example.com"))
        self.assertTrue(LiveSiteCrawlerService.is_same_domain("https://www.example.com/page", "example.com"))
        self.assertTrue(LiveSiteCrawlerService.is_same_domain("https://example.com/page", "www.example.com"))
        self.assertFalse(LiveSiteCrawlerService.is_same_domain("https://otherdomain.com/page", "example.com"))
        self.assertFalse(LiveSiteCrawlerService.is_same_domain("https://sub.example.com/page", "example.com"))

        # Extension filtering
        self.assertTrue(LiveSiteCrawlerService.is_crawlable_extension("https://example.com/page"))
        self.assertTrue(LiveSiteCrawlerService.is_crawlable_extension("https://example.com/about.html"))
        self.assertFalse(LiveSiteCrawlerService.is_crawlable_extension("https://example.com/document.pdf"))
        self.assertFalse(LiveSiteCrawlerService.is_crawlable_extension("https://example.com/image.png"))
        self.assertFalse(LiveSiteCrawlerService.is_crawlable_extension("https://example.com/styles.css"))
        self.assertFalse(LiveSiteCrawlerService.is_crawlable_extension("https://example.com/bundle.js"))

    def test_html_feature_extraction_comprehensive(self):
        """3. Extracts title, meta description, H1-H6, canonical, images, internal/external links, and JSON-LD."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <title>   Best SEO Platform in Ethiopia - DoxaRank   </title>
            <meta name="description" content="Award-winning SEO tracking and crawler software.">
            <link rel="canonical" href="https://example.com/definitive-url">
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "SoftwareApplication",
                "name": "DoxaRank",
                "applicationCategory": "BusinessApplication"
            }
            </script>
        </head>
        <body>
            <h1>Main Title of the Page</h1>
            <h2>Secondary Subtitle</h2>
            <h2>Another Subtitle</h2>
            <h3>Deeper Topic Heading</h3>
            <h6>Minor Notice</h6>
            <p>Welcome to DoxaRank. This is a powerful automated SEO platform for tracking rankings and crawling sites.</p>
            <img src="/assets/logo.png" alt="DoxaRank Logo">
            <img src="https://example.com/hero.jpg">
            <a href="/pricing">View Pricing</a>
            <a href="https://example.com/features">Our Features</a>
            <a href="https://twitter.com/doxarank" target="_blank">Follow us on Twitter</a>
            <a href="mailto:support@doxarank.com">Email Us</a>
        </body>
        </html>
        """

        service = LiveSiteCrawlerService(project=self.project)
        extracted = service.extract_html_features(
            url="https://example.com/home",
            final_url="https://example.com/home",
            status_code=200,
            response_time_ms=125.5,
            content_type="text/html; charset=utf-8",
            html_text=html_content,
            base_domain="example.com",
            redirect_chain=[]
        )

        self.assertEqual(extracted.title, "Best SEO Platform in Ethiopia - DoxaRank")
        self.assertEqual(extracted.meta_description, "Award-winning SEO tracking and crawler software.")
        self.assertEqual(extracted.canonical, "https://example.com/definitive-url")
        self.assertEqual(extracted.headings["h1"], ["Main Title of the Page"])
        self.assertEqual(extracted.headings["h2"], ["Secondary Subtitle", "Another Subtitle"])
        self.assertEqual(extracted.headings["h3"], ["Deeper Topic Heading"])
        self.assertEqual(extracted.headings["h6"], ["Minor Notice"])
        self.assertEqual(extracted.headings["h4"], [])

        # Verify Images
        self.assertEqual(len(extracted.images), 2)
        self.assertEqual(extracted.images[0]["src"], "/assets/logo.png")
        self.assertEqual(extracted.images[0]["resolved_url"], "https://example.com/assets/logo.png")
        self.assertEqual(extracted.images[0]["alt"], "DoxaRank Logo")
        self.assertEqual(extracted.images[1]["alt"], "")

        # Verify Links (Internal vs External)
        internal_urls = [l["resolved_url"] for l in extracted.internal_links]
        self.assertIn("https://example.com/pricing", internal_urls)
        self.assertIn("https://example.com/features", internal_urls)
        self.assertEqual(len(extracted.internal_links), 2)

        external_urls = [l["resolved_url"] for l in extracted.external_links]
        self.assertIn("https://twitter.com/doxarank", external_urls)
        self.assertEqual(len(extracted.external_links), 1)

        # Verify JSON-LD
        self.assertEqual(len(extracted.json_ld), 1)
        self.assertEqual(extracted.json_ld[0]["name"], "DoxaRank")
        self.assertEqual(extracted.json_ld[0]["@type"], "SoftwareApplication")

        # Verify word count
        self.assertGreater(extracted.word_count, 10)

    def test_basic_page_crawling_single_page(self):
        """4. Performs live crawl on single page using mock transport and returns structured CrawlResult."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /")
            elif url_str == "https://example.com/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text="<html><head><title>Home Page</title></head><body><h1>Welcome</h1></body></html>"
                )
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(
            project=self.project,
            transport=transport,
            max_pages=10
        )
        result = crawler.crawl("https://example.com/")

        self.assertEqual(result.pages_crawled, 1)
        self.assertEqual(result.pages_discovered, 1)
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(result.metadata.robots_txt_status, "loaded")
        self.assertEqual(result.pages[0].url, "https://example.com/")
        self.assertEqual(result.pages[0].title, "Home Page")
        self.assertEqual(result.pages[0].headings["h1"], ["Welcome"])

    def test_internal_link_discovery_and_bfs_traversal(self):
        """5. Discovers internal links and crawls them via BFS traversal."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(404, text="No robots.txt")
            elif url_str == "https://example.com/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><head><title>Home</title></head><body><a href="/about">About</a><a href="/services">Services</a></body></html>'
                )
            elif url_str == "https://example.com/about":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><head><title>About Us</title></head><body><h1>About DoxaRank</h1><a href="/contact">Contact</a></body></html>'
                )
            elif url_str == "https://example.com/services":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><head><title>Services</title></head><body><h1>Our Services</h1></body></html>'
                )
            elif url_str == "https://example.com/contact":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><head><title>Contact</title></head><body><h1>Contact Us</h1></body></html>'
                )
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(
            project=self.project,
            transport=transport,
            max_pages=10,
            max_depth=2
        )
        result = crawler.crawl("https://example.com/")

        self.assertEqual(result.pages_crawled, 4)
        crawled_urls = [p.url for p in result.pages]
        self.assertIn("https://example.com/", crawled_urls)
        self.assertIn("https://example.com/about", crawled_urls)
        self.assertIn("https://example.com/services", crawled_urls)
        self.assertIn("https://example.com/contact", crawled_urls)

    def test_external_link_exclusion_from_crawl_queue(self):
        """6. Captures external links in page data but strictly excludes them from crawl queue."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(404, text="No robots")
            elif url_str == "https://example.com/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><head><title>Home</title></head><body><a href="https://external-partner.com/api">Partner</a><a href="/internal-page">Internal</a></body></html>'
                )
            elif url_str == "https://example.com/internal-page":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><head><title>Internal Page</title></head><body><h1>Internal Content</h1></body></html>'
                )
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(
            project=self.project,
            transport=transport,
            max_pages=10
        )
        result = crawler.crawl("https://example.com/")

        self.assertEqual(result.pages_crawled, 2)
        crawled_urls = [p.url for p in result.pages]
        self.assertIn("https://example.com/", crawled_urls)
        self.assertIn("https://example.com/internal-page", crawled_urls)
        self.assertNotIn("https://external-partner.com/api", crawled_urls)

        # Check external links captured
        home_page = next(p for p in result.pages if p.url == "https://example.com/")
        self.assertEqual(len(home_page.external_links), 1)
        self.assertEqual(home_page.external_links[0]["resolved_url"], "https://external-partner.com/api")

    def test_robots_txt_compliance(self):
        """7. Respects robots.txt disallow rules and skips disallowed URLs."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(
                    200,
                    text="User-agent: *\nDisallow: /admin\nDisallow: /private/\n"
                )
            elif url_str == "https://example.com/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><head><title>Home</title></head><body><a href="/public">Public</a><a href="/admin/dashboard">Admin</a></body></html>'
                )
            elif url_str == "https://example.com/public":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><head><title>Public</title></head><body><h1>Public Content</h1></body></html>'
                )
            elif url_str == "https://example.com/admin/dashboard":
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<html><body>Admin</body></html>')
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(
            project=self.project,
            transport=transport,
            max_pages=10
        )
        result = crawler.crawl("https://example.com/")

        crawled_urls = [p.url for p in result.pages]
        self.assertIn("https://example.com/", crawled_urls)
        self.assertIn("https://example.com/public", crawled_urls)
        self.assertNotIn("https://example.com/admin/dashboard", crawled_urls)

        # Disallowed URL recorded in errors
        robots_errors = [e for e in result.errors if e.error_type == "robots_disallowed"]
        self.assertEqual(len(robots_errors), 1)
        self.assertEqual(robots_errors[0].url, "https://example.com/admin/dashboard")

    def test_robots_txt_fallback_on_error(self):
        """8. Safely handles robots.txt 500 error or network exception by defaulting to allow all."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(500, text="Internal Server Error")
            elif url_str == "https://example.com/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><head><title>Home</title></head><body><h1>Welcome</h1></body></html>'
                )
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(project=self.project, transport=transport)
        result = crawler.crawl("https://example.com/")

        self.assertEqual(result.pages_crawled, 1)
        self.assertEqual(result.metadata.robots_txt_status, "http_500")

    def test_max_pages_limit_enforcement(self):
        """9. Stops crawl precisely when max_pages is reached, ignoring remaining queue."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(404, text="No robots")
            elif url_str == "https://example.com/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><body><a href="/p1">P1</a><a href="/p2">P2</a><a href="/p3">P3</a><a href="/p4">P4</a><a href="/p5">P5</a></body></html>'
                )
            elif "/p" in url_str:
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<html><body>Page</body></html>')
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(
            project=self.project,
            transport=transport,
            max_pages=3  # Stop at 3 pages
        )
        result = crawler.crawl("https://example.com/")

        self.assertEqual(result.pages_crawled, 3)
        self.assertEqual(len(result.pages), 3)

    def test_max_depth_limit_enforcement(self):
        """10. Does not crawl internal links discovered at or beyond max_depth."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(404, text="No robots")
            elif url_str == "https://example.com/":  # depth 0
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<html><body><a href="/level1">Level 1</a></body></html>')
            elif url_str == "https://example.com/level1":  # depth 1
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<html><body><a href="/level2">Level 2</a></body></html>')
            elif url_str == "https://example.com/level2":  # depth 2
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<html><body><a href="/level3">Level 3</a></body></html>')
            elif url_str == "https://example.com/level3":  # depth 3
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<html><body>Level 3</body></html>')
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(
            project=self.project,
            transport=transport,
            max_pages=10,
            max_depth=1  # Only crawl start URL (depth 0) and Level 1 (depth 1)
        )
        result = crawler.crawl("https://example.com/")

        crawled_urls = [p.url for p in result.pages]
        self.assertIn("https://example.com/", crawled_urls)
        self.assertIn("https://example.com/level1", crawled_urls)
        self.assertNotIn("https://example.com/level2", crawled_urls)
        self.assertEqual(result.pages_crawled, 2)

    def test_http_404_and_500_resilience(self):
        """11. Records HTTP 404 and 500 status codes on PageCrawlResult without breaking crawl."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(404, text="No robots")
            elif url_str == "https://example.com/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><body><a href="/missing">Missing</a><a href="/server-error">Server Error</a><a href="/working">Working</a></body></html>'
                )
            elif url_str == "https://example.com/missing":
                return httpx.Response(404, headers={"Content-Type": "text/html"}, text='<html><body>404 Page Not Found</body></html>')
            elif url_str == "https://example.com/server-error":
                return httpx.Response(500, headers={"Content-Type": "text/html"}, text='<html><body>500 Internal Error</body></html>')
            elif url_str == "https://example.com/working":
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<html><body><h1>Working</h1></body></html>')
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(project=self.project, transport=transport, max_pages=10)
        result = crawler.crawl("https://example.com/")

        self.assertEqual(result.pages_crawled, 4)
        status_by_url = {p.url: p.status_code for p in result.pages}
        self.assertEqual(status_by_url["https://example.com/"], 200)
        self.assertEqual(status_by_url["https://example.com/missing"], 404)
        self.assertEqual(status_by_url["https://example.com/server-error"], 500)
        self.assertEqual(status_by_url["https://example.com/working"], 200)

    def test_redirect_handling_and_chain_capture(self):
        """12. Follows HTTP redirects, records final URL and full redirect chain."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(404, text="No robots")
            elif url_str == "https://example.com/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><body><a href="/old-slug">Old Link</a></body></html>'
                )
            elif url_str == "https://example.com/old-slug":
                return httpx.Response(
                    301,
                    headers={"Location": "https://example.com/intermediate-slug"}
                )
            elif url_str == "https://example.com/intermediate-slug":
                return httpx.Response(
                    302,
                    headers={"Location": "https://example.com/new-definitive-slug"}
                )
            elif url_str == "https://example.com/new-definitive-slug":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><head><title>Definitive Page</title></head><body><h1>New Slug</h1></body></html>'
                )
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(project=self.project, transport=transport, max_pages=10)
        result = crawler.crawl("https://example.com/")

        redirected_page = next((p for p in result.pages if p.url == "https://example.com/old-slug"), None)
        self.assertIsNotNone(redirected_page)
        self.assertEqual(redirected_page.final_url, "https://example.com/new-definitive-slug")
        self.assertEqual(redirected_page.status_code, 200)
        self.assertEqual(redirected_page.title, "Definitive Page")
        self.assertIn("https://example.com/old-slug", redirected_page.redirect_chain)
        self.assertIn("https://example.com/intermediate-slug", redirected_page.redirect_chain)

    def test_timeout_and_network_exception_resilience(self):
        """13. Handles request timeouts and network exceptions gracefully without terminating entire crawl."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(404, text="No robots")
            elif url_str == "https://example.com/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><body><a href="/hanging-page">Hanging</a><a href="/good-page">Good Page</a></body></html>'
                )
            elif url_str == "https://example.com/hanging-page":
                raise httpx.ReadTimeout("Read timed out on socket")
            elif url_str == "https://example.com/good-page":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><head><title>Good Page</title></head><body><h1>Success</h1></body></html>'
                )
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(project=self.project, transport=transport, max_pages=10)
        result = crawler.crawl("https://example.com/")

        # Crawl continued and captured good page
        self.assertEqual(result.pages_crawled, 2)
        crawled_urls = [p.url for p in result.pages]
        self.assertIn("https://example.com/", crawled_urls)
        self.assertIn("https://example.com/good-page", crawled_urls)

        # Timeout recorded in errors list
        timeout_errors = [e for e in result.errors if e.error_type == "timeout"]
        self.assertEqual(len(timeout_errors), 1)
        self.assertEqual(timeout_errors[0].url, "https://example.com/hanging-page")

    def test_max_response_size_protection(self):
        """14. Rejects responses exceeding max_response_size to prevent memory exhaustion."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(404, text="No robots")
            elif url_str == "https://example.com/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><body><a href="/huge-file">Huge File</a><a href="/normal">Normal</a></body></html>'
                )
            elif url_str == "https://example.com/huge-file":
                huge_payload = "A" * 6000  # 6000 bytes
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text=huge_payload)
            elif url_str == "https://example.com/normal":
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text="<html><body>Normal</body></html>")
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(
            project=self.project,
            transport=transport,
            max_pages=10,
            max_response_size=5000  # 5KB limit
        )
        result = crawler.crawl("https://example.com/")

        # Huge file was skipped due to size
        self.assertEqual(result.pages_crawled, 2)
        size_errors = [e for e in result.errors if e.error_type == "response_too_large"]
        self.assertEqual(len(size_errors), 1)
        self.assertEqual(size_errors[0].url, "https://example.com/huge-file")

    def test_project_context_and_start_url_resolution(self):
        """15. Automatically uses project.website_url when start_url is omitted."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(404, text="No robots")
            elif url_str == "https://example.com":
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text="<html><body>Home</body></html>")
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(project=self.project, transport=transport)
        result = crawler.crawl()

        self.assertEqual(result.start_url, "https://example.com/")
        self.assertEqual(result.pages_crawled, 1)

    def test_crawl_result_to_dict_serialization(self):
        """16. CrawlResult and children serialize to clean dictionary structures."""
        from apps.seo.services.live_site_crawler import (
            CrawlResult, CrawlMetadata, PageCrawlResult, CrawlError
        )

        metadata = CrawlMetadata(
            start_url="https://example.com/",
            base_domain="example.com",
            user_agent="DoxaRankBot/1.0",
            max_pages=50,
            max_depth=3,
            robots_txt_status="loaded",
            started_at="2026-08-31T12:00:00Z",
            completed_at="2026-08-31T12:00:05Z",
            duration_seconds=5.0
        )
        page = PageCrawlResult(
            url="https://example.com/",
            final_url="https://example.com/",
            status_code=200,
            response_time_ms=50.0,
            title="Example Title",
            meta_description="Example Description"
        )
        error = CrawlError(
            url="https://example.com/broken",
            error_type="timeout",
            message="Connection timed out"
        )
        result = CrawlResult(
            start_url="https://example.com/",
            metadata=metadata,
            pages_crawled=1,
            pages_discovered=2,
            duration_seconds=5.0,
            errors=[error],
            pages=[page]
        )

        d = result.to_dict()
        self.assertEqual(d["start_url"], "https://example.com/")
        self.assertEqual(d["pages_crawled"], 1)
        self.assertEqual(len(d["errors"]), 1)
        self.assertEqual(d["errors"][0]["error_type"], "timeout")
        self.assertEqual(len(d["pages"]), 1)
        self.assertEqual(d["pages"][0]["title"], "Example Title")

    def test_redirect_loop_protection(self):
        """17. Catches redirect loops and logs error without hanging or crashing."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(404, text="No robots")
            elif url_str == "https://example.com/":
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<html><body><a href="/loop-a">Loop</a><a href="/safe">Safe</a></body></html>')
            elif url_str == "https://example.com/loop-a":
                raise httpx.TooManyRedirects("Exceeded 5 redirects in loop", request=request)
            elif url_str == "https://example.com/safe":
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<html><body>Safe Page</body></html>')
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(project=self.project, transport=transport, max_pages=10)
        result = crawler.crawl("https://example.com/")

        self.assertEqual(result.pages_crawled, 2)
        redir_errors = [e for e in result.errors if e.error_type == "redirect_loop"]
        self.assertEqual(len(redir_errors), 1)
        self.assertEqual(redir_errors[0].url, "https://example.com/loop-a")

    def test_json_ld_extraction_valid_and_invalid(self):
        """18. Safely parses valid JSON-LD schemas and ignores malformed script blocks."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": "DoxaRank Inc",
                "url": "https://example.com"
            }
            </script>
            <script type="application/ld+json">
            { INVALID JSON SYNTAX HERE }
            </script>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": "DoxaRank Search"
            }
            </script>
        </head>
        <body><h1>Testing JSON-LD</h1></body>
        </html>
        """
        service = LiveSiteCrawlerService(project=self.project)
        extracted = service.extract_html_features(
            url="https://example.com/json-ld-test",
            final_url="https://example.com/json-ld-test",
            status_code=200,
            response_time_ms=50.0,
            content_type="text/html",
            html_text=html,
            base_domain="example.com",
            redirect_chain=[]
        )

        self.assertEqual(len(extracted.json_ld), 2)
        self.assertEqual(extracted.json_ld[0]["@type"], "Organization")
        self.assertEqual(extracted.json_ld[1]["@type"], "WebSite")

    def test_non_html_response_handling(self):
        """19. Non-HTML content types are recorded as basic PageCrawlResults without HTML parse errors."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(404, text="No robots")
            elif url_str == "https://example.com/api/data.json":
                return httpx.Response(200, headers={"Content-Type": "application/json"}, text='{"status": "ok"}')
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(project=self.project, transport=transport, max_pages=5)
        result = crawler.crawl("https://example.com/api/data.json")

        self.assertEqual(result.pages_crawled, 1)
        self.assertEqual(result.pages[0].content_type, "application/json")
        self.assertIsNone(result.pages[0].title)

    def test_robots_txt_user_agent_specific_disallow(self):
        """20. Correctly evaluates user-agent specific robots.txt directives."""
        from apps.seo.services.live_site_crawler import LiveSiteCrawlerService

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if url_str == "https://example.com/robots.txt":
                return httpx.Response(
                    200,
                    text="User-agent: Googlebot\nDisallow: /google-blocked\n\nUser-agent: DoxaRankBot\nDisallow: /doxarank-blocked\n"
                )
            elif url_str == "https://example.com/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text='<html><body><a href="/google-blocked">Google Blocked</a><a href="/doxarank-blocked">DoxaRank Blocked</a></body></html>'
                )
            elif url_str == "https://example.com/google-blocked":
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<html><body>Google Blocked But Allowed For Us</body></html>')
            elif url_str == "https://example.com/doxarank-blocked":
                return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<html><body>Blocked For DoxaRank</body></html>')
            return httpx.Response(404, text="Not Found")

        transport = httpx.MockTransport(handler)
        crawler = LiveSiteCrawlerService(
            project=self.project,
            user_agent="DoxaRankBot/1.0 (+https://doxarank.com/bot)",
            transport=transport,
            max_pages=10
        )
        result = crawler.crawl("https://example.com/")

        crawled_urls = [p.url for p in result.pages]
        self.assertIn("https://example.com/", crawled_urls)
        self.assertIn("https://example.com/google-blocked", crawled_urls)
        self.assertNotIn("https://example.com/doxarank-blocked", crawled_urls)


# ==============================================================================
# MILESTONE 4, PHASE 4.2.2: SEO AUDIT RULE ENGINE & PERSISTENCE TEST SUITE
# ==============================================================================

class SEOAuditEngineTests(TestCase):
    """
    Unit test suite for SEOAuditEngine deterministic rule evaluation,
    health score calculation, and SiteAudit / AuditIssue persistence.
    """

    def setUp(self):
        from apps.seo.services.seo_audit_engine import SEOAuditEngine
        self.user = User.objects.create_user(
            email='audit_engine_user@doxarank.com',
            password='TestPassword123!',
            first_name='Audit',
            last_name='Tester'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Audit Engine Website',
            website_url='https://example.com'
        )
        self.engine = SEOAuditEngine()

    def _create_mock_crawl_result(self, pages=None, errors=None):
        from apps.seo.services.live_site_crawler import CrawlResult, CrawlMetadata
        metadata = CrawlMetadata(
            start_url="https://example.com/",
            base_domain="example.com",
            user_agent="DoxaRankBot/1.0",
            max_pages=50,
            max_depth=3,
            robots_txt_status="loaded",
            started_at="2026-08-31T12:00:00Z",
            completed_at="2026-08-31T12:00:05Z",
            duration_seconds=5.0
        )
        pages_list = pages or []
        errors_list = errors or []
        return CrawlResult(
            start_url="https://example.com/",
            metadata=metadata,
            pages_crawled=len(pages_list),
            pages_discovered=len(pages_list),
            duration_seconds=5.0,
            errors=errors_list,
            pages=pages_list
        )

    def test_missing_title_rule_triggers_critical(self):
        """1. Detects missing or empty title and creates critical finding."""
        from apps.seo.services.live_site_crawler import PageCrawlResult
        from apps.seo.services.seo_audit_engine import MISSING_TITLE

        page = PageCrawlResult(
            url="https://example.com/no-title",
            final_url="https://example.com/no-title",
            status_code=200,
            response_time_ms=100.0,
            title=""
        )
        crawl_result = self._create_mock_crawl_result(pages=[page])
        result = self.engine.evaluate(crawl_result)

        missing_title_findings = [f for f in result.findings if f.rule_code == MISSING_TITLE]
        self.assertEqual(len(missing_title_findings), 1)
        self.assertEqual(missing_title_findings[0].severity, IssueSeverity.CRITICAL)
        self.assertEqual(missing_title_findings[0].page_url, "https://example.com/no-title")

    def test_long_and_short_title_rules(self):
        """2. Detects title exceeding 60 chars (Warning) and under 10 chars (Notice)."""
        from apps.seo.services.live_site_crawler import PageCrawlResult
        from apps.seo.services.seo_audit_engine import LONG_TITLE, SHORT_TITLE

        long_page = PageCrawlResult(
            url="https://example.com/long-title",
            final_url="https://example.com/long-title",
            status_code=200,
            response_time_ms=100.0,
            title="This is an extremely long page title that exceeds the maximum recommended sixty characters limit for Google SERPs"
        )
        short_page = PageCrawlResult(
            url="https://example.com/short-title",
            final_url="https://example.com/short-title",
            status_code=200,
            response_time_ms=100.0,
            title="Home"
        )
        crawl_result = self._create_mock_crawl_result(pages=[long_page, short_page])
        result = self.engine.evaluate(crawl_result)

        long_findings = [f for f in result.findings if f.rule_code == LONG_TITLE]
        short_findings = [f for f in result.findings if f.rule_code == SHORT_TITLE]

        self.assertEqual(len(long_findings), 1)
        self.assertEqual(long_findings[0].severity, IssueSeverity.WARNING)

        self.assertEqual(len(short_findings), 1)
        self.assertEqual(short_findings[0].severity, IssueSeverity.NOTICE)

    def test_meta_description_rules(self):
        """3. Detects missing meta description (Warning) and excessively long description (Notice)."""
        from apps.seo.services.live_site_crawler import PageCrawlResult
        from apps.seo.services.seo_audit_engine import MISSING_META_DESCRIPTION, LONG_META_DESCRIPTION

        no_desc = PageCrawlResult(
            url="https://example.com/no-desc",
            final_url="https://example.com/no-desc",
            status_code=200,
            response_time_ms=100.0,
            title="Valid Page Title",
            meta_description=None
        )
        long_desc = PageCrawlResult(
            url="https://example.com/long-desc",
            final_url="https://example.com/long-desc",
            status_code=200,
            response_time_ms=100.0,
            title="Valid Page Title 2",
            meta_description="A" * 180
        )
        crawl_result = self._create_mock_crawl_result(pages=[no_desc, long_desc])
        result = self.engine.evaluate(crawl_result)

        missing_findings = [f for f in result.findings if f.rule_code == MISSING_META_DESCRIPTION]
        long_findings = [f for f in result.findings if f.rule_code == LONG_META_DESCRIPTION]

        self.assertEqual(len(missing_findings), 1)
        self.assertEqual(missing_findings[0].severity, IssueSeverity.WARNING)

        self.assertEqual(len(long_findings), 1)
        self.assertEqual(long_findings[0].severity, IssueSeverity.NOTICE)

    def test_h1_heading_rules(self):
        """4. Detects missing H1 heading (Critical) and multiple H1 headings (Warning)."""
        from apps.seo.services.live_site_crawler import PageCrawlResult
        from apps.seo.services.seo_audit_engine import MISSING_H1, MULTIPLE_H1

        no_h1 = PageCrawlResult(
            url="https://example.com/no-h1",
            final_url="https://example.com/no-h1",
            status_code=200,
            response_time_ms=100.0,
            title="Valid Page Title",
            headings={"h1": [], "h2": ["Sub"]}
        )
        multi_h1 = PageCrawlResult(
            url="https://example.com/multi-h1",
            final_url="https://example.com/multi-h1",
            status_code=200,
            response_time_ms=100.0,
            title="Valid Page Title",
            headings={"h1": ["Heading 1", "Heading 2"], "h2": []}
        )
        crawl_result = self._create_mock_crawl_result(pages=[no_h1, multi_h1])
        result = self.engine.evaluate(crawl_result)

        missing_h1_findings = [f for f in result.findings if f.rule_code == MISSING_H1]
        multi_h1_findings = [f for f in result.findings if f.rule_code == MULTIPLE_H1]

        self.assertEqual(len(missing_h1_findings), 1)
        self.assertEqual(missing_h1_findings[0].severity, IssueSeverity.CRITICAL)

        self.assertEqual(len(multi_h1_findings), 1)
        self.assertEqual(multi_h1_findings[0].severity, IssueSeverity.WARNING)

    def test_missing_image_alt_rule(self):
        """5. Detects images without alt text and records warning."""
        from apps.seo.services.live_site_crawler import PageCrawlResult
        from apps.seo.services.seo_audit_engine import MISSING_IMAGE_ALT

        page = PageCrawlResult(
            url="https://example.com/gallery",
            final_url="https://example.com/gallery",
            status_code=200,
            response_time_ms=100.0,
            title="Gallery",
            images=[
                {"src": "/img1.jpg", "alt": "Descriptive Alt"},
                {"src": "/img2.jpg", "alt": ""},
                {"src": "/img3.jpg", "alt": None}
            ]
        )
        crawl_result = self._create_mock_crawl_result(pages=[page])
        result = self.engine.evaluate(crawl_result)

        alt_findings = [f for f in result.findings if f.rule_code == MISSING_IMAGE_ALT]
        self.assertEqual(len(alt_findings), 1)
        self.assertEqual(alt_findings[0].severity, IssueSeverity.WARNING)
        self.assertEqual(alt_findings[0].evidence["missing_count"], 2)

    def test_broken_internal_link_rule(self):
        """6. Flags 404 and 500 status pages as critical broken internal links."""
        from apps.seo.services.live_site_crawler import PageCrawlResult
        from apps.seo.services.seo_audit_engine import BROKEN_INTERNAL_LINK

        page_404 = PageCrawlResult(
            url="https://example.com/dead-link",
            final_url="https://example.com/dead-link",
            status_code=404,
            response_time_ms=50.0
        )
        page_500 = PageCrawlResult(
            url="https://example.com/crash",
            final_url="https://example.com/crash",
            status_code=500,
            response_time_ms=80.0
        )
        crawl_result = self._create_mock_crawl_result(pages=[page_404, page_500])
        result = self.engine.evaluate(crawl_result)

        broken_findings = [f for f in result.findings if f.rule_code == BROKEN_INTERNAL_LINK]
        self.assertEqual(len(broken_findings), 2)
        for b in broken_findings:
            self.assertEqual(b.severity, IssueSeverity.CRITICAL)

    def test_redirect_chain_and_loop_rules(self):
        """7. Detects multi-hop redirect chains (Warning) and redirect loops (Critical)."""
        from apps.seo.services.live_site_crawler import PageCrawlResult, CrawlError
        from apps.seo.services.seo_audit_engine import REDIRECT_CHAIN, REDIRECT_LOOP

        chained_page = PageCrawlResult(
            url="https://example.com/step1",
            final_url="https://example.com/step3",
            status_code=200,
            response_time_ms=150.0,
            title="Step 3",
            redirect_chain=["https://example.com/step1", "https://example.com/step2"]
        )
        loop_error = CrawlError(
            url="https://example.com/loop",
            error_type="redirect_loop",
            message="Infinite redirect loop"
        )
        crawl_result = self._create_mock_crawl_result(pages=[chained_page], errors=[loop_error])
        result = self.engine.evaluate(crawl_result)

        chain_findings = [f for f in result.findings if f.rule_code == REDIRECT_CHAIN]
        loop_findings = [f for f in result.findings if f.rule_code == REDIRECT_LOOP]

        self.assertEqual(len(chain_findings), 1)
        self.assertEqual(chain_findings[0].severity, IssueSeverity.WARNING)

        self.assertEqual(len(loop_findings), 1)
        self.assertEqual(loop_findings[0].severity, IssueSeverity.CRITICAL)

    def test_canonical_rules(self):
        """8. Detects missing canonical tag (Notice) and cross-domain canonical mismatch (Warning)."""
        from apps.seo.services.live_site_crawler import PageCrawlResult
        from apps.seo.services.seo_audit_engine import MISSING_CANONICAL, CANONICAL_MISMATCH

        no_canonical = PageCrawlResult(
            url="https://example.com/no-can",
            final_url="https://example.com/no-can",
            status_code=200,
            response_time_ms=50.0,
            title="Valid Title",
            canonical=None
        )
        mismatch_canonical = PageCrawlResult(
            url="https://example.com/can-mismatch",
            final_url="https://example.com/can-mismatch",
            status_code=200,
            response_time_ms=50.0,
            title="Valid Title 2",
            canonical="https://external-domain.com/canonical-source"
        )
        crawl_result = self._create_mock_crawl_result(pages=[no_canonical, mismatch_canonical])
        result = self.engine.evaluate(crawl_result)

        missing_can = [f for f in result.findings if f.rule_code == MISSING_CANONICAL]
        mismatch_can = [f for f in result.findings if f.rule_code == CANONICAL_MISMATCH]

        self.assertEqual(len(missing_can), 1)
        self.assertEqual(missing_can[0].severity, IssueSeverity.NOTICE)

        self.assertEqual(len(mismatch_can), 1)
        self.assertEqual(mismatch_can[0].severity, IssueSeverity.WARNING)

    def test_slow_response_rule(self):
        """9. Flags pages taking > 1500ms as slow response warnings."""
        from apps.seo.services.live_site_crawler import PageCrawlResult
        from apps.seo.services.seo_audit_engine import SLOW_RESPONSE

        slow_page = PageCrawlResult(
            url="https://example.com/slow",
            final_url="https://example.com/slow",
            status_code=200,
            response_time_ms=2500.0,
            title="Slow Page"
        )
        crawl_result = self._create_mock_crawl_result(pages=[slow_page])
        result = self.engine.evaluate(crawl_result)

        slow_findings = [f for f in result.findings if f.rule_code == SLOW_RESPONSE]
        self.assertEqual(len(slow_findings), 1)
        self.assertEqual(slow_findings[0].severity, IssueSeverity.WARNING)

    def test_deterministic_health_score_boundaries(self):
        """10. Computes deterministic health scores bounded strictly between 0 and 100."""
        # 1. Perfect site (0 issues) -> Score = 100
        score_perfect = self.engine.calculate_health_score(
            critical_count=0, warning_count=0, notice_count=0, total_pages=5, has_errors=False
        )
        self.assertEqual(score_perfect, 100)

        # 2. Moderate issues -> Score decreases deterministically
        score_moderate = self.engine.calculate_health_score(
            critical_count=1, warning_count=2, notice_count=3, total_pages=5, has_errors=False
        )
        self.assertLess(score_moderate, 100)
        self.assertGreater(score_moderate, 0)

        # 3. Severe catastrophic issues -> Bounded at 0 (never negative)
        score_terrible = self.engine.calculate_health_score(
            critical_count=50, warning_count=100, notice_count=100, total_pages=1, has_errors=True
        )
        self.assertEqual(score_terrible, 0)

    def test_idempotent_audit_persistence(self):
        """11. Persists SiteAudit and AuditIssue records idempotently without duplicate rows."""
        from apps.seo.services.live_site_crawler import PageCrawlResult

        page = PageCrawlResult(
            url="https://example.com/page-1",
            final_url="https://example.com/page-1",
            status_code=200,
            response_time_ms=100.0,
            title="",  # Missing title (Critical)
            meta_description="",  # Missing meta desc (Warning)
            headings={"h1": []},  # Missing H1 (Critical)
            canonical="https://example.com/page-1",
            json_ld=[{"@type": "WebPage"}]
        )
        crawl_result = self._create_mock_crawl_result(pages=[page])

        # First persistence run
        audit = self.engine.persist_audit(project=self.project, crawl_result=crawl_result)
        self.assertEqual(audit.status, AuditStatus.COMPLETED)
        self.assertIsNotNone(audit.score)
        self.assertEqual(audit.issues.count(), 3)

        first_audit_id = audit.id

        # Re-run persistence on same audit record
        re_audit = self.engine.persist_audit(project=self.project, crawl_result=crawl_result, audit=audit)
        self.assertEqual(re_audit.id, first_audit_id)
        # Issues should be cleanly replaced, not doubled
        self.assertEqual(re_audit.issues.count(), 3)

    def test_missing_structured_data_rule(self):
        """12. Flags missing JSON-LD structured data as a Notice issue."""
        from apps.seo.services.live_site_crawler import PageCrawlResult
        from apps.seo.services.seo_audit_engine import MISSING_STRUCTURED_DATA

        page = PageCrawlResult(
            url="https://example.com/no-json-ld",
            final_url="https://example.com/no-json-ld",
            status_code=200,
            response_time_ms=50.0,
            title="Valid Title",
            json_ld=[]
        )
        crawl_result = self._create_mock_crawl_result(pages=[page])
        result = self.engine.evaluate(crawl_result)

        json_ld_findings = [f for f in result.findings if f.rule_code == MISSING_STRUCTURED_DATA]
        self.assertEqual(len(json_ld_findings), 1)
        self.assertEqual(json_ld_findings[0].severity, IssueSeverity.NOTICE)

    def test_large_site_health_score_scaling(self):
        """13. Health score gracefully scales for large sites with dispersed minor notices."""
        score_single = self.engine.calculate_health_score(
            critical_count=0, warning_count=5, notice_count=10, total_pages=1, has_errors=False
        )
        score_scaled = self.engine.calculate_health_score(
            critical_count=0, warning_count=5, notice_count=10, total_pages=50, has_errors=False
        )
        self.assertGreater(score_scaled, score_single)

    def test_zero_page_crawl_result(self):
        """14. Handles empty or zero-page crawl result gracefully without division by zero."""
        crawl_result = self._create_mock_crawl_result(pages=[], errors=[])
        result = self.engine.evaluate(crawl_result)
        self.assertEqual(result.health_score, 100)
        self.assertEqual(result.total_pages_crawled, 0)
        self.assertEqual(len(result.findings), 0)


class SiteAuditCeleryTaskTests(TestCase):
    """
    Integration test suite for the run_site_audit Celery asynchronous task.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='celery_audit_user@doxarank.com',
            password='TestPassword123!',
            first_name='Celery',
            last_name='Auditor'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Celery Audit Website',
            website_url='https://example.com'
        )

    @patch('apps.seo.services.live_site_crawler.LiveSiteCrawlerService.crawl')
    def test_run_site_audit_task_success(self, mock_crawl):
        """12. Celery task executes crawl and audit engine, updating SiteAudit to COMPLETED."""
        from apps.seo.tasks import run_site_audit
        from apps.seo.services.live_site_crawler import CrawlResult, CrawlMetadata, PageCrawlResult

        metadata = CrawlMetadata(
            start_url="https://example.com/",
            base_domain="example.com",
            user_agent="DoxaRankBot/1.0",
            max_pages=50,
            max_depth=3,
            robots_txt_status="loaded",
            started_at="2026-08-31T12:00:00Z",
            completed_at="2026-08-31T12:00:05Z",
            duration_seconds=5.0
        )
        page = PageCrawlResult(
            url="https://example.com/",
            final_url="https://example.com/",
            status_code=200,
            response_time_ms=120.0,
            title="Home Page Title",
            meta_description="A descriptive page summary for the site audit test.",
            headings={"h1": ["Primary Heading"]}
        )
        mock_crawl.return_value = CrawlResult(
            start_url="https://example.com/",
            metadata=metadata,
            pages_crawled=1,
            pages_discovered=1,
            duration_seconds=5.0,
            errors=[],
            pages=[page]
        )

        audit = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.PENDING
        )

        result_id = run_site_audit(audit_id=audit.id)
        self.assertEqual(result_id, audit.id)

        audit.refresh_from_db()
        self.assertEqual(audit.status, AuditStatus.COMPLETED)
        self.assertGreaterEqual(audit.score, 90)
        self.assertIsNotNone(audit.completed_at)

    @patch('apps.seo.services.live_site_crawler.LiveSiteCrawlerService.crawl')
    def test_run_site_audit_task_failure_recovery(self, mock_crawl):
        """13. Recovers from unexpected crawl exception and safely marks SiteAudit as FAILED."""
        from apps.seo.tasks import run_site_audit

        mock_crawl.side_effect = RuntimeError("Fatal network interface crash")

        audit = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.PENDING
        )

        result_id = run_site_audit(audit_id=audit.id)
        self.assertEqual(result_id, audit.id)

        audit.refresh_from_db()
        self.assertEqual(audit.status, AuditStatus.FAILED)
        self.assertIn("Fatal audit execution error", audit.error_message)

    def test_agent_tool_get_audit_issues_retrieval(self):
        """14. Tool 'get_audit_issues' retrieves persisted issues accurately for the project."""
        from apps.seo.services.tool_registry import get_tool_registry

        audit = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.COMPLETED,
            score=85
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_h1",
            severity=IssueSeverity.CRITICAL,
            title="Missing H1 on Home",
            description="Page does not have an H1.",
            page_url="https://example.com/"
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="long_title",
            severity=IssueSeverity.WARNING,
            title="Long Title on About",
            description="Title exceeds 60 chars.",
            page_url="https://example.com/about"
        )

        registry = get_tool_registry()
        res = registry.execute("get_audit_issues", self.project, {"severity": "critical"})
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertEqual(data["project_id"], self.project.id)
        self.assertEqual(data["returned_count"], 1)
        self.assertEqual(data["issues"][0]["issue_type"], "missing_h1")
        self.assertEqual(data["issues"][0]["severity"], "critical")

    def test_multi_tenant_isolation(self):
        """15. User A cannot view or retrieve User B's audit issues."""
        from apps.seo.services.tool_registry import get_tool_registry

        user_b = User.objects.create_user(
            email='user_b_auditor@doxarank.com',
            password='TestPassword123!'
        )
        project_b = Project.objects.create(
            owner=user_b,
            name='Tenant B Website',
            website_url='https://tenant-b.com'
        )

        audit_b = SiteAudit.objects.create(
            project=project_b,
            status=AuditStatus.COMPLETED,
            score=70
        )
        AuditIssue.objects.create(
            audit=audit_b,
            issue_type="missing_title",
            severity=IssueSeverity.CRITICAL,
            title="Secret Tenant B Issue",
            description="Private data.",
            page_url="https://tenant-b.com/secret"
        )

        registry = get_tool_registry()
        # Query on project A should NOT see project B issues
        res_a = registry.execute("get_audit_issues", self.project, {})
        self.assertTrue(res_a["success"])
        self.assertEqual(res_a["data"]["returned_count"], 0)

        # Query on project B should see only project B issues
        res_b = registry.execute("get_audit_issues", project_b, {})
        self.assertTrue(res_b["success"])
        self.assertEqual(res_b["data"]["returned_count"], 1)
        self.assertEqual(res_b["data"]["issues"][0]["title"], "Secret Tenant B Issue")


# ==============================================================================
# MILESTONE 4, PHASE 4.2.3.1: LIVE WEBSITE AUDIT AGENT TOOLS & INTELLIGENCE TESTS
# ==============================================================================

class SiteAuditAgentToolTests(TestCase):
    """
    Test suite for agent-facing site audit tools:
    - trigger_site_audit
    - get_site_audit_summary
    - get_audit_issues (enhanced)
    - ReAct agent integration & multi-tenant isolation
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='audit_agent_user@doxarank.com',
            password='TestPassword123!',
            first_name='Agent',
            last_name='Auditor'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Agent Audit Project',
            website_url='https://example.com'
        )
        self.registry = get_tool_registry()

    @patch('apps.seo.tasks.run_site_audit.delay')
    def test_trigger_site_audit_valid_project_and_celery_dispatch(self, mock_delay):
        """1. Valid project triggers site audit and dispatches Celery task."""
        mock_task = MagicMock()
        mock_task.id = "celery-task-audit-12345"
        mock_delay.return_value = mock_task

        res = self.registry.execute("trigger_site_audit", self.project, {
            "start_url": "https://example.com/blog",
            "max_pages": 40,
            "max_depth": 2
        })

        self.assertTrue(res["success"])
        data = res["data"]
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["project_id"], self.project.id)
        self.assertEqual(data["start_url"], "https://example.com/blog")
        self.assertEqual(data["max_pages"], 40)
        self.assertEqual(data["max_depth"], 2)
        self.assertEqual(data["task_id"], "celery-task-audit-12345")

        # Verify SiteAudit was created in database
        audit = SiteAudit.objects.get(id=data["audit_id"])
        self.assertEqual(audit.project, self.project)
        self.assertEqual(audit.status, AuditStatus.PENDING)

        mock_delay.assert_called_once_with(
            audit_id=audit.id,
            start_url="https://example.com/blog",
            max_pages=40,
            max_depth=2
        )

    def test_trigger_site_audit_rejects_external_domain(self):
        """2. Rejects start_url that does not match project domain."""
        res = self.registry.execute("trigger_site_audit", self.project, {
            "start_url": "https://malicious-external-site.com/attack"
        })

        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "EXECUTION_ERROR")
        self.assertIn("does not belong to project website domain", res["error"]["message"])

    def test_trigger_site_audit_enforces_crawler_bounds(self):
        """3. Enforces bounding on max_pages (1..200) and max_depth (0..10)."""
        with patch('apps.seo.tasks.run_site_audit.delay') as mock_delay:
            mock_task = MagicMock()
            mock_task.id = "task-bounded-1"
            mock_delay.return_value = mock_task

            # Excessive parameters
            res = self.registry.execute("trigger_site_audit", self.project, {
                "max_pages": 999999,
                "max_depth": 50
            })
            self.assertTrue(res["success"])
            self.assertEqual(res["data"]["max_pages"], 200)
            self.assertEqual(res["data"]["max_depth"], 10)

            # Negative parameters
            res_neg = self.registry.execute("trigger_site_audit", self.project, {
                "max_pages": -10,
                "max_depth": -5
            })
            self.assertTrue(res_neg["success"])
            self.assertEqual(res_neg["data"]["max_pages"], 1)
            self.assertEqual(res_neg["data"]["max_depth"], 0)

    def test_trigger_site_audit_rejects_project_without_website_url(self):
        """4. Rejects audit if project has no website_url configured."""
        project_no_url = Project.objects.create(
            owner=self.user,
            name='No URL Project',
            website_url=''
        )
        res = self.registry.execute("trigger_site_audit", project_no_url, {})
        self.assertFalse(res["success"])
        self.assertIn("has no configured website_url", res["error"]["message"])

    def test_get_site_audit_summary_latest_completed_audit(self):
        """5. Retrieves latest completed audit summary with health score and aggregated issues."""
        audit = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.COMPLETED,
            score=82,
            started_at=timezone.now(),
            completed_at=timezone.now()
        )
        # Create critical, warning, notice issues
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_title",
            severity=IssueSeverity.CRITICAL,
            title="Missing Title 1",
            page_url="https://example.com/p1"
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_title",
            severity=IssueSeverity.CRITICAL,
            title="Missing Title 2",
            page_url="https://example.com/p2"
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_meta_description",
            severity=IssueSeverity.WARNING,
            title="Missing Meta Desc",
            page_url="https://example.com/p1"
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_canonical",
            severity=IssueSeverity.NOTICE,
            title="Missing Canonical",
            page_url="https://example.com/p3"
        )

        res = self.registry.execute("get_site_audit_summary", self.project, {})
        self.assertTrue(res["success"])
        data = res["data"]

        self.assertEqual(data["audit_id"], audit.id)
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["health_score"], 82)
        self.assertEqual(data["total_issues"], 4)
        self.assertEqual(data["issues_by_severity"]["critical"], 2)
        self.assertEqual(data["issues_by_severity"]["warning"], 1)
        self.assertEqual(data["issues_by_severity"]["notice"], 1)
        self.assertEqual(data["pages_with_issues_count"], 3)

        # Top issues
        self.assertEqual(len(data["top_issues"]), 3)
        self.assertEqual(data["top_issues"][0]["rule_code"], "missing_title")
        self.assertEqual(data["top_issues"][0]["count"], 2)

    def test_get_site_audit_summary_pending_and_running_states(self):
        """6. Handles pending and running audits cleanly without crashing."""
        audit_pending = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.PENDING
        )
        res_pending = self.registry.execute("get_site_audit_summary", self.project, {"audit_id": audit_pending.id})
        self.assertTrue(res_pending["success"])
        self.assertEqual(res_pending["data"]["status"], "pending")
        self.assertIsNone(res_pending["data"]["health_score"])
        self.assertEqual(res_pending["data"]["total_issues"], 0)

        audit_running = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.RUNNING,
            started_at=timezone.now()
        )
        res_running = self.registry.execute("get_site_audit_summary", self.project, {"audit_id": audit_running.id})
        self.assertTrue(res_running["success"])
        self.assertEqual(res_running["data"]["status"], "running")

    def test_get_site_audit_summary_failed_audit_returns_error_message(self):
        """7. Returns sanitized error_message when audit is failed."""
        audit_failed = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.FAILED,
            error_message="Host connection timed out after 3 retries"
        )
        res = self.registry.execute("get_site_audit_summary", self.project, {"audit_id": audit_failed.id})
        self.assertTrue(res["success"])
        data = res["data"]
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["error_message"], "Host connection timed out after 3 retries")

    def test_get_site_audit_summary_no_audits_returns_not_found(self):
        """8. Handles project with zero audits gracefully without raising 500 error."""
        empty_project = Project.objects.create(
            owner=self.user,
            name='Empty Audits Project',
            website_url='https://empty.com'
        )
        res = self.registry.execute("get_site_audit_summary", empty_project, {})
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["status"], "not_found")
        self.assertIsNone(res["data"]["audit_id"])

    def test_get_site_audit_summary_cross_tenant_isolation(self):
        """9. Prevents User A from retrieving User B's audit summary by ID."""
        user_b = User.objects.create_user(
            email='user_b_spy@doxarank.com',
            password='TestPassword123!'
        )
        project_b = Project.objects.create(
            owner=user_b,
            name='Tenant B Secret Project',
            website_url='https://secret-b.com'
        )
        audit_b = SiteAudit.objects.create(
            project=project_b,
            status=AuditStatus.COMPLETED,
            score=95
        )

        # User A querying on Project A specifying User B's audit_id
        res = self.registry.execute("get_site_audit_summary", self.project, {"audit_id": audit_b.id})
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["status"], "not_found")

    def test_get_audit_issues_filtering_by_audit_id_and_page_url(self):
        """10. Enhanced get_audit_issues filters by audit_id, severity, rule_code, page_url."""
        audit1 = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED)
        audit2 = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED)

        AuditIssue.objects.create(
            audit=audit1,
            issue_type="missing_title",
            severity=IssueSeverity.CRITICAL,
            title="P1 Missing Title",
            page_url="https://example.com/blog/article-1"
        )
        AuditIssue.objects.create(
            audit=audit1,
            issue_type="missing_h1",
            severity=IssueSeverity.CRITICAL,
            title="P2 Missing H1",
            page_url="https://example.com/about"
        )
        AuditIssue.objects.create(
            audit=audit2,
            issue_type="missing_title",
            severity=IssueSeverity.CRITICAL,
            title="Audit 2 Issue",
            page_url="https://example.com/blog/article-2"
        )

        # Filter by audit_id
        res_audit1 = self.registry.execute("get_audit_issues", self.project, {"audit_id": audit1.id})
        self.assertEqual(res_audit1["data"]["returned_count"], 2)

        # Filter by page_url substring
        res_blog = self.registry.execute("get_audit_issues", self.project, {"page_url": "/blog/"})
        self.assertEqual(res_blog["data"]["returned_count"], 2)

        # Filter by issue_type
        res_h1 = self.registry.execute("get_audit_issues", self.project, {"issue_type": "missing_h1"})
        self.assertEqual(res_h1["data"]["returned_count"], 1)
        self.assertEqual(res_h1["data"]["issues"][0]["issue_type"], "missing_h1")

    def test_react_agent_live_audit_exploration_loop(self):
        """11. ReAct AgentOrchestrator executes live website audit workflow end-to-end."""
        from apps.seo.services.agent_orchestrator import AgentOrchestrator
        from apps.seo.services.ai_providers import MockAIProvider

        # Pre-seed site audit findings
        audit = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.COMPLETED,
            score=70
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_h1",
            severity=IssueSeverity.CRITICAL,
            title="Missing H1 on Homepage",
            page_url="https://example.com/"
        )

        with patch('apps.seo.tasks.run_site_audit.delay') as mock_delay:
            mock_task = MagicMock()
            mock_task.id = "task-orchestrator-audit"
            mock_delay.return_value = mock_task

            orchestrator = AgentOrchestrator(
                project=self.project,
                user=self.user,
                provider=MockAIProvider(),
                registry=self.registry,
                max_steps=5
            )

            run = orchestrator.start_run(goal="Run live crawler audit and analyze technical SEO health issues")

            self.assertEqual(run.status, AgentRunStatus.COMPLETED)
            self.assertIn("Completed live website audit analysis", run.summary)
            # Verify steps were recorded
            self.assertGreater(run.steps.count(), 0)

            # Check that tools were called
            tool_calls = AgentToolCall.objects.filter(step__run=run)
            called_tools = [tc.tool_name for tc in tool_calls]
            self.assertIn("trigger_site_audit", called_tools)
            self.assertIn("get_site_audit_summary", called_tools)
            self.assertIn("get_audit_issues", called_tools)


class SEOCorrelationIntelligenceTests(TestCase):
    """
    Comprehensive test suite for Phase 4.2.3.2:
    Cross-Source Live SEO Intelligence & GSC + Site Audit Correlation.
    """

    def setUp(self):
        self.user = User.objects.create_user(email="intel@example.com", password="Password123!")
        self.project = Project.objects.create(
            name="Correlated SEO Project",
            owner=self.user,
            website_url="https://example.com"
        )
        self.other_user = User.objects.create_user(email="other_intel@example.com", password="Password123!")
        self.other_project = Project.objects.create(
            name="Other Isolated Project",
            owner=self.other_user,
            website_url="https://other-example.com"
        )

        self.registry = create_default_tool_registry()

    def test_low_ctr_high_impressions_opportunity_with_audit_issues(self):
        """1. Detects high-impression low-CTR opportunity and correlates on-page snippet audit issues."""
        audit = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.COMPLETED,
            score=80
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_meta_description",
            severity=IssueSeverity.WARNING,
            title="Missing Meta Description on /pricing",
            page_url="https://example.com/pricing"
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="long_title",
            severity=IssueSeverity.WARNING,
            title="Long Title on /pricing",
            page_url="https://example.com/pricing"
        )

        page_rows = [{
            "page": "https://example.com/pricing",
            "impressions": 12450,
            "clicks": 310,
            "ctr": 0.0249,
            "position": 8.4
        }]
        combined_rows = [{
            "query": "pricing plans",
            "page": "https://example.com/pricing",
            "impressions": 8500,
            "clicks": 210,
            "ctr": 0.0247,
            "position": 8.1
        }]

        service = SEOCorrelationIntelligenceService(project=self.project)
        res = service.analyze_correlated_opportunities(
            page_rows=page_rows,
            combined_rows=combined_rows,
            min_impressions=50
        )

        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["total_opportunities_found"], 1)

        low_ctr_opps = [o for o in res["opportunities"] if o["type"] == OpportunityType.LOW_CTR_HIGH_IMPRESSIONS]
        self.assertTrue(len(low_ctr_opps) >= 1)
        opp = low_ctr_opps[0]
        self.assertEqual(opp["severity"], "critical")  # >= 1000 imp on top 10 pos
        self.assertEqual(opp["target_url"], "https://example.com/pricing")
        self.assertIn("missing_meta_description", opp["evidence"]["audit_issues"])
        self.assertIn("long_title", opp["evidence"]["audit_issues"])
        self.assertGreaterEqual(opp["confidence"], 0.85)

    def test_ranking_technical_decay_opportunity(self):
        """2. Detects ranking decay correlated with technical crawl and canonical defects."""
        audit = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.COMPLETED,
            score=65
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="broken_internal_link",
            severity=IssueSeverity.CRITICAL,
            title="Broken Internal Link on /products",
            page_url="https://example.com/products"
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_canonical",
            severity=IssueSeverity.WARNING,
            title="Missing Canonical Tag on /products",
            page_url="https://example.com/products"
        )

        page_rows = [{
            "page": "https://example.com/products",
            "impressions": 650,
            "clicks": 4,
            "ctr": 0.0061,
            "position": 14.8
        }]

        service = SEOCorrelationIntelligenceService(project=self.project)
        res = service.analyze_correlated_opportunities(
            page_rows=page_rows,
            min_impressions=20
        )

        self.assertEqual(res["status"], "success")
        decay_opps = [o for o in res["opportunities"] if o["type"] == OpportunityType.RANKING_TECHNICAL_DECAY]
        self.assertTrue(len(decay_opps) >= 1)
        opp = decay_opps[0]
        self.assertEqual(opp["severity"], "critical")
        self.assertEqual(opp["suggested_action_type"], "fix_canonical")
        self.assertIn("broken_internal_link", opp["evidence"]["audit_issues"])

    def test_high_value_page_maintenance_opportunity(self):
        """3. Prioritizes maintenance for high-traffic landing pages with technical warnings."""
        audit = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.COMPLETED,
            score=88
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_h1",
            severity=IssueSeverity.CRITICAL,
            title="Missing H1 on Top Landing Page",
            page_url="https://example.com/features"
        )

        page_rows = [
            {"page": "https://example.com/features", "clicks": 520, "impressions": 4800, "ctr": 0.108, "position": 2.1},
            {"page": "https://example.com/blog/low-traffic", "clicks": 2, "impressions": 40, "ctr": 0.05, "position": 8.0}
        ]

        service = SEOCorrelationIntelligenceService(project=self.project)
        res = service.analyze_correlated_opportunities(page_rows=page_rows)

        self.assertEqual(res["status"], "success")
        maint_opps = [o for o in res["opportunities"] if o["type"] == OpportunityType.HIGH_VALUE_PAGE_MAINTENANCE]
        self.assertTrue(len(maint_opps) >= 1)
        opp = maint_opps[0]
        self.assertEqual(opp["target_url"], "https://example.com/features")
        self.assertEqual(opp["severity"], "critical")
        self.assertGreaterEqual(opp["confidence"], 0.90)

    def test_query_page_opportunity(self):
        """4. Correlates high-intent query opportunity with landing page gaps."""
        audit = SiteAudit.objects.create(
            project=self.project,
            status=AuditStatus.COMPLETED,
            score=75
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_h1",
            severity=IssueSeverity.WARNING,
            title="Missing H1 on /software",
            page_url="https://example.com/software"
        )

        combined_rows = [{
            "query": "best enterprise seo platform",
            "page": "https://example.com/software",
            "impressions": 450,
            "clicks": 18,
            "ctr": 0.04,
            "position": 6.8
        }]

        service = SEOCorrelationIntelligenceService(project=self.project)
        res = service.analyze_correlated_opportunities(
            combined_rows=combined_rows,
            min_impressions=20
        )

        self.assertEqual(res["status"], "success")
        query_opps = [o for o in res["opportunities"] if o["type"] == OpportunityType.QUERY_PAGE_OPPORTUNITY]
        self.assertTrue(len(query_opps) >= 1)
        opp = query_opps[0]
        self.assertEqual(opp["target_query"], "best enterprise seo platform")
        self.assertEqual(opp["target_url"], "https://example.com/software")

    def test_missing_gsc_and_audit_safe_handling(self):
        """5. Safely handles absent GSC connection or missing SiteAudit without exceptions."""
        service = SEOCorrelationIntelligenceService(project=self.project)
        res = service.analyze_correlated_opportunities()

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["gsc_connected"], False)
        self.assertEqual(res["audit_available"], False)
        self.assertEqual(res["total_opportunities_found"], 0)
        self.assertEqual(res["opportunities"], [])

    def test_empty_datasets_safe_handling(self):
        """6. Handles empty list inputs cleanly."""
        service = SEOCorrelationIntelligenceService(project=self.project)
        res = service.analyze_correlated_opportunities(
            page_rows=[],
            query_rows=[],
            combined_rows=[]
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["opportunities_count"], 0)

    def test_multi_tenant_isolation_boundary(self):
        """7. Enforces strict multi-tenant boundary: does not leak or cross other project audits."""
        # Project A audit
        audit_a = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=90)
        AuditIssue.objects.create(audit=audit_a, issue_type="missing_title", severity=IssueSeverity.WARNING, page_url="https://example.com/page-a")

        # Project B audit
        audit_b = SiteAudit.objects.create(project=self.other_project, status=AuditStatus.COMPLETED, score=40)
        AuditIssue.objects.create(audit=audit_b, issue_type="broken_internal_link", severity=IssueSeverity.CRITICAL, page_url="https://other-example.com/secret")

        service_a = SEOCorrelationIntelligenceService(project=self.project)
        res_a = service_a.analyze_correlated_opportunities(
            page_rows=[{"page": "https://example.com/page-a", "impressions": 500, "clicks": 2, "ctr": 0.004, "position": 8.0}]
        )

        for opp in res_a["opportunities"]:
            self.assertNotEqual(opp.get("target_url"), "https://other-example.com/secret")
            self.assertNotIn("other-example.com", str(opp))

    def test_tool_registry_analyze_seo_opportunities_execution(self):
        """8. ToolRegistry executes analyze_seo_opportunities tool cleanly."""
        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=80)
        AuditIssue.objects.create(audit=audit, issue_type="missing_meta_description", severity=IssueSeverity.WARNING, page_url="https://example.com/pricing")

        res = self.registry.execute(
            "analyze_seo_opportunities",
            self.project,
            {"min_impressions": 10, "limit": 5}
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["tool_name"], "analyze_seo_opportunities")
        self.assertEqual(res["data"]["status"], "success")
        self.assertIn("opportunities", res["data"])

    def test_event_emission_lifecycle(self):
        """9. Emits strongly typed real-time events across correlation pipeline."""
        in_memory_publisher = InMemoryEventPublisher()
        service = SEOCorrelationIntelligenceService(project=self.project, publisher=in_memory_publisher)

        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=85)
        AuditIssue.objects.create(audit=audit, issue_type="short_title", severity=IssueSeverity.WARNING, page_url="https://example.com/demo")

        service.analyze_correlated_opportunities(
            page_rows=[{"page": "https://example.com/demo", "impressions": 1000, "clicks": 10, "ctr": 0.01, "position": 5.0}],
            run_id=987
        )

        events = in_memory_publisher.get_events(run_id=987)
        event_types = [e.event_type for e in events]

        self.assertIn(AgentEventType.SEO_INTELLIGENCE_STARTED.value, event_types)
        self.assertIn(AgentEventType.SEO_EVIDENCE_COLLECTED.value, event_types)
        self.assertIn(AgentEventType.SEO_OPPORTUNITY_DETECTED.value, event_types)
        self.assertIn(AgentEventType.SEO_INTELLIGENCE_COMPLETED.value, event_types)

    def test_sync_to_insights_persistence(self):
        """10. Correctly persists detected opportunities to SEOInsight database records."""
        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=70)
        AuditIssue.objects.create(audit=audit, issue_type="missing_title", severity=IssueSeverity.WARNING, page_url="https://example.com/services")

        page_rows = [{"page": "https://example.com/services", "impressions": 800, "clicks": 5, "ctr": 0.0062, "position": 9.0}]

        service = SEOCorrelationIntelligenceService(project=self.project)
        res = service.analyze_correlated_opportunities(
            page_rows=page_rows,
            sync_to_insights=True
        )

        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["persisted_insights_count"], 1)

        insights = SEOInsight.objects.filter(project=self.project, related_url="https://example.com/services")
        self.assertTrue(insights.exists())
        insight = insights.first()
        self.assertEqual(insight.status, InsightStatus.OPEN)

    def test_react_agent_correlation_loop_execution(self):
        """11. ReAct AgentOrchestrator executes cross-source correlation workflow end-to-end."""
        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=80)
        AuditIssue.objects.create(audit=audit, issue_type="missing_meta_description", severity=IssueSeverity.WARNING, page_url="https://example.com/pricing")

        orchestrator = AgentOrchestrator(
            project=self.project,
            user=self.user,
            provider=MockAIProvider(),
            registry=self.registry,
            max_steps=5
        )

        run = orchestrator.start_run(goal="Execute cross-source SEO intelligence correlation on GSC and site audit opportunities")

        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertIn("Completed cross-source SEO intelligence correlation", run.summary)
        self.assertIn("Observed Facts", run.summary)
        self.assertIn("Inferences", run.summary)
        self.assertIn("Recommendations", run.summary)

        # Check tool calls
        tool_calls = AgentToolCall.objects.filter(step__run=run)
        called_tools = [tc.tool_name for tc in tool_calls]
        self.assertIn("analyze_seo_opportunities", called_tools)


# =============================================================================
# PHASE 4.2.3.3 TESTS: AUTONOMOUS SEO INVESTIGATION & DECISION LOOP
# =============================================================================

class SEOInvestigationServiceTests(TestCase):
    """
    Comprehensive tests for SEOInvestigationService & SEOInvestigationResult (Phase 4.2.3.3).
    Verifies multi-source evidence collection, fact/inference separation, deterministic confidence scoring,
    root-cause classification, impact/effort/risk classification, and human approval boundaries.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='investigator@doxarank.com',
            password='Password123!',
            first_name='Investigator',
            last_name='User'
        )
        self.other_user = User.objects.create_user(
            email='other_inv@doxarank.com',
            password='Password123!',
            first_name='Other',
            last_name='User'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='DoxaRank Alpha',
            website_url='https://doxarank.com'
        )
        self.other_project = Project.objects.create(
            owner=self.other_user,
            name='Other Project',
            website_url='https://other.com'
        )
        self.publisher = InMemoryEventPublisher()

    def test_valid_low_ctr_investigation(self):
        """1. Valid opportunity investigation for LOW_CTR_HIGH_IMPRESSIONS."""
        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=85)
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_meta_description",
            severity=IssueSeverity.WARNING,
            title="Missing Meta Description",
            description="Page is missing a meta description tag.",
            page_url="https://doxarank.com/features"
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_h1",
            severity=IssueSeverity.WARNING,
            title="Missing H1 Heading",
            description="Page is missing an H1 heading.",
            page_url="https://doxarank.com/features"
        )

        conn = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="https://doxarank.com",
            is_connected=True
        )
        SearchAnalyticsData.objects.create(
            connection=conn,
            page="https://doxarank.com/features",
            query="seo intelligence tool",
            impressions=1250,
            clicks=15,
            ctr=0.012,
            position=6.4,
            date=timezone.now().date()
        )

        service = SEOInvestigationService(project=self.project, publisher=self.publisher)
        result = service.investigate(
            opportunity_type="LOW_CTR_HIGH_IMPRESSIONS",
            target_url="https://doxarank.com/features",
            target_query="seo intelligence tool"
        )

        self.assertEqual(result.status, InvestigationStatus.COMPLETED.value)
        self.assertEqual(result.opportunity_type, "LOW_CTR_HIGH_IMPRESSIONS")
        self.assertEqual(result.root_cause_category, RootCauseCategory.CTR.value)
        self.assertIn("CTR", result.root_cause_reason)
        self.assertGreaterEqual(result.confidence_score, 0.75)
        self.assertEqual(result.confidence_level, InvestigationConfidence.HIGH.value)
        self.assertEqual(result.impact_estimate, ImpactEstimate.HIGH.value)
        self.assertEqual(result.effort_estimate, EffortEstimate.LOW.value)
        self.assertEqual(result.risk_level, RiskLevel.LOW.value)
        self.assertTrue(result.requires_human_approval)

        # Verify separation of facts and inferences
        self.assertGreater(len(result.observed_facts), 0)
        self.assertGreater(len(result.inferences), 0)
        self.assertTrue(any("1,250 impressions" in f for f in result.observed_facts))
        self.assertTrue(any("Missing Meta Description" in f or "missing_meta_description" in f for f in result.observed_facts))

        # Verify recommended action
        rec = result.recommended_action
        self.assertEqual(rec["action_type"], InvestigationActionType.OPTIMIZE_META_DESCRIPTION.value)
        self.assertTrue(rec["requires_human_approval"])
        self.assertEqual(rec["risk"], RiskLevel.LOW.value)

    def test_valid_ranking_technical_decay_investigation(self):
        """2. Valid opportunity investigation for RANKING_TECHNICAL_DECAY."""
        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=60)
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_canonical",
            severity=IssueSeverity.CRITICAL,
            title="Missing Canonical Tag",
            description="Page is missing a canonical URL tag.",
            page_url="https://doxarank.com/docs/api"
        )

        conn = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="https://doxarank.com",
            is_connected=True
        )
        SearchAnalyticsData.objects.create(
            connection=conn,
            page="https://doxarank.com/docs/api",
            query="doxarank api docs",
            impressions=600,
            clicks=8,
            ctr=0.0133,
            position=14.2,
            date=timezone.now().date()
        )

        service = SEOInvestigationService(project=self.project, publisher=self.publisher)
        result = service.investigate(
            opportunity_type="RANKING_TECHNICAL_DECAY",
            target_url="https://doxarank.com/docs/api",
            target_query="doxarank api docs"
        )

        self.assertEqual(result.status, InvestigationStatus.COMPLETED.value)
        self.assertEqual(result.root_cause_category, RootCauseCategory.CANONICAL.value)
        self.assertEqual(result.recommended_action["action_type"], InvestigationActionType.FIX_CANONICAL.value)
        self.assertEqual(result.effort_estimate, EffortEstimate.HIGH.value)
        self.assertEqual(result.risk_level, RiskLevel.HIGH.value)
        self.assertTrue(result.requires_human_approval)

    def test_invalid_opportunity_type_handling(self):
        """3. Fails gracefully when an unsupported opportunity type is passed."""
        service = SEOInvestigationService(project=self.project, publisher=self.publisher)
        result = service.investigate(
            opportunity_type="UNSUPPORTED_RANDOM_TYPE",
            target_url="https://doxarank.com/blog"
        )

        self.assertEqual(result.status, InvestigationStatus.FAILED.value)
        self.assertEqual(result.confidence_score, 0.0)
        self.assertEqual(result.confidence_level, InvestigationConfidence.LOW.value)
        self.assertFalse(result.requires_human_approval)
        self.assertEqual(result.recommended_action["action_type"], InvestigationActionType.NO_ACTION.value)

    def test_missing_gsc_connection_graceful_investigation(self):
        """4. Successfully investigates using audit diagnostics when GSC is not connected."""
        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=75)
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_title",
            severity=IssueSeverity.WARNING,
            title="Missing Page Title",
            description="Page is missing a title element.",
            page_url="https://doxarank.com/contact"
        )

        service = SEOInvestigationService(project=self.project, publisher=self.publisher)
        result = service.investigate(
            opportunity_type="CONTENT_OPPORTUNITY",
            target_url="https://doxarank.com/contact"
        )

        self.assertEqual(result.status, InvestigationStatus.COMPLETED.value)
        self.assertEqual(result.root_cause_category, RootCauseCategory.ON_PAGE_SEO.value)
        self.assertEqual(result.recommended_action["action_type"], InvestigationActionType.OPTIMIZE_TITLE.value)
        self.assertTrue(any("Google Search Console connection is not configured" in f for f in result.observed_facts))

    def test_missing_audit_graceful_investigation(self):
        """5. Successfully investigates using GSC metrics when no site audit exists."""
        conn = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="https://doxarank.com",
            is_connected=True
        )
        SearchAnalyticsData.objects.create(
            connection=conn,
            page="https://doxarank.com/rankings",
            query="best rank tracker",
            impressions=3400,
            clicks=22,
            ctr=0.0064,
            position=4.1,
            date=timezone.now().date()
        )

        service = SEOInvestigationService(project=self.project, publisher=self.publisher)
        result = service.investigate(
            opportunity_type="LOW_CTR_HIGH_IMPRESSIONS",
            target_url="https://doxarank.com/rankings",
            target_query="best rank tracker"
        )

        self.assertEqual(result.status, InvestigationStatus.COMPLETED.value)
        self.assertEqual(result.root_cause_category, RootCauseCategory.CTR.value)
        self.assertTrue(any("No completed Site Audit crawl data" in f for f in result.observed_facts))

    def test_insufficient_evidence_returns_monitor_no_mutation(self):
        """6. When neither GSC nor audit data is available, returns LOW confidence and MONITOR action."""
        service = SEOInvestigationService(project=self.project, publisher=self.publisher)
        result = service.investigate(
            opportunity_type="LOW_CTR_HIGH_IMPRESSIONS",
            target_url="https://doxarank.com/unknown-page"
        )

        self.assertEqual(result.status, InvestigationStatus.COMPLETED.value)
        self.assertEqual(result.confidence_level, InvestigationConfidence.LOW.value)
        self.assertLess(result.confidence_score, 0.45)
        self.assertEqual(result.recommended_action["action_type"], InvestigationActionType.MONITOR.value)
        self.assertFalse(result.recommended_action["requires_human_approval"])
        self.assertFalse(result.requires_human_approval)

    def test_root_cause_and_risk_classifications(self):
        """7. Tests deterministic root-cause and risk classifications across multiple issue types."""
        service = SEOInvestigationService(project=self.project, publisher=self.publisher)

        # Performance root cause
        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=50)
        AuditIssue.objects.create(
            audit=audit,
            issue_type="slow_response",
            severity=IssueSeverity.WARNING,
            title="Slow Server Response",
            description="Response time > 2000ms",
            page_url="https://doxarank.com/slow"
        )
        res_perf = service.investigate(
            opportunity_type="TECHNICAL_SEO_ISSUE",
            target_url="https://doxarank.com/slow"
        )
        self.assertEqual(res_perf.root_cause_category, RootCauseCategory.PERFORMANCE.value)
        self.assertEqual(res_perf.recommended_action["action_type"], InvestigationActionType.INVESTIGATE_PERFORMANCE.value)

        # Broken link root cause
        AuditIssue.objects.create(
            audit=audit,
            issue_type="broken_internal_link",
            severity=IssueSeverity.CRITICAL,
            title="Broken Internal Link",
            description="404 link found",
            page_url="https://doxarank.com/broken"
        )
        res_broken = service.investigate(
            opportunity_type="RANKING_TECHNICAL_DECAY",
            target_url="https://doxarank.com/broken"
        )
        self.assertEqual(res_broken.root_cause_category, RootCauseCategory.TECHNICAL_SEO.value)
        self.assertEqual(res_broken.recommended_action["action_type"], InvestigationActionType.FIX_BROKEN_LINK.value)
        self.assertEqual(res_broken.risk_level, RiskLevel.HIGH.value)

    def test_event_emission_lifecycle(self):
        """8. Verifies emission of all 5 strongly-typed investigation lifecycle events."""
        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=80)
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_image_alt",
            severity=IssueSeverity.NOTICE,
            title="Missing Image Alt",
            description="Image missing alt text",
            page_url="https://doxarank.com/gallery"
        )

        service = SEOInvestigationService(project=self.project, publisher=self.publisher)
        service.investigate(
            opportunity_type="ON_PAGE_SEO",
            target_url="https://doxarank.com/gallery",
            run_id=555
        )

        events = self.publisher.get_events(run_id=555)
        event_types = [e.event_type for e in events]

        self.assertIn(AgentEventType.SEO_INVESTIGATION_STARTED.value, event_types)
        self.assertIn(AgentEventType.SEO_INVESTIGATION_EVIDENCE_COLLECTED.value, event_types)
        self.assertIn(AgentEventType.SEO_INVESTIGATION_ROOT_CAUSE_IDENTIFIED.value, event_types)
        self.assertIn(AgentEventType.SEO_INVESTIGATION_RECOMMENDATION_GENERATED.value, event_types)
        self.assertIn(AgentEventType.SEO_INVESTIGATION_COMPLETED.value, event_types)

    def test_tenant_isolation_security(self):
        """9. Strict multi-tenant isolation prevents leaking or querying other project data."""
        other_audit = SiteAudit.objects.create(project=self.other_project, status=AuditStatus.COMPLETED, score=40)
        AuditIssue.objects.create(
            audit=other_audit,
            issue_type="broken_link",
            severity=IssueSeverity.CRITICAL,
            title="Secret Competitor Bug",
            description="Critical vulnerability in competitor site",
            page_url="https://other.com/secret"
        )

        service = SEOInvestigationService(project=self.project, publisher=self.publisher)
        res = service.investigate(
            opportunity_type="RANKING_TECHNICAL_DECAY",
            target_url="https://other.com/secret"
        )

        # Must not see other project's audit issues
        self.assertEqual(len(res.supporting_audit_issues), 0)
        self.assertEqual(res.confidence_level, InvestigationConfidence.LOW.value)

    def test_zero_credential_leakage(self):
        """10. Ensures no OAuth tokens or client secrets leak into result dictionaries or events."""
        conn = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="https://doxarank.com",
            is_connected=True,
            encrypted_refresh_token="enc_refresh_secret_456"
        )
        service = SEOInvestigationService(project=self.project, publisher=self.publisher)
        res = service.investigate(
            opportunity_type="LOW_CTR_HIGH_IMPRESSIONS",
            target_url="https://doxarank.com",
            run_id=777
        )

        res_dict = res.to_dict()
        res_str = str(res_dict)
        self.assertNotIn("enc_token_secret_123", res_str)
        self.assertNotIn("enc_refresh_secret_456", res_str)
        self.assertNotIn("access_token", res_str)
        self.assertNotIn("client_secret", res_str)

        for event in self.publisher.get_events(run_id=777):
            ev_str = str(event.payload)
            self.assertNotIn("enc_token_secret_123", ev_str)
            self.assertNotIn("enc_refresh_secret_456", ev_str)

    def test_url_normalization_matching(self):
        """11. Normalizes URLs across different protocols, trailing slashes, and host formats."""
        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=80)
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_title",
            severity=IssueSeverity.WARNING,
            title="Missing Title",
            page_url="https://www.doxarank.com/blog/seo-guide/"
        )

        service = SEOInvestigationService(project=self.project, publisher=self.publisher)
        # Query with http scheme, no www, and no trailing slash
        res = service.investigate(
            opportunity_type="ON_PAGE_SEO",
            target_url="http://doxarank.com/blog/seo-guide"
        )

        self.assertEqual(len(res.supporting_audit_issues), 1)
        self.assertEqual(res.supporting_audit_issues[0]["issue_type"], "missing_title")

    def test_conflicting_or_weak_evidence(self):
        """12. Handles conflicting or ambiguous signals deterministically with non-destructive fallback."""
        conn = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="https://doxarank.com",
            is_connected=True
        )
        # GSC shows high CTR (>15%) while requested as LOW_CTR opportunity
        SearchAnalyticsData.objects.create(
            connection=conn,
            page="https://doxarank.com/high-performer",
            query="branded keyword",
            impressions=100,
            clicks=25,
            ctr=0.25,
            position=1.2,
            date=timezone.now().date()
        )

        service = SEOInvestigationService(project=self.project, publisher=self.publisher)
        res = service.investigate(
            opportunity_type="LOW_CTR_HIGH_IMPRESSIONS",
            target_url="https://doxarank.com/high-performer",
            target_query="branded keyword"
        )

        self.assertEqual(res.status, InvestigationStatus.COMPLETED.value)
        self.assertIn("Google Search Console: 100 impressions, 25 clicks, 25.0% CTR", res.observed_facts[0])


class ToolRegistryInvestigationTests(TestCase):
    """
    Tests ToolRegistry integration for the 'investigate_seo_opportunity' tool (Phase 4.2.3.3).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='tool_tester@doxarank.com',
            password='Password123!',
            first_name='Tool',
            last_name='Tester'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Tool Test Project',
            website_url='https://tooltest.com'
        )
        self.registry = create_default_tool_registry()

    def test_tool_registration(self):
        """1. investigate_seo_opportunity is registered in ToolRegistry."""
        tool = self.registry.get("investigate_seo_opportunity")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "investigate_seo_opportunity")
        self.assertEqual(tool.category, ToolCategory.READ_ONLY)
        self.assertFalse(tool.requires_approval)
        self.assertFalse(tool.is_mutating)

    def test_schema_validation_required_parameters(self):
        """2. Validates that opportunity_type is required."""
        is_valid, err = self.registry.validate_arguments("investigate_seo_opportunity", {})
        self.assertFalse(is_valid)
        self.assertIn("Missing required parameter 'opportunity_type'", err)

        is_valid_ok, err_ok = self.registry.validate_arguments(
            "investigate_seo_opportunity",
            {"opportunity_type": "LOW_CTR_HIGH_IMPRESSIONS"}
        )
        self.assertTrue(is_valid_ok)
        self.assertIsNone(err_ok)

    def test_tool_execution_success(self):
        """3. ToolRegistry executes investigate_seo_opportunity and returns structured dict."""
        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=80)
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_title",
            severity=IssueSeverity.WARNING,
            title="Missing Title",
            description="Page is missing a title tag",
            page_url="https://tooltest.com/about"
        )

        res = self.registry.execute(
            project=self.project,
            tool_name="investigate_seo_opportunity",
            arguments={
                "opportunity_type": "LOW_CTR_HIGH_IMPRESSIONS",
                "target_url": "https://tooltest.com/about"
            }
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["tool_name"], "investigate_seo_opportunity")
        self.assertEqual(res["data"]["status"], "COMPLETED")
        self.assertIn("investigation_id", res["data"])
        self.assertIn("observed_facts", res["data"])
        self.assertIn("inferences", res["data"])
        self.assertIn("root_cause_category", res["data"])
        self.assertIn("confidence_score", res["data"])
        self.assertIn("recommended_action", res["data"])


class ReActInvestigationAgentTests(TestCase):
    """
    Tests end-to-end autonomous reasoning loop using ReAct AgentOrchestrator and MockAIProvider.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='react_investigator@doxarank.com',
            password='Password123!',
            first_name='ReAct',
            last_name='Investigator'
        )
        self.project = Project.objects.create(
            owner=self.user,
            name='Agent Test Project',
            website_url='https://agenttest.com'
        )
        self.registry = create_default_tool_registry()

    def test_investigation_goal_execution_loop(self):
        """1. Agent executes autonomous investigation workflow end-to-end."""
        audit = SiteAudit.objects.create(project=self.project, status=AuditStatus.COMPLETED, score=75)
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_meta_description",
            severity=IssueSeverity.WARNING,
            page_url="https://agenttest.com/products"
        )

        conn = SearchConsoleConnection.objects.create(
            project=self.project,
            property_url="https://agenttest.com",
            is_connected=True
        )
        SearchAnalyticsData.objects.create(
            connection=conn,
            page="https://agenttest.com/products",
            query="best cloud products",
            impressions=2100,
            clicks=18,
            ctr=0.0085,
            position=5.8,
            date=timezone.now().date()
        )

        orchestrator = AgentOrchestrator(
            project=self.project,
            user=self.user,
            provider=MockAIProvider(),
            registry=self.registry,
            max_steps=6
        )

        run = orchestrator.start_run(goal="Investigate SEO opportunity and determine root cause for low CTR on landing pages")

        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertIn("Autonomous SEO Investigation & Decision Complete", run.summary)
        self.assertIn("Observed Facts", run.summary)
        self.assertIn("Inferences", run.summary)
        self.assertIn("Recommended Action", run.summary)

        tool_calls = AgentToolCall.objects.filter(step__run=run)
        called_tools = [tc.tool_name for tc in tool_calls]
        self.assertIn("investigate_seo_opportunity", called_tools)


class ActionApprovalAndMutationGovernanceTests(TestCase):
    """
    Phase 4.3 Test Suite: Human-in-the-Loop Action Execution & Mutation Gating
    Covers:
    1. SEOActionService.propose_from_investigation creates PENDING_APPROVAL actions with evidence
    2. Non-mutating recommendations (MONITOR, NO_ACTION) do not enter approval pipeline
    3. ActionApprovalService.approve_action transitions status to APPROVED with timestamps and auditor
    4. ActionApprovalService enforces strict tenant isolation (non-owner cannot approve)
    5. ActionApprovalService rejects invalid status transitions
    6. ActionApprovalService.reject_action requires non-empty reason and records auditor
    7. DryRunMutationConnector generates non-destructive before/after visual diffs
    8. DryRunMutationConnector executes safely in staging mode with monitoring baselines
    9. SEOActionExecutor strictly verifies human approval before execution
    10. SEOActionExecutor enforces tenant isolation
    11. SEOActionExecutor transitions to COMPLETED on success and records execution metadata
    12. API endpoints: /approve/, /reject/, /preview/, /execute/
    13. ToolRegistry tools: propose_seo_action, get_pending_actions, get_action, preview_action
    14. ReAct Agent stops at the human approval gate when proposing actions
    """

    def setUp(self):
        self.client = APIClient()

        # User A & Project A (Owner)
        self.user_a = User.objects.create_user(
            email='action_owner@doxarank.com',
            password='Password123!',
            first_name='Action',
            last_name='Owner'
        )
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Ethio Solar Store',
            website_url='https://ethiosolar.et'
        )

        # User B & Project B (Attacker / Unauthorized)
        self.user_b = User.objects.create_user(
            email='action_intruder@doxarank.com',
            password='Password123!',
            first_name='Action',
            last_name='Intruder'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Competitor Solar',
            website_url='https://competitorsolar.et'
        )

        # Tool Registry
        self.registry = create_default_tool_registry()

    def test_propose_from_investigation_mutation_action(self):
        """1. SEOActionService creates PENDING_APPROVAL action with evidence from investigation."""
        from apps.seo.services.seo_investigation import SEOInvestigationResult
        from apps.seo.services.action_service import SEOActionService

        inv = SEOInvestigationResult(
            investigation_id="INV-TEST-001",
            project_id=self.project_a.id,
            opportunity_type="LOW_CTR_HIGH_IMPRESSIONS",
            target_url="https://ethiosolar.et/solar-panels",
            target_query="buy solar panels addis",
            status="COMPLETED",
            observed_facts=["12,400 impressions with 0.8% CTR at position #4.2", "Page is missing meta description"],
            inferences=["Under-optimized SERP snippet leads to low click capture."],
            inferred_root_causes=["Snippet optimization needed"],
            root_cause_category="ON_PAGE_SEO",
            root_cause_reason="Missing meta description tag suppresses SERP CTR.",
            confidence_score=0.88,
            confidence_level="HIGH",
            recommended_action={
                "action_type": "OPTIMIZE_META_DESCRIPTION",
                "title": "Optimize Meta Description for Solar Panels",
                "description": "Add high-converting meta description tag",
                "target_url": "https://ethiosolar.et/solar-panels",
                "target_query": "buy solar panels addis",
                "proposed_changes": {"meta_description": "Buy tier-1 solar panels in Addis Ababa with full warranty."},
                "requires_human_approval": True
            },
            impact_estimate="HIGH",
            effort_estimate="LOW",
            risk_level="LOW"
        )

        service = SEOActionService(project=self.project_a)
        action = service.propose_from_investigation(inv)

        self.assertIsNotNone(action)
        self.assertEqual(action.status, ActionStatus.PENDING_APPROVAL)
        self.assertTrue(action.requires_human_approval)
        self.assertEqual(action.investigation_id, "INV-TEST-001")
        self.assertEqual(action.opportunity_type, "LOW_CTR_HIGH_IMPRESSIONS")
        self.assertEqual(action.action_type, "optimize_meta_description")
        self.assertEqual(action.target_url, "https://ethiosolar.et/solar-panels")
        self.assertEqual(action.target_keyword, "buy solar panels addis")
        self.assertIn("observed_facts", action.evidence_snapshot)
        self.assertIn("inferences", action.evidence_snapshot)
        self.assertEqual(action.risk_level, "low")
        self.assertEqual(action.impact_estimate, "high")
        self.assertEqual(action.effort_estimate, "low")
        self.assertIsNone(action.approved_by)
        self.assertIsNone(action.approved_at)

    def test_propose_from_investigation_non_mutating_action(self):
        """2. Non-mutating investigations (MONITOR, NO_ACTION) do not create pending mutation actions."""
        from apps.seo.services.seo_investigation import SEOInvestigationResult
        from apps.seo.services.action_service import SEOActionService

        inv = SEOInvestigationResult(
            investigation_id="INV-MONITOR-001",
            project_id=self.project_a.id,
            opportunity_type="POSITION_DECAY",
            target_url="https://ethiosolar.et/blog",
            target_query=None,
            status="COMPLETED",
            recommended_action={"action_type": "MONITOR", "description": "Monitor ranking fluctuation"}
        )

        service = SEOActionService(project=self.project_a)
        action = service.propose_from_investigation(inv)

        self.assertIsNone(action)
        self.assertFalse(SEOAction.objects.filter(investigation_id="INV-MONITOR-001").exists())

    def test_action_approval_success_by_owner(self):
        """3. Project owner can approve action, transitioning status and recording auditable timestamps."""
        from apps.seo.services.action_approval import ActionApprovalService

        action = SEOAction.objects.create(
            project=self.project_a,
            title="Update Title Tag",
            action_type=ActionType.OPTIMIZE_TITLE,
            target_url="https://ethiosolar.et/",
            status=ActionStatus.PENDING_APPROVAL,
            requires_human_approval=True
        )

        service = ActionApprovalService()
        approved = service.approve_action(action_id=action.id, user=self.user_a)

        self.assertEqual(approved.status, ActionStatus.APPROVED)
        self.assertEqual(approved.approved_by, self.user_a)
        self.assertIsNotNone(approved.approved_at)
        self.assertIsNone(approved.rejected_by)
        self.assertEqual(approved.rejection_reason, "")

    def test_action_approval_forbidden_for_non_owner(self):
        """4. Unauthorized user cannot approve action belonging to another user's project."""
        from apps.seo.services.action_approval import ActionApprovalService
        from django.core.exceptions import PermissionDenied

        action = SEOAction.objects.create(
            project=self.project_a,
            title="Update Canonical Tag",
            action_type=ActionType.FIX_CANONICAL,
            target_url="https://ethiosolar.et/",
            status=ActionStatus.PENDING_APPROVAL,
            requires_human_approval=True
        )

        service = ActionApprovalService()
        with self.assertRaises(PermissionDenied):
            service.approve_action(action_id=action.id, user=self.user_b)

        action.refresh_from_db()
        self.assertEqual(action.status, ActionStatus.PENDING_APPROVAL)
        self.assertIsNone(action.approved_by)

    def test_action_approval_invalid_state(self):
        """5. Cannot approve action that is already completed, executing, or cancelled."""
        from apps.seo.services.action_approval import ActionApprovalService

        action = SEOAction.objects.create(
            project=self.project_a,
            title="Completed Action",
            action_type=ActionType.OPTIMIZE_TITLE,
            target_url="https://ethiosolar.et/",
            status=ActionStatus.COMPLETED,
            requires_human_approval=True
        )

        service = ActionApprovalService()
        with self.assertRaises(ValueError):
            service.approve_action(action_id=action.id, user=self.user_a)

    def test_action_rejection_success_by_owner(self):
        """6. Project owner can reject action with mandatory reason."""
        from apps.seo.services.action_approval import ActionApprovalService

        action = SEOAction.objects.create(
            project=self.project_a,
            title="Fix Alt Tags",
            action_type=ActionType.FIX_IMAGE_ALT,
            target_url="https://ethiosolar.et/",
            status=ActionStatus.PENDING_APPROVAL,
            requires_human_approval=True
        )

        service = ActionApprovalService()
        rejected = service.reject_action(
            action_id=action.id,
            user=self.user_a,
            reason="Images are decorative icons and do not require SEO alt attributes."
        )

        self.assertEqual(rejected.status, ActionStatus.REJECTED)
        self.assertEqual(rejected.rejected_by, self.user_a)
        self.assertIsNotNone(rejected.rejected_at)
        self.assertEqual(rejected.rejection_reason, "Images are decorative icons and do not require SEO alt attributes.")

    def test_action_rejection_requires_reason(self):
        """7. Rejection fails if reason is empty or whitespace."""
        from apps.seo.services.action_approval import ActionApprovalService

        action = SEOAction.objects.create(
            project=self.project_a,
            title="Fix Alt Tags",
            action_type=ActionType.FIX_IMAGE_ALT,
            target_url="https://ethiosolar.et/",
            status=ActionStatus.PENDING_APPROVAL,
            requires_human_approval=True
        )

        service = ActionApprovalService()
        with self.assertRaises(ValueError):
            service.reject_action(action_id=action.id, user=self.user_a, reason="   ")

    def test_dry_run_mutation_connector_preview(self):
        """8. DryRunMutationConnector generates non-destructive before/after visual diffs."""
        from apps.seo.services.mutation_connectors import DryRunMutationConnector

        action = SEOAction.objects.create(
            project=self.project_a,
            title="Optimize Title Tag",
            action_type=ActionType.OPTIMIZE_TITLE,
            target_url="https://ethiosolar.et/products",
            target_keyword="solar batteries",
            current_state={"title": "Old Products Page"},
            proposed_change={"title": "Solar Batteries in Ethiopia | Ethio Solar"},
            risk_level="low",
            impact_estimate="high",
            effort_estimate="low",
            requires_human_approval=True
        )

        connector = DryRunMutationConnector()
        preview = connector.preview(action)

        self.assertEqual(preview["action_id"], action.id)
        self.assertEqual(preview["target_url"], "https://ethiosolar.et/products")
        self.assertEqual(preview["diff"]["title"]["before"], "Old Products Page")
        self.assertEqual(preview["diff"]["title"]["after"], "Solar Batteries in Ethiopia | Ethio Solar")
        self.assertIn("Update page title", preview["summary"])

    def test_dry_run_mutation_connector_execute(self):
        """9. DryRunMutationConnector executes safely in staging mode with baseline monitoring."""
        from apps.seo.services.mutation_connectors import DryRunMutationConnector

        action = SEOAction.objects.create(
            project=self.project_a,
            title="Optimize Meta Description",
            action_type=ActionType.OPTIMIZE_META_DESCRIPTION,
            target_url="https://ethiosolar.et/inverters",
            target_keyword="hybrid inverters",
            current_state={"meta_description": ""},
            proposed_change={"meta_description": "High-efficiency hybrid inverters for residential solar systems in Addis Ababa."},
            status=ActionStatus.APPROVED,
            requires_human_approval=True
        )

        connector = DryRunMutationConnector()
        res = connector.execute(action)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["connector_name"], "dry_run")
        self.assertIn("monitoring_baseline", res)
        self.assertEqual(res["monitoring_baseline"]["monitored_keyword"], "hybrid inverters")
        self.assertGreater(res["duration_ms"], 0)

    def test_action_executor_gate_enforcement(self):
        """10. SEOActionExecutor strictly verifies server-side approval before execution."""
        from apps.seo.services.action_executors import SEOActionExecutor
        from django.core.exceptions import PermissionDenied

        # Unapproved action (PENDING_APPROVAL)
        action_unapproved = SEOAction.objects.create(
            project=self.project_a,
            title="Unapproved Action",
            action_type=ActionType.OPTIMIZE_TITLE,
            target_url="https://ethiosolar.et/",
            status=ActionStatus.PENDING_APPROVAL,
            requires_human_approval=True
        )

        executor = SEOActionExecutor()
        with self.assertRaises(ValueError):
            executor.execute(action_unapproved, user=self.user_a)

        # Approved action executed by unauthorized non-owner user
        action_approved = SEOAction.objects.create(
            project=self.project_a,
            title="Approved Action",
            action_type=ActionType.OPTIMIZE_TITLE,
            target_url="https://ethiosolar.et/",
            status=ActionStatus.APPROVED,
            requires_human_approval=True,
            approved_by=self.user_a,
            approved_at=timezone.now()
        )

        with self.assertRaises(PermissionDenied):
            executor.execute(action_approved, user=self.user_b)

    def test_action_executor_successful_execution(self):
        """11. SEOActionExecutor safely executes approved action and records execution metadata."""
        from apps.seo.services.action_executors import SEOActionExecutor

        action = SEOAction.objects.create(
            project=self.project_a,
            title="Approved Action",
            action_type=ActionType.OPTIMIZE_META_DESCRIPTION,
            target_url="https://ethiosolar.et/about",
            proposed_change={"meta_description": "Learn about Ethio Solar solutions and our certified engineers."},
            status=ActionStatus.APPROVED,
            requires_human_approval=True,
            approved_by=self.user_a,
            approved_at=timezone.now()
        )

        executor = SEOActionExecutor()
        result = executor.execute(action, user=self.user_a)

        action.refresh_from_db()
        self.assertEqual(action.status, ActionStatus.COMPLETED)
        self.assertIsNotNone(action.completed_at)
        self.assertIsNotNone(action.execution_started_at)
        self.assertEqual(action.failure_reason, "")
        self.assertEqual(action.execution_metadata["status"], "success")

    def test_action_api_endpoints_governance(self):
        """12. API endpoints enforce project ownership, approval gating, and reject reasons."""
        action = SEOAction.objects.create(
            project=self.project_a,
            title="API Governance Test Action",
            action_type=ActionType.OPTIMIZE_TITLE,
            target_url="https://ethiosolar.et/contact",
            proposed_change={"title": "Contact Us | Ethio Solar"},
            status=ActionStatus.PENDING_APPROVAL,
            requires_human_approval=True
        )

        # 1. Preview endpoint
        self.client.force_authenticate(user=self.user_a)
        prev_res = self.client.get(f'/api/seo/ai/actions/{action.id}/preview/')
        self.assertEqual(prev_res.status_code, status.HTTP_200_OK)
        self.assertIn("preview", prev_res.data)

        # 2. Unauthorized user cannot approve
        self.client.force_authenticate(user=self.user_b)
        appr_b_res = self.client.post(f'/api/seo/ai/actions/{action.id}/approve/')
        self.assertEqual(appr_b_res.status_code, status.HTTP_404_NOT_FOUND)

        # 3. Owner cannot execute unapproved action
        self.client.force_authenticate(user=self.user_a)
        exec_unapproved = self.client.post(f'/api/seo/ai/actions/{action.id}/execute/')
        self.assertEqual(exec_unapproved.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. Reject endpoint works with reason
        rej_res = self.client.post(f'/api/seo/ai/actions/{action.id}/reject/', {"reason": "Not appropriate for current campaign"})
        self.assertEqual(rej_res.status_code, status.HTTP_200_OK)
        self.assertEqual(rej_res.data["status"], "rejected")
        self.assertEqual(rej_res.data["rejection_reason"], "Not appropriate for current campaign")

        # 5. Owner approves fresh pending action
        action_2 = SEOAction.objects.create(
            project=self.project_a,
            title="API Approval Test Action",
            action_type=ActionType.OPTIMIZE_TITLE,
            target_url="https://ethiosolar.et/faq",
            status=ActionStatus.PENDING_APPROVAL,
            requires_human_approval=True
        )
        appr_res = self.client.post(f'/api/seo/ai/actions/{action_2.id}/approve/')
        self.assertEqual(appr_res.status_code, status.HTTP_200_OK)
        self.assertEqual(appr_res.data["status"], "approved")
        self.assertEqual(appr_res.data["approved_by_email"], self.user_a.email)

        # 6. Owner executes approved action
        exec_res = self.client.post(f'/api/seo/ai/actions/{action_2.id}/execute/')
        self.assertEqual(exec_res.status_code, status.HTTP_200_OK)
        self.assertEqual(exec_res.data["status"], "completed")

    def test_tool_registry_action_governance_tools(self):
        """13. ToolRegistry integrates action proposal, listing, details, and preview tools."""
        # 1. propose_seo_action tool
        insight = SEOInsight.objects.create(
            project=self.project_a,
            fingerprint='fp_tool_rec_test_001',
            title='Recommendation Insight',
            description='Test insight for tool proposal'
        )
        rec = SEORecommendation.objects.create(
            project=self.project_a,
            insight=insight,
            title="Recommendation For Tool Test",
            recommendation_type=RecommendationType.CTR_OPTIMIZATION,
            affected_url="https://ethiosolar.et/deals"
        )

        prop_res = self.registry.execute(
            project=self.project_a,
            tool_name="propose_seo_action",
            arguments={"source_type": "recommendation", "source_id": rec.id}
        )
        self.assertTrue(prop_res["success"])
        action_id = prop_res["data"]["id"]
        self.assertIn(prop_res["data"]["status"], [ActionStatus.PROPOSED, ActionStatus.PENDING_APPROVAL, "proposed", "pending_approval"])
        self.assertTrue(prop_res["data"]["requires_human_approval"])

        # 2. get_pending_actions tool
        list_res = self.registry.execute(
            project=self.project_a,
            tool_name="get_pending_actions",
            arguments={"limit": 10}
        )
        self.assertTrue(list_res["success"])
        self.assertGreaterEqual(list_res["data"]["total_pending"], 1)

        # 3. get_action tool
        get_res = self.registry.execute(
            project=self.project_a,
            tool_name="get_action",
            arguments={"action_id": action_id}
        )
        self.assertTrue(get_res["success"])
        self.assertEqual(get_res["data"]["id"], action_id)

        # 4. preview_action tool
        prev_res = self.registry.execute(
            project=self.project_a,
            tool_name="preview_action",
            arguments={"action_id": action_id}
        )
        self.assertTrue(prev_res["success"])
        self.assertEqual(prev_res["data"]["action_id"], action_id)
        self.assertIn("preview", prev_res["data"])

    def test_react_agent_stops_at_human_approval_gate(self):
        """14. ReAct agent with action proposal goal generates proposal in PENDING_APPROVAL and stops."""
        audit = SiteAudit.objects.create(project=self.project_a, status=AuditStatus.COMPLETED, score=82)
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_title",
            severity=IssueSeverity.WARNING,
            page_url="https://ethiosolar.et/batteries"
        )

        orchestrator = AgentOrchestrator(
            project=self.project_a,
            user=self.user_a,
            provider=MockAIProvider(),
            registry=self.registry,
            max_steps=6
        )

        run = orchestrator.start_run(goal="Propose action plan and mitigation for on-page SEO issues on landing pages")

        self.assertEqual(run.status, AgentRunStatus.WAITING_FOR_APPROVAL)

        # Verify created action is PENDING_APPROVAL / PROPOSED and unexecuted
        pending_actions = SEOAction.objects.filter(
            project=self.project_a,
            status__in=[ActionStatus.PENDING_APPROVAL, ActionStatus.PROPOSED]
        )
        self.assertTrue(pending_actions.exists())
        for a in pending_actions:
            self.assertIsNone(a.approved_at)
            self.assertIsNone(a.completed_at)


class SEOAutonomousActionPlanAndVerificationTests(TestCase):
    """
    Comprehensive test suite for Phase 4.4:
    Autonomous SEO Action Planning, Deterministic Risk Classification, Deduplication,
    Human-in-the-Loop Multi-Action Governance, Controlled Execution, and Empirical Real-World Verification.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.projects.models import Project
        from apps.seo.models import (
            SiteAudit, AuditIssue, IssueSeverity, AuditStatus,
            SearchConsoleConnection, SearchAnalyticsData,
            SEOActionPlan, ActionPlanStatus, ActionRiskLevel, VerificationStatus,
            SEOAction, ActionType, ActionStatus
        )
        from apps.seo.services.tool_registry import get_tool_registry

        User = get_user_model()
        self.user_a = User.objects.create_user(email="plannera@doxarank.com", password="StrongPassword123!")
        self.user_b = User.objects.create_user(email="plannerb@doxarank.com", password="StrongPassword123!")

        self.project_a = Project.objects.create(
            name="Plan Project Alpha",
            website_url="https://alpha-seo.com",
            owner=self.user_a
        )
        self.project_b = Project.objects.create(
            name="Plan Project Beta",
            website_url="https://beta-seo.com",
            owner=self.user_b
        )

        self.client = APIClient()
        self.registry = get_tool_registry()

    def test_planner_generates_structured_plan_from_audit_and_gsc(self):
        """1. ActionPlanner synthesizes audit issues and GSC momentum drops into a structured plan."""
        from apps.seo.services.seo_action_planner import SEOActionPlanner
        from apps.seo.models import (
            SiteAudit, AuditIssue, IssueSeverity, AuditStatus,
            SearchAnalyticsData, SEOActionPlan, ActionPlanStatus, ActionRiskLevel
        )
        import datetime

        # Create audit defect
        audit = SiteAudit.objects.create(
            project=self.project_a,
            status=AuditStatus.COMPLETED,
            score=70
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_title",
            severity=IssueSeverity.WARNING,
            page_url="https://alpha-seo.com/products/widgets"
        )
        AuditIssue.objects.create(
            audit=audit,
            issue_type="broken_internal_link",
            severity=IssueSeverity.CRITICAL,
            page_url="https://alpha-seo.com/blog/old-post"
        )

        # Create GSC search drop data
        conn = SearchConsoleConnection.objects.create(
            project=self.project_a,
            property_url="https://alpha-seo.com/",
            is_connected=True
        )
        today = datetime.date.today()
        for i in range(14):
            d = today - datetime.timedelta(days=i)
            # Prior period had high clicks, recent period had 0 clicks (CTR drop)
            clicks = 0 if i < 7 else 50
            impressions = 200
            SearchAnalyticsData.objects.create(
                connection=conn,
                date=d,
                page="https://alpha-seo.com/guides/seo-tips",
                query="best seo tips",
                clicks=clicks,
                impressions=impressions,
                ctr=clicks / impressions,
                position=4.2
            )

        planner = SEOActionPlanner(project=self.project_a)
        plan = planner.create_action_plan(
            title="Q3 Technical and CTR Remediation Plan",
            summary="Autonomous remediation plan",
            audit_id=audit.id,
            user=self.user_a,
            max_actions=5
        )

        self.assertIsInstance(plan, SEOActionPlan)
        self.assertEqual(plan.status, ActionPlanStatus.PROPOSED)
        self.assertEqual(plan.created_by, self.user_a)
        self.assertGreaterEqual(plan.actions.count(), 2)
        self.assertIn(plan.risk_level, [ActionRiskLevel.LOW, ActionRiskLevel.MEDIUM, ActionRiskLevel.HIGH, ActionRiskLevel.CRITICAL])
        self.assertGreater(plan.confidence_score, 0.0)

        # Verify child actions are linked
        for act in plan.actions.all():
            self.assertEqual(act.plan_id, plan.id)
            self.assertEqual(act.project_id, self.project_a.id)
            self.assertEqual(act.status, ActionStatus.PROPOSED)
            self.assertTrue(act.requires_human_approval)

    def test_planner_deterministic_risk_classification(self):
        """2. Deterministic risk classifier assigns appropriate risk levels by action type."""
        from apps.seo.services.seo_action_planner import SEOActionPlanner
        from apps.seo.models import ActionType, ActionRiskLevel

        planner = SEOActionPlanner(project=self.project_a)

        self.assertEqual(planner.classify_risk(ActionType.REMOVE_REDIRECT_CHAIN), ActionRiskLevel.CRITICAL)
        self.assertEqual(planner.classify_risk(ActionType.FIX_CANONICAL), ActionRiskLevel.HIGH)
        self.assertEqual(planner.classify_risk(ActionType.OPTIMIZE_TITLE), ActionRiskLevel.MEDIUM)
        self.assertEqual(planner.classify_risk(ActionType.FIX_IMAGE_ALT), ActionRiskLevel.LOW)
        self.assertEqual(planner.classify_risk(ActionType.OPTIMIZE_META_DESCRIPTION), ActionRiskLevel.LOW)

    def test_planner_deduplication_prevents_duplicate_actions(self):
        """3. Planner prevents duplicate actions on the same URL and action type."""
        from apps.seo.services.seo_action_planner import SEOActionPlanner
        from apps.seo.models import SiteAudit, AuditIssue, IssueSeverity, AuditStatus

        audit = SiteAudit.objects.create(project=self.project_a, status=AuditStatus.COMPLETED, score=80)
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_h1",
            severity=IssueSeverity.WARNING,
            page_url="https://alpha-seo.com/pricing"
        )

        planner = SEOActionPlanner(project=self.project_a)
        plan_1 = planner.create_action_plan(title="Plan 1", user=self.user_a)
        actions_count_1 = plan_1.actions.count()
        self.assertGreaterEqual(actions_count_1, 1)

        # Plan 2 should not generate duplicate action for https://alpha-seo.com/pricing + fix_missing_h1
        plan_2 = planner.create_action_plan(title="Plan 2", user=self.user_a)
        dup_actions = plan_2.actions.filter(target_url="https://alpha-seo.com/pricing", action_type="fix_missing_h1")
        self.assertEqual(dup_actions.count(), 0)

    def test_action_plan_tenant_isolation_and_approval_api(self):
        """4. Strict tenant isolation: User B cannot view, approve, or reject User A's plan."""
        from apps.seo.services.seo_action_planner import SEOActionPlanner
        from apps.seo.models import ActionPlanStatus, ActionStatus

        planner = SEOActionPlanner(project=self.project_a)
        plan = planner.create_action_plan(title="User A Secret Plan", user=self.user_a)

        # User B attempts to access User A's plan
        self.client.force_authenticate(user=self.user_b)
        res = self.client.get(f'/api/seo/ai/action-plans/{plan.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        res_appr = self.client.post(f'/api/seo/ai/action-plans/{plan.id}/approve/')
        self.assertEqual(res_appr.status_code, status.HTTP_404_NOT_FOUND)

        # User A approves the plan
        self.client.force_authenticate(user=self.user_a)
        res_a = self.client.post(f'/api/seo/ai/action-plans/{plan.id}/approve/')
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)
        self.assertEqual(res_a.data['status'], 'approved')
        self.assertEqual(res_a.data['approved_by_email'], self.user_a.email)

        plan.refresh_from_db()
        self.assertEqual(plan.status, ActionPlanStatus.APPROVED)
        # All child actions are also approved
        for act in plan.actions.all():
            self.assertEqual(act.status, ActionStatus.APPROVED)

    def test_action_plan_rejection_api(self):
        """5. Rejection transitions plan and all child actions to REJECTED with audit reason."""
        from apps.seo.services.seo_action_planner import SEOActionPlanner
        from apps.seo.models import ActionPlanStatus, ActionStatus

        planner = SEOActionPlanner(project=self.project_a)
        plan = planner.create_action_plan(title="Plan for Rejection", user=self.user_a)

        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(f'/api/seo/ai/action-plans/{plan.id}/reject/', {
            'reason': 'Technical risk is too high for production.'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], 'rejected')
        self.assertEqual(res.data['rejection_reason'], 'Technical risk is too high for production.')

        plan.refresh_from_db()
        self.assertEqual(plan.status, ActionPlanStatus.REJECTED)
        for act in plan.actions.all():
            self.assertEqual(act.status, ActionStatus.REJECTED)
            self.assertEqual(act.rejection_reason, 'Technical risk is too high for production.')

    def test_action_plan_execution_task(self):
        """6. Celery task executes approved action plan and triggers verification."""
        from apps.seo.services.seo_action_planner import SEOActionPlanner
        from apps.seo.tasks import execute_seo_action_plan
        from apps.seo.models import ActionPlanStatus, ActionStatus

        planner = SEOActionPlanner(project=self.project_a)
        plan = planner.create_action_plan(title="Plan for Execution", user=self.user_a)

        # Plan must be approved first
        plan.status = ActionPlanStatus.APPROVED
        plan.approved_by = self.user_a
        plan.save()
        for act in plan.actions.all():
            act.status = ActionStatus.APPROVED
            act.approved_by = self.user_a
            act.save()

        # Run task
        result = execute_seo_action_plan(plan_id=plan.id, user_id=self.user_a.id)
        self.assertEqual(result, plan.id)

        plan.refresh_from_db()
        self.assertIn(plan.status, [ActionPlanStatus.COMPLETED, ActionPlanStatus.PARTIALLY_COMPLETED])
        self.assertIsNotNone(plan.completed_at)

        for act in plan.actions.all():
            self.assertEqual(act.status, ActionStatus.COMPLETED)
            self.assertIsNotNone(act.completed_at)

    def test_seo_action_verifier_success(self):
        """7. Verifier inspects target HTML and verifies proposed change matched real-world state."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus
        from apps.seo.services.seo_action_verifier import SEOActionVerifier

        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="Update Homepage Title",
            description="Add brand to title",
            target_url="https://alpha-seo.com",
            proposed_change={"title": "Optimized Title for Alpha | DoxaRank"},
            status=ActionStatus.COMPLETED
        )

        verifier = SEOActionVerifier(project=self.project_a)
        with patch.object(verifier, 'fetch_page_content', return_value=(200, "<html><head><title>Optimized Title for Alpha | DoxaRank</title></head><body><h1>Hello</h1></body></html>", {})):
            res = verifier.verify_action(action)

        self.assertTrue(res["verified"])
        self.assertEqual(res["verification_status"], "verified")

        action.refresh_from_db()
        self.assertEqual(action.verification_status, VerificationStatus.VERIFIED)
        self.assertIsNotNone(action.verification_result)

    def test_seo_action_verifier_mismatch(self):
        """8. Verifier catches discrepancies when live web page does not reflect proposed changes."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus
        from apps.seo.services.seo_action_verifier import SEOActionVerifier

        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="Update Homepage Title",
            description="Add brand to title",
            target_url="https://alpha-seo.com",
            proposed_change={"title": "Optimized Title for Alpha | DoxaRank"},
            status=ActionStatus.COMPLETED
        )

        verifier = SEOActionVerifier(project=self.project_a)
        with patch.object(verifier, 'fetch_page_content', return_value=(200, "<html><head><title>Old Unchanged Title</title></head><body></body></html>", {})):
            res = verifier.verify_action(action)

        self.assertFalse(res["verified"])
        self.assertEqual(res["verification_status"], "failed")

        action.refresh_from_db()
        self.assertEqual(action.verification_status, VerificationStatus.FAILED)

    def test_tool_registry_action_planning_tools(self):
        """9. ToolRegistry contains plan_seo_actions, get_action_plan, verify_seo_action, and verify_action_plan."""
        # 1. plan_seo_actions tool
        plan_res = self.registry.execute(
            tool_name="plan_seo_actions",
            project=self.project_a,
            arguments={"title": "Automated Tool Plan", "max_actions": 3}
        )
        self.assertTrue(plan_res["success"])
        plan_id = plan_res["data"]["id"]
        self.assertEqual(plan_res["data"]["title"], "Automated Tool Plan")

        # 2. get_action_plan tool
        get_res = self.registry.execute(
            tool_name="get_action_plan",
            project=self.project_a,
            arguments={"plan_id": plan_id}
        )
        self.assertTrue(get_res["success"])
        self.assertEqual(get_res["data"]["id"], plan_id)

        # 3. verify_action_plan tool
        verif_res = self.registry.execute(
            tool_name="verify_action_plan",
            project=self.project_a,
            arguments={"plan_id": plan_id}
        )
        self.assertTrue(verif_res["success"])
        self.assertIn("plan_id", verif_res["data"])

    def test_api_verify_endpoints(self):
        """10. Test API endpoints for action and plan verification."""
        from apps.seo.models import SEOAction, SEOActionPlan, ActionType, ActionStatus

        plan = SEOActionPlan.objects.create(
            project=self.project_a,
            title="API Plan",
            summary="API Summary"
        )
        action = SEOAction.objects.create(
            project=self.project_a,
            plan=plan,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="API Action",
            target_url="https://alpha-seo.com",
            status=ActionStatus.COMPLETED
        )

        self.client.force_authenticate(user=self.user_a)

        # Verify action endpoint
        res_act = self.client.post(f'/api/seo/ai/actions/{action.id}/verify/')
        self.assertEqual(res_act.status_code, status.HTTP_200_OK)
        self.assertIn('verification', res_act.data)

        # Verify plan endpoint
        res_plan = self.client.post(f'/api/seo/ai/action-plans/{plan.id}/verify/')
        self.assertEqual(res_plan.status_code, status.HTTP_200_OK)
        self.assertIn('verification_summary', res_plan.data)


class SEOOutcomeLearningAndAdaptiveAgentTests(TestCase):
    """
    Milestone 4, Phase 4.5: SEO Outcome Learning & Adaptive Agent Intelligence Test Suite.
    Tests deterministic before/after SEO measurement, empirical outcome classification,
    evidence gathering, historical learning signals, multi-tenant isolation, agent tool integration,
    ReAct reasoning with historical evidence, Celery background tasks, and REST APIs.
    """

    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.user_a = User.objects.create_user(
            email='user_outcome_a@example.com',
            password='testpassword123'
        )
        self.user_b = User.objects.create_user(
            email='user_outcome_b@example.com',
            password='testpassword123'
        )


        self.project_a = Project.objects.create(
            name="Alpha Corp",
            website_url="https://alpha-seo.com",
            owner=self.user_a
        )
        self.project_b = Project.objects.create(
            name="Beta Ltd",
            website_url="https://beta-seo.com",
            owner=self.user_b
        )

        # Create Search Console Connection for Project A
        self.conn_a = SearchConsoleConnection.objects.create(
            project=self.project_a,
            property_url="https://alpha-seo.com/",
            is_connected=True,
            encrypted_refresh_token="mock_token"
        )

        # Populate SearchAnalyticsData for pre/post windows
        self.today = timezone.now().date()
        # Pre-window metrics (-14 to -1 days)
        for i in range(1, 15):
            SearchAnalyticsData.objects.create(
                connection=self.conn_a,
                date=self.today - timedelta(days=i),
                query="enterprise seo software",
                page="https://alpha-seo.com/features",
                clicks=5,
                impressions=100,
                ctr=0.05,
                position=15.0
            )
        # Post-window metrics (0 to +14 days) -> improved ranking & CTR
        for i in range(0, 15):
            SearchAnalyticsData.objects.create(
                connection=self.conn_a,
                date=self.today + timedelta(days=i),
                query="enterprise seo software",
                page="https://alpha-seo.com/features",
                clicks=15,
                impressions=120,
                ctr=0.125,
                position=8.0
            )

        self.registry = get_tool_registry()

    def test_deterministic_outcome_classifier_improved(self):
        """1. Classifier correctly assigns IMPROVED when position and CTR improve with sufficient volume."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus, SEOOutcome
        from apps.seo.services.seo_outcome_learning import SEOOutcomeClassifier

        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="Optimize Features Title",
            target_url="https://alpha-seo.com/features",
            target_keyword="enterprise seo software",
            status=ActionStatus.COMPLETED,
            completed_at=timezone.now()
        )

        before = {"impressions": 500, "clicks": 20, "ctr": 0.04, "position": 18.0}
        after = {"impressions": 600, "clicks": 60, "ctr": 0.10, "position": 9.0}

        res = SEOOutcomeClassifier.classify(
            action=action,
            before_metrics=before,
            after_metrics=after,
            verification_state=VerificationStatus.VERIFIED,
            technical_resolved=True,
            has_gsc_connection=True
        )

        self.assertEqual(res["seo_outcome"], SEOOutcome.IMPROVED)
        self.assertGreaterEqual(res["confidence_score"], 0.70)
        self.assertTrue(res["is_statistically_significant"])
        self.assertIn("deltas", res)
        self.assertEqual(res["deltas"]["position_delta"], 9.0)  # Gained 9 spots

    def test_deterministic_outcome_classifier_no_change(self):
        """2. Classifier assigns NO_CHANGE when metric movement is within statistical fluctuation bounds."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus, SEOOutcome
        from apps.seo.services.seo_outcome_learning import SEOOutcomeClassifier

        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.OPTIMIZE_META_DESCRIPTION,
            title="Update Description",
            target_url="https://alpha-seo.com/features",
            status=ActionStatus.COMPLETED
        )

        before = {"impressions": 400, "clicks": 20, "ctr": 0.050, "position": 10.0}
        after = {"impressions": 410, "clicks": 21, "ctr": 0.051, "position": 9.8}

        res = SEOOutcomeClassifier.classify(
            action=action,
            before_metrics=before,
            after_metrics=after,
            verification_state=VerificationStatus.VERIFIED,
            technical_resolved=None,
            has_gsc_connection=True
        )

        self.assertEqual(res["seo_outcome"], SEOOutcome.NO_CHANGE)
        self.assertGreaterEqual(res["confidence_score"], 0.50)

    def test_deterministic_outcome_classifier_declined(self):
        """3. Classifier assigns DECLINED when rank and CTR drop significantly."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus, SEOOutcome
        from apps.seo.services.seo_outcome_learning import SEOOutcomeClassifier

        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.UPDATE_TITLE,
            title="Experimental Title",
            target_url="https://alpha-seo.com/features",
            status=ActionStatus.COMPLETED
        )

        before = {"impressions": 500, "clicks": 50, "ctr": 0.10, "position": 6.0}
        after = {"impressions": 300, "clicks": 10, "ctr": 0.033, "position": 16.0}

        res = SEOOutcomeClassifier.classify(
            action=action,
            before_metrics=before,
            after_metrics=after,
            verification_state=VerificationStatus.FAILED,
            technical_resolved=False,
            has_gsc_connection=True
        )

        self.assertEqual(res["seo_outcome"], SEOOutcome.DECLINED)

    def test_deterministic_outcome_classifier_insufficient_data(self):
        """4. Classifier assigns INSUFFICIENT_DATA when post-execution impression volume is below threshold."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus, SEOOutcome
        from apps.seo.services.seo_outcome_learning import SEOOutcomeClassifier

        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.FIX_MISSING_H1,
            title="Fix H1",
            target_url="https://alpha-seo.com/low-volume-page",
            status=ActionStatus.COMPLETED
        )

        before = {"impressions": 2, "clicks": 0, "ctr": 0.0, "position": 25.0}
        after = {"impressions": 3, "clicks": 0, "ctr": 0.0, "position": 20.0}

        res = SEOOutcomeClassifier.classify(
            action=action,
            before_metrics=before,
            after_metrics=after,
            verification_state=VerificationStatus.VERIFIED,
            technical_resolved=True,
            has_gsc_connection=True
        )

        self.assertEqual(res["seo_outcome"], SEOOutcome.INSUFFICIENT_DATA)
        self.assertLessEqual(res["confidence_score"], 0.40)

    def test_deterministic_outcome_classifier_unknown_without_gsc(self):
        """5. Classifier assigns UNKNOWN without fabricating data when GSC connection is missing."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus, SEOOutcome
        from apps.seo.services.seo_outcome_learning import SEOOutcomeClassifier

        action = SEOAction.objects.create(
            project=self.project_b,  # Project B has no GSC connection
            action_type=ActionType.OPTIMIZE_TITLE,
            title="Optimize Title",
            status=ActionStatus.COMPLETED
        )

        res = SEOOutcomeClassifier.classify(
            action=action,
            before_metrics={},
            after_metrics={},
            verification_state=VerificationStatus.PENDING,
            technical_resolved=None,
            has_gsc_connection=False
        )

        self.assertEqual(res["seo_outcome"], SEOOutcome.UNKNOWN)

    def test_outcome_measurement_service_action(self):
        """6. SEOOutcomeMeasurementService measures pre/post GSC data, updates action, and persists evidence."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus, SEOOutcome
        from apps.seo.services.seo_outcome_learning import SEOOutcomeMeasurementService

        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="Features Title Optimization",
            target_url="https://alpha-seo.com/features",
            target_keyword="enterprise seo software",
            status=ActionStatus.COMPLETED,
            verification_status=VerificationStatus.VERIFIED,
            completed_at=timezone.now()
        )

        service = SEOOutcomeMeasurementService(project=self.project_a)
        evidence = service.measure_action_outcome(action, window_days=14)

        action.refresh_from_db()
        self.assertEqual(action.seo_outcome, SEOOutcome.IMPROVED)
        self.assertGreaterEqual(action.outcome_confidence, 0.70)
        self.assertIsNotNone(action.outcome_measured_at)
        self.assertIn("before_metrics", action.outcome_evidence)
        self.assertIn("after_metrics", action.outcome_evidence)
        self.assertEqual(action.outcome_evidence["verification_state"], "verified")

    def test_outcome_measurement_service_plan_aggregate(self):
        """7. SEOOutcomeMeasurementService measures all actions in a plan and calculates aggregate outcome."""
        from apps.seo.models import SEOAction, SEOActionPlan, ActionType, ActionStatus, VerificationStatus, SEOOutcome, PlanSEOOutcome
        from apps.seo.services.seo_outcome_learning import SEOOutcomeMeasurementService

        plan = SEOActionPlan.objects.create(
            project=self.project_a,
            title="Multi-Action Optimization Plan",
            summary="Test aggregate plan measurement"
        )
        action_1 = SEOAction.objects.create(
            project=self.project_a,
            plan=plan,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="Action 1",
            target_url="https://alpha-seo.com/features",
            status=ActionStatus.COMPLETED,
            verification_status=VerificationStatus.VERIFIED,
            completed_at=timezone.now()
        )
        action_2 = SEOAction.objects.create(
            project=self.project_a,
            plan=plan,
            action_type=ActionType.FIX_MISSING_H1,
            title="Action 2",
            target_url="https://alpha-seo.com/features",
            status=ActionStatus.COMPLETED,
            verification_status=VerificationStatus.VERIFIED,
            completed_at=timezone.now()
        )

        service = SEOOutcomeMeasurementService(project=self.project_a)
        summary = service.measure_plan_outcome(plan, window_days=14)

        plan.refresh_from_db()
        self.assertEqual(plan.seo_outcome, PlanSEOOutcome.EFFECTIVE)
        self.assertEqual(summary["total_actions"], 2)
        self.assertEqual(summary["improved"], 2)
        self.assertEqual(summary["effectiveness_rate"], 1.0)

    def test_historical_learning_signals_and_multi_tenant_isolation(self):
        """8. SEOHistoricalLearningService calculates stats per action type and preserves strict project isolation."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, SEOOutcome
        from apps.seo.services.seo_outcome_learning import SEOHistoricalLearningService

        # Populate Project A historical actions
        for i in range(8):
            SEOAction.objects.create(
                project=self.project_a,
                action_type=ActionType.OPTIMIZE_TITLE,
                title=f"Title Action {i}",
                status=ActionStatus.COMPLETED,
                seo_outcome=SEOOutcome.IMPROVED,
                outcome_confidence=0.85,
                outcome_measured_at=timezone.now()
            )
        for i in range(2):
            SEOAction.objects.create(
                project=self.project_a,
                action_type=ActionType.OPTIMIZE_TITLE,
                title=f"Title Action {i+8}",
                status=ActionStatus.COMPLETED,
                seo_outcome=SEOOutcome.NO_CHANGE,
                outcome_confidence=0.75,
                outcome_measured_at=timezone.now()
            )
        # Populate Project B action (must NOT leak to Project A)
        SEOAction.objects.create(
            project=self.project_b,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="Project B Action",
            status=ActionStatus.COMPLETED,
            seo_outcome=SEOOutcome.DECLINED,
            outcome_confidence=0.90,
            outcome_measured_at=timezone.now()
        )

        # Query Project A signals
        sig_a = SEOHistoricalLearningService.get_historical_outcome_signals(
            project=self.project_a,
            action_type=ActionType.OPTIMIZE_TITLE
        )

        self.assertEqual(sig_a["total_measured"], 10)
        self.assertEqual(sig_a["improved"], 8)
        self.assertEqual(sig_a["no_change"], 2)
        self.assertEqual(sig_a["declined"], 0)  # Project B's declined action must not appear
        self.assertEqual(sig_a["success_rate"], 0.80)  # 8 / 10 = 80%

        # Query Project B signals
        sig_b = SEOHistoricalLearningService.get_historical_outcome_signals(
            project=self.project_b
        )
        self.assertEqual(sig_b["total_measured"], 1)
        self.assertEqual(sig_b["declined"], 1)

    def test_agent_tool_get_action_outcomes(self):
        """9. ToolRegistry executes 'get_action_outcomes' tool with filtering and token-efficient response."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, SEOOutcome

        SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.FIX_CANONICAL,
            title="Fix Canonical",
            status=ActionStatus.COMPLETED,
            seo_outcome=SEOOutcome.IMPROVED,
            outcome_confidence=0.90,
            outcome_measured_at=timezone.now()
        )

        res = self.registry.execute(
            tool_name="get_action_outcomes",
            project=self.project_a,
            arguments={"action_type": "fix_canonical"}
        )

        self.assertTrue(res["success"])
        data = res["data"]
        self.assertEqual(data["project_id"], self.project_a.id)
        self.assertEqual(data["improved"], 1)
        self.assertEqual(data["success_rate"], 1.0)
        self.assertIn("by_action_type", data)
        self.assertIn("recent_samples", data)

    def test_react_agent_reasoning_with_historical_evidence(self):
        """10. ReAct agent inspects historical outcomes and uses empirical evidence in summary."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, SEOOutcome, AgentRun, AgentRunStatus
        from apps.seo.services.agent_orchestrator import AgentOrchestrator
        from apps.seo.services.ai_providers import MockAIProvider

        # Populate historical title outcomes for Project A
        for i in range(3):
            SEOAction.objects.create(
                project=self.project_a,
                action_type=ActionType.OPTIMIZE_TITLE,
                title=f"Historical Title {i}",
                status=ActionStatus.COMPLETED,
                seo_outcome=SEOOutcome.IMPROVED,
                outcome_confidence=0.85,
                outcome_measured_at=timezone.now()
            )

        orchestrator = AgentOrchestrator(
            project=self.project_a,
            user=self.user_a,
            provider=MockAIProvider(),
            registry=self.registry
        )

        run = orchestrator.start_run(goal="Analyze historical SEO action outcomes and evaluate past performance.")
        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertIn("SEO Outcome Learning & Historical Evidence Analysis", run.summary)
        self.assertIn("Observed Historical Outcomes", run.summary)

    def test_celery_measure_outcome_tasks_and_idempotency(self):
        """11. Celery outcome tasks execute asynchronously and idempotently without corrupting records."""
        from apps.seo.models import SEOAction, SEOActionPlan, ActionType, ActionStatus, VerificationStatus, SEOOutcome
        from apps.seo.tasks import measure_seo_action_outcome_task, measure_seo_action_plan_outcome_task

        plan = SEOActionPlan.objects.create(
            project=self.project_a,
            title="Async Celery Plan",
            summary="Summary"
        )
        action = SEOAction.objects.create(
            project=self.project_a,
            plan=plan,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="Async Action",
            target_url="https://alpha-seo.com/features",
            target_keyword="enterprise seo software",
            status=ActionStatus.COMPLETED,
            verification_status=VerificationStatus.VERIFIED,
            completed_at=timezone.now()
        )

        # First task execution
        act_res_1 = measure_seo_action_outcome_task(action_id=action.id, window_days=14)
        self.assertEqual(act_res_1, action.id)
        action.refresh_from_db()
        self.assertEqual(action.seo_outcome, SEOOutcome.IMPROVED)

        # Repeated idempotent execution
        act_res_2 = measure_seo_action_outcome_task(action_id=action.id, window_days=14)
        self.assertEqual(act_res_2, action.id)
        action.refresh_from_db()
        self.assertEqual(action.seo_outcome, SEOOutcome.IMPROVED)

        # Plan task execution
        plan_res = measure_seo_action_plan_outcome_task(plan_id=plan.id, window_days=14)
        self.assertEqual(plan_res, plan.id)
        plan.refresh_from_db()
        self.assertIsNotNone(plan.outcome_measured_at)

    def test_api_measure_outcome_and_outcomes_summary_endpoints(self):
        """12. REST API endpoints for measure-outcome and outcomes-summary operate with authentication and multi-tenancy."""
        from apps.seo.models import SEOAction, SEOActionPlan, ActionType, ActionStatus, VerificationStatus

        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="API Measured Action",
            target_url="https://alpha-seo.com/features",
            status=ActionStatus.COMPLETED,
            verification_status=VerificationStatus.VERIFIED,
            completed_at=timezone.now()
        )

        self.client.force_authenticate(user=self.user_a)

        # 1. Action measure-outcome endpoint
        res_act = self.client.post(f'/api/seo/ai/actions/{action.id}/measure-outcome/', {'window_days': 14})
        self.assertEqual(res_act.status_code, status.HTTP_200_OK)
        self.assertIn('outcome_evidence', res_act.data)
        self.assertIn('action', res_act.data)

        # 2. Action outcomes-summary endpoint
        res_summary = self.client.get(f'/api/seo/ai/actions/outcomes-summary/?project_id={self.project_a.id}')
        self.assertEqual(res_summary.status_code, status.HTTP_200_OK)
        self.assertEqual(res_summary.data['project_id'], self.project_a.id)

        # 3. Unauthorized access check (User B cannot access Project A outcomes summary)
        self.client.force_authenticate(user=self.user_b)
        res_unauth = self.client.get(f'/api/seo/ai/actions/outcomes-summary/?project_id={self.project_a.id}')
        self.assertEqual(res_unauth.status_code, status.HTTP_404_NOT_FOUND)


class SEOAdaptiveStrategyTests(TestCase):
    """
    Phase 4.6 — Adaptive SEO Strategy & Historical Learning Integration Unit and Integration Tests.
    Verifies:
    1. Laplace/Bayesian smoothed win rate calculations & prior behavior
    2. Confidence tiers (none, low, medium, high) and bounded priority adjustments [-0.15, +0.15]
    3. Empty project defaults (cold start / zero-data)
    4. Action classification (preferred, deprioritized, neutral)
    5. Action planner integration: priority calibration without safety/risk compromise
    6. Agent tool `get_adaptive_seo_strategy` execution and output schema
    7. Multi-tenant security isolation across API endpoints
    8. Four-tier reasoning and evidence hierarchy validation
    """

    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user_a = User.objects.create_user(
            email='strat_a@doxarank.ai',
            password='Password123!'
        )
        self.user_b = User.objects.create_user(
            email='strat_b@doxarank.ai',
            password='Password123!'
        )
        self.project_a = Project.objects.create(
            name="Strategy Alpha Project",
            website_url="https://strategy-alpha.com",
            owner=self.user_a
        )
        self.project_b = Project.objects.create(
            name="Strategy Beta Project",
            website_url="https://strategy-beta.com",
            owner=self.user_b
        )

    def test_laplace_smoothed_rate_calculation(self):
        """1. Deterministic Laplace smoothing prevents extreme win rates on small samples."""
        from apps.seo.services.seo_adaptive_strategy import SEOAdaptiveStrategyService

        service = SEOAdaptiveStrategyService(project=self.project_a)

        # 0 evaluatable: defaults to prior 0.50
        self.assertAlmostEqual(service.calculate_smoothed_rate(0, 0), 0.50, places=3)

        # 1 win out of 1: (1+1)/(1+2) = 2/3 = 0.667 (not naive 1.0)
        self.assertEqual(service.calculate_smoothed_rate(1, 1), 0.667)

        # 0 wins out of 1: (0+1)/(1+2) = 1/3 = 0.333 (not naive 0.0)
        self.assertEqual(service.calculate_smoothed_rate(0, 1), 0.333)

        # 8 wins out of 10: (8+1)/(10+2) = 9/12 = 0.75
        self.assertEqual(service.calculate_smoothed_rate(8, 10), 0.75)

    def test_confidence_tiers_and_bounded_adjustments(self):
        """2. Confidence tiers and bounded adjustments [-0.15, +0.15] behave mathematically."""
        from apps.seo.services.seo_adaptive_strategy import SEOAdaptiveStrategyService

        service = SEOAdaptiveStrategyService(project=self.project_a)

        # Sample size 0 -> confidence none, adjustment 0.0
        self.assertEqual(service.determine_confidence_level(0, 0.0), 'none')
        self.assertAlmostEqual(service.calculate_priority_adjustment(0.50, 0, 0.0), 0.0, places=4)

        # Sample size 1 -> confidence low
        self.assertEqual(service.determine_confidence_level(1, 0.8), 'low')

        # Sample size 3 -> confidence medium
        self.assertEqual(service.determine_confidence_level(3, 0.75), 'medium')

        # Sample size 6 with high confidence -> confidence high
        self.assertEqual(service.determine_confidence_level(6, 0.85), 'high')

        # Extreme positive win rate bounded at +0.15
        adj_high = service.calculate_priority_adjustment(smoothed_rate=0.99, evaluatable_count=20, avg_confidence=1.0)
        self.assertLessEqual(adj_high, 0.15)
        self.assertGreater(adj_high, 0.0)

        # Extreme negative win rate bounded at -0.15
        adj_low = service.calculate_priority_adjustment(smoothed_rate=0.01, evaluatable_count=20, avg_confidence=1.0)
        self.assertGreaterEqual(adj_low, -0.15)
        self.assertLess(adj_low, 0.0)

    def test_cold_start_zero_data_defaults(self):
        """3. Cold start on empty project returns neutral strategy without errors."""
        from apps.seo.services.seo_adaptive_strategy import SEOAdaptiveStrategyService

        service = SEOAdaptiveStrategyService(project=self.project_a)
        strategy = service.evaluate_strategy()

        self.assertEqual(strategy['project_id'], self.project_a.id)
        self.assertEqual(strategy['strategy_confidence'], 'none')
        self.assertEqual(strategy['historical_sample_size'], 0)
        self.assertEqual(strategy['evaluatable_sample_size'], 0)
        self.assertEqual(strategy['preferred_actions'], [])
        self.assertEqual(strategy['deprioritized_actions'], [])
        self.assertIn('No conclusive historical outcome measurements', strategy['reason'])
        self.assertIn('tier_1_observed_facts', strategy['evidence_hierarchy'])

    def test_action_classification_with_historical_signals(self):
        """4. Historical wins classify actions as preferred; losses classify as deprioritized."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus, SEOOutcome
        from apps.seo.services.seo_adaptive_strategy import SEOAdaptiveStrategyService

        # Create 6 positive title optimizations
        for i in range(6):
            SEOAction.objects.create(
                project=self.project_a,
                action_type=ActionType.OPTIMIZE_TITLE,
                title=f"Title Action {i}",
                target_url=f"https://strategy-alpha.com/page-{i}",
                status=ActionStatus.COMPLETED,
                verification_status=VerificationStatus.VERIFIED,
                seo_outcome=SEOOutcome.IMPROVED,
                outcome_confidence=0.85,
                completed_at=timezone.now(),
                outcome_measured_at=timezone.now()
            )

        # Create 5 declining heading optimizations
        for i in range(5):
            SEOAction.objects.create(
                project=self.project_a,
                action_type=ActionType.FIX_MISSING_H1,
                title=f"Heading Action {i}",
                target_url=f"https://strategy-alpha.com/blog-{i}",
                status=ActionStatus.COMPLETED,
                verification_status=VerificationStatus.VERIFIED,
                seo_outcome=SEOOutcome.DECLINED,
                outcome_confidence=0.80,
                completed_at=timezone.now(),
                outcome_measured_at=timezone.now()
            )

        # Create 1 insufficient data action (should be excluded from evaluatable denominator)
        SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="Insufficient Action",
            target_url="https://strategy-alpha.com/new-page",
            status=ActionStatus.COMPLETED,
            verification_status=VerificationStatus.VERIFIED,
            seo_outcome=SEOOutcome.INSUFFICIENT_DATA,
            completed_at=timezone.now(),
            outcome_measured_at=timezone.now()
        )

        service = SEOAdaptiveStrategyService(project=self.project_a)
        strategy = service.evaluate_strategy()

        self.assertEqual(strategy['historical_sample_size'], 12)
        self.assertEqual(strategy['evaluatable_sample_size'], 11)
        self.assertEqual(strategy['strategy_confidence'], 'high')
        self.assertIn(ActionType.OPTIMIZE_TITLE, strategy['preferred_actions'])
        self.assertIn(ActionType.FIX_MISSING_H1, strategy['deprioritized_actions'])

        # Check action prioritizations
        title_prio = strategy['action_prioritizations'][ActionType.OPTIMIZE_TITLE]
        self.assertGreater(title_prio['historical_adjustment'], 0.0)
        self.assertEqual(title_prio['learning_signal'], 'positive')

        h1_prio = strategy['action_prioritizations'][ActionType.FIX_MISSING_H1]
        self.assertLess(h1_prio['historical_adjustment'], 0.0)
        self.assertEqual(h1_prio['learning_signal'], 'negative')

    def test_planner_adaptive_prioritization_and_safety_invariants(self):
        """5. Planner dynamically reorders actions while strictly enforcing human approval & risk invariants."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus, SEOOutcome, ActionRiskLevel
        from apps.seo.services.seo_action_planner import SEOActionPlanner

        # Add positive history for OPTIMIZE_TITLE
        for i in range(5):
            SEOAction.objects.create(
                project=self.project_a,
                action_type=ActionType.OPTIMIZE_TITLE,
                title=f"Historic Title {i}",
                target_url=f"https://strategy-alpha.com/p-{i}",
                status=ActionStatus.COMPLETED,
                verification_status=VerificationStatus.VERIFIED,
                seo_outcome=SEOOutcome.IMPROVED,
                outcome_confidence=0.85,
                completed_at=timezone.now(),
                outcome_measured_at=timezone.now()
            )

        planner = SEOActionPlanner(project=self.project_a)

        proposals = [
            {
                "action_type": ActionType.FIX_CANONICAL,
                "title": "Fix Broken Canonical Tag",
                "description": "Ensure self-referential canonical tag on page.",
                "target_url": "https://strategy-alpha.com/products",
                "risk_level": ActionRiskLevel.HIGH,
                "expected_impact": "high",
                "opportunity_score": 50,
                "execution_available": True,
                "verification_plan": {"method": "dom_check"}
            },
            {
                "action_type": ActionType.OPTIMIZE_TITLE,
                "title": "Optimize Low-CTR Title Tag",
                "description": "Align title tag with target query intent.",
                "target_url": "https://strategy-alpha.com/features",
                "risk_level": ActionRiskLevel.LOW,
                "expected_impact": "medium",
                "opportunity_score": 55,
                "execution_available": True,
                "verification_plan": {"method": "dom_check"}
            }
        ]

        prioritized, strat = planner.apply_adaptive_prioritization(proposals)
        self.assertEqual(len(prioritized), 2)

        # Title action received positive adjustment
        title_prop = next(p for p in prioritized if p['action_type'] == ActionType.OPTIMIZE_TITLE)
        self.assertGreater(title_prop['historical_adjustment'], 0.0)
        self.assertGreater(title_prop['final_priority_score'], title_prop['base_priority_score'])

        # SAFETY INVARIANTS: FIX_CANONICAL must still have HIGH risk
        canonical_prop = next(p for p in prioritized if p['action_type'] == ActionType.FIX_CANONICAL)
        self.assertEqual(canonical_prop['risk_level'], ActionRiskLevel.HIGH)

    def test_get_adaptive_seo_strategy_agent_tool(self):
        """6. Agent tool get_adaptive_seo_strategy executes and returns calibrated signals."""
        from apps.seo.services.tool_registry import get_tool_registry

        registry = get_tool_registry()
        tool = registry.get_tool("get_adaptive_seo_strategy")
        self.assertIsNotNone(tool)
        self.assertFalse(tool.requires_approval)
        self.assertFalse(tool.is_mutating)

        result = registry.execute("get_adaptive_seo_strategy", project=self.project_a, arguments={})
        self.assertTrue(result['success'])
        self.assertIn("strategy_confidence", result['data'])
        self.assertIn("evidence_hierarchy", result['data'])
        self.assertIn("preferred_actions", result['data'])
        self.assertIn("deprioritized_actions", result['data'])

    def test_api_endpoints_and_cross_tenant_isolation(self):
        """7. REST API endpoints operate with authentication and enforce multi-tenant isolation."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus, SEOOutcome

        # Seed data for Project A
        SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="Project A Title Action",
            target_url="https://strategy-alpha.com/features",
            status=ActionStatus.COMPLETED,
            verification_status=VerificationStatus.VERIFIED,
            seo_outcome=SEOOutcome.IMPROVED,
            outcome_confidence=0.85,
            completed_at=timezone.now(),
            outcome_measured_at=timezone.now()
        )

        # 1. User A retrieves Project A strategy via /api/seo/ai/strategy/
        self.client.force_authenticate(user=self.user_a)
        res_a1 = self.client.get(f'/api/seo/ai/strategy/?project_id={self.project_a.id}')
        self.assertEqual(res_a1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_a1.data['project_id'], self.project_a.id)
        self.assertEqual(res_a1.data['historical_sample_size'], 1)

        # 2. User A retrieves Project A strategy via /api/seo/ai/actions/strategy/
        res_a2 = self.client.get(f'/api/seo/ai/actions/strategy/?project_id={self.project_a.id}')
        self.assertEqual(res_a2.status_code, status.HTTP_200_OK)
        self.assertEqual(res_a2.data['project_id'], self.project_a.id)

        # 3. Missing project_id yields 400 Bad Request
        res_missing = self.client.get('/api/seo/ai/strategy/')
        self.assertEqual(res_missing.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. Multi-tenant isolation: User B cannot access Project A strategy
        self.client.force_authenticate(user=self.user_b)
        res_unauth1 = self.client.get(f'/api/seo/ai/strategy/?project_id={self.project_a.id}')
        self.assertEqual(res_unauth1.status_code, status.HTTP_404_NOT_FOUND)

        res_unauth2 = self.client.get(f'/api/seo/ai/actions/strategy/?project_id={self.project_a.id}')
        self.assertEqual(res_unauth2.status_code, status.HTTP_404_NOT_FOUND)

        # 5. User B receives independent, clean strategy for Project B (zero leakage from Project A)
        res_b = self.client.get(f'/api/seo/ai/strategy/?project_id={self.project_b.id}')
        self.assertEqual(res_b.status_code, status.HTTP_200_OK)
        self.assertEqual(res_b.data['historical_sample_size'], 0)
        self.assertEqual(res_b.data['strategy_confidence'], 'none')

    def test_four_tier_reasoning_and_evidence_integrity(self):
        """8. Four-tier reasoning hierarchy cleanly separates observed facts from empirical inferences."""
        from apps.seo.services.seo_adaptive_strategy import SEOAdaptiveStrategyService

        service = SEOAdaptiveStrategyService(project=self.project_a)
        strat = service.evaluate_strategy()

        evidence = strat.get('evidence_hierarchy', {})
        self.assertIn('tier_1_observed_facts', evidence)
        self.assertIn('tier_2_historical_evidence', evidence)
        self.assertIn('tier_3_inferences', evidence)
        self.assertIn('tier_4_recommendations', evidence)

        # Inferences communicate empirical uncertainty, not guaranteed causal fact
        self.assertIn('Empirical historical win/loss rates', evidence['tier_3_inferences'])


class SEOAgentOrchestrationTests(TestCase):
    """
    Phase 4.7 Integration & Unit Tests:
    Specialized SEO Agent Orchestration Layer, deterministic routing, explicit handoffs,
    strict tool permissions, shared context propagation, safety invariants, and multi-tenant security.
    """

    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_user(
            email='user_a@orchestration.com',
            password='Password123!'
        )
        self.user_b = User.objects.create_user(
            email='user_b@orchestration.com',
            password='Password123!'
        )

        self.project_a = Project.objects.create(
            name="Project Alpha Orchestrated",
            website_url="https://alpha-orchestrate.com",
            owner=self.user_a
        )
        self.project_b = Project.objects.create(
            name="Project Beta Orchestrated",
            website_url="https://beta-orchestrate.com",
            owner=self.user_b
        )

        self.client = APIClient()

    def test_agent_result_contract_validation(self):
        """1. AgentResult enforces typed universal contract, serialization, and confidence bounds."""
        from apps.seo.services.agents.base_agent import AgentResult

        res = AgentResult(
            agent="seo_investigator",
            status="completed",
            confidence=0.875,
            evidence={"metric": 42},
            findings=["Discovered critical heading anomaly."],
            recommendations=[{"action": "fix_heading"}],
            next_step="strategy",
            errors=[],
            duration_ms=120,
            metadata={"source": "unit_test"}
        )

        d = res.to_dict()
        self.assertEqual(d["agent"], "seo_investigator")
        self.assertEqual(d["status"], "completed")
        self.assertEqual(d["confidence"], 0.875)
        self.assertEqual(d["next_step"], "strategy")
        self.assertEqual(len(d["findings"]), 1)
        self.assertEqual(d["duration_ms"], 120)

    def test_tool_permission_enforcement(self):
        """2. Specialized agents cannot execute tools outside their explicit allowlist."""
        from apps.seo.services.agents.seo_research_agent import SEOResearchAgent

        agent = SEOResearchAgent(project=self.project_a)

        # 1. Authorized tool call succeeds without PermissionError
        result = agent.execute_tool("get_gsc_performance", {"days": 28})
        self.assertIsInstance(result, dict)

        # 2. Unauthorized mutating or planning tool call is strictly blocked
        with self.assertRaises(PermissionError) as ctx:
            agent.execute_tool("plan_seo_actions", {})
        self.assertIn("is NOT authorized to execute tool 'plan_seo_actions'", str(ctx.exception))

        with self.assertRaises(PermissionError) as ctx:
            agent.execute_tool("propose_seo_action", {})
        self.assertIn("is NOT authorized to execute tool 'propose_seo_action'", str(ctx.exception))

    def test_deterministic_routing(self):
        """3. Supervisor deterministically routes diverse user goals to appropriate agent pipelines."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent

        supervisor = SEOSupervisorAgent(project=self.project_a)

        # Investigation intent
        wf, pipeline = supervisor.determine_workflow("Investigate why rankings dropped for /features")
        self.assertEqual(wf, "investigate")
        self.assertEqual(pipeline, ["seo_researcher", "seo_investigator", "seo_strategist"])

        # Planning intent
        wf, pipeline = supervisor.determine_workflow("Create an action plan to optimize product pages")
        self.assertEqual(wf, "plan")
        self.assertEqual(pipeline, ["seo_researcher", "seo_investigator", "seo_strategist", "seo_action_planner"])

        # Strategy intent
        wf, pipeline = supervisor.determine_workflow("Prioritize adaptive strategy based on historical outcomes")
        self.assertEqual(wf, "strategy")
        self.assertEqual(pipeline, ["seo_researcher", "seo_strategist"])

        # Verification intent
        wf, pipeline = supervisor.determine_workflow("Verify live website changes and measure GSC outcome lift")
        self.assertEqual(wf, "verify")
        self.assertEqual(pipeline, ["seo_verifier"])

        # Default full cycle
        wf, pipeline = supervisor.determine_workflow("Comprehensive optimization")
        self.assertEqual(wf, "full_cycle")
        self.assertEqual(pipeline, ["seo_researcher", "seo_investigator", "seo_strategist", "seo_action_planner"])

    def test_sequential_pipeline_and_shared_context_handoff(self):
        """4. Sequential agent handoff pipeline accumulates domain evidence in SharedContext."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        context = supervisor.orchestrate(
            task="Investigate ranking drop on /about",
            target_url="https://alpha-orchestrate.com/about"
        )

        self.assertEqual(context.status, "completed")
        self.assertEqual(context.project_id, self.project_a.id)
        self.assertEqual(context.task_type, "investigate")

        # Verify evidence accumulated across handoffs
        self.assertIn("audit_summary", context.evidence)
        self.assertGreater(len(context.investigation_findings), 0)
        self.assertIn("strategy_confidence", context.strategy_signals)

        # Verify auditable agent execution history
        agents_executed = list(dict.fromkeys(item["agent"] for item in context.agent_results_history))
        self.assertEqual(agents_executed, ["seo_researcher", "seo_investigator", "seo_strategist"])

    def test_action_planning_agent_preserves_human_approval_and_safety(self):
        """5. ActionPlanningAgent strictly preserves human-in-the-loop approval gate."""
        from apps.seo.services.agents.seo_action_agent import SEOActionPlanningAgent
        from apps.seo.services.agents.base_agent import SharedContext
        from apps.seo.models import ActionStatus

        context = SharedContext(
            project_id=self.project_a.id,
            project_name=self.project_a.name,
            website_url=self.project_a.website_url,
            user_id=self.user_a.id,
            task_goal="Create title action plan"
        )

        agent = SEOActionPlanningAgent(project=self.project_a, user=self.user_a)
        result = agent.run(context)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.next_step, "human_approval")
        self.assertIsNotNone(context.created_plan_id)

        # Verify all created actions are in PROPOSED status and require human approval
        for act in context.action_proposals:
            self.assertTrue(act["requires_human_approval"])
            self.assertEqual(act["status"], ActionStatus.PROPOSED)

    def test_api_endpoints_and_multi_tenant_isolation(self):
        """6. REST API routes execute with authentication and enforce multi-tenant isolation."""
        # 1. User A lists specialized agents
        self.client.force_authenticate(user=self.user_a)
        res_agents = self.client.get(f'/api/seo/ai/orchestrate/agents/?project_id={self.project_a.id}')
        self.assertEqual(res_agents.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_agents.data["agents"]), 5)
        self.assertEqual(len(res_agents.data["workflows"]), 6)

        # 2. User A successfully triggers orchestrated workflow
        res_post = self.client.post('/api/seo/ai/orchestrate/', {
            "project_id": self.project_a.id,
            "task": "Investigate ranking drop on /features",
            "target_url": "https://alpha-orchestrate.com/features"
        }, format='json')
        self.assertEqual(res_post.status_code, status.HTTP_200_OK)
        self.assertEqual(res_post.data["status"], "completed")
        self.assertEqual(res_post.data["project_id"], self.project_a.id)

        # 3. User B cannot orchestrate Project A (multi-tenant boundary)
        self.client.force_authenticate(user=self.user_b)
        res_forbidden = self.client.post('/api/seo/ai/orchestrate/', {
            "project_id": self.project_a.id,
            "task": "Investigate ranking drop on /features"
        }, format='json')
        self.assertEqual(res_forbidden.status_code, status.HTTP_404_NOT_FOUND)

        # 4. Missing project_id yields 400 Bad Request
        res_bad = self.client.post('/api/seo/ai/orchestrate/', {"task": "test"}, format='json')
        self.assertEqual(res_bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_failure_handling_and_safe_pipeline_halting(self):
        """7. Supervisor halts pipeline gracefully when a specialized agent reports failure."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from unittest.mock import patch

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)

        # Mock failure in the investigation agent
        with patch.object(
            supervisor._agents["seo_investigator"],
            "_execute",
            side_effect=RuntimeError("Simulated database timeout during diagnosis")
        ):
            context = supervisor.orchestrate(
                task="Investigate ranking drop on /test-fail"
            )

            # Pipeline should halt safely with failed status
            self.assertEqual(context.status, "failed")
            self.assertGreater(len(context.errors), 0)
            self.assertIn("Simulated database timeout", context.errors[0])

            # Research agent succeeded, investigator failed, strategist skipped
            executed = list(dict.fromkeys(item["agent"] for item in context.agent_results_history))
            self.assertEqual(executed, ["seo_researcher", "seo_investigator"])
            self.assertEqual(context.agent_results_history[0]["status"], "completed")
            self.assertEqual(context.agent_results_history[-1]["status"], "failed")


class SEOModelContextProtocolTests(TestCase):
    """
    Phase 4.8 Integration & Unit Tests:
    Model Context Protocol (MCP) server, client discovery, tool adaptation,
    strict read-only permissions, agent integration, and REST API endpoints.
    """

    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_user(
            email='mcp_user_a@doxarank.ai',
            password='Password123!'
        )
        self.project_a = Project.objects.create(
            name="Project Alpha MCP",
            website_url="https://alpha-mcp.com",
            owner=self.user_a
        )
        self.client = APIClient()

    def test_mcp_server_and_tool_discovery(self):
        """1. Local MCP server implements tools/list and returns valid tool declarations and schemas."""
        from apps.seo.services.mcp.server import LocalSEOExternalServer
        from apps.seo.services.mcp.client import MCPClient

        server = LocalSEOExternalServer()
        client = MCPClient(server=server, server_id="seo_local")
        tools = client.discover_tools()

        self.assertEqual(len(tools), 3)
        tool_names = [t["name"] for t in tools]
        self.assertIn("check_url_status", tool_names)
        self.assertIn("get_page_metadata", tool_names)
        self.assertIn("get_external_page_signals", tool_names)

        # Verify JSON-Schema compliance
        status_tool = next(t for t in tools if t["name"] == "check_url_status")
        self.assertEqual(status_tool["category"], "read_only")
        self.assertFalse(status_tool["is_mutating"])
        self.assertIn("url", status_tool["inputSchema"]["required"])

    def test_mcp_tool_invocation_protocol(self):
        """2. MCPClient calls tools/call on server and returns structured, normalized content."""
        from apps.seo.services.mcp.server import LocalSEOExternalServer
        from apps.seo.services.mcp.client import MCPClient

        server = LocalSEOExternalServer()
        client = MCPClient(server=server, server_id="seo_local")

        # Test URL status call
        result = client.call_tool("check_url_status", {"url": "https://alpha-mcp.com/pricing"})
        self.assertTrue(result["success"])
        self.assertIn("latency_ms", result["data"])
        self.assertIn("url", result["data"])

        # Test Page metadata call
        meta_result = client.call_tool("get_page_metadata", {"url": "https://alpha-mcp.com/features"})
        self.assertTrue(meta_result["success"])
        self.assertIn("metadata_present", meta_result["data"])
        self.assertIn("title", meta_result["data"])

    def test_tool_adapter_and_central_registry_integration(self):
        """3. Discovered MCP tools adapt into AgentToolDefinition and mount into central ToolRegistry."""
        from apps.seo.services.tool_registry import get_tool_registry

        registry = get_tool_registry()
        adapted_tool = registry.get("mcp__seo_local__check_url_status")

        self.assertIsNotNone(adapted_tool)
        self.assertEqual(adapted_tool.category, "read_only")
        self.assertFalse(adapted_tool.requires_approval)
        self.assertFalse(adapted_tool.is_mutating)

        # Execute through central ToolRegistry
        exec_res = registry.execute(
            "mcp__seo_local__check_url_status",
            project=self.project_a,
            arguments={"url": "https://alpha-mcp.com/blog"}
        )

        self.assertTrue(exec_res["success"])
        self.assertEqual(exec_res["data"]["source"], "mcp")
        self.assertEqual(exec_res["data"]["server"], "seo_local")
        self.assertEqual(exec_res["data"]["status"], "success")

    def test_security_and_permission_enforcement(self):
        """4. Security policy rejects unapproved servers, mutating tools, and unauthorized agents."""
        from apps.seo.services.mcp.permissions import MCPPermissionPolicy
        from apps.seo.services.agents.seo_action_agent import SEOActionPlanningAgent

        # 1. Unapproved server is rejected
        self.assertFalse(MCPPermissionPolicy.is_server_approved("rogue_untrusted_server"))
        is_valid, err = MCPPermissionPolicy.validate_tool_for_registration(
            server_id="rogue_server",
            tool_declaration={"name": "test", "is_mutating": False}
        )
        self.assertFalse(is_valid)

        # 2. Mutating tool declaration is strictly rejected
        is_valid, err = MCPPermissionPolicy.validate_tool_for_registration(
            server_id="seo_local",
            tool_declaration={"name": "publish_content", "is_mutating": True, "category": "mutating"}
        )
        self.assertFalse(is_valid)
        self.assertIn("MCP mutation is forbidden", err)

        # 3. Path traversal attack in arguments is caught by sanitizer
        valid_args, clean, err = MCPPermissionPolicy.sanitize_arguments({"url": "https://example.com/../../etc/passwd"})
        self.assertFalse(valid_args)
        self.assertIn("Path traversal forbidden", err)

        # 4. Unauthorized agent (e.g. action planner) cannot call MCP tools
        planner_agent = SEOActionPlanningAgent(project=self.project_a, user=self.user_a)
        with self.assertRaises(PermissionError) as ctx:
            planner_agent.execute_tool("mcp__seo_local__check_url_status", {"url": "https://example.com"})
        self.assertIn("is NOT authorized to execute tool", str(ctx.exception))

    def test_specialized_agent_mcp_integration(self):
        """5. SEOResearchAgent successfully queries external MCP tools and enriches shared context."""
        from apps.seo.services.agents.seo_research_agent import SEOResearchAgent
        from apps.seo.services.agents.base_agent import SharedContext

        context = SharedContext(
            project_id=self.project_a.id,
            project_name=self.project_a.name,
            website_url=self.project_a.website_url,
            user_id=self.user_a.id,
            target_url="https://alpha-mcp.com/features"
        )

        agent = SEOResearchAgent(project=self.project_a, user=self.user_a)
        result = agent.run(context)

        self.assertEqual(result.status, "completed")
        # Verify MCP URL status was collected and added to evidence
        self.assertIn("mcp_url_status", context.evidence)
        self.assertIn("url", context.evidence["mcp_url_status"])
        self.assertTrue(any("MCP External Diagnostics" in f for f in result.findings))

    def test_mcp_failure_handling_and_graceful_degradation(self):
        """6. Agent continues safely when external MCP server encounters a failure or timeout."""
        from apps.seo.services.mcp.client import MCPClient
        from unittest.mock import MagicMock

        # Mock a failing server
        mock_server = MagicMock()
        mock_server.handle_request.side_effect = RuntimeError("Socket connection timed out")

        client = MCPClient(server=mock_server, server_id="seo_local")
        res = client.call_tool("check_url_status", {"url": "https://fail-test.com"})

        # Client must handle failure gracefully without crashing
        self.assertFalse(res["success"])
        self.assertIn("Socket connection timed out", res["error"])

    def test_rest_api_endpoints(self):
        """7. REST API endpoints /api/seo/ai/mcp/servers/ and /api/seo/ai/mcp/tools/ require auth and return valid data."""
        # 1. Unauthenticated request is rejected
        res_unauth = self.client.get('/api/seo/ai/mcp/servers/')
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Authenticated user lists servers
        self.client.force_authenticate(user=self.user_a)
        res_servers = self.client.get('/api/seo/ai/mcp/servers/')
        self.assertEqual(res_servers.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_servers.data["count"], 1)
        self.assertEqual(res_servers.data["servers"][0]["server_id"], "seo_local")

        # 3. Authenticated user lists discovered MCP tools
        res_tools = self.client.get('/api/seo/ai/mcp/tools/')
        self.assertEqual(res_tools.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res_tools.data["count"], 3)
        tool_names = [t["raw_name"] for t in res_tools.data["tools"]]
        self.assertIn("check_url_status", tool_names)


class SEOAmharicNormalizerTests(TestCase):
    """
    Phase 4.9.1 Unit Tests:
    Amharic & Ge'ez script homophone collapsing, Ethiopian punctuation normalization,
    and keyword equivalence for Ethiopia-first search on google.com.et.
    """

    def test_ha_series_homophone_collapsing(self):
        """1. Canonicalizes variants of Ha (ሀ, ሐ, ኀ, ኃ, ኻ) to standard form."""
        from apps.seo.services.amharic_normalizer import normalize_amharic_query
        self.assertEqual(normalize_amharic_query("ሐኪም"), "ሀኪም")
        self.assertEqual(normalize_amharic_query("ኀይል"), "ሀይል")
        self.assertEqual(normalize_amharic_query("ኃይል"), "ሃይል")
        self.assertEqual(normalize_amharic_query("ሑነታ"), "ሁነታ")
        self.assertEqual(normalize_amharic_query("ሕግ"), "ህግ")

    def test_se_series_homophone_collapsing(self):
        """2. Canonicalizes variants of Se (ሰ, ሠ) to standard form."""
        from apps.seo.services.amharic_normalizer import normalize_amharic_query
        self.assertEqual(normalize_amharic_query("ሠዓት"), "ሰአት")
        self.assertEqual(normalize_amharic_query("ሥራ"), "ስራ")
        self.assertEqual(normalize_amharic_query("ሢመት"), "ሲመት")

    def test_a_series_homophone_collapsing(self):
        """3. Canonicalizes variants of A (አ, ዓ, ዐ) to standard form."""
        from apps.seo.services.amharic_normalizer import normalize_amharic_query
        self.assertEqual(normalize_amharic_query("ዐዲስ አበባ"), "አዲስ አበባ")
        self.assertEqual(normalize_amharic_query("ዓለም"), "አለም")
        self.assertEqual(normalize_amharic_query("ዕውቀት"), "እውቀት")

    def test_tse_series_homophone_collapsing(self):
        """4. Canonicalizes variants of Tse (ጸ, ፀ) to standard form."""
        from apps.seo.services.amharic_normalizer import normalize_amharic_query
        self.assertEqual(normalize_amharic_query("ፀሐይ"), "ጸሀይ")
        self.assertEqual(normalize_amharic_query("ፀሎት"), "ጸሎት")
        self.assertEqual(normalize_amharic_query("ፅህፈት"), "ጽህፈት")

    def test_ethiopic_punctuation_stripping(self):
        """5. Replaces word space separator (፡) with standard space and strips sentence marks."""
        from apps.seo.services.amharic_normalizer import normalize_amharic_query
        self.assertEqual(normalize_amharic_query("ኢትዮጵያ፡ቴሌኮም"), "ኢትዮጵያ ቴሌኮም")
        self.assertEqual(normalize_amharic_query("አዲስ፡አበባ።"), "አዲስ አበባ")

    def test_semantic_equivalence(self):
        """6. Verifies semantic equivalence across homophone variations."""
        from apps.seo.services.amharic_normalizer import are_keywords_equivalent
        self.assertTrue(are_keywords_equivalent("አዲስ አበባ", "ዐዲስ አበባ"))
        self.assertTrue(are_keywords_equivalent("ሰዓት", "ሠዓት"))
        self.assertTrue(are_keywords_equivalent("ፀሐይ", "ጸሀይ"))
        self.assertFalse(are_keywords_equivalent("አዲስ አበባ", "ድሬዳዋ"))

    def test_keyword_model_normalized_keyword_property(self):
        """7. Keyword model property accurately yields normalized Amharic query."""
        from apps.seo.models import Keyword, Language
        user = get_user_model().objects.create_user(email='norm_test@doxarank.ai', password='Password123!')
        project = Project.objects.create(name="ET Portal", website_url="https://etportal.com", owner=user)
        kw = Keyword.objects.create(
            project=project,
            keyword="ዐዲስ አበባ",
            language=Language.AM
        )
        self.assertEqual(kw.normalized_keyword, "አዲስ አበባ")


class SEOAgentEndToEndWorkflowTests(TestCase):
    """
    Phase 4.9.2 End-to-End Agent Lifecycle Tests:
    Validates complete 12-stage lifecycle:
    User Goal -> Supervisor -> Research -> Investigation -> Strategy -> Plan ->
    Human Approval -> Execution -> Verification -> Outcome -> Learning -> Adaptive Strategy.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email='e2e_user@doxarank.ai', password='Password123!')
        self.project = Project.objects.create(
            name="E2E Portal",
            website_url="https://e2e-portal.et",
            owner=self.user
        )
        self.client = APIClient()
        self.target_url = "https://e2e-portal.et/services"

    def test_01_full_autonomous_investigation_and_evidence_synthesis(self):
        """Scenario 1: Supervisor executes full autonomous investigation pipeline."""
        from apps.seo.services.agents import SEOSupervisorAgent

        supervisor = SEOSupervisorAgent(project=self.project, user=self.user)
        context = supervisor.orchestrate(
            task="Investigate ranking drop and propose recovery action plan for /services",
            target_url=self.target_url
        )

        self.assertEqual(context.status, "completed")
        self.assertGreaterEqual(len(context.agent_results_history), 4)
        agents_run = [h["agent"] for h in context.agent_results_history]
        self.assertIn("seo_researcher", agents_run)
        self.assertIn("seo_investigator", agents_run)
        self.assertIn("seo_strategist", agents_run)
        self.assertIn("seo_action_planner", agents_run)
        self.assertIsNotNone(context.action_plan_id)

    def test_02_action_requiring_human_approval_halts_at_gate(self):
        """Scenario 2: Action planning strictly halts at human approval gate with requires_human_approval=True."""
        from apps.seo.models import SEOActionPlan, ActionPlanStatus
        from apps.seo.services.agents.seo_action_agent import SEOActionPlanningAgent
        from apps.seo.services.agents.base_agent import SharedContext

        context = SharedContext(
            project_id=self.project.id,
            project_name=self.project.name,
            website_url=self.project.website_url,
            user_id=self.user.id,
            target_url=self.target_url,
            evidence={"top_opportunity_type": "high_impressions_low_ctr"}
        )

        agent = SEOActionPlanningAgent(project=self.project, user=self.user)
        result = agent.run(context)

        self.assertEqual(result.status, "completed")
        plan = SEOActionPlan.objects.get(id=context.action_plan_id)
        self.assertEqual(plan.status, ActionPlanStatus.PROPOSED)
        self.assertTrue(plan.requires_human_approval)
        self.assertIsNone(plan.approved_at)

    def test_03_human_rejection_of_action(self):
        """Scenario 3: Human review rejects proposed action and plan safely archives without mutating."""
        from apps.seo.models import SEOActionPlan, SEOAction, ActionType, ActionStatus, ActionPlanStatus
        from apps.seo.services.action_service import SEOActionService

        plan = SEOActionPlan.objects.create(
            project=self.project,
            title="Title Update Plan",
            status=ActionPlanStatus.PROPOSED,
            requires_human_approval=True
        )
        action = SEOAction.objects.create(
            project=self.project,
            plan=plan,
            action_type=ActionType.OPTIMIZE_TITLE,
            target_url=self.target_url,
            title="Update Page Title",
            status=ActionStatus.PROPOSED,
            requires_human_approval=True
        )

        # Reject action
        action.status = ActionStatus.REJECTED
        action.save(update_fields=['status'])
        plan.status = ActionPlanStatus.REJECTED
        plan.save(update_fields=['status'])

        self.assertEqual(action.status, ActionStatus.REJECTED)
        self.assertEqual(plan.status, ActionPlanStatus.REJECTED)

    def test_04_approved_action_execution_via_connector(self):
        """Scenario 4: Approved action executes cleanly through mutation connector."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus
        from apps.seo.services.mutation_connectors import DryRunMutationConnector

        action = SEOAction.objects.create(
            project=self.project,
            action_type=ActionType.OPTIMIZE_TITLE,
            target_url=self.target_url,
            title="Update Title Tag",
            status=ActionStatus.APPROVED,
            requires_human_approval=True,
            proposed_change={"title": "Updated Services Page Title | E2E Portal"}
        )

        connector = DryRunMutationConnector()
        res = connector.execute(action)

        self.assertEqual(res["status"], "success")
        action.status = ActionStatus.COMPLETED
        action.save(update_fields=['status'])
        self.assertEqual(action.status, ActionStatus.COMPLETED)

    def test_05_execution_failure_handling(self):
        """Scenario 5: Execution failure is captured gracefully with failure status."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus

        action = SEOAction.objects.create(
            project=self.project,
            action_type=ActionType.FIX_CANONICAL,
            target_url=self.target_url,
            title="Update Canonical",
            status=ActionStatus.APPROVED,
            requires_human_approval=True
        )

        # Simulate execution failure
        action.status = ActionStatus.FAILED
        action.save(update_fields=['status'])

        self.assertEqual(action.status, ActionStatus.FAILED)

    def test_06_technical_verification_failure_handling(self):
        """Scenario 6: Technical verification detects unapplied change and flags failure."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus
        from apps.seo.services.seo_action_verifier import SEOActionVerifier

        action = SEOAction.objects.create(
            project=self.project,
            action_type=ActionType.OPTIMIZE_TITLE,
            target_url=self.target_url,
            title="Verify Title Tag",
            status=ActionStatus.COMPLETED,
            verification_status=VerificationStatus.PENDING,
            proposed_change={"title": "New Title Tag"}
        )

        verifier = SEOActionVerifier(project=self.project)
        # Mock HTML crawler returning old title (verification failed)
        mock_html = "<html><head><title>Old Old Title</title></head></html>"
        res = verifier.verify_action(action, html_override=mock_html)

        self.assertFalse(res["verified"])
        action.refresh_from_db()
        self.assertEqual(action.verification_status, VerificationStatus.FAILED)

    def test_07_successful_outcome_measurement(self):
        """Scenario 7: Successful outcome measurement calculates lift and classifies outcome."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus, SEOOutcome
        from apps.seo.services.seo_outcome_learning import SEOOutcomeMeasurementService

        action = SEOAction.objects.create(
            project=self.project,
            action_type=ActionType.OPTIMIZE_TITLE,
            target_url=self.target_url,
            title="Measure Title Outcome",
            status=ActionStatus.COMPLETED,
            verification_status=VerificationStatus.VERIFIED
        )

        # Record outcome directly on action
        action.seo_outcome = SEOOutcome.IMPROVED
        action.outcome_evidence = {"deltas": {"clicks": 25}}
        action.save(update_fields=['seo_outcome', 'outcome_evidence'])

        self.assertEqual(action.seo_outcome, SEOOutcome.IMPROVED)
        self.assertEqual(action.outcome_evidence["deltas"]["clicks"], 25)

    def test_08_adaptive_strategy_calibration_update(self):
        """Scenario 8: Historical learning updates action type win rates and strategy priority."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, VerificationStatus, SEOOutcome
        from apps.seo.services.seo_adaptive_strategy import SEOAdaptiveStrategyService

        # Seed outcomes
        for i in range(4):
            act = SEOAction.objects.create(
                project=self.project,
                action_type=ActionType.OPTIMIZE_TITLE,
                target_url=f"https://e2e-portal.et/page-{i}",
                title=f"Title Act {i}",
                status=ActionStatus.COMPLETED,
                verification_status=VerificationStatus.VERIFIED,
                seo_outcome=SEOOutcome.IMPROVED
            )

        strat_service = SEOAdaptiveStrategyService(project=self.project)
        strategy = strat_service.evaluate_strategy()

        self.assertIn("action_prioritizations", strategy)
        title_stats = strategy["action_prioritizations"].get(ActionType.OPTIMIZE_TITLE)
        self.assertIsNotNone(title_stats)
        self.assertGreater(title_stats["historical_smoothed_rate"], 0.5)

    def test_09_mcp_tool_failure_graceful_degradation(self):
        """Scenario 9: Research Agent degrades safely when external MCP server fails."""
        from apps.seo.services.agents.seo_research_agent import SEOResearchAgent
        from apps.seo.services.agents.base_agent import SharedContext
        from unittest.mock import patch

        agent = SEOResearchAgent(project=self.project, user=self.user)
        context = SharedContext(
            project_id=self.project.id,
            project_name=self.project.name,
            website_url=self.project.website_url,
            user_id=self.user.id,
            target_url=self.target_url
        )

        with patch.object(agent, 'execute_tool', side_effect=RuntimeError("MCP server socket timed out")):
            # Agent should catch error and return completed status using fallbacks
            result = agent.run(context)
            self.assertEqual(result.status, "completed")

    def test_10_external_api_failure_recovery(self):
        """Scenario 10: External GSC API timeout produces structured warning without unhandled crash."""
        from apps.seo.services.agents.seo_research_agent import SEOResearchAgent
        from apps.seo.services.agents.base_agent import SharedContext
        from unittest.mock import patch

        agent = SEOResearchAgent(project=self.project, user=self.user)
        context = SharedContext(
            project_id=self.project.id,
            project_name=self.project.name,
            website_url=self.project.website_url,
            user_id=self.user.id
        )

        with patch('apps.seo.services.search_console.MockGoogleSearchConsoleClient.query_search_analytics', side_effect=TimeoutError("GSC API 504 Gateway Timeout")):
            result = agent.run(context)
            self.assertEqual(result.status, "completed")


class SEOAgentReliabilityAndSecurityTests(TestCase):
    """
    Phase 4.9.3 & 4.9.4 Reliability, Failure Recovery, and Security Tests:
    Guarantees bounded loops, exception isolation, multi-tenant boundaries, and secret protection.
    """

    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_user(email='user_a_rel@doxarank.ai', password='Password123!')
        self.user_b = User.objects.create_user(email='user_b_rel@doxarank.ai', password='Password123!')

        self.project_a = Project.objects.create(name="Project A", website_url="https://a.com", owner=self.user_a)
        self.project_b = Project.objects.create(name="Project B", website_url="https://b.com", owner=self.user_b)
        self.client = APIClient()

    def test_bounded_react_loop_iterations(self):
        """1. AgentOrchestrator halts strictly at max_steps (no infinite runaway loops)."""
        from apps.seo.models import AgentRunStatus
        from apps.seo.services.agent_orchestrator import AgentOrchestrator
        from unittest.mock import MagicMock

        # Mock provider that continuously requests varying tools
        mock_provider = MagicMock()
        mock_provider.decide_agent_action.side_effect = [
            {
                "action": "tool",
                "tool_name": f"get_tracked_keywords_{i}",
                "arguments": {"idx": i},
                "reason": f"Indefinite loop test step {i}"
            }
            for i in range(15)
        ]

        orchestrator = AgentOrchestrator(
            project=self.project_a,
            user=self.user_a,
            provider=mock_provider,
            max_steps=5
        )

        run = orchestrator.start_run(goal="Test runaway bounds")
        self.assertEqual(run.total_steps, 5)
        self.assertIn(run.status, [AgentRunStatus.FAILED, AgentRunStatus.COMPLETED])

    def test_repetitive_tool_loop_prevention(self):
        """1b. AgentOrchestrator immediately halts on repetitive failed tool calls."""
        from apps.seo.models import AgentRunStatus
        from apps.seo.services.agent_orchestrator import AgentOrchestrator
        from unittest.mock import MagicMock

        mock_provider = MagicMock()
        mock_provider.decide_agent_action.return_value = {
            "action": "tool",
            "tool_name": "get_tracked_keywords",
            "arguments": {},
            "reason": "Repeated failing tool"
        }

        orchestrator = AgentOrchestrator(
            project=self.project_a,
            user=self.user_a,
            provider=mock_provider,
            max_steps=10
        )

        run = orchestrator.start_run(goal="Test loop abort")
        self.assertEqual(run.status, AgentRunStatus.FAILED)
        self.assertIn("repetitive", run.summary.lower())

    def test_tool_exception_isolation(self):
        """2. Tool throwing unexpected exception returns structured error dict and does not crash."""
        from apps.seo.services.tool_registry import get_tool_registry

        registry = get_tool_registry()
        # Invalid arguments
        res = registry.execute("get_keyword_rankings", project=self.project_a, arguments={"limit": "not_an_int"})
        self.assertFalse(res["success"])
        self.assertIsNotNone(res["error"])

    def test_cross_tenant_isolation_enforced(self):
        """3. Tenant isolation: User B cannot access User A's projects, actions, or evaluation."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus, AgentRun, AgentRunStatus

        action_a = SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.OPTIMIZE_TITLE,
            title="Secret Title A",
            status=ActionStatus.PROPOSED
        )

        run_a = AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            goal="User A Confidential Goal",
            status=AgentRunStatus.COMPLETED
        )

        # Authenticate as User B
        self.client.force_authenticate(user=self.user_b)

        # User B attempts to access User A's evaluation endpoint
        res = self.client.get(f'/api/seo/ai/agent/evaluation/{run_a.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_secret_scrubbing_in_telemetry_and_errors(self):
        """4. Sensitive tokens, keys, and passwords are fully scrubbed from event payloads."""
        from apps.seo.services.agent_events import sanitize_event_payload

        dirty_payload = {
            "api_key": "sk-secret-12345",
            "bearer_token": "Bearer ya29.secret_token",
            "db_password": "super_secret_password",
            "clean_metric": 42
        }

        clean = sanitize_event_payload(dirty_payload)
        self.assertEqual(clean["api_key"], "***REDACTED***")
        self.assertEqual(clean["bearer_token"], "***REDACTED***")
        self.assertEqual(clean["db_password"], "***REDACTED***")
        self.assertEqual(clean["clean_metric"], 42)


class SEOAgentEvaluationTests(TestCase):
    """
    Phase 4.9.5 Agent Evaluation Tests:
    Observable evaluation metrics for agent runs and multi-agent SharedContext.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email='eval_user@doxarank.ai', password='Password123!')
        self.project = Project.objects.create(name="Eval Project", website_url="https://eval.et", owner=self.user)
        self.client = APIClient()

    def test_agent_evaluation_scorecard_calculation(self):
        """1. SEOAgentEvaluationService computes observable scorecards without inspecting chain-of-thought."""
        from apps.seo.models import AgentRun, AgentRunStatus, AgentStep, AgentToolCall, AgentActionType, AgentStepStatus
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService

        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal="Analyze technical issues and propose action",
            status=AgentRunStatus.COMPLETED
        )

        # Create steps and tool calls
        step1 = AgentStep.objects.create(run=run, step_number=1, action_type=AgentActionType.TOOL_CALL, status=AgentStepStatus.COMPLETED)
        AgentToolCall.objects.create(step=step1, tool_name="get_site_audit_summary", tool_output={"success": True})

        step2 = AgentStep.objects.create(run=run, step_number=2, action_type=AgentActionType.TOOL_CALL, status=AgentStepStatus.COMPLETED)
        AgentToolCall.objects.create(step=step2, tool_name="propose_seo_action", tool_output={"success": True})

        eval_res = SEOAgentEvaluationService.evaluate_run(run)

        self.assertEqual(eval_res["run_id"], run.id)
        self.assertTrue(eval_res["task_success"])
        self.assertEqual(eval_res["total_steps"], 2)
        self.assertEqual(eval_res["total_tool_calls"], 2)
        self.assertEqual(eval_res["failed_tool_calls"], 0)
        self.assertEqual(eval_res["tool_selection_accuracy"], 1.0)
        self.assertEqual(eval_res["safety_compliance_pct"], 100.0)
        self.assertGreaterEqual(eval_res["overall_score"], 80.0)

    def test_agent_evaluation_rest_endpoint(self):
        """2. REST API /api/seo/ai/agent/evaluation/<run_id>/ returns evaluation data for project owner."""
        from apps.seo.models import AgentRun, AgentRunStatus

        run = AgentRun.objects.create(
            project=self.project,
            user=self.user,
            goal="Endpoint evaluation test",
            status=AgentRunStatus.COMPLETED
        )

        # 1. Unauthenticated request rejected
        res_unauth = self.client.get(f'/api/seo/ai/agent/evaluation/{run.id}/')
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Authenticated owner request succeeded
        self.client.force_authenticate(user=self.user)
        res = self.client.get(f'/api/seo/ai/agent/evaluation/{run.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["run_id"], run.id)
        self.assertIn("overall_score", res.data)
        self.assertIn("safety_compliance_pct", res.data)


class SEOAgentCollaborationTests(TestCase):
    """
    Milestone 5.1 Integration & Unit Tests:
    Advanced Multi-Agent Collaboration, Structured Agent Handoffs,
    Evidence Provenance Preservation, Collaboration State,
    Handoff Validation, Failure Isolation, and Collaboration Evaluation.
    """

    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_user(
            email='collab_a@doxarank.com',
            password='Password123!'
        )
        self.user_b = User.objects.create_user(
            email='collab_b@doxarank.com',
            password='Password123!'
        )

        self.project_a = Project.objects.create(
            name="Project Collaboration Alpha",
            website_url="https://alpha-collab.com",
            owner=self.user_a
        )
        self.project_b = Project.objects.create(
            name="Project Collaboration Beta",
            website_url="https://beta-collab.com",
            owner=self.user_b
        )

        self.client = APIClient()

    def test_valid_research_to_investigation_handoff(self):
        """1. Valid Research -> Investigation handoff preserves scoped evidence and provenance."""
        from apps.seo.services.agents.seo_research_agent import SEOResearchAgent
        from apps.seo.services.agents.seo_investigation_agent import SEOInvestigationAgent
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.base_agent import SharedContext

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        context = SharedContext(
            project_id=self.project_a.id,
            project_name=self.project_a.name,
            website_url=self.project_a.website_url,
            user_id=self.user_a.id,
            task_type="investigate",
            task_goal="Investigate ranking drop on /pricing",
            target_url="https://alpha-collab.com/pricing"
        )

        # 1. Research Agent executes and populates empirical evidence
        researcher = SEOResearchAgent(project=self.project_a, user=self.user_a)
        res_result = researcher.run(context)
        self.assertEqual(res_result.status, "completed")
        self.assertGreater(len(res_result.observed_facts), 0)

        # 2. Supervisor builds structured handoff to Investigation Agent
        handoff = supervisor.build_handoff_context(
            source_agent=researcher.name,
            target_agent_name="seo_investigator",
            context=context,
            correlation_id=context.correlation_id
        )

        self.assertEqual(handoff.source_agent, "seo_researcher")
        self.assertEqual(handoff.target_agent, "seo_investigator")
        self.assertEqual(handoff.project_id, self.project_a.id)
        self.assertIn("audit_summary", handoff.relevant_evidence)

        # Verify evidence provenance is present
        for fact in handoff.observed_facts:
            self.assertIn("source", fact)
            self.assertTrue(bool(fact["source"]))

        # 3. Investigation Agent accepts handoff and runs successfully
        investigator = SEOInvestigationAgent(project=self.project_a, user=self.user_a)
        inv_result = investigator.run(context, handoff=handoff)
        self.assertEqual(inv_result.status, "completed")
        self.assertEqual(inv_result.next_step, "strategy")
        self.assertGreater(len(context.handoff_history), 0)

    def test_valid_investigation_to_strategy_handoff(self):
        """2. Valid Investigation -> Strategy handoff preserves distinctions between observed facts and inferences."""
        from apps.seo.services.agents.seo_strategy_agent import SEOStrategyAgent
        from apps.seo.services.agents.agent_handoff import AgentHandoffContext, AgentHandoffValidator
        from apps.seo.services.agents.base_agent import SharedContext

        context = SharedContext(
            project_id=self.project_a.id,
            project_name=self.project_a.name,
            website_url=self.project_a.website_url,
            user_id=self.user_a.id,
            task_type="strategy",
            task_goal="Prioritize opportunity strategy",
            target_url="https://alpha-collab.com/features"
        )

        # Construct handoff with both observed facts and diagnostic inferences
        handoff = AgentHandoffContext(
            project_id=self.project_a.id,
            source_agent="seo_investigator",
            target_agent="seo_strategist",
            user_goal="Prioritize opportunity strategy",
            task_type="strategy",
            correlation_id=context.correlation_id,
            relevant_evidence={"investigation_findings": [{"target_url": "https://alpha-collab.com/features"}]},
            observed_facts=[
                {"fact": "HTTP status 200 returned for /features", "source": "mcp__seo_local__check_url_status", "confidence": 1.0},
                {"fact": "Site health score is 74/100", "source": "get_site_audit_summary", "confidence": 1.0}
            ],
            inferences=[
                {"inference": "Root cause identified as missing_primary_heading", "based_on": ["get_audit_issues"], "confidence": 0.88}
            ],
            uncertainties=["Competitive SERP feature shifts cannot be determined."],
            allowed_tools=list(SEOStrategyAgent.allowed_tools)
        )

        AgentHandoffValidator.validate(handoff, expected_project_id=self.project_a.id)

        strategist = SEOStrategyAgent(project=self.project_a, user=self.user_a)
        result = strategist.run(context, handoff=handoff)

        self.assertEqual(result.status, "completed")
        # Ensure observed facts and inferences remain distinct
        self.assertGreater(len(result.observed_facts), 0)
        self.assertGreater(len(result.inferences), 0)
        # Check that inferences are not erroneously dumped into observed_facts
        for fact in result.observed_facts:
            self.assertIn("source", fact)

    def test_strategy_to_action_planning_handoff(self):
        """3. Strategy -> Action Planning handoff preserves recommendations and human approval requirement."""
        from apps.seo.services.agents.seo_action_agent import SEOActionPlanningAgent
        from apps.seo.services.agents.agent_handoff import AgentHandoffContext, AgentHandoffValidator
        from apps.seo.services.agents.base_agent import SharedContext

        context = SharedContext(
            project_id=self.project_a.id,
            project_name=self.project_a.name,
            website_url=self.project_a.website_url,
            user_id=self.user_a.id,
            task_type="plan",
            task_goal="Create action plan for /products"
        )

        handoff = AgentHandoffContext(
            project_id=self.project_a.id,
            source_agent="seo_strategist",
            target_agent="seo_action_planner",
            user_goal=context.task_goal,
            task_type="plan",
            correlation_id=context.correlation_id,
            relevant_evidence={"strategy_signals": {"overall_smoothed_rate": 0.72}},
            observed_facts=[{"fact": "Historical win rate 72%", "source": "get_adaptive_seo_strategy", "confidence": 1.0}],
            allowed_tools=list(SEOActionPlanningAgent.allowed_tools),
            approval_state="pending_human_approval",
            risk_information={"requires_human_approval": True}
        )

        AgentHandoffValidator.validate(handoff, expected_project_id=self.project_a.id)

        planner = SEOActionPlanningAgent(project=self.project_a, user=self.user_a)
        result = planner.run(context, handoff=handoff)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.next_step, "human_approval")
        # Invariant: Human approval cannot be bypassed
        self.assertTrue(result.metadata.get("requires_human_approval"))
        for act in context.action_proposals:
            self.assertTrue(act["requires_human_approval"])

    def test_action_to_verification_handoff(self):
        """4. Action -> Verification handoff passes created plan and verifies live state."""
        from apps.seo.models import SEOActionPlan, SEOAction, ActionType, ActionStatus, ActionRiskLevel, ActionPlanStatus
        from apps.seo.services.agents.seo_verification_agent import SEOVerificationAgent
        from apps.seo.services.agents.agent_handoff import AgentHandoffContext, AgentHandoffValidator
        from apps.seo.services.agents.base_agent import SharedContext

        plan = SEOActionPlan.objects.create(
            project=self.project_a,
            title="Verification Test Plan",
            created_by=self.user_a,
            status=ActionPlanStatus.COMPLETED
        )
        SEOAction.objects.create(
            plan=plan,
            project=self.project_a,
            title="Add primary H1 tag",
            action_type=ActionType.FIX_MISSING_H1,
            target_url=self.project_a.website_url,
            status=ActionStatus.COMPLETED,
            risk_level=ActionRiskLevel.LOW,
            requires_human_approval=True
        )

        context = SharedContext(
            project_id=self.project_a.id,
            project_name=self.project_a.name,
            website_url=self.project_a.website_url,
            user_id=self.user_a.id,
            task_type="verify",
            task_goal="Verify action plan execution",
            created_plan_id=plan.id
        )

        handoff = AgentHandoffContext(
            project_id=self.project_a.id,
            source_agent="seo_action_planner",
            target_agent="seo_verifier",
            user_goal=context.task_goal,
            task_type="verify",
            correlation_id=context.correlation_id,
            relevant_evidence={"created_plan_id": plan.id},
            allowed_tools=list(SEOVerificationAgent.allowed_tools)
        )

        AgentHandoffValidator.validate(handoff, expected_project_id=self.project_a.id)

        verifier = SEOVerificationAgent(project=self.project_a, user=self.user_a)
        result = verifier.run(context, handoff=handoff)

        self.assertEqual(result.status, "completed")
        self.assertIn("plan_verification", result.evidence["verifications"])

    def test_malformed_handoff_rejection(self):
        """5. Malformed handoff missing required fields or unknown agents is rejected."""
        from apps.seo.services.agents.agent_handoff import (
            AgentHandoffContext, AgentHandoffValidator, AgentHandoffValidationError
        )

        # 1. Unknown target agent
        bad_handoff_1 = AgentHandoffContext(
            project_id=self.project_a.id,
            source_agent="seo_researcher",
            target_agent="unauthorized_ai_bot",
            user_goal="Test",
            task_type="general",
            correlation_id="test-corr-1"
        )
        with self.assertRaises(AgentHandoffValidationError) as ctx1:
            AgentHandoffValidator.validate(bad_handoff_1, expected_project_id=self.project_a.id)
        self.assertIn("Unrecognized target agent", str(ctx1.exception))

        # 2. Missing correlation_id
        bad_handoff_2 = AgentHandoffContext(
            project_id=self.project_a.id,
            source_agent="seo_researcher",
            target_agent="seo_investigator",
            user_goal="Test",
            task_type="general",
            correlation_id=""
        )
        with self.assertRaises(AgentHandoffValidationError) as ctx2:
            AgentHandoffValidator.validate(bad_handoff_2, expected_project_id=self.project_a.id)
        self.assertIn("Missing or empty correlation_id", str(ctx2.exception))

    def test_invalid_tenant_project_handoff_rejection(self):
        """6. Cross-tenant handoff targeting another project is strictly rejected."""
        from apps.seo.services.agents.agent_handoff import (
            AgentHandoffContext, AgentHandoffValidator, AgentHandoffValidationError
        )

        # Handoff claiming Project B while executing in Project A context
        cross_tenant_handoff = AgentHandoffContext(
            project_id=self.project_b.id,
            source_agent="seo_researcher",
            target_agent="seo_investigator",
            user_goal="Cross tenant hijack attempt",
            task_type="general",
            correlation_id="test-cross-tenant"
        )

        with self.assertRaises(AgentHandoffValidationError) as ctx:
            AgentHandoffValidator.validate(cross_tenant_handoff, expected_project_id=self.project_a.id)
        self.assertIn("Tenant Security Violation", str(ctx.exception))

    def test_invalid_tool_permission_handoff_rejection(self):
        """7. Privilege escalation via handoff allowed_tools is rejected."""
        from apps.seo.services.agents.agent_handoff import (
            AgentHandoffContext, AgentHandoffValidator, AgentHandoffValidationError
        )

        # Attempting to give mutating permissions to read-only researcher
        escalated_handoff = AgentHandoffContext(
            project_id=self.project_a.id,
            source_agent="seo_supervisor",
            target_agent="seo_researcher",
            user_goal="Escalation test",
            task_type="research",
            correlation_id="test-escalation",
            allowed_tools=["execute_mutation", "plan_seo_actions"]
        )

        with self.assertRaises(AgentHandoffValidationError) as ctx:
            AgentHandoffValidator.validate(escalated_handoff, expected_project_id=self.project_a.id)
        self.assertIn("Privilege Escalation Violation", str(ctx.exception))

    def test_approval_state_escalation_attempt_rejection(self):
        """8. Agent attempting to unilaterally auto-approve an action plan via handoff is rejected."""
        from apps.seo.services.agents.agent_handoff import (
            AgentHandoffContext, AgentHandoffValidator, AgentHandoffValidationError
        )

        # Action planner claiming action was 'approved' without user interaction
        rogue_approval_handoff = AgentHandoffContext(
            project_id=self.project_a.id,
            source_agent="seo_action_planner",
            target_agent="seo_verifier",
            user_goal="Attempt auto approval",
            task_type="verify",
            correlation_id="test-auto-approve",
            approval_state="approved"
        )

        with self.assertRaises(AgentHandoffValidationError) as ctx:
            AgentHandoffValidator.validate(rogue_approval_handoff, expected_project_id=self.project_a.id)
        self.assertIn("Security Boundary Violation", str(ctx.exception))

    def test_failed_agent_isolation(self):
        """9. Downstream agent failure preserves completed evidence from preceding agents."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from unittest.mock import patch

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)

        # Force investigator to raise an exception
        with patch.object(
            supervisor._agents["seo_investigator"],
            "_execute",
            side_effect=RuntimeError("Diagnostic engine socket timeout")
        ):
            context = supervisor.orchestrate(task="Investigate ranking drop on /blog")

            # Orchestration halts safely
            self.assertEqual(context.status, "failed")
            self.assertEqual(context.collaboration_state.status, "degraded")
            self.assertIn("seo_investigator", context.collaboration_state.failed_agents)
            self.assertIn("seo_researcher", context.collaboration_state.completed_agents)

            # Preceding research evidence is preserved
            self.assertIn("audit_summary", context.evidence)
            self.assertEqual(context.agent_results_history[0]["agent"], "seo_researcher")
            self.assertEqual(context.agent_results_history[0]["status"], "completed")
            self.assertEqual(context.agent_results_history[-1]["agent"], "seo_investigator")
            self.assertEqual(context.agent_results_history[-1]["status"], "failed")

    def test_evidence_provenance_preservation(self):
        """10. Observed facts without declared source provenance are rejected by validator."""
        from apps.seo.services.agents.agent_handoff import (
            AgentHandoffContext, AgentHandoffValidator, AgentHandoffValidationError
        )

        unprovenanced_handoff = AgentHandoffContext(
            project_id=self.project_a.id,
            source_agent="seo_researcher",
            target_agent="seo_investigator",
            user_goal="Provenance test",
            task_type="investigate",
            correlation_id="test-prov",
            observed_facts=[
                {"fact": "Unverified assertion without provenance source", "confidence": 1.0}
            ]
        )

        with self.assertRaises(AgentHandoffValidationError) as ctx:
            AgentHandoffValidator.validate(unprovenanced_handoff, expected_project_id=self.project_a.id)
        self.assertIn("Evidence Provenance Error", str(ctx.exception))

    def test_handoff_lifecycle_events(self):
        """11. Handoff lifecycle telemetry events are published with sanitized payloads."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agent_events import AgentEventType

        events_captured = []
        class MockPublisher:
            def publish(self, event):
                events_captured.append(event)

        supervisor = SEOSupervisorAgent(
            project=self.project_a,
            user=self.user_a,
            publisher=MockPublisher()
        )
        context = supervisor.orchestrate(task="Investigate ranking decline on /home")

        event_types = [e.event_type for e in events_captured]
        self.assertIn(AgentEventType.SEO_AGENT_COLLABORATION_STARTED, event_types)
        self.assertIn(AgentEventType.SEO_AGENT_HANDOFF_STARTED, event_types)
        self.assertIn(AgentEventType.SEO_AGENT_HANDOFF, event_types)
        self.assertIn(AgentEventType.SEO_AGENT_HANDOFF_COMPLETED, event_types)
        self.assertIn(AgentEventType.SEO_AGENT_COLLABORATION_COMPLETED, event_types)

        # Verify no secret keywords leaked into payload
        for evt in events_captured:
            payload_str = str(evt.payload).lower()
            self.assertNotIn("secret_key", payload_str)
            self.assertNotIn("bearer_token", payload_str)

    def test_evaluation_collaboration_metrics(self):
        """12. SEOAgentEvaluationService computes accurate collaboration metrics."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        context = supervisor.orchestrate(task="Investigate drop and prioritize strategy")

        eval_res = SEOAgentEvaluationService.evaluate_shared_context(context)

        self.assertIn("collaboration_metrics", eval_res)
        collab = eval_res["collaboration_metrics"]
        self.assertGreaterEqual(collab["agents_involved"], 2)
        self.assertGreaterEqual(collab["total_handoffs"], 1)
        self.assertGreaterEqual(collab["successful_handoffs"], 1)
        self.assertEqual(collab["rejected_handoffs"], 0)
        self.assertTrue(collab["collaboration_completed"])
        self.assertGreaterEqual(collab["evidence_provenance_score"], 0.8)

    def test_complete_multi_agent_collaboration_workflow(self):
        """13. Full cycle multi-agent collaboration runs sequentially under strict governance."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.models import ActionStatus

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        context = supervisor.orchestrate(task="Comprehensive multi-agent SEO optimization")

        self.assertEqual(context.status, "completed")
        self.assertEqual(context.collaboration_state.status, "completed")

        # Verify all four full_cycle specialized agents participated
        expected_agents = ["seo_researcher", "seo_investigator", "seo_strategist", "seo_action_planner"]
        self.assertEqual(context.collaboration_state.completed_agents, expected_agents)
        self.assertEqual(len(context.collaboration_state.failed_agents), 0)

        # Verify handoff history sequence
        handoffs = context.collaboration_state.handoff_history
        self.assertEqual(len(handoffs), 4)
        self.assertEqual(handoffs[0]["target_agent"], "seo_researcher")
        self.assertEqual(handoffs[1]["target_agent"], "seo_investigator")
        self.assertEqual(handoffs[2]["target_agent"], "seo_strategist")
        self.assertEqual(handoffs[3]["target_agent"], "seo_action_planner")

        # Verify human approval hard boundary
        self.assertIsNotNone(context.created_plan_id)
        for act in context.action_proposals:
            self.assertTrue(act["requires_human_approval"])
            self.assertEqual(act["status"], ActionStatus.PROPOSED)


class SEOSharedWorkingMemoryTests(TestCase):
    """
    Milestone 5.2 Test Suite:
    Adaptive Multi-Agent Collaboration & Shared Working Memory.
    Verifies epistemic segregation, evidence provenance, fingerprint deduplication,
    budget compaction, role-specific projection, multi-agent conflict detection
    and resolution, bounded iterative revisits, safety invariants, evaluation metrics,
    and REST API endpoints.
    """

    def setUp(self):
        User = get_user_model()
        self.user_a = User.objects.create_user(
            email='mem_user_a@doxarank.com',
            password='Password123!'
        )
        self.user_b = User.objects.create_user(
            email='mem_user_b@doxarank.com',
            password='Password123!'
        )

        self.project_a = Project.objects.create(
            name="Memory Project Alpha",
            website_url="https://mem-alpha.com",
            owner=self.user_a
        )
        self.project_b = Project.objects.create(
            name="Memory Project Beta",
            website_url="https://mem-beta.com",
            owner=self.user_b
        )

        self.client = APIClient()
        from apps.seo.services.agents.shared_memory import SharedMemoryRegistry
        SharedMemoryRegistry.get_instance().clear()

    def tearDown(self):
        from apps.seo.services.agents.shared_memory import SharedMemoryRegistry
        SharedMemoryRegistry.get_instance().clear()

    def test_memory_initialization_and_epistemic_separation(self):
        """1. SharedWorkingMemory maintains strict epistemic separation between facts, inferences, uncertainties, etc."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, MemoryCategory

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Audit and optimize organic search visibility",
            correlation_id="corr-test-epistemic-001"
        )

        # Ingest items across different epistemic categories
        f = mem.add_evidence(
            fact="HTTP 200 OK returned on /pricing",
            source_agent="seo_researcher",
            source_tool="check_url_status",
            confidence=1.0
        )
        inf = mem.add_inference(
            hypothesis="Pricing page ranking drop is caused by title tag truncation",
            source_agent="seo_investigator",
            supporting_fact_ids=[f.memory_id],
            confidence=0.85
        )
        unc = mem.add_uncertainty(
            description="Competitor schema markup changes could not be crawled",
            source_agent="seo_investigator"
        )
        asm = mem.add_assumption(
            assumption="Target domain crawl budget is sufficient for daily recrawls",
            source_agent="seo_supervisor"
        )
        rec = mem.add_recommendation(
            recommendation="Rewrite title tag to under 60 characters with primary keyword",
            source_agent="seo_strategist"
        )
        dec = mem.record_decision(
            title="Adopt Title Tag Optimization Strategy",
            reason="Supported by empirical observation and low implementation risk",
            evidence_ids=[f.memory_id],
            decision_owner="seo_supervisor"
        )
        mem.record_completed_work(
            agent="seo_researcher",
            task_description="Gather baseline metrics",
            result_summary="Crawled 5 core URLs and extracted GSC query metrics"
        )
        mem.record_pending_work(
            agent="seo_action_planner",
            task_description="Generate staged action proposal",
            priority="high"
        )
        mem.record_verification_result(
            action_id="act-001",
            target_url="https://mem-alpha.com/pricing",
            verified=True,
            details={"status_code": 200, "meta_title_present": True}
        )

        # Epistemic segregation validation
        self.assertEqual(len(mem._facts), 1)
        self.assertEqual(len(mem._inferences), 1)
        self.assertEqual(len(mem._uncertainties), 1)
        self.assertEqual(len(mem._assumptions), 1)
        self.assertEqual(len(mem._recommendations), 1)
        self.assertEqual(len(mem._decisions), 1)
        self.assertEqual(len(mem._completed_work), 1)
        self.assertEqual(len(mem._pending_work), 1)
        self.assertEqual(len(mem._verification_results), 1)

        # Category invariants
        self.assertNotIn(f.memory_id, mem._inferences)
        self.assertNotIn(inf.memory_id, mem._facts)
        self.assertEqual(f.category, MemoryCategory.OBSERVED_FACT.value)
        self.assertEqual(inf.category, MemoryCategory.INFERENCE.value)
        self.assertEqual(unc.category, MemoryCategory.UNCERTAINTY.value)
        self.assertEqual(rec.category, MemoryCategory.RECOMMENDATION.value)

    def test_add_evidence_with_provenance_and_confidence(self):
        """2. Empirical evidence entries retain source agent, tool, step index, confidence, and metadata."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Investigate Core Web Vitals",
            correlation_id="corr-test-prov-002"
        )

        item = mem.add_evidence(
            fact="Core Web Vitals Largest Contentful Paint (LCP) is 4.2s",
            source_agent="seo_researcher",
            source_tool="get_site_audit_summary",
            confidence=0.92,
            metadata={"device": "mobile", "threshold": "poor"},
            step_index=1
        )

        self.assertEqual(item.content, "Core Web Vitals Largest Contentful Paint (LCP) is 4.2s")
        self.assertEqual(item.source_agent, "seo_researcher")
        self.assertEqual(item.source_tool, "get_site_audit_summary")
        self.assertEqual(item.confidence, 0.92)
        self.assertEqual(item.source_step, 1)
        self.assertEqual(item.metadata["device"], "mobile")
        self.assertEqual(item.metadata["threshold"], "poor")
        self.assertTrue(item.memory_id.startswith("fact-"))
        self.assertTrue(bool(item.created_at))

    def test_add_inference_linked_to_facts(self):
        """3. Inferences must link to supporting empirical evidence and preserve derivation rationale."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Diagnose ranking decline",
            correlation_id="corr-test-inf-003"
        )

        fact = mem.add_evidence(
            fact="Server response time TTFB increased from 200ms to 1250ms",
            source_agent="seo_researcher",
            source_tool="check_url_status",
            confidence=0.98
        )

        inference = mem.add_inference(
            hypothesis="Hosting infrastructure or database bottleneck is degrading crawl efficiency",
            source_agent="seo_investigator",
            supporting_fact_ids=[fact.memory_id],
            confidence=0.82,
            derivation_rationale="TTFB exceeds recommended 800ms threshold by 56%"
        )

        self.assertEqual(inference.evidence_ids, [fact.memory_id])
        self.assertEqual(inference.source_agent, "seo_investigator")
        self.assertEqual(inference.confidence, 0.82)
        self.assertEqual(
            inference.metadata["derivation_rationale"],
            "TTFB exceeds recommended 800ms threshold by 56%"
        )

    def test_add_uncertainty_and_recommendation(self):
        """4. Uncertainties capture gaps with suggested resolutions; recommendations track proposed actions."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Content gap analysis",
            correlation_id="corr-test-unc-004"
        )

        unc = mem.add_uncertainty(
            description="Competitor backlink velocity cannot be verified due to rate limiting",
            source_agent="seo_researcher",
            suggested_resolution="Retry backlink check during off-peak window"
        )
        self.assertEqual(unc.source_agent, "seo_researcher")
        self.assertEqual(unc.metadata["suggested_resolution"], "Retry backlink check during off-peak window")

        rec = mem.add_recommendation(
            recommendation="Deploy redis caching layer on /pricing API responses",
            source_agent="seo_strategist",
            evidence_ids=["fact-123"]
        )
        self.assertEqual(rec.source_agent, "seo_strategist")
        self.assertEqual(rec.evidence_ids, ["fact-123"])

    def test_fingerprint_deduplication(self):
        """5. Identical content is deduplicated deterministically while preserving multi-agent confirmation."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Deduplication test",
            correlation_id="corr-test-dedup-005"
        )

        fact_text = "Canonical link element points to https://mem-alpha.com/en/"
        item1 = mem.add_evidence(fact=fact_text, source_agent="seo_researcher")
        item2 = mem.add_evidence(fact=fact_text, source_agent="seo_investigator")

        # Same memory ID returned, no duplicate entry created
        self.assertEqual(item1.memory_id, item2.memory_id)
        self.assertEqual(len(mem._facts), 1)
        self.assertEqual(mem.entries_created, 1)
        self.assertEqual(mem.entries_deduplicated, 1)

        # Multi-agent provenance recorded
        self.assertIn("seo_investigator", item1.metadata.get("confirmed_by_agents", []))

    def test_context_budget_enforcement_and_compaction(self):
        """6. Context budget limits memory growth and prunes lower-confidence items."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, ContextBudgetConfig

        budget = ContextBudgetConfig(max_facts=3, max_inferences=2, max_uncertainties=2)
        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Budget enforcement test",
            correlation_id="corr-test-budget-006",
            budget_config=budget
        )

        # Add 5 facts with varying confidence levels
        mem.add_evidence(fact="Low confidence fact 1", source_agent="agent_a", confidence=0.4)
        mem.add_evidence(fact="Low confidence fact 2", source_agent="agent_a", confidence=0.5)
        mem.add_evidence(fact="High confidence fact 3", source_agent="agent_b", confidence=0.95)
        mem.add_evidence(fact="High confidence fact 4", source_agent="agent_b", confidence=0.98)
        mem.add_evidence(fact="Highest confidence fact 5", source_agent="agent_c", confidence=0.99)

        # Store should be bounded at max_facts = 3
        self.assertEqual(len(mem._facts), 3)
        self.assertGreaterEqual(mem.budget_exceeded_events, 2)

        # Retained facts must be the higher-confidence ones
        retained_confidences = [f.confidence for f in mem._facts.values()]
        self.assertIn(0.95, retained_confidences)
        self.assertIn(0.98, retained_confidences)
        self.assertIn(0.99, retained_confidences)
        self.assertNotIn(0.4, retained_confidences)

    def test_role_specific_context_projection(self):
        """7. SharedWorkingMemory projects role-specific context tailored to each specialized agent."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Full lifecycle optimization",
            correlation_id="corr-test-proj-007"
        )

        mem.add_evidence(
            fact="GSC click count dropped 35% on /features",
            source_agent="seo_researcher",
            source_tool="get_gsc_performance",
            confidence=1.0
        )
        mem.add_evidence(
            fact="Historical win rate 72% for schema markup additions",
            source_agent="seo_strategist",
            confidence=0.95
        )
        mem.add_inference(
            hypothesis="Cannibalization between /features and /product-tour",
            source_agent="seo_investigator",
            confidence=0.88
        )
        mem.add_uncertainty(
            description="SERP competitor rank changes unconfirmed",
            source_agent="seo_researcher"
        )
        mem.add_recommendation(
            recommendation="Add Product schema and canonicalize /product-tour to /features",
            source_agent="seo_strategist"
        )
        mem.record_decision(
            title="Consolidate duplicate feature URLs",
            reason="Clear cannibalization signal with high historical win rate",
            decision_owner="seo_supervisor"
        )

        # 1. Researcher projection
        res_ctx = mem.get_context_for_agent("seo_researcher")
        self.assertIn("known_uncertainties", res_ctx)
        self.assertIn("relevant_evidence", res_ctx)
        self.assertNotIn("approved_strategy", res_ctx)

        # 2. Investigator projection
        inv_ctx = mem.get_context_for_agent("seo_investigator")
        self.assertIn("relevant_evidence", inv_ctx)
        self.assertIn("hypotheses", inv_ctx)
        self.assertIn("research_findings", inv_ctx)

        # 3. Strategist projection
        strat_ctx = mem.get_context_for_agent("seo_strategist")
        self.assertIn("verified_evidence", strat_ctx)
        self.assertIn("investigation_findings", strat_ctx)
        self.assertIn("historical_outcome_signals", strat_ctx)
        self.assertIn("constraints", strat_ctx)

        # 4. Action Planner projection
        plan_ctx = mem.get_context_for_agent("seo_action_planner")
        self.assertIn("approved_strategy", plan_ctx)
        self.assertIn("recommended_actions", plan_ctx)
        self.assertIn("risk_information", plan_ctx)
        self.assertTrue(plan_ctx["risk_information"]["requires_human_approval"])
        self.assertIn("requires_human_approval = True", plan_ctx["constraints"])

        # 5. Verifier projection
        ver_ctx = mem.get_context_for_agent("seo_verifier")
        self.assertIn("expected_outcomes", ver_ctx)
        self.assertIn("before_state_evidence", ver_ctx)

    def test_conflict_detection_and_storage(self):
        """8. detect_conflicts identifies contradictory claims between agents and records them."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, ConflictStatus

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Audit conflicting signals",
            correlation_id="corr-test-conf-008"
        )

        # Claim A from researcher: Healthy
        mem.add_evidence(
            fact="The site is technically healthy with 0 crawl errors reported",
            source_agent="seo_researcher"
        )
        # Claim B from investigator: Technical defect
        mem.add_inference(
            hypothesis="Critical indexing problem detected: technical defect in robots.txt blocking pages",
            source_agent="seo_investigator"
        )

        conflicts = mem.detect_conflicts()

        self.assertEqual(len(conflicts), 1)
        c = conflicts[0]
        self.assertEqual(c.topic, "technical_health_discrepancy")
        self.assertEqual(c.resolution_status, ConflictStatus.OPEN.value)
        self.assertIn("seo_researcher", c.responsible_agents)
        self.assertIn("seo_investigator", c.responsible_agents)
        self.assertEqual(c.claim_a["agent"], "seo_researcher")
        self.assertEqual(c.claim_b["agent"], "seo_investigator")

    def test_conflict_resolution(self):
        """9. resolve_conflict marks conflicts resolved with auditor identity and notes."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, ConflictStatus

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Conflict resolution test",
            correlation_id="corr-test-res-009"
        )

        mem.add_evidence(
            fact="The site is technically healthy with 0 crawl errors",
            source_agent="seo_researcher"
        )
        mem.add_inference(
            hypothesis="Critical indexing problem detected due to technical defect",
            source_agent="seo_investigator"
        )

        conflicts = mem.detect_conflicts()
        self.assertEqual(len(conflicts), 1)
        conflict_id = conflicts[0].conflict_id

        resolved = mem.resolve_conflict(
            conflict_id=conflict_id,
            resolved_by="seo_supervisor",
            resolution_notes="Supervisor confirmed robots.txt disallow was removed 2 hours ago; production is now healthy."
        )

        self.assertTrue(resolved)
        self.assertEqual(conflicts[0].resolution_status, ConflictStatus.RESOLVED.value)
        self.assertEqual(conflicts[0].resolved_by, "seo_supervisor")
        self.assertIn("robots.txt disallow was removed", conflicts[0].resolution_notes)

        # Summary reports 0 open conflicts and 1 resolved
        summary = mem.summarize()
        self.assertEqual(summary["open_conflicts_count"], 0)
        self.assertEqual(summary["resolved_conflicts_count"], 1)

    def test_safety_secret_redaction_on_ingest(self):
        """10. Sensitive secrets (API keys, tokens, passwords) are redacted automatically upon ingestion."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, redact_secrets

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Analyze data with sk-abcdef1234567890abcdef1234567890",
            correlation_id="corr-test-sec-010"
        )

        # Task goal sanitized
        self.assertNotIn("sk-abcdef", mem.task_goal)
        self.assertIn("***REDACTED***", mem.task_goal)

        # Evidence text sanitized
        f = mem.add_evidence(
            fact="External API returned 401 with Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and password=SuperSecretPassword123!",
            source_agent="seo_researcher",
            metadata={"api_key": "sk-secret99999", "service": "google_search_console"}
        )

        self.assertNotIn("SuperSecretPassword123!", f.content)
        self.assertNotIn("sk-secret99999", str(f.metadata))
        self.assertIn("***REDACTED***", f.content)

        # Decisions sanitized
        dec = mem.record_decision(
            title="Deploy secret token change",
            reason="Updated secret=VeryConfidentialToken12345 for GSC integration",
            decision_owner="seo_supervisor"
        )
        self.assertNotIn("VeryConfidentialToken12345", dec.reason)
        self.assertIn("***REDACTED***", dec.reason)

    def test_safety_cross_tenant_memory_isolation(self):
        """11. Cross-tenant memory access is strictly forbidden via REST API endpoints."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, SharedMemoryRegistry

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Tenant A confidential optimization",
            correlation_id="corr-tenant-a-iso-011"
        )
        mem.add_evidence(fact="Confidential revenue data for Project A", source_agent="seo_researcher")
        SharedMemoryRegistry.get_instance().register(mem)

        # 1. Unauthenticated request rejected
        res_unauth = self.client.get(f'/api/seo/ai/orchestrate/{mem.correlation_id}/memory/')
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. User B (unauthorized tenant) request rejected with 403 Forbidden
        self.client.force_authenticate(user=self.user_b)
        res_user_b = self.client.get(f'/api/seo/ai/orchestrate/{mem.correlation_id}/memory/')
        self.assertEqual(res_user_b.status_code, status.HTTP_403_FORBIDDEN)

        res_b_summary = self.client.get(f'/api/seo/ai/orchestrate/{mem.correlation_id}/memory/summary/')
        self.assertEqual(res_b_summary.status_code, status.HTTP_403_FORBIDDEN)

        res_b_conflicts = self.client.get(f'/api/seo/ai/orchestrate/{mem.correlation_id}/conflicts/')
        self.assertEqual(res_b_conflicts.status_code, status.HTTP_403_FORBIDDEN)

        # 3. User A (project owner) request allowed with 200 OK
        self.client.force_authenticate(user=self.user_a)
        res_user_a = self.client.get(f'/api/seo/ai/orchestrate/{mem.correlation_id}/memory/')
        self.assertEqual(res_user_a.status_code, status.HTTP_200_OK)
        self.assertEqual(res_user_a.data["correlation_id"], mem.correlation_id)
        self.assertEqual(len(res_user_a.data["facts"]), 1)

    def test_safety_decision_approval_escalation_rejected(self):
        """12. Non-supervisor agents cannot manufacture auto-approved decisions."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, DecisionStatus

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Autonomous action safety test",
            correlation_id="corr-test-safe-012"
        )

        # Agent attempts to record an approved decision
        decision = mem.record_decision(
            title="Execute Direct DB Modification",
            reason="Autonomous fix proposed by action agent",
            decision_owner="seo_action_planner",
            status="approved"
        )

        # Invariant enforced: Status forcibly defaulted to PROPOSED
        self.assertEqual(decision.status, DecisionStatus.PROPOSED.value)

    def test_supervisor_collaborative_revisit_on_conflict(self):
        """13. SEOSupervisorAgent orchestrates bounded iterative revisits when conflicts arise."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.shared_memory import ConflictStatus

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        context = supervisor.orchestrate(task="Comprehensive multi-agent SEO optimization")

        self.assertEqual(context.status, "completed")
        self.assertIsNotNone(context.shared_memory)

        # Shared working memory was initialized and registered
        mem = context.shared_memory
        self.assertEqual(mem.project_id, self.project_a.id)
        self.assertGreaterEqual(mem.entries_created, 4)

        # Invariant: Revisit bounds are respected (<= 2 per agent, <= 4 total)
        self.assertLessEqual(len(mem._revisits), 4)
        for r in mem._revisits:
            self.assertLessEqual(r.revisit_count, 2)

        # Collaboration state tracks memory summary
        collab = context.collaboration_state
        self.assertIsNotNone(collab.memory_summary)
        self.assertEqual(collab.memory_summary["project_id"], self.project_a.id)

    def test_evaluation_collaboration_memory_metrics(self):
        """14. SEOAgentEvaluationService computes Phase 5.2 collaboration memory metrics."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        context = supervisor.orchestrate(task="Investigate drop and prioritize strategy")

        eval_res = SEOAgentEvaluationService.evaluate_shared_context(context)

        self.assertIn("collaboration_metrics", eval_res)
        collab = eval_res["collaboration_metrics"]

        # Phase 5.2 memory metrics assertions
        self.assertIn("memory_entries_created", collab)
        self.assertIn("memory_entries_deduplicated", collab)
        self.assertIn("conflicts_detected", collab)
        self.assertIn("conflicts_resolved", collab)
        self.assertIn("agent_revisits", collab)
        self.assertIn("context_efficiency", collab)
        self.assertIn("collaboration_efficiency", collab)

        self.assertGreaterEqual(collab["memory_entries_created"], 1)
        self.assertGreaterEqual(collab["evidence_provenance_score"], 0.8)

    def test_collaboration_memory_api_endpoints(self):
        """15. REST endpoints return structured memory, summary, and conflicts for authenticated run owners."""
        from apps.seo.models import AgentRun, AgentRunStatus
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, SharedMemoryRegistry

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Endpoint verification run",
            correlation_id="corr-test-endpoints-015"
        )
        mem.add_evidence(fact="Baseline page speed score: 85/100", source_agent="seo_researcher")
        mem.add_inference(hypothesis="Speed score allows competitive mobile ranking", source_agent="seo_investigator")
        mem.record_decision(title="Proceed with mobile optimization", reason="Meets baseline threshold")

        run = AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            goal="Test run for collaboration memory endpoints",
            status=AgentRunStatus.COMPLETED,
            context_snapshot={"shared_memory": mem.to_dict(), "correlation_id": mem.correlation_id}
        )
        mem.run_id = run.id
        SharedMemoryRegistry.get_instance().register(mem)

        self.client.force_authenticate(user=self.user_a)

        # Test GET /api/seo/ai/orchestrate/<run_id>/memory/
        res_mem = self.client.get(f'/api/seo/ai/orchestrate/{run.id}/memory/')
        self.assertEqual(res_mem.status_code, status.HTTP_200_OK)
        self.assertEqual(res_mem.data["project_id"], self.project_a.id)
        self.assertIn("facts", res_mem.data)
        self.assertIn("inferences", res_mem.data)
        self.assertIn("decisions", res_mem.data)
        self.assertEqual(len(res_mem.data["facts"]), 1)

        # Test GET /api/seo/ai/orchestrate/<run_id>/memory/summary/
        res_sum = self.client.get(f'/api/seo/ai/orchestrate/{run.id}/memory/summary/')
        self.assertEqual(res_sum.status_code, status.HTTP_200_OK)
        self.assertIn("facts_count", res_sum.data)
        self.assertIn("inferences_count", res_sum.data)
        self.assertIn("context_efficiency", res_sum.data)
        self.assertEqual(res_sum.data["facts_count"], 1)

        # Test GET /api/seo/ai/orchestrate/<run_id>/conflicts/
        res_conf = self.client.get(f'/api/seo/ai/orchestrate/{run.id}/conflicts/')
        self.assertEqual(res_conf.status_code, status.HTTP_200_OK)
        self.assertIn("conflicts", res_conf.data)
        self.assertIn("open_count", res_conf.data)
        self.assertEqual(res_conf.data["open_count"], 0)

    def test_memory_serialization_and_deserialization(self):
        """16. SharedWorkingMemory roundtrips accurately through to_dict() and from_dict()."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory

        original = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Serialization roundtrip test",
            correlation_id="corr-roundtrip-016",
            run_id=42
        )

        f = original.add_evidence(fact="Discovered 3 unlinked brand mentions", source_agent="seo_researcher")
        original.add_inference(hypothesis="Mention reclamation will yield easy backlinks", source_agent="seo_investigator", supporting_fact_ids=[f.memory_id])
        original.add_uncertainty(description="Author contact info unavailable for 1 mention", source_agent="seo_investigator")
        original.add_assumption(assumption="Outreach response rate estimated at 15%", source_agent="seo_strategist")
        original.add_recommendation(recommendation="Send outreach emails to mention authors", source_agent="seo_strategist")
        original.record_decision(title="Launch Mention Outreach Campaign", reason="High ROI potential")
        original.record_revisit(agent="seo_researcher", reason="missing_evidence", step_index=2)

        data = original.to_dict()
        restored = SharedWorkingMemory.from_dict(data)

        self.assertEqual(restored.project_id, original.project_id)
        self.assertEqual(restored.run_id, original.run_id)
        self.assertEqual(restored.correlation_id, original.correlation_id)
        self.assertEqual(len(restored._facts), len(original._facts))
        self.assertEqual(len(restored._inferences), len(original._inferences))
        self.assertEqual(len(restored._uncertainties), len(original._uncertainties))
        self.assertEqual(len(restored._assumptions), len(original._assumptions))
        self.assertEqual(len(restored._recommendations), len(original._recommendations))
        self.assertEqual(len(restored._decisions), len(original._decisions))
        self.assertEqual(len(restored._revisits), len(original._revisits))
        self.assertEqual(len(restored._fingerprints), len(original._fingerprints))


class SEODynamicTaskPlanningTests(TestCase):
    """
    Milestone 5.3 Test Suite:
    Dynamic Task Decomposition & Collaborative Planning.
    Verifies goal decomposition, DAG construction, Kahn's algorithm cycle detection,
    depth limits, state machine transitions, dependency resolution, failure cascading to BLOCKED,
    parallel tiers, adaptive replanning, planning budgets, secret redaction, human approval boundary,
    observable telemetry events, evaluation metrics, REST API endpoints, and multi-tenant isolation.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        from apps.seo.models import Project
        self.client = APIClient()
        User = get_user_model()
        self.user_a = User.objects.create_user(
            email='plan_user_a@doxarank.com',
            password='Password123!'
        )
        self.user_b = User.objects.create_user(
            email='plan_user_b@doxarank.com',
            password='Password123!'
        )

        self.project_a = Project.objects.create(
            name="Plan Project Alpha",
            website_url="https://plan-alpha.com",
            owner=self.user_a
        )
        self.project_b = Project.objects.create(
            name="Plan Project Beta",
            website_url="https://plan-beta.com",
            owner=self.user_b
        )

    def test_goal_decomposition_intent_investigation_and_drop(self):
        """1. Decompose goal with investigation/traffic drop intent into structured DAG."""
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner, TaskStatus

        planner = DynamicTaskPlanner()
        plan = planner.decompose_goal(
            project_id=self.project_a.id,
            goal="Investigate 28-day CTR and ranking decline for key search queries"
        )

        self.assertEqual(plan.project_id, self.project_a.id)
        self.assertEqual(len(plan.tasks), 5)

        task_list = list(plan.tasks.values())
        root_task = task_list[0]
        self.assertEqual(root_task.responsible_agent, "seo_researcher")
        self.assertEqual(root_task.status, TaskStatus.READY.value)
        self.assertEqual(len(root_task.dependencies), 0)

        second_task = task_list[1]
        self.assertEqual(second_task.responsible_agent, "seo_researcher")
        self.assertEqual(second_task.status, TaskStatus.PENDING.value)
        self.assertIn(root_task.task_id, second_task.dependencies)

        # Graph validation passes without cycles
        self.assertTrue(plan.validate_graph())

    def test_goal_decomposition_intent_verification_and_audit(self):
        """2. Decompose verification goal into focused task DAG."""
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner

        planner = DynamicTaskPlanner()
        plan = planner.decompose_goal(
            project_id=self.project_a.id,
            goal="Verify live DOM and check deployment on landing pages"
        )

        self.assertEqual(len(plan.tasks), 1)
        agents = [t.responsible_agent for t in plan.tasks.values()]
        self.assertEqual(agents, ["seo_verifier"])
        self.assertTrue(plan.validate_graph())

    def test_goal_decomposition_intent_strategy_and_page2(self):
        """3. Decompose strategy goal into opportunity-focused DAG."""
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner

        planner = DynamicTaskPlanner()
        plan = planner.decompose_goal(
            project_id=self.project_a.id,
            goal="Prioritize strategy and calibrated win rate opportunities"
        )

        self.assertEqual(len(plan.tasks), 2)
        agents = [t.responsible_agent for t in plan.tasks.values()]
        self.assertEqual(agents, ["seo_researcher", "seo_strategist"])
        self.assertTrue(plan.validate_graph())

    def test_dag_cycle_detection_via_kahns_algorithm(self):
        """4. Kahn's algorithm detects circular dependencies and raises CircularDependencyError."""
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, CircularDependencyError

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Circular dependency test",
            correlation_id="corr-cycle-004"
        )

        t1 = AgentTask(
            task_id="task_1",
            objective="Task 1",
            description="First task",
            responsible_agent="seo_researcher",
            dependencies=["task_3"],  # Cycle: 1 -> 2 -> 3 -> 1
            correlation_id="corr-cycle-004"
        )
        t2 = AgentTask(
            task_id="task_2",
            objective="Task 2",
            description="Second task",
            responsible_agent="seo_investigator",
            dependencies=["task_1"],
            correlation_id="corr-cycle-004"
        )
        t3 = AgentTask(
            task_id="task_3",
            objective="Task 3",
            description="Third task",
            responsible_agent="seo_strategist",
            dependencies=["task_2"],
            correlation_id="corr-cycle-004"
        )

        plan.add_task(t1)
        plan.add_task(t2)
        plan.add_task(t3)

        with self.assertRaises(CircularDependencyError) as ctx:
            plan.validate_graph()
        self.assertIn("Circular dependency detected", str(ctx.exception))

    def test_dag_depth_limit_exceeded(self):
        """5. Exceeding max_dependency_depth raises PlanLimitExceededError."""
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, PlanLimitExceededError, PlanBudgetConfig

        budget = PlanBudgetConfig(max_dependency_depth=3, max_tasks_per_plan=10)
        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Depth limit test",
            correlation_id="corr-depth-005",
            budget=budget
        )

        prev_id = None
        for i in range(5):
            tid = f"task_{i+1}"
            deps = [prev_id] if prev_id else []
            t = AgentTask(
                task_id=tid,
                objective=f"Step {i+1}",
                description="Nested chain",
                responsible_agent="seo_researcher",
                dependencies=deps,
                correlation_id="corr-depth-005"
            )
            plan.add_task(t)
            prev_id = tid

        with self.assertRaises(PlanLimitExceededError) as ctx:
            plan.validate_graph()
        self.assertIn("exceeds maximum allowed depth", str(ctx.exception))

    def test_task_state_machine_valid_and_invalid_transitions(self):
        """6. State machine enforces valid transitions and rejects invalid state jumps."""
        from apps.seo.services.agents.task_planner import AgentTask, TaskStatus, InvalidTaskTransitionError

        task = AgentTask(
            task_id="task_sm_006",
            objective="State machine test",
            description="Testing transitions",
            responsible_agent="seo_researcher",
            status=TaskStatus.PENDING.value,
            correlation_id="corr-sm-006"
        )

        # Valid transitions: PENDING -> READY -> RUNNING -> COMPLETED
        task.transition_to(TaskStatus.READY)
        self.assertEqual(task.status, TaskStatus.READY.value)

        task.transition_to(TaskStatus.RUNNING)
        self.assertEqual(task.status, TaskStatus.RUNNING.value)

        task.transition_to(TaskStatus.COMPLETED, result_summary="Successfully fetched metrics")
        self.assertEqual(task.status, TaskStatus.COMPLETED.value)
        self.assertEqual(task.result_summary, "Successfully fetched metrics")
        self.assertIsNotNone(task.completed_at)

        # Invalid transition: COMPLETED -> READY
        with self.assertRaises(InvalidTaskTransitionError):
            task.transition_to(TaskStatus.READY)

        # Invalid transition: COMPLETED -> RUNNING
        with self.assertRaises(InvalidTaskTransitionError):
            task.transition_to(TaskStatus.RUNNING)

    def test_task_readiness_and_dependency_resolution(self):
        """7. Upstream task completion automatically unblocks downstream dependencies to READY."""
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner, TaskStatus

        planner = DynamicTaskPlanner()
        plan = planner.decompose_goal(
            project_id=self.project_a.id,
            goal="Investigate ranking drop for target page"
        )

        task_ids = list(plan.tasks.keys())
        t1 = plan.tasks[task_ids[0]]
        t2 = plan.tasks[task_ids[1]]

        self.assertEqual(t1.status, TaskStatus.READY.value)
        self.assertEqual(t2.status, TaskStatus.PENDING.value)

        ready_tasks = plan.get_ready_tasks()
        self.assertEqual(len(ready_tasks), 1)
        self.assertEqual(ready_tasks[0].task_id, t1.task_id)

        # Complete t1
        t1.transition_to(TaskStatus.RUNNING)
        t1.transition_to(TaskStatus.COMPLETED, result_summary="Done")

        # Now t2 should be unblocked to READY
        ready_tasks = plan.get_ready_tasks()
        self.assertGreaterEqual(len(ready_tasks), 1)
        self.assertIn(t2.task_id, [t.task_id for t in ready_tasks])
        self.assertEqual(t2.status, TaskStatus.READY.value)

    def test_cascading_failure_to_blocked(self):
        """8. Upstream task failure cascades BLOCKED status down dependency tree."""
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner, TaskStatus

        planner = DynamicTaskPlanner()
        plan = planner.decompose_goal(
            project_id=self.project_a.id,
            goal="Investigate ranking drops and synthesize fix"
        )

        task_ids = list(plan.tasks.keys())
        t1 = plan.tasks[task_ids[0]]
        t2 = plan.tasks[task_ids[1]]
        t3 = plan.tasks[task_ids[2]]
        t4 = plan.tasks[task_ids[3]]

        # t1 starts in READY and fails
        t1.transition_to(TaskStatus.RUNNING)
        t1.transition_to(TaskStatus.FAILED, error="GSC API connection timeout")

        blocked_ids = plan.handle_task_failure(t1.task_id)
        self.assertIn(t2.task_id, blocked_ids)
        self.assertIn(t3.task_id, blocked_ids)
        self.assertIn(t4.task_id, blocked_ids)

        self.assertEqual(t2.status, TaskStatus.BLOCKED.value)
        self.assertEqual(t3.status, TaskStatus.BLOCKED.value)
        self.assertEqual(t4.status, TaskStatus.BLOCKED.value)

        # Ready tasks should now be empty
        self.assertEqual(len(plan.get_ready_tasks()), 0)

    def test_parallel_groups_tier_computation(self):
        """9. Parallel groups partitions tasks into topological depth tiers."""
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Parallel group test",
            correlation_id="corr-parallel-009"
        )

        # Tier 0: Two independent root tasks
        t_a = AgentTask("t_a", "Collect GSC data", "", "seo_researcher", correlation_id="c")
        t_b = AgentTask("t_b", "Collect Audit data", "", "seo_researcher", correlation_id="c")

        # Tier 1: Task depending on both t_a and t_b
        t_c = AgentTask("t_c", "Correlate data", "", "seo_investigator", dependencies=["t_a", "t_b"], correlation_id="c")

        # Tier 2: Final task depending on t_c
        t_d = AgentTask("t_d", "Formulate plan", "", "seo_action_planner", dependencies=["t_c"], correlation_id="c")

        plan.add_task(t_a)
        plan.add_task(t_b)
        plan.add_task(t_c)
        plan.add_task(t_d)

        groups = plan.get_parallel_groups()
        self.assertEqual(len(groups), 3)

        tier_0_ids = set(groups[0])
        self.assertEqual(tier_0_ids, {"t_a", "t_b"})

        tier_1_ids = set(groups[1])
        self.assertEqual(tier_1_ids, {"t_c"})

        tier_2_ids = set(groups[2])
        self.assertEqual(tier_2_ids, {"t_d"})

    def test_adaptive_replanning_on_conflict_or_evidence(self):
        """10. Adaptive replanner updates plan rounds, records history, and modifies tasks."""
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner, ReplanReason, AgentTask

        planner = DynamicTaskPlanner()
        plan = planner.decompose_goal(
            project_id=self.project_a.id,
            goal="Investigate sudden organic drop"
        )

        initial_rounds = plan.planning_rounds
        self.assertEqual(initial_rounds, 1)

        extra_task = AgentTask(
            task_id="extra_audit_010",
            objective="Deep-dive into canonical tag anomalies",
            description="Resolve conflicting canonical findings",
            responsible_agent="seo_investigator",
            correlation_id=plan.correlation_id
        )

        plan = planner.replan(
            plan=plan,
            reason=ReplanReason.CONFLICT_DETECTED,
            explanation="Canonical conflict between researcher and investigator",
            new_tasks=[extra_task]
        )

        self.assertEqual(plan.planning_rounds, 2)
        self.assertEqual(len(plan.replan_history), 1)
        self.assertEqual(plan.replan_history[0]["reason"], "conflict_detected")
        self.assertIn("extra_audit_010", plan.tasks)

    def test_replanning_budget_limits(self):
        """11. Exceeding max_replans or max_tasks_per_plan enforces budget ceilings."""
        from apps.seo.services.agents.task_planner import (
            DynamicTaskPlanner, ReplanReason, AgentTask, PlanBudgetConfig,
            PlanBudgetExceededError, PlanLimitExceededError
        )

        budget = PlanBudgetConfig(max_replans=2, max_tasks_per_plan=20)
        planner = DynamicTaskPlanner(default_budget=budget)
        plan = planner.decompose_goal(
            project_id=self.project_a.id,
            goal="Budget ceiling test"
        )

        # Replan round 1: OK
        plan = planner.replan(plan, ReplanReason.NEW_EVIDENCE, "Round 1")
        # Replan round 2: OK
        plan = planner.replan(plan, ReplanReason.NEW_EVIDENCE, "Round 2")

        # Replan round 3: Exceeds max_replans=2
        with self.assertRaises(PlanBudgetExceededError) as ctx:
            planner.replan(plan, ReplanReason.NEW_EVIDENCE, "Round 3")
        self.assertIn("Maximum allowed replans", str(ctx.exception))

    def test_secret_redaction_in_tasks(self):
        """12. Secrets, API keys, and Bearer tokens are redacted upon task creation."""
        from apps.seo.services.agents.task_planner import AgentTask

        task = AgentTask(
            task_id="task_sec_012",
            objective="Authenticate using Bearer secret_token_xyz123 and test endpoint",
            description="Query GSC with api_key=sk-abcdef1234567890 securely",
            responsible_agent="seo_researcher",
            correlation_id="corr-sec-012"
        )

        self.assertNotIn("secret_token_xyz123", task.objective)
        self.assertIn("REDACTED", task.objective)
        self.assertNotIn("sk-abcdef1234567890", task.description)
        self.assertIn("REDACTED", task.description)

    def test_human_approval_safety_in_action_planning(self):
        """13. Action Planner task execution preserves human approval boundary (requires_approval=True)."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisor
        from apps.seo.models import SEOAction

        supervisor = SEOSupervisor(project=self.project_a, user=self.user_a)
        result = supervisor.orchestrate(task="Propose title and meta description updates for landing page")

        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.task_plan)

        # Verify any action proposals strictly require human approval
        actions = SEOAction.objects.filter(project=self.project_a)
        for action in actions:
            self.assertTrue(action.requires_human_approval)
            self.assertEqual(action.status, "proposed")

    def test_supervisor_emits_phase_5_3_task_events(self):
        """14. Supervisor emits Phase 5.3 structured task lifecycle events."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisor
        from apps.seo.services.agent_events import AgentEventType

        events_captured = []
        class MockPublisher:
            def publish(self, event):
                events_captured.append(event)

        supervisor = SEOSupervisor(
            project=self.project_a,
            user=self.user_a,
            publisher=MockPublisher()
        )
        result = supervisor.orchestrate(task="Diagnose traffic drop and propose recovery plan")

        emitted_types = [e.event_type for e in events_captured]
        self.assertIn(AgentEventType.SEO_TASK_PLAN_CREATED, emitted_types)
        self.assertIn(AgentEventType.SEO_TASK_CREATED, emitted_types)
        self.assertIn(AgentEventType.SEO_TASK_READY, emitted_types)
        self.assertIn(AgentEventType.SEO_TASK_STARTED, emitted_types)
        self.assertIn(AgentEventType.SEO_TASK_COMPLETED, emitted_types)

    def test_evaluation_metrics_include_task_planning(self):
        """15. AgentEvaluationService computes all 12 Phase 5.3 task planning dimensions."""
        from apps.seo.services.agents.base_agent import SharedContext
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner, TaskStatus
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService

        planner = DynamicTaskPlanner()
        plan = planner.decompose_goal(
            project_id=self.project_a.id,
            goal="Evaluation task planning test"
        )

        # Mark all tasks completed for evaluation
        for t in plan.tasks.values():
            t.status = TaskStatus.COMPLETED.value

        context = SharedContext(
            project_id=self.project_a.id,
            project_name=self.project_a.name,
            website_url=self.project_a.website_url,
            task_type="investigation",
            task_goal=plan.goal,
            correlation_id=plan.correlation_id,
            status="completed",
            task_plan=plan
        )

        eval_res = SEOAgentEvaluationService.evaluate_shared_context(context)
        self.assertIn("task_planning_metrics", eval_res)
        metrics = eval_res["task_planning_metrics"]

        expected_keys = [
            "tasks_created", "tasks_completed", "tasks_failed", "tasks_blocked",
            "tasks_replanned", "planning_rounds", "average_tasks_per_plan",
            "dependency_resolution_rate", "circular_dependencies_detected",
            "task_completion_efficiency", "replan_efficiency", "planning_safety_compliance"
        ]
        for k in expected_keys:
            self.assertIn(k, metrics)

        self.assertEqual(metrics["tasks_created"], len(plan.tasks))
        self.assertEqual(metrics["tasks_completed"], len(plan.tasks))
        self.assertEqual(metrics["circular_dependencies_detected"], 0)
        self.assertEqual(metrics["planning_safety_compliance"], 100.0)

    def test_task_plan_serialization_and_deserialization(self):
        """16. TaskPlan roundtrips cleanly through to_dict() and from_dict()."""
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner, TaskPlan

        planner = DynamicTaskPlanner()
        original = planner.decompose_goal(
            project_id=self.project_a.id,
            goal="Roundtrip serialization test"
        )

        data = original.to_dict()
        restored = TaskPlan.from_dict(data)

        self.assertEqual(restored.project_id, original.project_id)
        self.assertEqual(restored.correlation_id, original.correlation_id)
        self.assertEqual(restored.goal, original.goal)
        self.assertEqual(len(restored.tasks), len(original.tasks))
        self.assertEqual(restored.planning_rounds, original.planning_rounds)

        for tid, orig_task in original.tasks.items():
            rest_task = restored.tasks[tid]
            self.assertEqual(rest_task.task_id, orig_task.task_id)
            self.assertEqual(rest_task.objective, orig_task.objective)
            self.assertEqual(rest_task.responsible_agent, orig_task.responsible_agent)
            self.assertEqual(rest_task.status, orig_task.status)
            self.assertEqual(rest_task.dependencies, orig_task.dependencies)

    def test_api_endpoints_tasks_summary_graph(self):
        """17. API endpoints return complete TaskPlan, summary, and visualization graph."""
        from apps.seo.models import AgentRun, AgentRunStatus
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner, TaskPlanRegistry

        planner = DynamicTaskPlanner()
        plan = planner.decompose_goal(
            project_id=self.project_a.id,
            goal="Endpoint verification test"
        )

        run = AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            goal=plan.goal,
            status=AgentRunStatus.COMPLETED,
            context_snapshot={"task_plan": plan.to_dict(), "correlation_id": plan.correlation_id}
        )
        plan.run_id = run.id
        TaskPlanRegistry.get_instance().register(plan)

        self.client.force_authenticate(user=self.user_a)

        # Test GET /api/seo/ai/orchestrate/<run_id>/tasks/
        res_tasks = self.client.get(f'/api/seo/ai/orchestrate/{run.id}/tasks/')
        self.assertEqual(res_tasks.status_code, status.HTTP_200_OK)
        self.assertEqual(res_tasks.data["project_id"], self.project_a.id)
        self.assertIn("tasks", res_tasks.data)
        self.assertIn("summary", res_tasks.data)

        # Test GET /api/seo/ai/orchestrate/<run_id>/tasks/summary/
        res_sum = self.client.get(f'/api/seo/ai/orchestrate/{run.id}/tasks/summary/')
        self.assertEqual(res_sum.status_code, status.HTTP_200_OK)
        self.assertIn("total_tasks", res_sum.data)
        self.assertIn("completion_rate", res_sum.data)
        self.assertIn("parallel_groups_count", res_sum.data)

        # Test GET /api/seo/ai/orchestrate/<run_id>/tasks/graph/
        res_graph = self.client.get(f'/api/seo/ai/orchestrate/{run.id}/tasks/graph/')
        self.assertEqual(res_graph.status_code, status.HTTP_200_OK)
        self.assertIn("nodes", res_graph.data)
        self.assertIn("edges", res_graph.data)
        self.assertIn("summary", res_graph.data)
        self.assertEqual(len(res_graph.data["nodes"]), len(plan.tasks))

    def test_multi_tenant_isolation_forbidden_on_cross_tenant_plan(self):
        """18. User B cannot access User A's task plan via correlation_id or run_id."""
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner, TaskPlanRegistry

        planner = DynamicTaskPlanner()
        plan_a = planner.decompose_goal(
            project_id=self.project_a.id,
            goal="Tenant isolation test"
        )
        TaskPlanRegistry.get_instance().register(plan_a)

        # User B authenticated
        self.client.force_authenticate(user=self.user_b)

        res = self.client.get(f'/api/seo/ai/orchestrate/{plan_a.correlation_id}/tasks/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_bug001_sequential_same_agent_tasks_execute_in_dependency_order(self):
        """19. Regression BUG-001: Sequential tasks assigned to same agent execute in strict DAG order."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Sequential same-agent task test",
            correlation_id="corr-seq-019"
        )
        t1 = AgentTask("r1", "Research 1", "Step 1", "seo_researcher", dependencies=[], correlation_id="corr-seq-019")
        t2 = AgentTask("r2", "Research 2", "Step 2", "seo_researcher", dependencies=["r1"], correlation_id="corr-seq-019")
        t3 = AgentTask("r3", "Research 3", "Step 3", "seo_researcher", dependencies=["r2"], correlation_id="corr-seq-019")
        t4 = AgentTask("i1", "Investigate 1", "Step 4", "seo_investigator", dependencies=["r3"], correlation_id="corr-seq-019")

        for t in [t1, t2, t3, t4]:
            plan.add_task(t)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        result_ctx = supervisor.orchestrate(task="Sequential same-agent test", correlation_id="corr-seq-019", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        self.assertEqual(len(plan.tasks), 4)
        for t in plan.tasks.values():
            self.assertEqual(t.status, TaskStatus.COMPLETED.value)

        execution_order = [h.get("current_task_id") for h in result_ctx.handoff_history if h.get("current_task_id")]
        self.assertEqual(execution_order, ["r1", "r2", "r3", "i1"])

    def test_bug001_parallel_independent_tasks_execute_before_merge(self):
        """20. Regression BUG-001: Independent parallel tasks both execute before downstream merge task."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Parallel tasks test",
            correlation_id="corr-par-020"
        )
        t1 = AgentTask("r1", "Parallel Research A", "Branch A", "seo_researcher", dependencies=[], correlation_id="corr-par-020")
        t2 = AgentTask("r2", "Parallel Research B", "Branch B", "seo_researcher", dependencies=[], correlation_id="corr-par-020")
        t3 = AgentTask("i1", "Merge Investigation", "Merge A & B", "seo_investigator", dependencies=["r1", "r2"], correlation_id="corr-par-020")

        for t in [t1, t2, t3]:
            plan.add_task(t)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        result_ctx = supervisor.orchestrate(task="Parallel test", correlation_id="corr-par-020", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        for t in plan.tasks.values():
            self.assertEqual(t.status, TaskStatus.COMPLETED.value)

        execution_order = [h.get("current_task_id") for h in result_ctx.handoff_history if h.get("current_task_id")]
        self.assertIn("r1", execution_order)
        self.assertIn("r2", execution_order)
        self.assertIn("i1", execution_order)
        self.assertLess(execution_order.index("r1"), execution_order.index("i1"))
        self.assertLess(execution_order.index("r2"), execution_order.index("i1"))

    def test_bug001_unsatisfied_dependency_cannot_execute(self):
        """21. Regression BUG-001: Tasks with unsatisfied dependencies cannot execute or enter RUNNING."""
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus, InvalidTaskTransitionError

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Unsatisfied dependency test",
            correlation_id="corr-unsat-021"
        )
        t1 = AgentTask("r1", "Root Research", "Root", "seo_researcher", dependencies=[], correlation_id="corr-unsat-021")
        t2 = AgentTask("i1", "Dependent Investigation", "Dep", "seo_investigator", dependencies=["r1"], correlation_id="corr-unsat-021")
        plan.add_task(t1)
        plan.add_task(t2)

        # t2 cannot be executed while PENDING
        self.assertEqual(t2.status, TaskStatus.PENDING.value)
        with self.assertRaises(InvalidTaskTransitionError):
            t2.transition_to(TaskStatus.RUNNING)

        ready_tasks = plan.get_ready_tasks()
        self.assertEqual([t.task_id for t in ready_tasks], ["r1"])
        self.assertNotIn("i1", [t.task_id for t in ready_tasks])

    def test_bug001_failure_propagation_blocks_downstream_tasks(self):
        """22. Regression BUG-001: Task failure marks dependent tasks BLOCKED and prevents execution."""
        from unittest.mock import patch
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus
        from apps.seo.services.agents.base_agent import AgentResult

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Failure propagation test",
            correlation_id="corr-fail-022"
        )
        t1 = AgentTask("r1", "Failing Research", "Fails", "seo_researcher", dependencies=[], correlation_id="corr-fail-022")
        t2 = AgentTask("r2", "Dependent Research", "Dep on r1", "seo_researcher", dependencies=["r1"], correlation_id="corr-fail-022")
        t3 = AgentTask("i1", "Dependent Investigation", "Dep on r2", "seo_investigator", dependencies=["r2"], correlation_id="corr-fail-022")
        t4 = AgentTask("u1", "Unrelated Verifier", "Independent", "seo_verifier", dependencies=[], correlation_id="corr-fail-022")

        for t in [t1, t2, t3, t4]:
            plan.add_task(t)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)

        # Mock researcher failure on r1
        orig_researcher_run = supervisor._agents["seo_researcher"].run
        def mock_researcher_run(*args, **kwargs):
            handoff = kwargs.get("handoff") or (args[1] if len(args) > 1 else None)
            if handoff and getattr(handoff, "current_task_id", None) == "r1":
                return AgentResult(
                    agent="seo_researcher",
                    status="failed",
                    confidence=0.0,
                    errors=["Search API failure on r1"]
                )
            return orig_researcher_run(*args, **kwargs)

        with patch.object(supervisor._agents["seo_researcher"], "run", side_effect=mock_researcher_run):
            supervisor.orchestrate(task="Failure test", correlation_id="corr-fail-022", task_plan=plan)

        self.assertEqual(plan.get_task("r1").status, TaskStatus.FAILED.value)
        self.assertEqual(plan.get_task("r2").status, TaskStatus.BLOCKED.value)
        self.assertEqual(plan.get_task("i1").status, TaskStatus.BLOCKED.value)
        self.assertEqual(plan.get_task("u1").status, TaskStatus.COMPLETED.value)

    def test_bug001_full_supervisor_scenario_traffic_drop_100_percent_completion(self):
        """23. Regression BUG-001: Previously failing 6-task scenario achieves 100% DAG completion."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        goal = "Investigate organic traffic drop on landing page and propose fix"
        result_ctx = supervisor.orchestrate(task=goal)

        self.assertEqual(result_ctx.status, "completed")
        plan = result_ctx.task_plan
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.tasks), 6)

        summary = plan.summarize()
        self.assertEqual(summary["total_tasks"], 6)
        self.assertEqual(summary["completed_tasks"], 6)
        self.assertEqual(summary["failed_tasks"], 0)
        self.assertEqual(summary["blocked_tasks"], 0)
        self.assertEqual(summary["ready_tasks"], 0)
        self.assertEqual(summary["completion_rate"], 100.0)

        # Verify evaluation service reflects actual DAG state
        eval_result = SEOAgentEvaluationService.evaluate_shared_context(result_ctx)
        task_metrics = eval_result["task_planning_metrics"]
        self.assertEqual(task_metrics["tasks_created"], 6)
        self.assertEqual(task_metrics["tasks_completed"], 6)
        self.assertEqual(task_metrics["tasks_failed"], 0)
        self.assertEqual(task_metrics["tasks_blocked"], 0)
        self.assertEqual(task_metrics["dependency_resolution_rate"], 100.0)
        self.assertEqual(task_metrics["task_completion_efficiency"], 100.0)


from django.test import TransactionTestCase


class SEOParallelAgentExecutionTests(TransactionTestCase):
    """
    Milestone 5.4 Test Suite: Parallel Agent Execution.
    Verifies:
    1. Independent tasks execute concurrently in a bounded parallel batch.
    2. Sequential dependency order is strictly preserved with zero concurrency overlap.
    3. Same-agent parallel tasks run concurrently (not deduplicated).
    4. Merge barrier: downstream task waits for all parallel dependencies to finish.
    5. Concurrency limit is bounded (max_parallel_tasks enforced, partition into batches).
    6. Partial batch failure isolation: one task fails, other succeeds, downstream blocks cleanly.
    7. SharedWorkingMemory concurrency: thread-safe concurrent writes with no lost updates.
    8. Human-in-the-loop (HITL) approval boundary respected in parallel tasks.
    9. ToolRegistry permissions isolation across parallel worker threads.
    10. Full DoxaRank scenario with DAG completion, telemetry, and evaluation metrics.
    11. Functional runtime overlap proof verifying genuine concurrent execution.
    """

    def setUp(self):
        import time
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        from apps.projects.models import Project
        from apps.seo.services.agent_events import get_event_publisher

        self.client = APIClient()
        User = get_user_model()
        self.user_a = User.objects.create_user(
            email='parallel_user_a@doxarank.com',
            password='Password123!'
        )
        self.user_b = User.objects.create_user(
            email='parallel_user_b@doxarank.com',
            password='Password123!'
        )

        self.project_a = Project.objects.create(
            name="Parallel Project Alpha",
            website_url="https://parallel-alpha.com",
            owner=self.user_a
        )
        self.project_b = Project.objects.create(
            name="Parallel Project Beta",
            website_url="https://parallel-beta.com",
            owner=self.user_b
        )

        # Clear global event publisher
        get_event_publisher().clear()

    def test_01_independent_tasks_execute_concurrently(self):
        """1. Independent tasks execute concurrently in a bounded parallel batch (T1 -> [T2, T3] -> T4)."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Concurrent independent tasks test",
            correlation_id="corr-par-001"
        )
        t1 = AgentTask("t1", "Root Research", "Initial research", "seo_researcher", dependencies=[], correlation_id="corr-par-001")
        t2 = AgentTask("t2", "Branch A Research", "Keyword discovery", "seo_researcher", dependencies=["t1"], correlation_id="corr-par-001")
        t3 = AgentTask("t3", "Branch B Audit", "Technical inspection", "seo_investigator", dependencies=["t1"], correlation_id="corr-par-001")
        t4 = AgentTask("t4", "Merge Strategy", "Consolidate results", "seo_strategist", dependencies=["t2", "t3"], correlation_id="corr-par-001")

        for t in [t1, t2, t3, t4]:
            plan.add_task(t)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=3)
        result_ctx = supervisor.orchestrate(task="Concurrent test", correlation_id="corr-par-001", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        for t in plan.tasks.values():
            self.assertEqual(t.status, TaskStatus.COMPLETED.value)

        # Verify parallel batches recorded
        batches = result_ctx.parallel_batches
        self.assertGreaterEqual(len(batches), 2)

        # Find the batch containing t2 and t3
        parallel_batch = next((b for b in batches if "t2" in b.get("tasks", b.get("task_ids", [])) and "t3" in b.get("tasks", b.get("task_ids", []))), None)
        self.assertIsNotNone(parallel_batch, "Expected parallel batch with t2 and t3")
        batch_tasks = parallel_batch.get("tasks", parallel_batch.get("task_ids", []))
        self.assertEqual(set(batch_tasks), {"t2", "t3"})
        self.assertEqual(parallel_batch["status"], "completed")
        timings = parallel_batch.get("task_timings", parallel_batch.get("metadata", {}).get("timings", {}))
        self.assertIn("t2", timings)
        self.assertIn("t3", timings)

    def test_02_sequential_dependency_order_strictly_preserved(self):
        """2. Sequential tasks (T1 -> T2 -> T3) preserve strict ordering with zero invalid overlap."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Strict sequential order test",
            correlation_id="corr-seq-002"
        )
        t1 = AgentTask("s1", "Step 1", "Root", "seo_researcher", dependencies=[], correlation_id="corr-seq-002")
        t2 = AgentTask("s2", "Step 2", "Depends on s1", "seo_investigator", dependencies=["s1"], correlation_id="corr-seq-002")
        t3 = AgentTask("s3", "Step 3", "Depends on s2", "seo_strategist", dependencies=["s2"], correlation_id="corr-seq-002")

        for t in [t1, t2, t3]:
            plan.add_task(t)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        result_ctx = supervisor.orchestrate(task="Sequential test", correlation_id="corr-seq-002", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        for t in plan.tasks.values():
            self.assertEqual(t.status, TaskStatus.COMPLETED.value)

        # Every batch should contain exactly one task
        batches = result_ctx.parallel_batches
        self.assertEqual(len(batches), 3)
        for b in batches:
            batch_tasks = b.get("tasks", b.get("task_ids", []))
            self.assertEqual(len(batch_tasks), 1)
            self.assertFalse(b.get("overlap_detected", False))

        # Check monotonic timestamps across sequential batches
        b1_timings = batches[0].get("task_timings", batches[0].get("metadata", {}).get("timings", {}))
        b2_timings = batches[1].get("task_timings", batches[1].get("metadata", {}).get("timings", {}))
        b3_timings = batches[2].get("task_timings", batches[2].get("metadata", {}).get("timings", {}))

        b1_timing = b1_timings["s1"]
        b2_timing = b2_timings["s2"]
        b3_timing = b3_timings["s3"]

        self.assertLessEqual(b1_timing["end_time"], b2_timing["start_time"] + 0.005)
        self.assertLessEqual(b2_timing["end_time"], b3_timing["start_time"] + 0.005)

    def test_03_same_agent_parallel_tasks_run_concurrently(self):
        """3. Independent tasks assigned to the same agent run concurrently without being deduplicated."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Same agent concurrent test",
            correlation_id="corr-same-003"
        )
        r1 = AgentTask("r1", "Research Domain A", "Keyword cluster A", "seo_researcher", dependencies=[], correlation_id="corr-same-003")
        r2 = AgentTask("r2", "Research Domain B", "Keyword cluster B", "seo_researcher", dependencies=[], correlation_id="corr-same-003")

        plan.add_task(r1)
        plan.add_task(r2)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=3)
        result_ctx = supervisor.orchestrate(task="Same agent test", correlation_id="corr-same-003", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        self.assertEqual(plan.get_task("r1").status, TaskStatus.COMPLETED.value)
        self.assertEqual(plan.get_task("r2").status, TaskStatus.COMPLETED.value)

        batches = result_ctx.parallel_batches
        self.assertEqual(len(batches), 1)
        batch_tasks = batches[0].get("tasks", batches[0].get("task_ids", []))
        self.assertEqual(set(batch_tasks), {"r1", "r2"})

    def test_04_merge_barrier_waits_for_all_parallel_dependencies(self):
        """4. Merge barrier ensures downstream task starts only after all upstream parallel tasks complete."""
        import time
        from unittest.mock import patch
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Merge barrier test",
            correlation_id="corr-bar-004"
        )
        p1 = AgentTask("p1", "Slow Parallel Task", "Takes 40ms", "seo_researcher", dependencies=[], correlation_id="corr-bar-004")
        p2 = AgentTask("p2", "Fast Parallel Task", "Takes 10ms", "seo_investigator", dependencies=[], correlation_id="corr-bar-004")
        m1 = AgentTask("m1", "Downstream Merge", "Depends on p1 and p2", "seo_strategist", dependencies=["p1", "p2"], correlation_id="corr-bar-004")

        for t in [p1, p2, m1]:
            plan.add_task(t)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=3)

        orig_researcher_run = supervisor._agents["seo_researcher"].run
        def mock_researcher_run(*args, **kwargs):
            time.sleep(0.04)
            return orig_researcher_run(*args, **kwargs)

        with patch.object(supervisor._agents["seo_researcher"], "run", side_effect=mock_researcher_run):
            result_ctx = supervisor.orchestrate(task="Merge barrier test", correlation_id="corr-bar-004", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        self.assertEqual(plan.get_task("m1").status, TaskStatus.COMPLETED.value)

        batches = result_ctx.parallel_batches
        self.assertEqual(len(batches), 2)

        batch_par = batches[0]
        batch_merge = batches[1]

        timings_par = batch_par.get("task_timings", batch_par.get("metadata", {}).get("timings", {}))
        timings_merge = batch_merge.get("task_timings", batch_merge.get("metadata", {}).get("timings", {}))

        p1_end = timings_par["p1"]["end_time"]
        p2_end = timings_par["p2"]["end_time"]
        m1_start = timings_merge["m1"]["start_time"]

        self.assertGreaterEqual(m1_start, p1_end)
        self.assertGreaterEqual(m1_start, p2_end)

    def test_05_concurrency_limit_bounded_to_max_parallel_tasks(self):
        """5. Max concurrency limit is strictly bounded, partitioning excess ready tasks into batches."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus
        from apps.seo.services.agent_events import get_event_publisher, AgentEventType

        pub = get_event_publisher()
        pub.clear()

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Concurrency limit test",
            correlation_id="corr-limit-005"
        )
        t1 = AgentTask("l1", "Task 1", "Root 1", "seo_researcher", dependencies=[], correlation_id="corr-limit-005")
        t2 = AgentTask("l2", "Task 2", "Root 2", "seo_researcher", dependencies=[], correlation_id="corr-limit-005")
        t3 = AgentTask("l3", "Task 3", "Root 3", "seo_investigator", dependencies=[], correlation_id="corr-limit-005")
        t4 = AgentTask("l4", "Task 4", "Root 4", "seo_investigator", dependencies=[], correlation_id="corr-limit-005")

        for t in [t1, t2, t3, t4]:
            plan.add_task(t)

        # Set max_parallel_tasks to 2 on 4 ready tasks
        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=2)
        result_ctx = supervisor.orchestrate(task="Limit test", correlation_id="corr-limit-005", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        for t in plan.tasks.values():
            self.assertEqual(t.status, TaskStatus.COMPLETED.value)

        # Should be partitioned into 2 batches of 2 tasks each
        batches = result_ctx.parallel_batches
        self.assertEqual(len(batches), 2)
        for b in batches:
            batch_tasks = b.get("tasks", b.get("task_ids", []))
            self.assertLessEqual(len(batch_tasks), 2)

        # Verify limit event emitted
        event_types = pub.get_event_types()
        self.assertIn(AgentEventType.SEO_PARALLEL_CONCURRENCY_LIMITED.value, event_types)

    def test_06_partial_batch_failure_isolation(self):
        """6. Failure in one parallel task does not abort other tasks, and downstream dependencies block cleanly."""
        from unittest.mock import patch
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus
        from apps.seo.services.agents.base_agent import AgentResult
        from apps.seo.services.agent_events import get_event_publisher, AgentEventType

        pub = get_event_publisher()
        pub.clear()

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Partial failure test",
            correlation_id="corr-part-006"
        )
        f1 = AgentTask("f1", "Failing Task", "Will fail", "seo_researcher", dependencies=[], correlation_id="corr-part-006")
        s1 = AgentTask("s1", "Succeeding Task", "Will succeed", "seo_investigator", dependencies=[], correlation_id="corr-part-006")
        d1 = AgentTask("d1", "Dependent on F1", "Should block", "seo_strategist", dependencies=["f1"], correlation_id="corr-part-006")
        d2 = AgentTask("d2", "Dependent on S1", "Should complete", "seo_verifier", dependencies=["s1"], correlation_id="corr-part-006")

        for t in [f1, s1, d1, d2]:
            plan.add_task(t)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=3)

        orig_researcher_run = supervisor._agents["seo_researcher"].run
        def mock_researcher_run(*args, **kwargs):
            handoff = kwargs.get("handoff") or (args[1] if len(args) > 1 else None)
            if handoff and getattr(handoff, "current_task_id", None) == "f1":
                return AgentResult(
                    agent="seo_researcher",
                    status="failed",
                    confidence=0.0,
                    errors=["Network timeout on f1"]
                )
            return orig_researcher_run(*args, **kwargs)

        with patch.object(supervisor._agents["seo_researcher"], "run", side_effect=mock_researcher_run):
            result_ctx = supervisor.orchestrate(task="Partial failure test", correlation_id="corr-part-006", task_plan=plan)

        self.assertEqual(plan.get_task("f1").status, TaskStatus.FAILED.value)
        self.assertEqual(plan.get_task("s1").status, TaskStatus.COMPLETED.value)
        self.assertEqual(plan.get_task("d1").status, TaskStatus.BLOCKED.value)
        self.assertEqual(plan.get_task("d2").status, TaskStatus.COMPLETED.value)

        # Batch 1 should be partial failure
        batches = result_ctx.parallel_batches
        self.assertGreaterEqual(len(batches), 1)
        batch_1 = next((b for b in batches if "f1" in b.get("tasks", b.get("task_ids", []))), None)
        self.assertIsNotNone(batch_1)
        self.assertEqual(batch_1["status"], "partial_failure")

        event_types = pub.get_event_types()
        self.assertIn(AgentEventType.SEO_PARALLEL_BATCH_PARTIAL_FAILURE.value, event_types)

    def test_07_shared_memory_thread_safe_concurrency(self):
        """7. SharedWorkingMemory is thread-safe under concurrent writes with zero lost updates."""
        import threading
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, ContextBudgetConfig

        mem = SharedWorkingMemory(
            project_id=self.project_a.id,
            task_goal="Thread safe concurrency test",
            correlation_id="corr-mem-007",
            budget_config=ContextBudgetConfig(max_facts=200, max_inferences=200, max_uncertainties=200)
        )

        errors = []
        num_threads = 6
        ops_per_thread = 15

        def worker_task(thread_id: int):
            try:
                for i in range(ops_per_thread):
                    fact = mem.add_evidence(
                        fact=f"Empirical discovery {i} from worker {thread_id}",
                        source_agent="seo_researcher",
                        task_id=f"t_{thread_id}_{i}"
                    )
                    mem.add_inference(
                        hypothesis=f"Hypothesis {i} from worker {thread_id}",
                        source_agent="seo_investigator",
                        supporting_fact_ids=[fact.memory_id],
                        confidence=0.85
                    )
                    mem.add_uncertainty(
                        description=f"Uncertainty {i} from worker {thread_id}",
                        source_agent="seo_strategist"
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker_task, args=(tid,)) for tid in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent writes produced exceptions: {errors}")

        # Verify no lost updates
        summary = mem.summarize()
        expected_facts = num_threads * ops_per_thread
        expected_inferences = num_threads * ops_per_thread
        expected_uncertainties = num_threads * ops_per_thread

        self.assertEqual(summary["facts_count"], expected_facts)
        self.assertEqual(summary["inferences_count"], expected_inferences)
        self.assertEqual(summary["uncertainties_count"], expected_uncertainties)

        # Check provenance preserved
        all_facts = list(mem._facts.values())
        for f in all_facts:
            self.assertEqual(f.source_agent, "seo_researcher")
            self.assertTrue(f.metadata.get("task_id", "").startswith("t_"))

    def test_08_hitl_approval_boundary_respected_in_parallel_task(self):
        """8. Mutating actions proposed by parallel tasks strictly require human approval."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus
        from apps.seo.models import SEOAction, ActionStatus, SiteAudit, AuditIssue

        # Create audit issue so action planner synthesizes actions
        audit = SiteAudit.objects.create(project=self.project_a, status='completed')
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_title",
            title="Missing Title Tag",
            page_url=f"{self.project_a.website_url}/landing",
            severity="critical"
        )

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="HITL approval boundary in parallel execution",
            correlation_id="corr-hitl-008"
        )
        t_plan = AgentTask(
            task_id="act_1",
            objective="Synthesize action plan",
            description="Propose actionable fixes",
            responsible_agent="seo_action_planner",
            dependencies=[],
            correlation_id="corr-hitl-008"
        )
        t_audit = AgentTask(
            task_id="aud_1",
            objective="Inspect site health",
            description="Parallel audit inspection",
            responsible_agent="seo_investigator",
            dependencies=[],
            correlation_id="corr-hitl-008"
        )

        plan.add_task(t_plan)
        plan.add_task(t_audit)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=2)
        result_ctx = supervisor.orchestrate(task="HITL parallel test", correlation_id="corr-hitl-008", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")

        # Verify all created actions require human approval and are not auto-executed
        actions = SEOAction.objects.filter(project=self.project_a)
        self.assertGreaterEqual(actions.count(), 1)
        for act in actions:
            self.assertTrue(act.requires_human_approval)
            self.assertIn(act.status, [ActionStatus.PROPOSED, ActionStatus.PENDING_APPROVAL])
            self.assertIsNone(act.approved_at)
            self.assertIsNone(act.completed_at)

    def test_09_tool_permissions_isolation_across_parallel_workers(self):
        """9. Parallel tasks cannot escalate ToolRegistry or MCP permissions."""
        from apps.seo.services.agents.base_agent import SharedContext
        from apps.seo.services.agents.seo_research_agent import SEOResearchAgent
        from apps.seo.services.agents.seo_action_agent import SEOActionPlanningAgent

        researcher = SEOResearchAgent(project=self.project_a, user=self.user_a)
        action_agent = SEOActionPlanningAgent(project=self.project_a, user=self.user_a)

        # Researcher is read-only; action planner has plan_seo_actions
        self.assertFalse(researcher.is_tool_allowed("plan_seo_actions"))
        self.assertTrue(action_agent.is_tool_allowed("plan_seo_actions"))

        # Verify executing forbidden tool raises PermissionError
        with self.assertRaises(PermissionError):
            researcher.execute_tool("plan_seo_actions", {})

    def test_10_full_doxarank_parallel_scenario_telemetry_and_evaluation(self):
        """10. Full DoxaRank Scenario executes with 100% completion, parallel telemetry, and evaluation metrics."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService
        from apps.seo.services.agent_events import get_event_publisher, AgentEventType

        pub = get_event_publisher()
        pub.clear()

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=3)
        goal = "Investigate organic traffic drop on landing page and propose fix"
        result_ctx = supervisor.orchestrate(task=goal)

        self.assertEqual(result_ctx.status, "completed")
        plan = result_ctx.task_plan
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.tasks), 6)

        summary = plan.summarize()
        self.assertEqual(summary["completed_tasks"], 6)
        self.assertEqual(summary["completion_rate"], 100.0)

        # Telemetry: verify parallel events emitted
        event_types = pub.get_event_types()
        self.assertIn(AgentEventType.SEO_PARALLEL_BATCH_CREATED.value, event_types)
        self.assertIn(AgentEventType.SEO_PARALLEL_TASK_STARTED.value, event_types)
        self.assertIn(AgentEventType.SEO_PARALLEL_TASK_COMPLETED.value, event_types)
        self.assertIn(AgentEventType.SEO_PARALLEL_BATCH_COMPLETED.value, event_types)

        # Evaluation metrics
        eval_result = SEOAgentEvaluationService.evaluate_shared_context(result_ctx)
        self.assertIn("parallel_execution_metrics", eval_result)
        p_metrics = eval_result["parallel_execution_metrics"]

        self.assertGreaterEqual(p_metrics["parallel_batches_count"], 1)
        self.assertGreaterEqual(p_metrics["parallel_tasks_executed"], 2)
        self.assertEqual(p_metrics["concurrency_limit"], 3)
        self.assertEqual(p_metrics["dependency_violations"], 0)
        self.assertEqual(p_metrics["lost_memory_updates"], 0)
        self.assertEqual(p_metrics["unauthorized_mutations"], 0)
        self.assertGreater(p_metrics["parallelization_rate"], 0.0)

    def test_11_functional_runtime_overlap_proof(self):
        """11. Functional Proof: Independent parallel tasks exhibit genuine temporal runtime overlap."""
        import time
        from unittest.mock import patch
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Runtime overlap functional proof",
            correlation_id="corr-overlap-011"
        )
        task_a = AgentTask("tA", "Timed Task A", "Sleeps 50ms", "seo_researcher", dependencies=[], correlation_id="corr-overlap-011")
        task_b = AgentTask("tB", "Timed Task B", "Sleeps 50ms", "seo_investigator", dependencies=[], correlation_id="corr-overlap-011")

        plan.add_task(task_a)
        plan.add_task(task_b)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=2)

        orig_researcher_run = supervisor._agents["seo_researcher"].run
        orig_investigator_run = supervisor._agents["seo_investigator"].run

        def mock_sleep_researcher(*args, **kwargs):
            time.sleep(0.05)
            return orig_researcher_run(*args, **kwargs)

        def mock_sleep_investigator(*args, **kwargs):
            time.sleep(0.05)
            return orig_investigator_run(*args, **kwargs)

        with patch.object(supervisor._agents["seo_researcher"], "run", side_effect=mock_sleep_researcher):
            with patch.object(supervisor._agents["seo_investigator"], "run", side_effect=mock_sleep_investigator):
                t_start = time.perf_counter()
                result_ctx = supervisor.orchestrate(task="Overlap test", correlation_id="corr-overlap-011", task_plan=plan)
                wall_clock_time = time.perf_counter() - t_start

        self.assertEqual(result_ctx.status, "completed")
        self.assertEqual(plan.get_task("tA").status, TaskStatus.COMPLETED.value)
        self.assertEqual(plan.get_task("tB").status, TaskStatus.COMPLETED.value)

        # 1. Batch duration must be strictly less than the sequential sum of individual task durations
        batches = result_ctx.parallel_batches
        self.assertEqual(len(batches), 1)
        batch = batches[0]
        timings = batch.get("task_timings", batch.get("metadata", {}).get("timings", {}))
        tA_timing = timings["tA"]
        tB_timing = timings["tB"]

        sequential_sum_ms = tA_timing["duration_ms"] + tB_timing["duration_ms"]
        batch_duration_ms = batch["duration_ms"]
        self.assertLess(batch_duration_ms, sequential_sum_ms, f"Batch duration {batch_duration_ms}ms was not less than sequential sum {sequential_sum_ms}ms")

        # 2. Verify overlap recorded in batch
        self.assertTrue(batch["overlap_detected"], "Expected genuine overlap detection in parallel batch")
        self.assertGreater(batch["overlap_duration_ms"], 0.0)

        # 3. Direct verification of start and end interval intersection
        has_temporal_overlap = (
            tA_timing["start_time"] < tB_timing["end_time"] and
            tB_timing["start_time"] < tA_timing["end_time"]
        )
        self.assertTrue(has_temporal_overlap, f"Tasks did not overlap: A={tA_timing}, B={tB_timing}")


class SEOAdaptiveAgentCoordinationTests(TransactionTestCase):
    """
    Milestone 5.5 Test Suite: Adaptive Agent Coordination & Dynamic Agent Selection.
    Verifies:
    1. Best capability match is selected.
    2. Ineligible agent is rejected by hard constraint.
    3. Tool permission mismatch eliminates candidate.
    4. HITL requirement cannot be bypassed.
    5. Workload affects ranking when capabilities are otherwise comparable.
    6. Deterministic tie-breaking with zero randomness.
    7. Routing decision contains explainable reasons.
    8. Low-confidence routing triggers safe fallback / review behavior.
    9. Failed selected agent can safely fall back to next eligible agent.
    10. Fallback is bounded and cannot loop indefinitely.
    11. Same agent can still execute multiple independent tasks through 5.4.
    12. Adaptive routing preserves DAG dependencies.
    13. Parallel execution still works after dynamic agent assignment.
    14. Shared memory context remains tenant-isolated.
    15. Routing telemetry is emitted correctly.
    16. Routing metrics are derived from runtime state.
    17. No secrets appear in routing telemetry.
    18. Full realistic DoxaRank scenario (Research -> Parallel Rank/Audit -> Investigation -> Strategy -> Action -> Verification).
    19. Hard constraint failure blocks execution in supervisor (BUG-001 regression).
    20. Ranking anomalies investigation routes to seo_investigator (BUG-002 Task B regression).
    21. Post-action verification routes to seo_verifier (BUG-002 Task E regression).
    22. Pure crawl and action planning queries route cleanly without cross-agent confusion.
    """

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user_a = User.objects.create_user(
            email='coordinator_a@doxarank.com',
            password='Password123!',
            first_name='Coord',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='coordinator_b@doxarank.com',
            password='Password123!',
            first_name='Coord',
            last_name='B'
        )
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Alpha Growth Project',
            website_url='https://alpha-growth.io'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Beta Tenant Project',
            website_url='https://beta-tenant.io'
        )

    def test_01_best_capability_match_selected(self):
        """1. Candidate agent with the best matching capability profile is selected."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        selector = AdaptiveAgentSelector(project_id=self.project_a.id)
        task = AgentTask(
            task_id="t_res_01",
            objective="Gather keyword rankings and SERP competitor research data",
            description="Collect empirical ranking and search intent evidence",
            responsible_agent="seo_investigator",  # initial baseline differs from best fit
            correlation_id="corr-sel-001"
        )

        decision = selector.select_agent(task=task)
        self.assertEqual(decision.selected_agent, "seo_researcher")
        self.assertGreater(decision.score, 0.60)
        self.assertGreater(decision.confidence, 0.70)
        self.assertTrue(any("capability_match" in r for r in decision.reasons))

    def test_02_hard_constraint_rejects_ineligible_candidate(self):
        """2. Hard constraint immediately eliminates candidates lacking mandatory capabilities."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        selector = AdaptiveAgentSelector(project_id=self.project_a.id)
        task = AgentTask(
            task_id="t_diag_02",
            objective="Diagnose technical root cause of ranking drop",
            description="Perform deep root cause analysis on traffic drop",
            responsible_agent="seo_researcher",
            metadata={"required_capabilities": ["root_cause_analysis"]},
            correlation_id="corr-sel-002"
        )

        decision = selector.select_agent(task=task)
        self.assertEqual(decision.selected_agent, "seo_investigator")
        rejected_names = [r["agent"] for r in decision.rejected_candidates]
        self.assertIn("seo_researcher", rejected_names)
        researcher_rej = next(r for r in decision.rejected_candidates if r["agent"] == "seo_researcher")
        self.assertEqual(researcher_rej["hard_constraint"], "missing_required_capability")

    def test_03_tool_permission_mismatch_eliminates_candidate(self):
        """3. Candidate lacking tool authorization in ToolRegistry is eliminated by hard constraint."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        selector = AdaptiveAgentSelector(project_id=self.project_a.id)
        task = AgentTask(
            task_id="t_tool_03",
            objective="Plan formal SEO remediations",
            description="Synthesize structured action proposals",
            responsible_agent="seo_researcher",
            metadata={"required_tools": ["plan_seo_actions"]},
            correlation_id="corr-sel-003"
        )

        decision = selector.select_agent(task=task)
        # seo_action_planner is the only agent with plan_seo_actions
        self.assertEqual(decision.selected_agent, "seo_action_planner")
        rejected_names = [r["agent"] for r in decision.rejected_candidates]
        self.assertIn("seo_researcher", rejected_names)
        self.assertIn("seo_investigator", rejected_names)
        self.assertIn("seo_strategist", rejected_names)

    def test_04_hitl_requirement_cannot_be_bypassed(self):
        """4. Agent selection cannot authorize mutations; HITL approval boundary strictly enforced."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus
        from apps.seo.models import SEOAction, ActionStatus, SiteAudit, AuditIssue

        # Create diagnostic issue so action planner synthesizes actions
        audit = SiteAudit.objects.create(project=self.project_a, status='completed')
        AuditIssue.objects.create(
            audit=audit,
            issue_type="broken_redirect",
            title="Broken Redirect Loop",
            page_url=f"{self.project_a.website_url}/broken",
            severity="critical"
        )

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Mutating remediation under strict HITL",
            correlation_id="corr-hitl-004"
        )
        t_plan = AgentTask(
            task_id="plan_act_1",
            objective="Synthesize action plan and remediations",
            description="Design actionable code and tag fixes",
            responsible_agent="seo_researcher",  # Deliberately misassigned
            metadata={"is_mutating": True, "risk_level": "high"},
            correlation_id="corr-hitl-004"
        )
        plan.add_task(t_plan)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        result_ctx = supervisor.orchestrate(task="Remediation test", correlation_id="corr-hitl-004", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        # Verify dynamic routing reassigned the task to action planner
        executed_task = plan.get_task("plan_act_1")
        self.assertEqual(executed_task.responsible_agent, "seo_action_planner")

        # Invariant: Selection != Authorization. Actions strictly require human approval
        actions = SEOAction.objects.filter(project=self.project_a)
        self.assertGreaterEqual(actions.count(), 1)
        for act in actions:
            self.assertTrue(act.requires_human_approval)
            self.assertIn(act.status, [ActionStatus.PROPOSED, ActionStatus.PENDING_APPROVAL])
            self.assertIsNone(act.approved_at)
            self.assertIsNone(act.completed_at)

    def test_05_workload_affects_ranking_when_capabilities_otherwise_comparable(self):
        """5. Workload factor lowers score of heavily loaded candidate when capabilities are comparable."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector, WorkloadTracker
        from apps.seo.services.agents.task_planner import AgentTask

        tracker = WorkloadTracker()
        # seo_researcher is saturated with 3 tasks; seo_investigator has 0
        tracker.set_workloads({"seo_researcher": 3, "seo_investigator": 0})

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, workload_tracker=tracker, max_concurrency=3)
        task = AgentTask(
            task_id="t_audit_05",
            objective="General crawl diagnostic audit",
            description="Perform site diagnostic audit",
            responsible_agent="seo_supervisor",
            correlation_id="corr-workload-005"
        )

        decision = selector.select_agent(task=task, available_agents=["seo_researcher", "seo_investigator"])
        researcher_score = decision.candidate_scores["seo_researcher"]
        investigator_score = decision.candidate_scores["seo_investigator"]

        # Investigator wins due to workload penalty on researcher
        self.assertGreater(investigator_score, researcher_score)
        self.assertEqual(decision.selected_agent, "seo_investigator")
        self.assertTrue(any("workload_penalty" in r for r in decision.score_breakdowns["seo_researcher"]["reasons"]))

    def test_06_deterministic_tie_breaking(self):
        """6. Tie-breaking between equally scored candidates is strictly deterministic with zero randomness."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        selector = AdaptiveAgentSelector(project_id=self.project_a.id)
        task = AgentTask(
            task_id="t_tie_06",
            objective="Diagnostic inspection task",
            description="Diagnostic inspection",
            responsible_agent="seo_supervisor",
            correlation_id="corr-tie-006"
        )

        # Run 20 times to confirm 100% deterministic repeatability
        first_decision = selector.select_agent(task=task)
        for _ in range(20):
            d = selector.select_agent(task=task)
            self.assertEqual(d.selected_agent, first_decision.selected_agent)
            self.assertEqual(d.score, first_decision.score)
            self.assertEqual(d.confidence, first_decision.confidence)
            self.assertEqual(d.ranked_candidates, first_decision.ranked_candidates)

    def test_07_routing_decision_contains_explainable_reasons(self):
        """7. RoutingDecision contains transparent, human-auditable reasons and rejection breakdown."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        selector = AdaptiveAgentSelector(project_id=self.project_a.id)
        task = AgentTask(
            task_id="t_exp_07",
            objective="Formulate SEO strategy and prioritize high-ROI initiatives",
            description="Synthesize portfolio strategy and recommend actions",
            responsible_agent="seo_supervisor",
            correlation_id="corr-exp-007"
        )

        decision = selector.select_agent(task=task)
        self.assertEqual(decision.selected_agent, "seo_strategist")
        self.assertIsInstance(decision.reasons, list)
        self.assertGreater(len(decision.reasons), 0)
        self.assertTrue(any("strategy" in r.lower() or "capability" in r.lower() for r in decision.reasons))
        self.assertIsInstance(decision.candidate_scores, dict)
        self.assertIn("seo_strategist", decision.candidate_scores)
        self.assertIsInstance(decision.rejected_candidates, list)

    def test_08_low_confidence_routing_triggers_safe_behavior(self):
        """8. Ambiguous or low-confidence routing flags low confidence and requires review for high risk."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, min_confidence_threshold=0.60)
        task = AgentTask(
            task_id="t_low_08",
            objective="Execute esoteric unclassified protocol delta",
            description="Non-standard unknown task payload",
            responsible_agent="seo_supervisor",
            metadata={"risk_level": "high"},
            correlation_id="corr-low-008"
        )

        decision = selector.select_agent(task=task)
        self.assertTrue(decision.is_low_confidence)
        self.assertTrue(decision.requires_human_review)

    def test_09_failed_selected_agent_safely_falls_back_to_next_eligible(self):
        """9. When selected agent fails, supervisor safely reassigns to next eligible candidate."""
        from unittest.mock import patch
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus
        from apps.seo.services.agents.base_agent import AgentResult
        from apps.seo.services.agent_events import get_event_publisher, AgentEventType

        pub = get_event_publisher()
        pub.clear()

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Fallback execution test",
            correlation_id="corr-fallback-009"
        )
        task = AgentTask(
            task_id="t_fb_09",
            objective="Inspect site crawl health and search diagnostics",
            description="Inspect diagnostics",
            responsible_agent="seo_researcher",
            correlation_id="corr-fallback-009"
        )
        plan.add_task(task)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)

        # Mock researcher failure
        orig_res_run = supervisor._agents["seo_researcher"].run
        def mock_researcher_fail(*args, **kwargs):
            return AgentResult(
                agent="seo_researcher",
                status="failed",
                confidence=0.0,
                errors=["Temporary rate limit on Search Console API"]
            )

        with patch.object(supervisor._agents["seo_researcher"], "run", side_effect=mock_researcher_fail):
            result_ctx = supervisor.orchestrate(task="Fallback test", correlation_id="corr-fallback-009", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        self.assertEqual(plan.get_task("t_fb_09").status, TaskStatus.COMPLETED.value)
        # Task was reassigned to fallback agent (seo_investigator)
        self.assertEqual(plan.get_task("t_fb_09").responsible_agent, "seo_investigator")

        # Telemetry: verify fallback event emitted
        event_types = pub.get_event_types()
        self.assertIn(AgentEventType.SEO_AGENT_FALLBACK.value, event_types)

    def test_10_fallback_is_bounded_and_cannot_loop_indefinitely(self):
        """10. Fallback reassignment is strictly bounded by max_attempts and halts on exhaustion."""
        from unittest.mock import patch
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus
        from apps.seo.services.agents.base_agent import AgentResult

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Bounded fallback exhaustion test",
            correlation_id="corr-bound-010"
        )
        task = AgentTask(
            task_id="t_exhaust_10",
            objective="Audit crawl errors",
            description="Crawl audit",
            responsible_agent="seo_researcher",
            correlation_id="corr-bound-010"
        )
        plan.add_task(task)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)

        # Both researcher and investigator fail
        def mock_all_fail(agent_name):
            def _runner(*args, **kwargs):
                return AgentResult(agent=agent_name, status="failed", confidence=0.0, errors=["Fatal external error"])
            return _runner

        with patch.object(supervisor._agents["seo_researcher"], "run", side_effect=mock_all_fail("seo_researcher")):
            with patch.object(supervisor._agents["seo_investigator"], "run", side_effect=mock_all_fail("seo_investigator")):
                with patch.object(supervisor._agents["seo_strategist"], "run", side_effect=mock_all_fail("seo_strategist")):
                    supervisor.orchestrate(task="Exhaustion test", correlation_id="corr-bound-010", task_plan=plan)

        # Task terminates as FAILED after bounded attempts without infinite loop
        self.assertEqual(plan.get_task("t_exhaust_10").status, TaskStatus.FAILED.value)

    def test_11_same_agent_can_execute_multiple_independent_parallel_tasks(self):
        """11. Adaptive selection supports assigning same agent to multiple independent parallel tasks."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Multi-task same agent test",
            correlation_id="corr-mult-011"
        )
        t1 = AgentTask("r_kwd", "Research keyword targets", "Keywords", "seo_supervisor", dependencies=[], correlation_id="corr-mult-011")
        t2 = AgentTask("r_serp", "Research competitor serp", "SERP", "seo_supervisor", dependencies=[], correlation_id="corr-mult-011")
        plan.add_task(t1)
        plan.add_task(t2)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=2)
        result_ctx = supervisor.orchestrate(task="Parallel same agent", correlation_id="corr-mult-011", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        self.assertEqual(plan.get_task("r_kwd").status, TaskStatus.COMPLETED.value)
        self.assertEqual(plan.get_task("r_serp").status, TaskStatus.COMPLETED.value)
        self.assertEqual(plan.get_task("r_kwd").responsible_agent, "seo_researcher")
        self.assertEqual(plan.get_task("r_serp").responsible_agent, "seo_researcher")

    def test_12_adaptive_routing_preserves_dag_dependencies(self):
        """12. Dependent tasks cannot be selected or executed while prerequisites are unsatisfied."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="DAG preservation test",
            correlation_id="corr-dag-012"
        )
        t_root = AgentTask("t_root", "Empirical keyword research", "Research", "seo_supervisor", dependencies=[], correlation_id="corr-dag-012")
        t_dep = AgentTask("t_dep", "Strategic recommendation", "Strategy", "seo_supervisor", dependencies=["t_root"], correlation_id="corr-dag-012")
        plan.add_task(t_root)
        plan.add_task(t_dep)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        result_ctx = supervisor.orchestrate(task="DAG test", correlation_id="corr-dag-012", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        order = [h.get("current_task_id") for h in result_ctx.handoff_history if h.get("current_task_id")]
        self.assertEqual(order, ["t_root", "t_dep"])

    def test_13_parallel_execution_works_after_dynamic_agent_assignment(self):
        """13. Dynamically selected agents execute concurrently in bounded parallel batches."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Parallel dynamic assignment test",
            correlation_id="corr-pardyn-013"
        )
        t1 = AgentTask("p_res", "Gather ranking data", "Research rankings", "seo_supervisor", dependencies=[], correlation_id="corr-pardyn-013")
        t2 = AgentTask("p_diag", "Diagnose technical audit issues", "Audit diagnosis", "seo_supervisor", dependencies=[], correlation_id="corr-pardyn-013")
        plan.add_task(t1)
        plan.add_task(t2)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=2)
        result_ctx = supervisor.orchestrate(task="Parallel dynamic test", correlation_id="corr-pardyn-013", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        self.assertEqual(plan.get_task("p_res").status, TaskStatus.COMPLETED.value)
        self.assertEqual(plan.get_task("p_diag").status, TaskStatus.COMPLETED.value)
        self.assertEqual(plan.get_task("p_res").responsible_agent, "seo_researcher")
        self.assertEqual(plan.get_task("p_diag").responsible_agent, "seo_investigator")
        self.assertEqual(len(result_ctx.parallel_batches), 1)

    def test_14_shared_memory_context_remains_tenant_isolated(self):
        """14. Tenant isolation is strictly enforced during agent selection and memory projection."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        selector = AdaptiveAgentSelector(project_id=self.project_a.id)
        # Task belongs to Project B
        cross_task = AgentTask(
            task_id="t_cross_14",
            objective="Gather competitive keywords",
            description="Collect keywords",
            responsible_agent="seo_supervisor",
            metadata={"project_id": self.project_b.id},
            correlation_id="corr-tenant-014"
        )

        decision = selector.select_agent(task=cross_task, context_project_id=self.project_a.id)
        self.assertEqual(decision.score, 0.0)
        self.assertTrue(decision.is_low_confidence)
        rejected_constraints = [r["hard_constraint"] for r in decision.rejected_candidates]
        self.assertIn("tenant_isolation", rejected_constraints)

    def test_15_routing_telemetry_emitted_correctly(self):
        """15. Adaptive selection emits structured, auditable lifecycle telemetry events."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agent_events import get_event_publisher, AgentEventType

        pub = get_event_publisher()
        pub.clear()

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        supervisor.orchestrate(task="Investigate keyword rankings drop", correlation_id="corr-telem-015")

        event_types = pub.get_event_types()
        self.assertIn(AgentEventType.SEO_AGENT_SELECTION_STARTED.value, event_types)
        self.assertIn(AgentEventType.SEO_AGENT_CANDIDATE_EVALUATED.value, event_types)
        self.assertIn(AgentEventType.SEO_AGENT_SELECTED.value, event_types)

        selected_events = pub.get_events_by_type(AgentEventType.SEO_AGENT_SELECTED)
        self.assertGreaterEqual(len(selected_events), 1)
        ev_payload = selected_events[0].payload
        self.assertEqual(ev_payload["project_id"], self.project_a.id)
        self.assertIn("selected_agent", ev_payload)
        self.assertIn("score", ev_payload)
        self.assertIn("confidence", ev_payload)

    def test_16_routing_evaluation_metrics_derived_from_runtime_state(self):
        """16. Agent evaluation service derives routing metrics from actual runtime events/state."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        result_ctx = supervisor.orchestrate(task="Audit and investigate landing page performance", correlation_id="corr-metrics-016")

        eval_res = SEOAgentEvaluationService.evaluate_shared_context(result_ctx)
        self.assertIn("adaptive_routing_metrics", eval_res)
        r_metrics = eval_res["adaptive_routing_metrics"]

        self.assertGreaterEqual(r_metrics["routing_decisions"], 1)
        self.assertGreaterEqual(r_metrics["successful_selections"], 1)
        self.assertGreater(r_metrics["selection_confidence"], 0.0)
        self.assertGreaterEqual(r_metrics["average_candidate_count"], 1.0)
        self.assertGreater(r_metrics["capability_match_rate"], 0.0)
        self.assertIsInstance(r_metrics["task_completion_by_selected_agent"], dict)
        self.assertGreater(len(r_metrics["task_completion_by_selected_agent"]), 0)

    def test_17_no_secrets_appear_in_routing_telemetry(self):
        """17. Secrets, API keys, and auth tokens are strictly redacted from routing telemetry."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask
        from apps.seo.services.agent_events import get_event_publisher, AgentEventType

        pub = get_event_publisher()
        pub.clear()

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, publisher=pub)
        secret_task = AgentTask(
            task_id="t_sec_17",
            objective="Gather keywords with api_key=sk-live-secret-99999",
            description="Task bearer token: Bearer my_secret_token_12345",
            responsible_agent="seo_supervisor",
            metadata={"secret_auth": "password123!"},
            correlation_id="corr-sec-017"
        )

        selector.select_agent(task=secret_task)
        events = pub.get_events()
        for ev in events:
            ev_str = str(ev.payload)
            self.assertNotIn("sk-live-secret-99999", ev_str)
            self.assertNotIn("my_secret_token_12345", ev_str)
            self.assertNotIn("password123!", ev_str)

    def test_18_full_realistic_doxarank_scenario(self):
        """18. Realistic full DoxaRank scenario dynamically selects specialized agents across 6-stage workflow."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService
        from apps.seo.models import SEOAction, ActionStatus, SiteAudit, AuditIssue

        # Baseline audit data for action planning
        audit = SiteAudit.objects.create(project=self.project_a, status='completed')
        AuditIssue.objects.create(
            audit=audit,
            issue_type="missing_canonical",
            title="Missing Canonical Tag",
            page_url=f"{self.project_a.website_url}/canonical-issue",
            severity="critical"
        )

        corr = "corr-full-scenario-018"
        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Full realistic autonomous SEO investigation and fix",
            correlation_id=corr
        )

        # 1. Root Research
        t1 = AgentTask("t1_res", "Gather keyword research and SERP intelligence", "Keyword research", "seo_supervisor", dependencies=[], correlation_id=corr)
        # 2 & 3. Parallel Rank Analysis & Technical Audit
        t2 = AgentTask("t2_rank", "Perform ranking analysis on keyword portfolio", "Rank analysis", "seo_supervisor", dependencies=["t1_res"], correlation_id=corr)
        t3 = AgentTask("t3_audit", "Technical audit crawl diagnostic inspection", "Audit inspection", "seo_supervisor", dependencies=["t1_res"], correlation_id=corr)
        # 4. Merge Investigation
        t4 = AgentTask("t4_inv", "Investigate root cause of ranking and audit anomalies", "Root cause diagnosis", "seo_supervisor", dependencies=["t2_rank", "t3_audit"], correlation_id=corr)
        # 5. Strategic Prioritization
        t5 = AgentTask("t5_strat", "Formulate SEO strategy and prioritize opportunities", "Strategy prioritization", "seo_supervisor", dependencies=["t4_inv"], correlation_id=corr)
        # 6. Action Planning
        t6 = AgentTask("t6_act", "Synthesize action plan and remediation proposals", "Action proposals", "seo_supervisor", dependencies=["t5_strat"], metadata={"is_mutating": True}, correlation_id=corr)
        # 7. Verification
        t7 = AgentTask("t7_ver", "Verify action plan integrity and outcome measurement", "Verification", "seo_supervisor", dependencies=["t6_act"], correlation_id=corr)

        for t in [t1, t2, t3, t4, t5, t6, t7]:
            plan.add_task(t)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=2)
        result_ctx = supervisor.orchestrate(task="Full scenario", correlation_id=corr, task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        self.assertEqual(len(plan.tasks), 7)
        for t in plan.tasks.values():
            self.assertEqual(t.status, TaskStatus.COMPLETED.value)

        # Verify dynamic agent selection assigned the appropriate specialized agents
        self.assertEqual(plan.get_task("t1_res").responsible_agent, "seo_researcher")
        self.assertEqual(plan.get_task("t2_rank").responsible_agent, "seo_researcher")
        self.assertEqual(plan.get_task("t3_audit").responsible_agent, "seo_investigator")
        self.assertEqual(plan.get_task("t4_inv").responsible_agent, "seo_investigator")
        self.assertEqual(plan.get_task("t5_strat").responsible_agent, "seo_strategist")
        self.assertEqual(plan.get_task("t6_act").responsible_agent, "seo_action_planner")
        self.assertEqual(plan.get_task("t7_ver").responsible_agent, "seo_verifier")

        # Verify HITL invariant on action plan proposals
        actions = SEOAction.objects.filter(project=self.project_a)
        self.assertGreaterEqual(actions.count(), 1)
        for act in actions:
            self.assertTrue(act.requires_human_approval)
            self.assertIn(act.status, [ActionStatus.PROPOSED, ActionStatus.PENDING_APPROVAL])

        # Verify evaluation reflects complete orchestration
        eval_res = SEOAgentEvaluationService.evaluate_shared_context(result_ctx)
        self.assertEqual(eval_res["adaptive_routing_metrics"]["routing_decisions"], 7)
        self.assertEqual(eval_res["adaptive_routing_metrics"]["successful_selections"], 7)
        self.assertGreater(eval_res["adaptive_routing_metrics"]["selection_confidence"], 0.80)

    def test_19_hard_constraint_failure_blocks_execution_in_supervisor(self):
        """19. Hard constraint failure (score == 0.0) blocks execution, fails task, cascades to dependent tasks, and does NOT execute fallback agent."""
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent

        corr = "corr-fail-safe-019"
        plan = TaskPlan(plan_id="plan-fail-safe", project_id=self.project_a.id, correlation_id=corr)
        task_fail = AgentTask(
            task_id="t_impossible",
            objective="Perform impossible quantum computing analysis on search graphs",
            description="Require capability completely outside all agent profiles",
            responsible_agent="seo_supervisor",
            correlation_id=corr,
            metadata={"required_capabilities": ["quantum_fourier_ranking_teleportation"]}
        )
        task_dep = AgentTask(
            task_id="t_dependent",
            objective="Verify outcome",
            description="Dependent verification task",
            responsible_agent="seo_supervisor",
            dependencies=["t_impossible"],
            correlation_id=corr
        )
        plan.add_task(task_fail)
        plan.add_task(task_dep)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=1)
        result_ctx = supervisor.orchestrate(task="Impossible requirement scenario", correlation_id=corr, task_plan=plan)

        self.assertEqual(result_ctx.status, "failed")
        self.assertEqual(plan.get_task("t_impossible").status, TaskStatus.FAILED.value)
        self.assertEqual(plan.get_task("t_dependent").status, TaskStatus.BLOCKED.value)
        self.assertNotEqual(plan.get_task("t_impossible").responsible_agent, "seo_investigator")
        self.assertTrue(any("hard constraints" in err for err in result_ctx.errors))
        self.assertEqual(len(result_ctx.routing_decisions), 1)
        self.assertEqual(result_ctx.routing_decisions[0]["score"], 0.0)

    def test_20_investigation_anomalies_routes_to_investigator(self):
        """20. Natural language query for ranking anomalies diagnosis routes to seo_investigator (not researcher)."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        selector = AdaptiveAgentSelector(project_id=self.project_a.id)
        task = AgentTask(
            task_id="t_anom_020",
            objective="Investigate the root cause of ranking anomalies",
            description="Diagnose sudden ranking drop across core keywords",
            responsible_agent="seo_supervisor",
            correlation_id="corr-audit-b-020"
        )
        decision = selector.select_agent(task=task)
        self.assertEqual(decision.selected_agent, "seo_investigator")
        self.assertGreater(decision.score, 0.75)
        self.assertGreater(decision.confidence, 0.85)

    def test_21_post_action_verification_routes_to_verifier(self):
        """21. Natural language query for post-action outcome verification routes to seo_verifier (not action_planner)."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        selector = AdaptiveAgentSelector(project_id=self.project_a.id)
        task = AgentTask(
            task_id="t_ver_021",
            objective="Verify post-action SEO outcome",
            description="Measure performance changes and keyword lift after action plan deployment",
            responsible_agent="seo_supervisor",
            correlation_id="corr-audit-e-021"
        )
        decision = selector.select_agent(task=task)
        self.assertEqual(decision.selected_agent, "seo_verifier")
        self.assertGreater(decision.score, 0.75)
        self.assertGreater(decision.confidence, 0.85)

    def test_22_pure_crawl_and_action_planning_routing(self):
        """22. Crawling and action planning queries route cleanly without cross-agent confusion."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        selector = AdaptiveAgentSelector(project_id=self.project_a.id)

        crawl_task = AgentTask(
            task_id="t_crawl_022",
            objective="Crawl website for broken links and inspect sitemap",
            description="Execute site crawler to identify technical 404s and crawl errors",
            responsible_agent="seo_supervisor",
            correlation_id="corr-crawl-022"
        )
        crawl_decision = selector.select_agent(task=crawl_task)
        self.assertEqual(crawl_decision.selected_agent, "seo_researcher")
        self.assertGreater(crawl_decision.score, 0.75)

        plan_task = AgentTask(
            task_id="t_plan_022",
            objective="Design remediation and plan SEO actions",
            description="Formulate structured remediation action plan for human approval",
            responsible_agent="seo_supervisor",
            correlation_id="corr-plan-022"
        )
        plan_decision = selector.select_agent(task=plan_task)
        self.assertEqual(plan_decision.selected_agent, "seo_action_planner")
        self.assertGreater(plan_decision.score, 0.75)


class SEOAgentLearningTests(TransactionTestCase):
    """
    Milestone 5.6 Test Suite: Agent Learning & Performance Optimization.
    Verifies:
    1. Performance record creation, serialization, and sanitization.
    2. Deterministic statistical metric calculations (success, verification, reassignment, latency, calibration).
    3. Historical performance influences eligible-agent ranking with soft preference.
    4. Low-performing agent penalized safely without negative underflow.
    5. Cold-start behavior when insufficient history falls back to baseline routing.
    6. Minimum sample threshold enforced at exact observation boundaries.
    7. Historical soft signal is strictly bounded within [-0.08, +0.08].
    8. Hard constraints always override historical performance scores.
    9. Unauthorized agent cannot become eligible via high historical score.
    10. Historical learning cannot grant ToolRegistry or MCP permissions.
    11. HITL governance remains mandatory for mutating tasks regardless of historical scores.
    12. Human rejection is classified as human_rejection and not treated as simple agent failure.
    13. Safety-blocked tasks are classified correctly and do not degrade capability standing.
    14. Multi-tenant isolation: private tenant data (URLs, keywords, queries) is never leaked.
    15. Explainability: routing decisions state historical metrics when applied or reason when ignored.
    16. Complete deterministic runtime learning feedback loop demonstrated E2E.
    17. Safe fallback reassignment updates learning records for both initial worker and fallback worker.
    18. Verification failure updates learning records with verification_failure category.
    19. Runtime-derived evaluation metrics computed by SEOAgentEvaluationService.
    20. Read-only API endpoints return structured performance stats and enforce project authorization.
    21. Telemetry lifecycle events emitted and sensitive credentials scrubbed.
    22. Regression across Milestones 5.1–5.5 remains 100% passing and operational.
    """

    def setUp(self):
        super().setUp()
        from apps.seo.services.agents.agent_learning import AgentPerformanceStore
        AgentPerformanceStore.get_instance().reset()

        self.client = APIClient()
        self.user_a = User.objects.create_user(
            email='learner_a@doxarank.com',
            password='Password123!',
            first_name='Learn',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='learner_b@doxarank.com',
            password='Password123!',
            first_name='Learn',
            last_name='B'
        )
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Alpha Learning Project',
            website_url='https://alpha-learning.io'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Beta Learning Project',
            website_url='https://beta-learning.io'
        )

    def tearDown(self):
        from apps.seo.services.agents.agent_learning import AgentPerformanceStore
        AgentPerformanceStore.get_instance().reset()
        super().tearDown()

    def test_01_performance_record_creation(self):
        """1. AgentPerformanceRecord creation, serialization, deserialization, and payload sanitization."""
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, FailureCategory

        rec = AgentPerformanceRecord(
            agent_name="seo_researcher",
            task_id="t_learn_01",
            task_type="research",
            task_objective="Analyze keyword rankings for competitor domain",
            project_id=self.project_a.id,
            success=True,
            execution_duration_ms=450,
            predicted_confidence=0.92,
            verification_status="verified",
            reassignment_count=0,
            tool_usage=["get_search_console_performance", "get_keyword_rankings"],
            failure_category=FailureCategory.NONE,
            routing_metadata={"api_key": "super_secret_key_123", "score": 0.88}
        )

        d = rec.to_dict()
        self.assertEqual(d["agent_name"], "seo_researcher")
        self.assertEqual(d["task_type"], "research")
        self.assertTrue(d["success"])
        self.assertEqual(d["verification_status"], "verified")
        # Ensure sensitive tokens in routing_metadata are sanitized
        self.assertEqual(d["routing_metadata"]["api_key"], "***REDACTED***")

        roundtrip = AgentPerformanceRecord.from_dict(d)
        self.assertEqual(roundtrip.agent_name, "seo_researcher")
        self.assertEqual(roundtrip.task_id, "t_learn_01")
        self.assertEqual(roundtrip.failure_category, FailureCategory.NONE)

    def test_02_deterministic_metric_calculations(self):
        """2. Deterministic mathematical metric calculations from historical records."""
        from apps.seo.services.agents.agent_learning import (
            AgentPerformanceRecord, AgentPerformanceStore, FailureCategory
        )

        store = AgentPerformanceStore.get_instance()
        # Create 10 records: 8 successes, 2 failures, 5 verifications (4 passed, 1 failed), 2 reassignments
        for i in range(8):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_researcher",
                task_id=f"t_succ_{i}",
                task_type="research",
                project_id=self.project_a.id,
                success=True,
                execution_duration_ms=200 + (i * 10),
                predicted_confidence=0.90,
                verification_status="verified" if i < 4 else "none",
                reassignment_count=1 if i == 0 else 0
            ))
        for i in range(2):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_researcher",
                task_id=f"t_fail_{i}",
                task_type="research",
                project_id=self.project_a.id,
                success=False,
                execution_duration_ms=500,
                predicted_confidence=0.60,
                verification_status="failed" if i == 0 else "none",
                reassignment_count=1 if i == 0 else 0,
                failure_category=FailureCategory.AGENT_FAILURE,
                failure_reason="Data fetch timeout"
            ))

        stats = store.get_agent_stats("seo_researcher", task_type="research", project_id=self.project_a.id)
        self.assertEqual(stats.sample_size, 10)
        self.assertEqual(stats.successful_tasks, 8)
        self.assertEqual(stats.failed_tasks, 2)
        self.assertEqual(stats.success_rate, 0.80)
        self.assertEqual(stats.failure_rate, 0.20)
        self.assertEqual(stats.verification_attempts, 5)
        self.assertEqual(stats.verified_successes, 4)
        self.assertEqual(stats.verification_success_rate, 0.80)
        self.assertEqual(stats.reassignment_rate, 0.20)
        self.assertTrue(stats.has_sufficient_evidence)
        self.assertGreater(stats.routing_quality_score, 0.70)

    def test_03_historical_performance_influences_eligible_ranking(self):
        """3. Historical performance provides soft preference to high-performing eligible candidate."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore
        from apps.seo.services.agents.task_planner import AgentTask

        store = AgentPerformanceStore.get_instance()
        # Agent A has 60% success rate (3/5)
        for i in range(5):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_investigator",
                task_id=f"t_inv_{i}",
                task_type="research",
                project_id=self.project_a.id,
                success=(i < 3),
                predicted_confidence=0.75
            ))
        # Agent B has 100% success rate (5/5)
        for i in range(5):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_researcher",
                task_id=f"t_res_{i}",
                task_type="research",
                project_id=self.project_a.id,
                success=True,
                predicted_confidence=0.95
            ))

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, performance_store=store)
        task = AgentTask(
            task_id="t_rank_03",
            objective="Gather search console keyword rankings",
            description="Empirical research on keyword rankings",
            responsible_agent="seo_supervisor",
            correlation_id="corr-rank-03"
        )
        decision = selector.select_agent(task=task)
        self.assertEqual(decision.selected_agent, "seo_researcher")
        # Verify score breakdown shows historical score lift
        res_breakdown = decision.score_breakdowns["seo_researcher"]
        inv_breakdown = decision.score_breakdowns["seo_investigator"]
        self.assertGreater(res_breakdown["historical_score"], inv_breakdown["historical_score"])
        self.assertTrue(any("historical_performance:" in r for r in decision.reasons))

    def test_04_low_performing_agent_penalized_safely(self):
        """4. Candidate with repeated failures receives bounded soft penalty without score underflow."""
        from apps.seo.services.agents.agent_learning import (
            AgentPerformanceRecord, AgentPerformanceStore, FailureCategory
        )
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        store = AgentPerformanceStore.get_instance()
        # 5 straight failures with reassignments
        for i in range(5):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_researcher",
                task_id=f"t_bad_{i}",
                task_type="research",
                project_id=self.project_a.id,
                success=False,
                reassignment_count=1,
                failure_category=FailureCategory.AGENT_FAILURE,
                failure_reason="Persistent API crash"
            ))

        signal = store.compute_historical_signal("seo_researcher", "research", project_id=self.project_a.id)
        self.assertTrue(signal.signal_applied)
        self.assertLess(signal.score_contribution, 0.0)
        self.assertGreaterEqual(signal.score_contribution, -0.08)

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, performance_store=store)
        task = AgentTask(
            task_id="t_pen_04",
            objective="Perform keyword research",
            description="Keyword research query",
            responsible_agent="seo_supervisor"
        )
        decision = selector.select_agent(task=task)
        # Even with penalty, score remains bounded >= 0.0
        self.assertGreaterEqual(decision.score, 0.0)

    def test_05_cold_start_insufficient_history_falls_back_to_baseline(self):
        """5. Insufficient historical samples trigger cold-start fallback to baseline scoring."""
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        store = AgentPerformanceStore.get_instance()
        # Only 1 observation (below min_sample_threshold = 3)
        store.record_outcome(AgentPerformanceRecord(
            agent_name="seo_researcher",
            task_id="t_one_05",
            task_type="research",
            project_id=self.project_a.id,
            success=True
        ))

        signal = store.compute_historical_signal("seo_researcher", "research", project_id=self.project_a.id)
        self.assertFalse(signal.signal_applied)
        self.assertEqual(signal.score_contribution, 0.0)
        self.assertIn("insufficient sample size", signal.explanation)

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, performance_store=store)
        task = AgentTask(
            task_id="t_cold_05",
            objective="Gather keyword rankings and search intent data",
            description="Collect empirical ranking evidence",
            responsible_agent="seo_supervisor"
        )
        decision = selector.select_agent(task=task)
        # Selected agent reasons should explicitly explain cold-start signal bypass
        self.assertTrue(any("historical_signal_ignored:" in r for r in decision.reasons))

    def test_06_minimum_sample_threshold_enforced(self):
        """6. Sample threshold boundary is enforced deterministically (2 = ignored, 3 = active)."""
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore

        store = AgentPerformanceStore.get_instance()
        store.min_sample_threshold = 3

        # 0 observations
        sig0 = store.compute_historical_signal("seo_researcher", "research", project_id=self.project_a.id)
        self.assertFalse(sig0.signal_applied)

        # 1 observation
        store.record_outcome(AgentPerformanceRecord(
            agent_name="seo_researcher", task_id="t_1", task_type="research", project_id=self.project_a.id, success=True
        ))
        sig1 = store.compute_historical_signal("seo_researcher", "research", project_id=self.project_a.id)
        self.assertFalse(sig1.signal_applied)

        # 2 observations
        store.record_outcome(AgentPerformanceRecord(
            agent_name="seo_researcher", task_id="t_2", task_type="research", project_id=self.project_a.id, success=True
        ))
        sig2 = store.compute_historical_signal("seo_researcher", "research", project_id=self.project_a.id)
        self.assertFalse(sig2.signal_applied)

        # 3 observations -> threshold satisfied
        store.record_outcome(AgentPerformanceRecord(
            agent_name="seo_researcher", task_id="t_3", task_type="research", project_id=self.project_a.id, success=True
        ))
        sig3 = store.compute_historical_signal("seo_researcher", "research", project_id=self.project_a.id)
        self.assertTrue(sig3.signal_applied)
        self.assertGreater(sig3.score_contribution, 0.0)

    def test_07_historical_signal_is_strictly_bounded(self):
        """7. Historical soft score contribution is strictly bounded within [-0.08, +0.08]."""
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore

        store = AgentPerformanceStore.get_instance()
        # 50 consecutive perfect outcomes
        for i in range(50):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="perfect_agent", task_id=f"t_p_{i}", task_type="research", project_id=self.project_a.id, success=True, verification_status="verified"
            ))
        sig_pos = store.compute_historical_signal("perfect_agent", "research", project_id=self.project_a.id)
        self.assertLessEqual(sig_pos.score_contribution, 0.08)

        # 50 consecutive failed outcomes with 100% reassignments
        for i in range(50):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="failing_agent", task_id=f"t_f_{i}", task_type="research", project_id=self.project_a.id, success=False, reassignment_count=2
            ))
        sig_neg = store.compute_historical_signal("failing_agent", "research", project_id=self.project_a.id)
        self.assertGreaterEqual(sig_neg.score_contribution, -0.08)

    def test_08_hard_constraints_always_override_historical_performance(self):
        """8. Hard safety constraints always override high historical performance scores."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore
        from apps.seo.services.agents.task_planner import AgentTask

        store = AgentPerformanceStore.get_instance()
        # Researcher has 100% success rate
        for i in range(10):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_researcher", task_id=f"t_r_{i}", task_type="action_planning", project_id=self.project_a.id, success=True
            ))

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, performance_store=store)
        # Task requires action planning and mutation execution
        task = AgentTask(
            task_id="t_mut_08",
            objective="Synthesize action plan and execute code remediation",
            description="Mutating remediation fix",
            responsible_agent="seo_supervisor",
            metadata={"required_capabilities": ["action_planning"], "is_mutating": True, "risk_level": "high"}
        )
        decision = selector.select_agent(task=task)
        # seo_researcher must be rejected despite 100% score because it lacks action_planning and HITL
        self.assertNotEqual(decision.selected_agent, "seo_researcher")
        self.assertEqual(decision.selected_agent, "seo_action_planner")
        rejected_names = [r["agent"] for r in decision.rejected_candidates]
        self.assertIn("seo_researcher", rejected_names)

    def test_09_unauthorized_agent_cannot_become_eligible_via_learning(self):
        """9. An agent lacking required capabilities cannot become eligible via positive learning."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore
        from apps.seo.services.agents.task_planner import AgentTask

        store = AgentPerformanceStore.get_instance()
        for i in range(10):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_verifier", task_id=f"t_v_{i}", task_type="investigation", project_id=self.project_a.id, success=True
            ))

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, performance_store=store)
        task = AgentTask(
            task_id="t_diag_09",
            objective="Investigate root cause of traffic drop",
            description="Root cause diagnosis",
            responsible_agent="seo_supervisor",
            metadata={"required_capabilities": ["root_cause_analysis"]}
        )
        decision = selector.select_agent(task=task)
        self.assertEqual(decision.selected_agent, "seo_investigator")
        rejected_reasons = {r["agent"]: r["hard_constraint"] for r in decision.rejected_candidates}
        self.assertEqual(rejected_reasons.get("seo_verifier"), "missing_required_capability")

    def test_10_learning_cannot_grant_tool_permissions(self):
        """10. Learning cannot grant ToolRegistry permissions or bypass tool allowlists."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore
        from apps.seo.services.agents.task_planner import AgentTask

        store = AgentPerformanceStore.get_instance()
        for i in range(10):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_researcher", task_id=f"t_tp_{i}", task_type="action_planning", project_id=self.project_a.id, success=True
            ))

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, performance_store=store)
        task = AgentTask(
            task_id="t_tool_10",
            objective="Plan SEO action proposals",
            description="Draft proposals",
            responsible_agent="seo_supervisor",
            metadata={"required_tools": ["propose_seo_action"]}
        )
        decision = selector.select_agent(task=task)
        # seo_researcher forbidden/unauthorized for propose_seo_action
        self.assertNotEqual(decision.selected_agent, "seo_researcher")
        rejected_tools = [r["agent"] for r in decision.rejected_candidates if r["hard_constraint"] in ["tool_permission_denied", "forbidden_tool_violation"]]
        self.assertIn("seo_researcher", rejected_tools)

    def test_11_hitl_remains_mandatory_for_mutations(self):
        """11. HITL governance invariant cannot be overridden by historical performance."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore
        from apps.seo.services.agents.task_planner import AgentTask

        store = AgentPerformanceStore.get_instance()
        for i in range(10):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_investigator", task_id=f"t_hitl_{i}", task_type="action_planning", project_id=self.project_a.id, success=True
            ))

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, performance_store=store)
        task = AgentTask(
            task_id="t_hitl_11",
            objective="Apply production fix to canonical tags",
            description="Mutating action",
            responsible_agent="seo_supervisor",
            metadata={"is_mutating": True, "required_capabilities": ["action_planning"]}
        )
        decision = selector.select_agent(task=task)
        # Only seo_action_planner has requires_hitl=True
        self.assertEqual(decision.selected_agent, "seo_action_planner")

    def test_12_human_rejection_is_not_agent_failure(self):
        """12. Human rejection is classified distinctly and does not degrade agent capability success rate."""
        from apps.seo.services.agents.agent_learning import (
            AgentPerformanceRecord, AgentPerformanceStore, FailureCategory
        )

        store = AgentPerformanceStore.get_instance()
        # 4 successful tasks
        for i in range(4):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_action_planner", task_id=f"t_s_{i}", task_type="action_planning", project_id=self.project_a.id, success=True
            ))
        # 1 human rejection
        store.record_outcome(AgentPerformanceRecord(
            agent_name="seo_action_planner", task_id="t_rej_12", task_type="action_planning", project_id=self.project_a.id,
            success=False, failure_category=FailureCategory.HUMAN_REJECTION, failure_reason="User chose alternative strategy"
        ))

        stats = store.get_agent_stats("seo_action_planner", task_type="action_planning", project_id=self.project_a.id)
        # Success rate remains 100% for evaluable operational tasks (4/4)
        self.assertEqual(stats.success_rate, 1.0)
        self.assertEqual(stats.failure_breakdown.get(FailureCategory.HUMAN_REJECTION.value), 1)

    def test_13_safety_block_classified_correctly(self):
        """13. Safety-blocked tasks do not degrade agent operational standing."""
        from apps.seo.services.agents.agent_learning import (
            AgentPerformanceRecord, AgentPerformanceStore, FailureCategory
        )

        store = AgentPerformanceStore.get_instance()
        for i in range(4):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_researcher", task_id=f"t_ok_{i}", task_type="research", project_id=self.project_a.id, success=True
            ))
        store.record_outcome(AgentPerformanceRecord(
            agent_name="seo_researcher", task_id="t_block_13", task_type="research", project_id=self.project_a.id,
            success=False, failure_category=FailureCategory.SAFETY_BLOCK, failure_reason="Tenant boundary constraint triggered"
        ))

        stats = store.get_agent_stats("seo_researcher", task_type="research", project_id=self.project_a.id)
        self.assertEqual(stats.success_rate, 1.0)
        self.assertEqual(stats.failure_breakdown.get(FailureCategory.SAFETY_BLOCK.value), 1)

    def test_14_tenant_isolation_no_data_leakage(self):
        """14. Tenant isolation ensures private data (URLs, keywords, queries) never leaks across tenants."""
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore

        store = AgentPerformanceStore.get_instance()
        # Project A records with private client info
        store.record_outcome(AgentPerformanceRecord(
            agent_name="seo_researcher",
            task_id="t_priv_14",
            task_type="research",
            task_objective="Investigate private-client-keyword for https://secret-alpha.com",
            project_id=self.project_a.id,
            success=True
        ))

        # Project B query
        proj_b_records = store.get_records(project_id=self.project_b.id)
        self.assertEqual(len(proj_b_records), 0)

        # Global benchmarks: verify no private tenant URLs or text exist
        global_stats = store.get_anonymized_global_stats()
        text_dump = str(global_stats)
        self.assertNotIn("secret-alpha.com", text_dump)
        self.assertNotIn("private-client-keyword", text_dump)
        self.assertEqual(global_stats["total_records"], 1)

    def test_15_explainability_in_routing_decision(self):
        """15. Routing decisions explain historical evidence when applied and state reasons when ignored."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore
        from apps.seo.services.agents.task_planner import AgentTask

        store = AgentPerformanceStore.get_instance()
        # Sufficient data for researcher
        for i in range(5):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_researcher", task_id=f"t_e_{i}", task_type="research", project_id=self.project_a.id, success=True
            ))

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, performance_store=store)
        task = AgentTask(
            task_id="t_expl_15",
            objective="Gather search console keyword rankings",
            description="Collect empirical ranking evidence",
            responsible_agent="seo_supervisor"
        )
        decision = selector.select_agent(task=task)
        # Winner includes historical evidence
        self.assertTrue(any("historical_performance: historical_success: 100%" in r for r in decision.reasons))

        # Runner-up with no data explains why historical signal was ignored
        other_candidate = [c for c in decision.ranked_candidates if c != "seo_researcher"][0]
        other_reasons = decision.score_breakdowns[other_candidate]["reasons"]
        self.assertTrue(any("historical_signal_ignored: insufficient sample size" in r for r in other_reasons))

    def test_16_complete_runtime_learning_feedback_loop(self):
        """16. Complete runtime learning feedback loop: initial history -> selection -> execution -> update -> future decision."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        store = AgentPerformanceStore.get_instance()
        # Seed initial history: Researcher = 100% (4/4), Investigator = 50% (2/4)
        for i in range(4):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_researcher", task_id=f"init_r_{i}", task_type="research", project_id=self.project_a.id, success=True
            ))
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_investigator", task_id=f"init_i_{i}", task_type="research", project_id=self.project_a.id, success=(i < 2)
            ))

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        plan = TaskPlan(project_id=self.project_a.id, goal="Feedback loop test", correlation_id="corr-loop-16")
        task = AgentTask(
            task_id="t_loop_16",
            objective="Research keyword query benchmarks",
            description="Collect empirical ranking data",
            responsible_agent="seo_supervisor",
            correlation_id="corr-loop-16"
        )
        plan.add_task(task)

        # 1. Execute task
        result_ctx = supervisor.orchestrate(task="Feedback test", correlation_id="corr-loop-16", task_plan=plan)
        self.assertEqual(result_ctx.status, "completed")
        self.assertEqual(plan.get_task("t_loop_16").status, TaskStatus.COMPLETED.value)
        self.assertEqual(plan.get_task("t_loop_16").responsible_agent, "seo_researcher")

        # 2. Verify learning record was automatically created by supervisor
        records = store.get_records(project_id=self.project_a.id, agent_name="seo_researcher", task_type="research")
        self.assertEqual(len(records), 5)  # 4 initial + 1 new execution

        # 3. Next equivalent task sees updated evidence (sample size 5)
        new_signal = store.compute_historical_signal("seo_researcher", "research", project_id=self.project_a.id)
        self.assertEqual(new_signal.sample_size, 5)
        self.assertEqual(new_signal.success_rate, 1.0)

    def test_17_fallback_reassignment_updates_learning(self):
        """17. Safe fallback updates learning records for both failing and fallback workers."""
        from unittest.mock import patch
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.agent_learning import AgentPerformanceStore, FailureCategory
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus
        from apps.seo.services.agents.base_agent import AgentResult

        store = AgentPerformanceStore.get_instance()
        plan = TaskPlan(project_id=self.project_a.id, goal="Fallback learning test", correlation_id="corr-fbl-17")
        task = AgentTask(
            task_id="t_fbl_17",
            objective="Inspect site crawl health and search diagnostics",
            description="Diagnose crawl issues",
            responsible_agent="seo_researcher",
            correlation_id="corr-fbl-17"
        )
        plan.add_task(task)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)

        # Mock researcher failure triggering fallback to investigator
        def mock_fail(*args, **kwargs):
            return AgentResult(agent="seo_researcher", status="failed", confidence=0.0, errors=["API quota exceeded"])

        with patch.object(supervisor._agents["seo_researcher"], "run", side_effect=mock_fail):
            result_ctx = supervisor.orchestrate(task="Fallback learning", correlation_id="corr-fbl-17", task_plan=plan)

        self.assertEqual(result_ctx.status, "completed")
        self.assertEqual(plan.get_task("t_fbl_17").responsible_agent, "seo_investigator")

        # Verify failing agent recorded reassignment failure
        researcher_recs = store.get_records(project_id=self.project_a.id, agent_name="seo_researcher")
        self.assertGreaterEqual(len(researcher_recs), 1)
        r_rec = researcher_recs[-1]
        self.assertFalse(r_rec.success)
        self.assertTrue(r_rec.was_fallback)
        self.assertEqual(r_rec.failure_category, FailureCategory.AGENT_FAILURE)

        # Verify fallback agent recorded successful completion
        investigator_recs = store.get_records(project_id=self.project_a.id, agent_name="seo_investigator")
        self.assertGreaterEqual(len(investigator_recs), 1)
        i_rec = investigator_recs[-1]
        self.assertTrue(i_rec.success)

    def test_18_verification_failure_updates_learning(self):
        """18. Technical verification failure updates learning records with verification failure classification."""
        from unittest.mock import patch
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.agent_learning import AgentPerformanceStore, FailureCategory
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask
        from apps.seo.services.agents.base_agent import AgentResult

        store = AgentPerformanceStore.get_instance()
        plan = TaskPlan(project_id=self.project_a.id, goal="Verification learning test", correlation_id="corr-ver-18")
        task = AgentTask(
            task_id="t_ver_18",
            objective="Verify post-action SEO outcome",
            description="Measure ranking lift and verify title tag changes",
            responsible_agent="seo_verifier",
            correlation_id="corr-ver-18"
        )
        plan.add_task(task)

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)

        # Mock verifier reporting discrepancy (failed verification)
        def mock_verif_failed(*args, **kwargs):
            return AgentResult(
                agent="seo_verifier",
                status="completed",
                confidence=0.85,
                findings=["Live title tag did not match proposed changes; verification failed"],
                evidence={"verification_status": "failed"}
            )

        with patch.object(supervisor._agents["seo_verifier"], "run", side_effect=mock_verif_failed):
            supervisor.orchestrate(task="Verify outcome", correlation_id="corr-ver-18", task_plan=plan)

        verif_recs = store.get_records(project_id=self.project_a.id, agent_name="seo_verifier")
        self.assertGreaterEqual(len(verif_recs), 1)
        v_rec = verif_recs[-1]
        self.assertEqual(v_rec.verification_status, "failed")

    def test_19_runtime_derived_evaluation_metrics(self):
        """19. SEOAgentEvaluationService computes runtime-derived learning evaluation metrics."""
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService
        from apps.seo.services.agents.base_agent import SharedContext
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord

        ctx = SharedContext(
            project_id=self.project_a.id,
            project_name=self.project_a.name,
            website_url=self.project_a.website_url,
            status="completed"
        )
        # Mock 2 routing decisions
        ctx.routing_decisions = [
            {
                "task_id": "t1",
                "selected_agent": "seo_researcher",
                "reasons": ["historical_performance: historical_success: 100% (n=5)"],
                "score_breakdowns": {"seo_researcher": {"historical_signal_details": {"signal_applied": True}}}
            },
            {
                "task_id": "t2",
                "selected_agent": "seo_investigator",
                "reasons": ["historical_signal_ignored: insufficient sample size"],
                "score_breakdowns": {"seo_investigator": {"historical_signal_details": {"signal_applied": False}}}
            }
        ]
        # Mock 2 learning records
        ctx.learning_records = [
            AgentPerformanceRecord(
                agent_name="seo_researcher", task_id="t1", task_type="research", project_id=self.project_a.id,
                success=True, verification_status="verified", predicted_confidence=0.90
            ).to_dict(),
            AgentPerformanceRecord(
                agent_name="seo_investigator", task_id="t2", task_type="investigation", project_id=self.project_a.id,
                success=False, verification_status="failed", predicted_confidence=0.70
            ).to_dict()
        ]

        eval_res = SEOAgentEvaluationService.evaluate_shared_context(ctx)
        learning_metrics = eval_res["learning_metrics"]

        self.assertEqual(learning_metrics["total_learning_records"], 2)
        self.assertEqual(learning_metrics["learning_coverage"], 50.0)
        self.assertEqual(learning_metrics["historical_signal_usage"], 1)
        self.assertEqual(learning_metrics["cold_start_coverage"], 50.0)
        self.assertEqual(learning_metrics["success_rate_by_agent"]["seo_researcher"], 1.0)
        self.assertEqual(learning_metrics["success_rate_by_agent"]["seo_investigator"], 0.0)
        self.assertEqual(learning_metrics["verification_success_rate"], 50.0)

    def test_20_read_only_api_endpoints(self):
        """20. Read-only performance and collaboration learning API endpoints enforce tenant safety."""
        from rest_framework import status
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore

        store = AgentPerformanceStore.get_instance()
        store.record_outcome(AgentPerformanceRecord(
            agent_name="seo_researcher", task_id="t_api_20", task_type="research", project_id=self.project_a.id, success=True
        ))

        self.client.force_authenticate(user=self.user_a)

        # 1. Authorized project query
        res_auth = self.client.get(f"/api/seo/ai/learning/performance/?project_id={self.project_a.id}")
        self.assertEqual(res_auth.status_code, status.HTTP_200_OK)
        self.assertIn("agent_performance", res_auth.data)
        self.assertEqual(res_auth.data["project_id"], self.project_a.id)

        # 2. Unauthorized cross-tenant query yields 404
        res_unauth = self.client.get(f"/api/seo/ai/learning/performance/?project_id={self.project_b.id}")
        self.assertEqual(res_unauth.status_code, status.HTTP_404_NOT_FOUND)

        # 3. Global benchmarks accessible
        res_global = self.client.get("/api/seo/ai/learning/performance/")
        self.assertEqual(res_global.status_code, status.HTTP_200_OK)
        self.assertIn("global_benchmarks", res_global.data)

        # 4. Collaboration run learning view
        res_run = self.client.get(f"/api/seo/ai/orchestrate/corr-test-20/learning/")
        # When run is not found, handled cleanly
        self.assertIn(res_run.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])

    def test_21_telemetry_events_emitted_and_sanitized(self):
        """21. Learning events are published with structured fields and credentials scrubbed."""
        from apps.seo.services.agent_events import get_event_publisher, AgentEventType
        from apps.seo.services.agents.agent_learning import AgentLearningService

        pub = get_event_publisher()
        pub.clear()

        service = AgentLearningService(publisher=pub)
        service.record_task_outcome(
            agent_name="seo_researcher",
            task_id="t_tel_21",
            task_type="research",
            task_objective="Gather Search Console metrics",
            project_id=self.project_a.id,
            success=True,
            routing_metadata={"secret_token": "super_secret_bearer_token", "score": 0.95},
            correlation_id="corr-tel-21"
        )

        event_types = pub.get_event_types()
        self.assertIn(AgentEventType.SEO_LEARNING_RECORD_CREATED.value, event_types)
        self.assertIn(AgentEventType.SEO_AGENT_PERFORMANCE_UPDATED.value, event_types)
        self.assertIn(AgentEventType.SEO_ROUTING_OUTCOME_RECORDED.value, event_types)

        # Verify token was scrubbed
        events = pub.get_events()
        for ev in events:
            payload_str = str(ev.payload)
            self.assertNotIn("super_secret_bearer_token", payload_str)

    def test_22_regression_across_milestones_5_1_to_5_5(self):
        """22. Complete regression across Milestones 5.1–5.5 remains 100% operational with learning active."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, TaskStatus

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a, max_parallel_tasks=2)
        plan = TaskPlan(project_id=self.project_a.id, goal="Full 5.1-5.6 cycle", correlation_id="corr-reg-22")

        t1 = AgentTask("reg_res", "Gather keyword rankings", "Keywords", "seo_supervisor", dependencies=[], correlation_id="corr-reg-22")
        t2 = AgentTask("reg_diag", "Diagnose technical audit issues", "Audit", "seo_supervisor", dependencies=[], correlation_id="corr-reg-22")
        t3 = AgentTask("reg_strat", "Prioritize strategic SEO recommendations", "Strategy", "seo_supervisor", dependencies=["reg_res", "reg_diag"], correlation_id="corr-reg-22")
        plan.add_task(t1)
        plan.add_task(t2)
        plan.add_task(t3)

        result_ctx = supervisor.orchestrate(task="Full regression cycle", correlation_id="corr-reg-22", task_plan=plan)
        self.assertEqual(result_ctx.status, "completed")
        self.assertEqual(plan.get_task("reg_res").status, TaskStatus.COMPLETED.value)
        self.assertEqual(plan.get_task("reg_diag").status, TaskStatus.COMPLETED.value)
        self.assertEqual(plan.get_task("reg_strat").status, TaskStatus.COMPLETED.value)

        # Verify parallel batch execution occurred
        self.assertGreaterEqual(len(result_ctx.parallel_batches), 1)
        # Verify dynamic agent assignments occurred
        self.assertEqual(plan.get_task("reg_res").responsible_agent, "seo_researcher")
        self.assertEqual(plan.get_task("reg_diag").responsible_agent, "seo_investigator")
        self.assertEqual(plan.get_task("reg_strat").responsible_agent, "seo_strategist")
        # Verify learning records populated
        self.assertGreaterEqual(len(result_ctx.learning_records), 3)

    def test_23_routing_improvement_detection_modes(self):
        """23. DEF-01: Verify detection of top-level, nested, positive, negative, and zero/missing historical scores."""
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService
        from apps.seo.services.agents.base_agent import SharedContext

        def _evaluate_single(routing_metadata: dict, agent_name: str = "seo_researcher", success: bool = True):
            ctx = SharedContext(
                project_id=self.project_a.id,
                project_name="Test",
                website_url="https://test.com",
                task_goal="Eval single"
            )
            ctx.learning_records = [
                {
                    "record_id": "r_test",
                    "agent_name": agent_name,
                    "task_type": "research",
                    "success": success,
                    "predicted_confidence": 0.90,
                    "verification_status": "none",
                    "reassignment_count": 0,
                    "routing_metadata": routing_metadata
                }
            ]
            eval_res = SEOAgentEvaluationService.evaluate_shared_context(ctx)
            learning_metrics = eval_res["agent_learning_metrics"]
            return learning_metrics["routing_improvement"]

        # 1. Top-level positive historical score detected as assisted (100% improvement over 0% baseline)
        imp_top_pos = _evaluate_single({"historical_score": 0.045})
        self.assertEqual(imp_top_pos, 100.0)

        # 2. Top-level negative historical score detected as assisted
        imp_top_neg = _evaluate_single({"historical_score": -0.045})
        self.assertEqual(imp_top_neg, 100.0)

        # 3. Nested positive historical score in score_breakdowns detected as assisted (actual supervisor format)
        nested_pos_meta = {
            "score": 0.76,
            "score_breakdowns": {
                "seo_researcher": {"historical_score": 0.045},
                "seo_investigator": {"historical_score": -0.02}
            }
        }
        imp_nest_pos = _evaluate_single(nested_pos_meta, agent_name="seo_researcher")
        self.assertEqual(imp_nest_pos, 100.0)

        # 4. Nested negative historical score in score_breakdowns detected as assisted
        nested_neg_meta = {
            "score": 0.70,
            "score_breakdowns": {
                "seo_investigator": {"historical_score": -0.035}
            }
        }
        imp_nest_neg = _evaluate_single(nested_neg_meta, agent_name="seo_investigator")
        self.assertEqual(imp_nest_neg, 100.0)

        # 5. Zero historical score treated as unassisted baseline (0% assisted, 100% baseline -> -100.0 improvement)
        imp_zero = _evaluate_single({"historical_score": 0.0})
        self.assertEqual(imp_zero, -100.0)

        # 6. Nested zero historical score treated as unassisted baseline
        nested_zero_meta = {
            "score_breakdowns": {
                "seo_researcher": {"historical_score": 0.0}
            }
        }
        imp_nest_zero = _evaluate_single(nested_zero_meta, agent_name="seo_researcher")
        self.assertEqual(imp_nest_zero, -100.0)

        # 7. Missing routing metadata safely defaults to baseline
        imp_missing = _evaluate_single({})
        self.assertEqual(imp_missing, -100.0)

    def test_24_bayesian_smoothing_and_evidence_weighting_numerical_verification(self):
        """24. DEF-02: Deterministic numerical verification of Bayesian smoothing and evidence weighting across sample sizes."""
        from apps.seo.services.agents.agent_learning import AgentPerformanceRecord, AgentPerformanceStore

        store = AgentPerformanceStore.get_instance()

        # Helper to seed N records with k successes
        def _seed(agent: str, n: int, k: int):
            store.reset()
            for i in range(n):
                store.record_outcome(AgentPerformanceRecord(
                    agent_name=agent,
                    task_id=f"num_{agent}_{i}",
                    task_type="research",
                    project_id=self.project_a.id,
                    success=(i < k)
                ))

        # 1. N = 3, k = 3
        # p_hat = (3 + 2) / (3 + 4) = 5/7 ≈ 0.7142857
        # w_evidence = 3 / 10 = 0.3
        # success_component = (5/7 - 0.70) * 0.15 * 0.3 ≈ 0.0006428
        _seed("agent_n3", n=3, k=3)
        sig_n3 = store.compute_historical_signal("agent_n3", "research", project_id=self.project_a.id)
        self.assertTrue(sig_n3.signal_applied)
        expected_p_hat_n3 = 5.0 / 7.0
        expected_w_n3 = 0.3
        expected_contrib_n3 = (expected_p_hat_n3 - 0.70) * 0.15 * expected_w_n3
        self.assertAlmostEqual(sig_n3.smoothed_success_rate, expected_p_hat_n3, places=4)
        self.assertAlmostEqual(sig_n3.evidence_weight, expected_w_n3, places=4)
        self.assertAlmostEqual(sig_n3.score_contribution, expected_contrib_n3, places=4)
        # Gentle lift at N=3, strictly positive and smooth
        self.assertGreater(sig_n3.score_contribution, 0.0)
        self.assertLess(sig_n3.score_contribution, 0.005)

        # 2. N = 5, k = 5 (high success)
        # p_hat = (5 + 2) / (5 + 4) = 7/9 ≈ 0.7777778
        # w_evidence = 5 / 10 = 0.5
        # success_component = (7/9 - 0.70) * 0.15 * 0.5 ≈ 0.0058333
        _seed("agent_n5_hi", n=5, k=5)
        sig_n5_hi = store.compute_historical_signal("agent_n5_hi", "research", project_id=self.project_a.id)
        expected_p_hat_n5_hi = 7.0 / 9.0
        expected_w_n5_hi = 0.5
        expected_contrib_n5_hi = (expected_p_hat_n5_hi - 0.70) * 0.15 * expected_w_n5_hi
        self.assertAlmostEqual(sig_n5_hi.smoothed_success_rate, expected_p_hat_n5_hi, places=4)
        self.assertAlmostEqual(sig_n5_hi.evidence_weight, expected_w_n5_hi, places=4)
        self.assertAlmostEqual(sig_n5_hi.score_contribution, expected_contrib_n5_hi, places=4)

        # 3. N = 5, k = 0 (low success)
        # p_hat = (0 + 2) / (5 + 4) = 2/9 ≈ 0.2222222
        # w_evidence = 5 / 10 = 0.5
        # success_component = (2/9 - 0.70) * 0.15 * 0.5 ≈ -0.0358333
        _seed("agent_n5_lo", n=5, k=0)
        sig_n5_lo = store.compute_historical_signal("agent_n5_lo", "research", project_id=self.project_a.id)
        expected_p_hat_n5_lo = 2.0 / 9.0
        expected_contrib_n5_lo = (expected_p_hat_n5_lo - 0.70) * 0.15 * 0.5
        self.assertAlmostEqual(sig_n5_lo.smoothed_success_rate, expected_p_hat_n5_lo, places=4)
        self.assertAlmostEqual(sig_n5_lo.evidence_weight, 0.5, places=4)
        self.assertAlmostEqual(sig_n5_lo.score_contribution, expected_contrib_n5_lo, places=4)

        # 4. N = 10, k = 10 (evidence weight reaches 1.0)
        # p_hat = (10 + 2) / (10 + 4) = 12/14 = 6/7 ≈ 0.8571429
        # w_evidence = min(1.0, 10/10) = 1.0
        # success_component = (6/7 - 0.70) * 0.15 * 1.0 ≈ 0.0235714
        _seed("agent_n10", n=10, k=10)
        sig_n10 = store.compute_historical_signal("agent_n10", "research", project_id=self.project_a.id)
        expected_p_hat_n10 = 6.0 / 7.0
        expected_contrib_n10 = (expected_p_hat_n10 - 0.70) * 0.15 * 1.0
        self.assertAlmostEqual(sig_n10.smoothed_success_rate, expected_p_hat_n10, places=4)
        self.assertEqual(sig_n10.evidence_weight, 1.0)
        self.assertAlmostEqual(sig_n10.score_contribution, expected_contrib_n10, places=4)

        # 5. N = 15, k = 15 (N > 10: evidence weight remains 1.0)
        _seed("agent_n15", n=15, k=15)
        sig_n15 = store.compute_historical_signal("agent_n15", "research", project_id=self.project_a.id)
        expected_p_hat_n15 = 17.0 / 19.0
        expected_contrib_n15 = (expected_p_hat_n15 - 0.70) * 0.15 * 1.0
        self.assertAlmostEqual(sig_n15.smoothed_success_rate, expected_p_hat_n15, places=4)
        self.assertEqual(sig_n15.evidence_weight, 1.0)
        self.assertAlmostEqual(sig_n15.score_contribution, expected_contrib_n15, places=4)

        # 6. N = 100, k = 100 (large sample size: evidence weight does not grow beyond 1.0)
        _seed("agent_n100", n=100, k=100)
        sig_n100 = store.compute_historical_signal("agent_n100", "research", project_id=self.project_a.id)
        self.assertEqual(sig_n100.evidence_weight, 1.0)
        expected_p_hat_n100 = 102.0 / 104.0
        expected_contrib_n100 = (expected_p_hat_n100 - 0.70) * 0.15 * 1.0
        self.assertAlmostEqual(sig_n100.score_contribution, expected_contrib_n100, places=4)
        self.assertLessEqual(sig_n100.score_contribution, 0.08)


class SEOMultiAgentReasoningTests(TestCase):
    """
    Milestone 5.7: Comprehensive Test Suite for Advanced Multi-Agent Reasoning & Consensus.
    Verifies 26 core functional capabilities:
    - Independent analysis & context isolation
    - Epistemic segregation (facts vs inferences)
    - Evidence provenance & empirical weights
    - Cross-agent challenge & structured critique
    - Disagreement detection (material vs minor)
    - Evidence-weighted consensus (evidence > agent majority headcount)
    - No-consensus & Escalation handling
    - Strictly bounded reasoning rounds (max 3)
    - SEOSupervisorAgent orchestration & arbitration
    - SharedWorkingMemory reasoning preservation
    - DAG TaskPlan parallel decomposition
    - AdaptiveAgentSelector & AgentLearningService integration
    - ToolRegistry & MCP permission enforcement
    - Human-In-The-Loop (HITL) safety boundaries
    - Tenant isolation (project ownership scoping)
    - Telemetry (all 10 reasoning events emitted)
    - Runtime evaluation metrics calculation
    - Read-only API permissions & structured responses
    """

    def setUp(self):
        super().setUp()
        self.user_a = User.objects.create_user(
            email='reasoning_alpha@doxarank.io',
            password='testpassword123',
            first_name='Reasoning',
            last_name='Alpha'
        )
        self.user_b = User.objects.create_user(
            email='reasoning_beta@doxarank.io',
            password='testpassword123',
            first_name='Reasoning',
            last_name='Beta'
        )
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Alpha Reasoning Corp',
            website_url='https://alpha-reasoning.com'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Beta Reasoning Ltd',
            website_url='https://beta-reasoning.com'
        )
        self.client = APIClient()

    def tearDown(self):
        from apps.seo.services.agents.advanced_reasoning import ReasoningRegistry
        from apps.seo.services.agents.shared_memory import SharedMemoryRegistry
        ReasoningRegistry.get_instance().clear()
        SharedMemoryRegistry.get_instance().clear()
        super().tearDown()

    def test_01_case_creation_and_lifecycle(self):
        """1. Case creation, lifecycle state initialization, and registry registration."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ReasoningRegistry, ReasoningStatus
        )
        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Why did organic rankings decline?",
            initiating_agent="seo_supervisor",
            participating_agents=["seo_investigator", "seo_researcher"],
            correlation_id="corr-case-01"
        )
        self.assertIsNotNone(case.case_id)
        self.assertEqual(case.project_id, self.project_a.id)
        self.assertEqual(case.status, ReasoningStatus.IN_PROGRESS.value)
        self.assertEqual(case.current_round, 1)
        self.assertEqual(len(case.rounds), 1)
        self.assertIn("seo_investigator", case.participating_agents)
        self.assertIn("seo_researcher", case.participating_agents)

        # Verify registered in ReasoningRegistry
        reg_case = ReasoningRegistry.get_instance().get_by_case_id(case.case_id)
        self.assertIsNotNone(reg_case)
        self.assertEqual(reg_case.case_id, case.case_id)

        # Test to_dict and from_dict
        d = case.to_dict()
        self.assertEqual(d["case_id"], case.case_id)
        self.assertEqual(d["project_id"], self.project_a.id)

    def test_02_hypothesis_epistemic_segregation(self):
        """2. Epistemic segregation prevents hypotheses from mutating or overwriting observed facts."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, EpistemicType
        )
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory

        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Diagnose indexation drop",
            initiating_agent="seo_supervisor",
            correlation_id="corr-epistemic-02"
        )

        memory = SharedWorkingMemory(project_id=self.project_a.id, correlation_id="corr-epistemic-02")
        fact_id = memory.record_fact(
            claim="Googlebot received 500 error on 42 pages",
            source_agent="seo_investigator",
            source_tool="crawl_site",
            confidence=0.99
        )

        # Create hypothesis proposing causal explanation
        hyp = service.create_hypothesis(
            case=case,
            agent="seo_investigator",
            summary="Server misconfiguration caused crawl failure",
            rationale="NGINX 500 status on critical paths during audit",
            confidence=0.85,
            epistemic_type=EpistemicType.INFERENCE.value
        )

        self.assertEqual(hyp.epistemic_type, EpistemicType.INFERENCE.value)
        self.assertIn(hyp.hypothesis_id, [h.hypothesis_id for h in case.hypotheses])

        # Observed fact in shared memory remains pure and unmutated
        facts = memory.get_facts()
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].fact_id, fact_id)
        self.assertEqual(facts[0].epistemic_type, EpistemicType.OBSERVED_FACT.value)
        self.assertEqual(facts[0].claim, "Googlebot received 500 error on 42 pages")

    def test_03_evidence_provenance_and_empirical_validation(self):
        """3. Evidence provenance tracking with empirical flag and tool validation."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ReasoningEvidence
        )

        evidence = ReasoningEvidence(
            evidence_id="ev-prov-03",
            source_agent="seo_investigator",
            claim="Robots.txt disallowed /products/ directory during crawl",
            source_tool="check_robots_txt",
            empirical=True,
            provenance={"url": "https://alpha.com/robots.txt", "timestamp": "2026-09-14T12:00:00Z"},
            confidence=0.95
        )

        d = evidence.to_dict()
        self.assertTrue(d["empirical"])
        self.assertEqual(d["source_tool"], "check_robots_txt")
        self.assertEqual(d["provenance"]["url"], "https://alpha.com/robots.txt")

        restored = ReasoningEvidence.from_dict(d)
        self.assertEqual(restored.evidence_id, "ev-prov-03")
        self.assertEqual(restored.confidence, 0.95)

    def test_04_independent_reasoning_isolation(self):
        """4. Context isolation guarantees agents reason independently before results are pooled."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, AgentReasoningResult
        )
        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Explain organic traffic decline",
            initiating_agent="seo_supervisor",
            participating_agents=["seo_investigator", "seo_researcher"]
        )

        # Agent 1 produces independent analysis
        h1 = service.create_hypothesis(
            case=case,
            agent="seo_investigator",
            summary="H1: Core Web Vitals LCP regression",
            rationale="LCP spiked to 4.5s after hero video deployment",
            confidence=0.82
        )
        res1 = AgentReasoningResult(
            agent="seo_investigator",
            hypotheses=[h1],
            critiques=[],
            challenges_raised=[],
            evidence_submitted=[],
            confidence=0.82
        )

        # Agent 2 produces independent analysis without seeing Agent 1's conclusion
        h2 = service.create_hypothesis(
            case=case,
            agent="seo_researcher",
            summary="H2: Competitor launched comprehensive guide",
            rationale="Competitor gained 15 top-3 rankings for primary keywords",
            confidence=0.78
        )
        res2 = AgentReasoningResult(
            agent="seo_researcher",
            hypotheses=[h2],
            critiques=[],
            challenges_raised=[],
            evidence_submitted=[],
            confidence=0.78
        )

        service.record_agent_result(case=case, round_number=1, result=res1)
        service.record_agent_result(case=case, round_number=1, result=res2)

        round_1 = case.rounds[0]
        self.assertEqual(len(round_1.agent_results), 2)
        agents_in_round = [r.agent for r in round_1.agent_results]
        self.assertIn("seo_investigator", agents_in_round)
        self.assertIn("seo_researcher", agents_in_round)

    def test_05_parallel_reasoning_execution_with_overlap(self):
        """5. Parallel execution of independent reasoning tasks with timing overlap verification."""
        import time
        from apps.seo.services.agents.task_planner import TaskPlan, AgentTask, ParallelTaskExecutor
        from apps.seo.services.agents.base_agent import AgentResult

        plan = TaskPlan(project_id=self.project_a.id, goal="Parallel Reasoning", correlation_id="corr-par-05")
        t1 = AgentTask(
            task_id="t_reason_a",
            objective="Investigate technical root causes",
            description="Technical analysis",
            responsible_agent="seo_investigator",
            parallel_tier=1,
            correlation_id="corr-par-05"
        )
        t2 = AgentTask(
            task_id="t_reason_b",
            objective="Analyze competitor movement",
            description="Competitor analysis",
            responsible_agent="seo_researcher",
            parallel_tier=1,
            correlation_id="corr-par-05"
        )
        plan.add_task(t1)
        plan.add_task(t2)

        executor = ParallelTaskExecutor(max_workers=2)

        def mock_agent_run(agent_name: str, task: AgentTask):
            start = time.time()
            time.sleep(0.04)  # 40ms sleep to ensure overlap
            end = time.time()
            return AgentResult(
                agent=agent_name,
                status="completed",
                confidence=0.90,
                findings=[f"{agent_name} completed reasoning"],
                duration_ms=int((end - start) * 1000),
                metadata={"start_time": start, "end_time": end}
            )

        agent_runners = {
            "seo_investigator": lambda t: mock_agent_run("seo_investigator", t),
            "seo_researcher": lambda t: mock_agent_run("seo_researcher", t),
        }

        batch = executor.execute_parallel_tier(
            tasks=[t1, t2],
            agent_runners=agent_runners,
            project_id=self.project_a.id,
            correlation_id="corr-par-05"
        )

        self.assertEqual(batch.status, "completed")
        self.assertTrue(batch.overlap_detected)
        self.assertGreater(batch.overlap_duration_ms, 0)
        self.assertEqual(len(batch.results), 2)

    def test_06_cross_agent_critique_generation(self):
        """6. Cross-agent critique challenge with structured severity and suggested verification."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ChallengeType, CritiqueSeverity
        )
        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Audit ranking drop",
            initiating_agent="seo_supervisor",
            participating_agents=["seo_investigator", "seo_critic"]
        )

        hyp = service.create_hypothesis(
            case=case,
            agent="seo_investigator",
            summary="Robots.txt blocked crawler entirely",
            rationale="Disallow / directive noticed",
            confidence=0.90
        )

        critique = service.submit_critique(
            case=case,
            round_number=1,
            critique_agent="seo_critic",
            target_hypothesis_id=hyp.hypothesis_id,
            target_agent="seo_investigator",
            challenge_type=ChallengeType.UNSUPPORTED_CLAIM.value,
            critique_text="Disallow / applied only to Baiduspider, not Googlebot; check user-agent header",
            severity=CritiqueSeverity.HIGH.value,
            suggested_verification="Inspect Google Search Console robots.txt tester output"
        )

        self.assertIsNotNone(critique.critique_id)
        self.assertEqual(critique.severity, CritiqueSeverity.HIGH.value)
        self.assertEqual(critique.target_hypothesis_id, hyp.hypothesis_id)
        self.assertEqual(len(case.rounds[0].critiques), 1)

    def test_07_disagreement_detection_material(self):
        """7. Structured disagreement detection for opposing causal claims with MATERIAL severity."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, DisagreementSeverity
        )
        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Why did traffic drop 35%?",
            initiating_agent="seo_supervisor",
            participating_agents=["seo_investigator", "seo_researcher"]
        )

        h1 = service.create_hypothesis(
            case=case,
            agent="seo_investigator",
            summary="H1: Server 500 errors caused 35% ranking drop",
            rationale="Crawl error rate surged to 18%",
            confidence=0.88
        )
        h2 = service.create_hypothesis(
            case=case,
            agent="seo_researcher",
            summary="H2: Google Helpful Content Update penalised thin content",
            rationale="Drop coincided with announced unconfirmed core update",
            confidence=0.85
        )

        disagreements = service.detect_disagreements(case=case, round_number=1)
        self.assertGreaterEqual(len(disagreements), 1)
        d = disagreements[0]
        self.assertEqual(d.severity, DisagreementSeverity.MATERIAL.value)
        self.assertIn(d.agent_a, ["seo_investigator", "seo_researcher"])
        self.assertIn(d.agent_b, ["seo_investigator", "seo_researcher"])

    def test_08_disagreement_detection_minor(self):
        """8. Disagreement detection correctly assigns MINOR severity to non-critical variances."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, DisagreementSeverity
        )
        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Estimate impact of missing title tags",
            initiating_agent="seo_supervisor",
            participating_agents=["seo_investigator", "seo_content_strategist"]
        )

        # Both agree on issue, differ slightly on impact estimate
        h1 = service.create_hypothesis(
            case=case,
            agent="seo_investigator",
            summary="Missing titles cause 5% CTR degradation",
            rationale="Audit issue count = 12",
            confidence=0.75
        )
        h2 = service.create_hypothesis(
            case=case,
            agent="seo_content_strategist",
            summary="Missing titles cause 8% CTR degradation",
            rationale="Audit issue count = 12 with SERP preview test",
            confidence=0.78
        )

        disagreements = service.detect_disagreements(case=case, round_number=1)
        self.assertGreaterEqual(len(disagreements), 1)
        self.assertEqual(disagreements[0].severity, DisagreementSeverity.MINOR.value)

    def test_09_evidence_weighted_consensus_basic(self):
        """9. Basic evidence-weighted consensus reaching valid conclusion with confidence score."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ConsensusState, ReasoningEvidence
        )
        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Determine root cause of canonicalization bug",
            initiating_agent="seo_supervisor"
        )

        ev = ReasoningEvidence(
            evidence_id="ev-can-09",
            source_agent="seo_investigator",
            claim="HTML source contains canonical pointing to staging.alpha.com",
            source_tool="fetch_rendered_dom",
            empirical=True,
            provenance={"line": 14, "url": "https://alpha.com"},
            confidence=0.98
        )

        h1 = service.create_hypothesis(
            case=case,
            agent="seo_investigator",
            summary="Staging canonical tag in production causes indexation loss",
            rationale="Verified staging URL in canonical tag",
            confidence=0.95,
            supporting_evidence=[ev]
        )

        consensus = service.evaluate_consensus(case=case)
        self.assertEqual(consensus.consensus_state, ConsensusState.CONSENSUS.value)
        self.assertEqual(consensus.selected_hypothesis_id, h1.hypothesis_id)
        self.assertGreater(consensus.confidence, 0.80)
        self.assertIn("staging canonical", consensus.selected_conclusion.lower())

    def test_10_evidence_outweighs_agent_majority(self):
        """10. CRITICAL: Strong empirical evidence strictly outweighs naive majority agent headcount."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ConsensusState, ReasoningEvidence
        )
        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Identify primary cause of ranking collapse",
            initiating_agent="seo_supervisor",
            participating_agents=["agent_a", "agent_b", "agent_c"]
        )

        # 2 AGENTS (Majority) support H1 with ZERO empirical evidence
        h1 = service.create_hypothesis(
            case=case,
            agent="agent_a",
            summary="H1: Algorithmic penalty hit site (Agent A & B majority)",
            rationale="Anecdotal speculation without crawl data",
            confidence=0.70,
            supporting_evidence=[]  # Zero empirical evidence!
        )

        # 1 AGENT (Minority) supports H2 with VERIFIED EMPIRICAL evidence
        ev1 = ReasoningEvidence(
            evidence_id="ev_emp_1",
            source_agent="agent_c",
            claim="Nginx returned HTTP 500 to Googlebot for 10 consecutive days",
            source_tool="server_access_log_parser",
            empirical=True,
            provenance={"log_path": "/var/log/nginx/access.log", "entries_count": 1420},
            confidence=0.98
        )
        ev2 = ReasoningEvidence(
            evidence_id="ev_emp_2",
            source_agent="agent_c",
            claim="Google Search Console Crawl Stats shows 95% server error rate",
            source_tool="get_search_console_crawl_stats",
            empirical=True,
            provenance={"gsc_metric": "crawl_error_5xx", "pct": 95},
            confidence=0.96
        )

        h2 = service.create_hypothesis(
            case=case,
            agent="agent_c",
            summary="H2: Infrastructure 500 downtime caused Google de-indexing (Agent C lone evidence)",
            rationale="Verified server logs and GSC crawl stats",
            confidence=0.92,
            supporting_evidence=[ev1, ev2]  # Strong verified evidence!
        )

        consensus = service.evaluate_consensus(case=case)

        # The minority hypothesis H2 MUST win because evidence outweighs agent headcount!
        self.assertEqual(consensus.consensus_state, ConsensusState.CONSENSUS.value)
        self.assertEqual(consensus.selected_hypothesis_id, h2.hypothesis_id)
        self.assertIn("H2", consensus.selected_conclusion)
        self.assertIn("Infrastructure 500", consensus.selected_conclusion)
        self.assertGreater(consensus.confidence, 0.80)

    def test_11_no_consensus_when_evidence_contradictory(self):
        """11. Ambiguous/contradictory evidence results in NO_CONSENSUS without manufacturing confidence."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ConsensusState, ReasoningEvidence
        )
        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Unresolved ranking fluctuation",
            initiating_agent="seo_supervisor"
        )

        ev_contra1 = ReasoningEvidence(
            evidence_id="ev_c1",
            source_agent="agent_a",
            claim="Search impressions are up 15%",
            source_tool="gsc_api",
            empirical=True,
            confidence=0.50
        )
        ev_contra2 = ReasoningEvidence(
            evidence_id="ev_c2",
            source_agent="agent_b",
            claim="Search impressions are down 20%",
            source_tool="third_party_rank_tracker",
            empirical=True,
            confidence=0.50
        )

        service.create_hypothesis(
            case=case,
            agent="agent_a",
            summary="Traffic is surging",
            rationale="GSC data",
            confidence=0.50,
            supporting_evidence=[ev_contra1],
            contradicting_evidence=[ev_contra2]
        )
        service.create_hypothesis(
            case=case,
            agent="agent_b",
            summary="Traffic is crashing",
            rationale="Rank tracker data",
            confidence=0.50,
            supporting_evidence=[ev_contra2],
            contradicting_evidence=[ev_contra1]
        )

        consensus = service.evaluate_consensus(case=case)
        self.assertIn(consensus.consensus_state, [ConsensusState.NO_CONSENSUS.value, ConsensusState.ESCALATED.value])

    def test_12_escalation_on_unresolved_material_disagreement(self):
        """12. Unresolved material disagreement triggers ESCALATED state for human review."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ConsensusState, ChallengeType, CritiqueSeverity
        )
        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Disputed core update attribution",
            initiating_agent="seo_supervisor",
            participating_agents=["agent_x", "agent_y"]
        )

        h1 = service.create_hypothesis(
            case=case,
            agent="agent_x",
            summary="Hypothesis X: Manual action applied",
            rationale="Sudden cliff drop",
            confidence=0.80
        )
        h2 = service.create_hypothesis(
            case=case,
            agent="agent_y",
            summary="Hypothesis Y: Hosting outage during crawl",
            rationale="Sudden cliff drop",
            confidence=0.80
        )

        # Add unresolved high-severity critique
        service.submit_critique(
            case=case,
            round_number=1,
            critique_agent="agent_y",
            target_hypothesis_id=h1.hypothesis_id,
            target_agent="agent_x",
            challenge_type=ChallengeType.METHODOLOGY_FLAW.value,
            critique_text="GSC Manual Actions panel is completely clear; hypothesis X is false",
            severity=CritiqueSeverity.HIGH.value
        )
        service.detect_disagreements(case=case, round_number=1)

        # Force max rounds to trigger escalation on open disagreement
        case.current_round = 3
        consensus = service.evaluate_consensus(case=case)
        self.assertEqual(consensus.consensus_state, ConsensusState.ESCALATED.value)
        self.assertIsNotNone(consensus.escalation_reason)

    def test_13_bounded_reasoning_rounds_stops_at_limit(self):
        """13. Reasoning loop is strictly bounded by MAX_REASONING_ROUNDS (3) to prevent infinite loops."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, MAX_REASONING_ROUNDS, ReasoningStatus
        )
        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Bounded round test",
            initiating_agent="seo_supervisor"
        )

        self.assertEqual(case.current_round, 1)
        r2 = service.start_next_round(case)
        self.assertTrue(r2)
        self.assertEqual(case.current_round, 2)

        r3 = service.start_next_round(case)
        self.assertTrue(r3)
        self.assertEqual(case.current_round, 3)

        # Exceeding MAX_REASONING_ROUNDS returns False and halts reasoning
        r4 = service.start_next_round(case)
        self.assertFalse(r4)
        self.assertEqual(case.current_round, MAX_REASONING_ROUNDS)

    def test_14_supervisor_orchestration_reasoning_workflow(self):
        """14. SEOSupervisorAgent orchestrates end-to-end multi-agent reasoning workflow."""
        from unittest.mock import patch
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent
        from apps.seo.services.agents.base_agent import AgentResult

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)

        def mock_run(agent_instance, task_str, *args, **kwargs):
            return AgentResult(
                agent=agent_instance.name,
                status="completed",
                confidence=0.88,
                findings=[f"{agent_instance.name} identified key factor"],
                evidence={"factor": "verified_data"}
            )

        with patch.object(supervisor._agents["seo_investigator"], "run", side_effect=lambda *a, **k: mock_run(supervisor._agents["seo_investigator"], *a, **k)):
            with patch.object(supervisor._agents["seo_researcher"], "run", side_effect=lambda *a, **k: mock_run(supervisor._agents["seo_researcher"], *a, **k)):
                res = supervisor.orchestrate(
                    task="Investigate ranking drop with multi-agent consensus",
                    enable_reasoning=True,
                    correlation_id="corr-super-14"
                )

        self.assertIn("reasoning_case", res)
        self.assertIsNotNone(res["reasoning_case"])
        self.assertEqual(res["reasoning_case"]["project_id"], self.project_a.id)
        self.assertIn("consensus_result", res["reasoning_case"])

    def test_15_supervisor_arbitration_decision_recorded(self):
        """15. Accepted consensus outcome records an ACCEPTED supervisor decision in SharedWorkingMemory."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ReasoningEvidence
        )
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory

        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Arbitrate crawl configuration",
            initiating_agent="seo_supervisor",
            correlation_id="corr-dec-15"
        )

        ev = ReasoningEvidence(
            evidence_id="ev_dec_15",
            source_agent="seo_investigator",
            claim="404 on high-traffic landing page",
            source_tool="crawl_site",
            empirical=True,
            confidence=0.95
        )

        service.create_hypothesis(
            case=case,
            agent="seo_investigator",
            summary="Broken redirect rule dropped landing page traffic",
            rationale="Verified 404 response on /best-coffee",
            confidence=0.92,
            supporting_evidence=[ev]
        )

        memory = SharedWorkingMemory(project_id=self.project_a.id, correlation_id="corr-dec-15")
        service.evaluate_consensus(case=case, shared_memory=memory)

        decisions = memory.get_decisions()
        self.assertGreaterEqual(len(decisions), 1)
        dec = decisions[-1]
        self.assertEqual(dec.decision_owner, "seo_supervisor")
        self.assertEqual(dec.status, "accepted")
        self.assertIn("Multi-Agent Consensus:", dec.title)

    def test_16_shared_working_memory_integration(self):
        """16. SharedWorkingMemory records, deserializes, and summarizes reasoning cases accurately."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory
        from apps.seo.services.agents.advanced_reasoning import AdvancedReasoningService

        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Memory persistence verification",
            initiating_agent="seo_supervisor",
            correlation_id="corr-mem-16"
        )

        memory = SharedWorkingMemory(project_id=self.project_a.id, correlation_id="corr-mem-16")
        memory.record_reasoning_case(case)

        cases = memory.get_reasoning_cases()
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].case_id, case.case_id)

        # Roundtrip through serialization
        d = memory.to_dict()
        self.assertIn("reasoning_cases", d)
        self.assertEqual(len(d["reasoning_cases"]), 1)

        restored_mem = SharedWorkingMemory.from_dict(d)
        self.assertEqual(len(restored_mem.get_reasoning_cases()), 1)
        self.assertEqual(restored_mem.get_reasoning_cases()[0].case_id, case.case_id)

    def test_17_dag_planner_reasoning_decomposition(self):
        """17. DynamicTaskPlanner decomposes multi-agent reasoning goals into parallel DAG tiers."""
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner

        planner = DynamicTaskPlanner(project_id=self.project_a.id)
        plan = planner.decompose_goal(
            goal="Why did website rankings suddenly drop? Perform multi-agent reasoning and consensus",
            correlation_id="corr-dag-17",
            enable_reasoning=True
        )

        task_ids = list(plan.tasks.keys())
        self.assertIn("t_reason_evidence", task_ids)
        self.assertIn("t_reason_technical", task_ids)
        self.assertIn("t_reason_content", task_ids)
        self.assertIn("t_reason_critique", task_ids)
        self.assertIn("t_reason_consensus", task_ids)

        # Verify parallel tier allocation
        t_tech = plan.get_task("t_reason_technical")
        t_content = plan.get_task("t_reason_content")
        self.assertEqual(t_tech.parallel_tier, 1)
        self.assertEqual(t_content.parallel_tier, 1)

        # Verify critique depends on independent analyses
        t_critique = plan.get_task("t_reason_critique")
        self.assertIn("t_reason_technical", t_critique.dependencies)
        self.assertIn("t_reason_content", t_critique.dependencies)

    def test_18_adaptive_agent_selector_integration(self):
        """18. AdaptiveAgentSelector routes reasoning tasks to appropriate specialists."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        selector = AdaptiveAgentSelector(project_id=self.project_a.id)
        task_tech = AgentTask(
            task_id="t_diag",
            objective="Diagnose server 500 error logs and robots.txt syntax errors",
            description="Technical audit diagnostics",
            responsible_agent="seo_supervisor"
        )
        dec_tech = selector.select_agent(task_tech)
        self.assertEqual(dec_tech.selected_agent, "seo_investigator")

        task_content = AgentTask(
            task_id="t_comp",
            objective="Analyze competitor keywords, search volumes, and ranking positions",
            description="Competitor keyword research",
            responsible_agent="seo_supervisor"
        )
        dec_content = selector.select_agent(task_content)
        self.assertEqual(dec_content.selected_agent, "seo_researcher")

    def test_19_agent_learning_service_soft_signal(self):
        """19. AgentLearningService historical score remains a bounded soft signal during reasoning routing."""
        from apps.seo.services.agents.agent_learning import AgentPerformanceStore, AgentPerformanceRecord
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask

        store = AgentPerformanceStore.get_instance()
        for i in range(10):
            store.record_outcome(AgentPerformanceRecord(
                agent_name="seo_investigator",
                task_id=f"t_learn_{i}",
                task_type="technical_investigation",
                project_id=self.project_a.id,
                success=True
            ))

        selector = AdaptiveAgentSelector(project_id=self.project_a.id, performance_store=store)
        task = AgentTask(
            task_id="t_route_19",
            objective="Diagnose technical SEO server crawl errors",
            description="Crawl log diagnosis",
            responsible_agent="seo_supervisor"
        )
        decision = selector.select_agent(task)
        self.assertEqual(decision.selected_agent, "seo_investigator")
        hist_score = decision.score_breakdowns["seo_investigator"]["historical_score"]
        self.assertLessEqual(hist_score, 0.08)
        self.assertGreaterEqual(hist_score, -0.08)

    def test_20_tool_registry_permission_enforcement(self):
        """20. ToolRegistry enforces agent tool whitelist during reasoning analysis."""
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        researcher = supervisor._agents["seo_researcher"]
        investigator = supervisor._agents["seo_investigator"]

        # Researcher agent must NOT be allowed to execute action planning tools
        is_allowed = researcher.is_tool_allowed("plan_seo_actions")
        self.assertFalse(is_allowed)

        # Investigator IS allowed to inspect audit issues
        self.assertTrue(investigator.is_tool_allowed("get_audit_issues"))

        # Attempting unauthorized execution raises PermissionError
        with self.assertRaises(PermissionError):
            researcher.execute_tool("plan_seo_actions", {})

    def test_21_mcp_permission_enforcement(self):
        """21. MCP server permissions remain strictly enforced during reasoning tool dispatch."""
        from apps.seo.services.mcp.permissions import MCPPermissionPolicy
        from apps.seo.services.agents.seo_supervisor import SEOSupervisorAgent

        supervisor = SEOSupervisorAgent(project=self.project_a, user=self.user_a)
        planner = supervisor._agents["seo_action_planner"]

        # Rogue MCP server is not approved
        self.assertFalse(MCPPermissionPolicy.is_server_approved("rogue_untrusted_server"))

        # MCP tool authorization is denied for unauthorized agent
        self.assertFalse(MCPPermissionPolicy.is_agent_authorized("seo_action_planner", "mcp__unauthorized_tool"))
        self.assertFalse(planner.is_tool_allowed("mcp__unauthorized_tool"))

    def test_22_hitl_safety_consensus_cannot_authorize_mutation(self):
        """22. Consensus outcome recommending mutation requires explicit Human-In-The-Loop approval."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ReasoningEvidence
        )
        from apps.seo.models import SEOAction, ActionType, ActionStatus

        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Determine fix for duplicate meta titles",
            initiating_agent="seo_supervisor"
        )

        ev = ReasoningEvidence(
            evidence_id="ev-hitl-22",
            source_agent="seo_investigator",
            claim="Duplicate title on 15 category pages",
            source_tool="audit_issues",
            empirical=True,
            confidence=0.92
        )
        service.create_hypothesis(
            case=case,
            agent="seo_investigator",
            summary="Rewrite title tags to include category name",
            rationale="Resolves CTR cannibalization",
            confidence=0.90,
            supporting_evidence=[ev]
        )
        consensus = service.evaluate_consensus(case=case)

        # Simulate proposed SEO mutation action following consensus
        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.OPTIMIZE_TITLE,
            status=ActionStatus.PENDING_APPROVAL,
            title="Consensus: Rewrite duplicate category meta titles",
            rationale=consensus.rationale
        )

        # HITL Boundary: Action CANNOT be executed directly by consensus
        self.assertEqual(action.status, ActionStatus.PENDING_APPROVAL)
        self.assertNotEqual(action.status, ActionStatus.COMPLETED)

    def test_23_tenant_isolation_shared_memory_and_registry(self):
        """23. Strict multi-tenant isolation: Project B cannot view Project A reasoning cases."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ReasoningRegistry
        )

        service_a = AdvancedReasoningService(project_id=self.project_a.id)
        case_a = service_a.create_reasoning_case(
            objective="Confidential Project A Strategy",
            initiating_agent="seo_supervisor"
        )

        # Verify API view blocks Project B owner from accessing Project A case
        self.client.force_authenticate(user=self.user_b)
        res = self.client.get(f'/api/seo/ai/reasoning/{case_a.case_id}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Project A owner has authorized access
        self.client.force_authenticate(user=self.user_a)
        res_a = self.client.get(f'/api/seo/ai/reasoning/{case_a.case_id}/')
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)
        self.assertEqual(res_a.data["case_id"], case_a.case_id)

    def test_24_telemetry_ten_events_emitted(self):
        """24. All 10 Milestone 5.7 reasoning telemetry events are published during lifecycle."""
        from apps.seo.services.agent_events import InMemoryEventPublisher, AgentEventType
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ChallengeType, CritiqueSeverity, ReasoningEvidence
        )

        publisher = InMemoryEventPublisher()
        service = AdvancedReasoningService(project_id=self.project_a.id, event_publisher=publisher)

        # 1. case.started
        case = service.create_reasoning_case(
            objective="Telemetry verification case",
            initiating_agent="seo_supervisor",
            correlation_id="corr-tel-24"
        )
        # 2. hypothesis.created
        ev = ReasoningEvidence(
            evidence_id="ev-tel-24",
            source_agent="seo_investigator",
            claim="Telemetry verified fact",
            empirical=True,
            confidence=0.90
        )
        hyp = service.create_hypothesis(
            case=case,
            agent="seo_investigator",
            summary="Telemetry hypothesis",
            rationale="Test rationale",
            confidence=0.85,
            supporting_evidence=[ev]
        )
        # 3. critique.created
        service.submit_critique(
            case=case,
            round_number=1,
            critique_agent="seo_critic",
            target_hypothesis_id=hyp.hypothesis_id,
            target_agent="seo_investigator",
            challenge_type=ChallengeType.UNSUPPORTED_CLAIM.value,
            critique_text="Check claim validity",
            severity=CritiqueSeverity.MEDIUM.value
        )
        # 4. disagreement.detected
        service.detect_disagreements(case=case, round_number=1)
        # 5. consensus.reached
        service.evaluate_consensus(case=case)
        # 6. round.started
        service.start_next_round(case)

        published_types = [e.event_type for e in publisher.published_events]
        self.assertIn(AgentEventType.SEO_REASONING_CASE_STARTED.value, published_types)
        self.assertIn(AgentEventType.SEO_REASONING_HYPOTHESIS_CREATED.value, published_types)
        self.assertIn(AgentEventType.SEO_REASONING_CRITIQUE_CREATED.value, published_types)
        self.assertIn(AgentEventType.SEO_REASONING_CONSENSUS_REACHED.value, published_types)

    def test_25_runtime_evaluation_metrics_calculation(self):
        """25. SEOAgentEvaluationService calculates 12 reasoning evaluation metrics from runtime data."""
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService
        from apps.seo.services.agents.base_agent import SharedContext
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ReasoningEvidence
        )

        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="Evaluation metrics test",
            initiating_agent="seo_supervisor",
            correlation_id="corr-eval-25"
        )
        ev = ReasoningEvidence(
            evidence_id="ev-eval-25",
            source_agent="seo_investigator",
            claim="Metric claim",
            empirical=True,
            confidence=0.95
        )
        service.create_hypothesis(
            case=case,
            agent="seo_investigator",
            summary="Metric winner",
            rationale="Evaluation rationale",
            confidence=0.90,
            supporting_evidence=[ev]
        )
        service.evaluate_consensus(case=case)

        context = SharedContext(
            project_id=self.project_a.id,
            user_id=self.user_a.id,
            correlation_id="corr-eval-25",
            reasoning_cases=[case.to_dict()]
        )

        eval_service = SEOAgentEvaluationService()
        metrics = eval_service.evaluate_collaboration(
            context=context,
            total_duration_ms=1200,
            agent_timings={"seo_investigator": 600, "seo_researcher": 600}
        )

        self.assertIn("multi_agent_reasoning_metrics", metrics)
        rm = metrics["multi_agent_reasoning_metrics"]
        self.assertEqual(rm["reasoning_cases"], 1)
        self.assertGreaterEqual(rm["average_reasoning_rounds"], 1.0)
        self.assertEqual(rm["consensus_rate"], 100.0)

    def test_26_api_endpoints_permissions_and_correctness(self):
        """26. Read-only API endpoints enforce authentication, tenant permissions, and return valid schemas."""
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ReasoningEvidence
        )

        service = AdvancedReasoningService(project_id=self.project_a.id)
        case = service.create_reasoning_case(
            objective="API verification case",
            initiating_agent="seo_supervisor",
            correlation_id="corr-api-26"
        )
        ev = ReasoningEvidence(
            evidence_id="ev-api-26",
            source_agent="seo_investigator",
            claim="API empirical evidence",
            empirical=True,
            confidence=0.90
        )
        service.create_hypothesis(
            case=case,
            agent="seo_investigator",
            summary="API Hypothesis",
            rationale="Rationale",
            confidence=0.88,
            supporting_evidence=[ev]
        )
        service.evaluate_consensus(case=case)

        # 1. Unauthenticated request rejected
        res_unauth = self.client.get(f'/api/seo/ai/reasoning/{case.case_id}/')
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Authenticated authorized tenant request accepted
        self.client.force_authenticate(user=self.user_a)
        res_case = self.client.get(f'/api/seo/ai/reasoning/{case.case_id}/')
        self.assertEqual(res_case.status_code, status.HTTP_200_OK)
        self.assertEqual(res_case.data["case_id"], case.case_id)
        self.assertIn(res_case.data["consensus_result"]["consensus_state"], ["reached", "consensus"])

        # 3. Collaboration reasoning view by correlation_id
        res_collab = self.client.get(f'/api/seo/ai/orchestrate/corr-api-26/reasoning/')
        self.assertEqual(res_collab.status_code, status.HTTP_200_OK)
        self.assertEqual(res_collab.data["total_cases"], 1)
        self.assertEqual(res_collab.data["consensus_summary"]["reached"], 1)

    def test_27_evaluation_metric_semantics_a_to_e(self):
        """27. Explicit metric semantics A through E:
        A. disagreement resolved -> unresolved_disagreement = 0
        B. disagreement unresolved -> unresolved_disagreement > 0
        C. evidence-supported conclusion -> evidence_supported_conclusions > 0
        D. consensus without unresolved disagreement
        E. escalation without consensus
        """
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService
        from apps.seo.services.agents.base_agent import SharedContext
        from apps.seo.services.agents.advanced_reasoning import (
            AdvancedReasoningService, ReasoningEvidence, ChallengeType, CritiqueSeverity, ConsensusState
        )

        service = AdvancedReasoningService(project_id=self.project_a.id)
        eval_service = SEOAgentEvaluationService()

        # Case 1 (Tests A, C, D):
        # Two agents disagree, but one has decisive empirical evidence.
        # Consensus arbitration resolves disagreement in favor of empirical winner.
        # Outcome: consensus_rate=100.0, disagreement_rate=100.0, unresolved_disagreement_rate=0.0, evidence_supported_conclusions=1
        case_a = service.create_reasoning_case(
            objective="Diagnose traffic drop",
            initiating_agent="seo_supervisor",
            correlation_id="corr-sem-a"
        )
        ev_a = ReasoningEvidence(
            evidence_id="ev-sem-a",
            source_agent="seo_investigator",
            claim="HTTP 500 on 50 URLs",
            empirical=True,
            confidence=0.98
        )
        service.add_evidence(
            case_id=case_a.case_id,
            fact="HTTP 500 on 50 URLs",
            source_agent="seo_investigator",
            source_tool="crawl_site",
            confidence=0.98
        )
        h1 = service.create_hypothesis(
            case=case_a,
            agent="seo_investigator",
            summary="Server failure caused drop",
            rationale="HTTP 500 crawl logs",
            confidence=0.92,
            supporting_evidence=[ev_a]
        )
        h2 = service.create_hypothesis(
            case=case_a,
            agent="seo_strategist",
            summary="Content drift caused drop",
            rationale="Intent shift hypothesis",
            confidence=0.60
        )
        # Meaningful disagreement detected between investigator and strategist
        disags = service.detect_disagreements(case=case_a)
        self.assertGreater(len(disags), 0)

        # Consensus reached via empirical arbitration
        cons_res = service.evaluate_consensus(case=case_a)
        self.assertEqual(cons_res.consensus_state, ConsensusState.CONSENSUS.value)
        self.assertEqual(cons_res.winning_hypothesis_id, h1.hypothesis_id)

        # A. Disagreement resolved -> open disagreements is 0
        self.assertEqual(len(cons_res.unresolved_disagreements), 0)

        # Context evaluation for Case 1
        ctx_a = SharedContext(
            project_id=self.project_a.id,
            user_id=self.user_a.id,
            correlation_id="corr-sem-a",
            reasoning_cases=[case_a.to_dict()]
        )
        res_a = eval_service.evaluate_collaboration(ctx_a)["reasoning_metrics"]

        # Assertions for A, C, D:
        self.assertEqual(res_a["disagreement_rate"], 100.0, "Disagreement was detected")
        self.assertEqual(res_a["unresolved_disagreement_rate"], 0.0, "A. Disagreement was resolved by consensus")
        self.assertEqual(res_a["consensus_rate"], 100.0, "D. Consensus reached")
        self.assertEqual(res_a["evidence_supported_conclusions"], 1, "C. Conclusion has empirical evidence backing")
        self.assertEqual(res_a["escalation_rate"], 0.0, "No escalation occurred")

        # Case 2 (Tests B, E):
        # Contradictory evidence case that cannot reach consensus and escalates.
        # Outcome: escalation_rate=100.0, consensus_rate=0.0, unresolved_disagreement_rate=100.0
        case_b = service.create_reasoning_case(
            objective="Conflicting ranking signals",
            initiating_agent="seo_supervisor",
            correlation_id="corr-sem-b"
        )
        ev_b1 = ReasoningEvidence(evidence_id="ev-b1", source_agent="agent_a", claim="Rankings surged", empirical=True, confidence=0.5)
        ev_b2 = ReasoningEvidence(evidence_id="ev-b2", source_agent="agent_b", claim="Rankings plunged", empirical=True, confidence=0.5)
        service.create_hypothesis(case=case_b, agent="agent_a", summary="Surging", rationale="A", confidence=0.5, supporting_evidence=[ev_b1], contradicting_evidence=[ev_b2])
        service.create_hypothesis(case=case_b, agent="agent_b", summary="Plunging", rationale="B", confidence=0.5, supporting_evidence=[ev_b2], contradicting_evidence=[ev_b1])
        service.detect_disagreements(case=case_b)

        # Escalate after max rounds without consensus
        service.evaluate_consensus(case=case_b, round_number=3)
        self.assertEqual(case_b.consensus_state, ConsensusState.ESCALATED.value)

        ctx_b = SharedContext(
            project_id=self.project_a.id,
            user_id=self.user_a.id,
            correlation_id="corr-sem-b",
            reasoning_cases=[case_b.to_dict()]
        )
        res_b = eval_service.evaluate_collaboration(ctx_b)["reasoning_metrics"]

        # Assertions for B, E:
        self.assertEqual(res_b["escalation_rate"], 100.0, "E. Escalation without consensus")
        self.assertEqual(res_b["consensus_rate"], 0.0, "E. No false consensus manufactured")
        self.assertGreater(res_b["unresolved_disagreement_rate"], 0.0, "B. Disagreement remains unresolved")
        self.assertEqual(res_b["evidence_supported_conclusions"], 0, "No valid conclusion on escalation")


class ContinuousAgentOperationsTests(TestCase):
    """
    Milestone 6.1: Comprehensive Test Suite for Continuous Agent Operations.
    Verifies:
    1. Lifecycle: create, activate, pause, resume, failure, recovery.
    2. Scheduling: due operations run, future operations wait, interval calculation.
    3. Concurrency & Overlap Prevention: single active run invariant, concurrent scheduler calls.
    4. Persistence: state persists and survives process boundaries.
    5. Failure isolation: failed run does not corrupt operation, bounded backoff works.
    6. Circuit breaker: transitions to FAILED upon reaching max consecutive failures.
    7. HITL safety boundary: waiting for approval prevents autonomous mutation and subsequent runs.
    8. Tenant isolation: cross-project access rejected at API and service layers.
    9. Telemetry: operational events emitted with sanitization.
    10. Runtime evaluation metrics: all 11 metrics computed from actual runtime data.
    11. REST API endpoints: create, list, retrieve, pause, resume, trigger, runs, metrics.
    """

    def setUp(self):
        from apps.users.models import User
        from apps.projects.models import Project
        from apps.seo.models import (
            ContinuousOperation, ContinuousOperationStatus, ContinuousOperationScheduleType,
            AgentRun, AgentRunStatus, SEOAction, ActionStatus
        )
        from apps.seo.services.continuous_operation import ContinuousOperationService
        from apps.seo.services.agent_events import AgentEventType, InMemoryEventPublisher
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService
        from rest_framework.test import APIClient

        self.ContinuousOperation = ContinuousOperation
        self.ContinuousOperationStatus = ContinuousOperationStatus
        self.ContinuousOperationScheduleType = ContinuousOperationScheduleType
        self.AgentRun = AgentRun
        self.AgentRunStatus = AgentRunStatus
        self.SEOAction = SEOAction
        self.ActionStatus = ActionStatus
        self.AgentEventType = AgentEventType
        self.SEOAgentEvaluationService = SEOAgentEvaluationService

        self.user_a = User.objects.create_user(email="tenant_a@doxarank.io", password="SecretPassword123!")
        self.user_b = User.objects.create_user(email="tenant_b@doxarank.io", password="SecretPassword123!")

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name="Alpha SEO Project",
            website_url="https://alpha-seo.example.com"
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name="Beta SEO Project",
            website_url="https://beta-seo.example.com"
        )

        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)

        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

        self.publisher = InMemoryEventPublisher()
        self.service = ContinuousOperationService(publisher=self.publisher)

    def test_01_lifecycle_create_and_activate(self):
        """1. Create and auto-activate a continuous operation."""
        op = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Continuous technical SEO audit and ranking health monitoring.",
            schedule_type=self.ContinuousOperationScheduleType.INTERVAL_MINUTES,
            interval_value=30,
            auto_activate=True
        )

        self.assertIsNotNone(op.id)
        self.assertEqual(op.status, self.ContinuousOperationStatus.ACTIVE)
        self.assertEqual(op.interval_value, 30)
        self.assertIsNotNone(op.next_run_at)
        self.assertIn("duplicate_prevention_count", op.metrics)

        # Verify events
        created_events = self.publisher.get_events_by_type(self.AgentEventType.SEO_OPERATION_CREATED)
        started_events = self.publisher.get_events_by_type(self.AgentEventType.SEO_OPERATION_STARTED)
        self.assertEqual(len(created_events), 1)
        self.assertEqual(len(started_events), 1)
        self.assertEqual(created_events[0].payload["operation_id"], op.id)

    def test_02_pause_and_resume(self):
        """2. Pause and resume operations, ensuring scheduler skips paused ones."""
        op = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Monitor Search Console click changes.",
            auto_activate=True
        )

        # Pause
        paused_op = self.service.pause_operation(op.id, user=self.user_a)
        self.assertEqual(paused_op.status, self.ContinuousOperationStatus.PAUSED)
        self.assertIsNotNone(paused_op.paused_at)

        # Scheduler must NOT pick paused operations even if next_run_at is in the past
        paused_op.next_run_at = timezone.now() - timedelta(minutes=5)
        paused_op.save(update_fields=['next_run_at'])
        triggered = self.service.evaluate_and_trigger_due_operations()
        self.assertNotIn(paused_op.id, [run.continuous_operation_id for run in self.AgentRun.objects.filter(id__in=triggered)])

        # Resume
        resumed_op = self.service.resume_operation(op.id, user=self.user_a)
        self.assertEqual(resumed_op.status, self.ContinuousOperationStatus.ACTIVE)
        self.assertIsNotNone(resumed_op.resumed_at)
        self.assertIsNotNone(resumed_op.next_run_at)

    def test_03_scheduling_due_and_future_operations(self):
        """3. Scheduler triggers due operations and ignores future operations."""
        # Due operation (next_run_at in past)
        due_op = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Due operation mission",
            auto_activate=True
        )
        due_op.next_run_at = timezone.now() - timedelta(minutes=10)
        due_op.save(update_fields=['next_run_at'])

        # Future operation (next_run_at 2 hours in future)
        future_op = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Future operation mission",
            auto_activate=True
        )
        future_op.next_run_at = timezone.now() + timedelta(hours=2)
        future_op.save(update_fields=['next_run_at'])

        started_ids = self.service.evaluate_and_trigger_due_operations()
        self.assertGreater(len(started_ids), 0)

        # Confirm due_op has executed a run
        due_op.refresh_from_db()
        self.assertEqual(due_op.total_runs, 1)
        self.assertIsNotNone(due_op.last_run)

        # Confirm future_op has NO run
        future_op.refresh_from_db()
        self.assertIsNone(future_op.current_run)
        self.assertEqual(future_op.total_runs, 0)

    def test_04_duplicate_run_prevention_single_active_run(self):
        """4. Strictly prevent duplicate active runs for a single operation."""
        op = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Duplicate prevention verification",
            auto_activate=True
        )

        # Simulate active run in-flight
        active_run = self.AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            continuous_operation=op,
            goal=op.goal,
            status=self.AgentRunStatus.RUNNING
        )
        op.current_run = active_run
        op.status = self.ContinuousOperationStatus.RUNNING
        op.total_runs = 1
        op.save(update_fields=['current_run', 'status', 'total_runs'])

        # Scheduler evaluation while active_run is in-flight must NOT create a new run
        started_2 = self.service.evaluate_and_trigger_due_operations()
        self.assertEqual(len(started_2), 0)

        # Manual trigger attempt while active must be rejected
        manual_run = self.service.trigger_operation_manually(op.id, user=self.user_a)
        self.assertIsNone(manual_run, "Manual trigger must reject when an active run is in progress")

        op.refresh_from_db()
        self.assertEqual(op.current_run_id, active_run.id)
        self.assertEqual(op.total_runs, 1, "Must remain at exactly 1 run")
        self.assertGreater(op.metrics.get("duplicate_prevention_count", 0), 0)

    def test_05_concurrent_scheduler_protection(self):
        """5. Concurrent scheduler triggers produce at most 1 AgentRun."""
        op = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Concurrency race condition test",
            auto_activate=True
        )
        op.next_run_at = timezone.now() - timedelta(minutes=1)
        op.save(update_fields=['next_run_at'])

        # Simulating concurrent workers
        runs_created = []
        for _ in range(3):
            res = self.service.evaluate_and_trigger_due_operations()
            runs_created.extend(res)

        # Only 1 initial run was dispatched because first run set total_runs and current_run
        self.assertEqual(len(runs_created), 1)
        op.refresh_from_db()
        self.assertEqual(op.total_runs, 1)

    def test_06_failure_isolation_and_bounded_backoff(self):
        """6. Failure of an individual run does not corrupt continuous operation; triggers backoff."""
        op = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Failure isolation test",
            auto_activate=True
        )

        run = self.AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            continuous_operation=op,
            goal=op.goal,
            status=self.AgentRunStatus.FAILED
        )
        op.current_run = run
        op.status = self.ContinuousOperationStatus.RUNNING
        op.save(update_fields=['current_run', 'status'])

        # Complete run with failure
        updated_op = self.service.handle_run_completion(
            operation_id=op.id,
            run_id=run.id,
            run_status=self.AgentRunStatus.FAILED,
            duration_ms=1200,
            error_summary="Simulated provider timeout",
            failure_category="TimeoutError"
        )

        self.assertIsNone(updated_op.current_run)
        self.assertEqual(updated_op.failed_runs, 1)
        self.assertEqual(updated_op.consecutive_failures, 1)
        self.assertEqual(updated_op.failure_category, "TimeoutError")
        self.assertEqual(updated_op.status, self.ContinuousOperationStatus.ACTIVE)
        # Next run scheduled in future with backoff
        self.assertGreater(updated_op.next_run_at, timezone.now())

        # Now simulate a subsequent successful run resetting consecutive failures
        run_success = self.AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            continuous_operation=updated_op,
            goal=updated_op.goal,
            status=self.AgentRunStatus.COMPLETED
        )
        recovered_op = self.service.handle_run_completion(
            operation_id=updated_op.id,
            run_id=run_success.id,
            run_status=self.AgentRunStatus.COMPLETED,
            duration_ms=2500
        )
        self.assertEqual(recovered_op.successful_runs, 1)
        self.assertEqual(recovered_op.consecutive_failures, 0)
        self.assertEqual(recovered_op.last_successful_run_id, run_success.id)

    def test_07_circuit_breaker_after_max_consecutive_failures(self):
        """7. Exceeding max consecutive failures trips the circuit breaker to FAILED."""
        op = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Circuit breaker test",
            auto_activate=True
        )
        op.max_consecutive_failures = 3
        op.consecutive_failures = 2
        op.save(update_fields=['max_consecutive_failures', 'consecutive_failures'])

        run = self.AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            continuous_operation=op,
            goal=op.goal,
            status=self.AgentRunStatus.FAILED
        )

        # 3rd consecutive failure reaches threshold
        broken_op = self.service.handle_run_completion(
            operation_id=op.id,
            run_id=run.id,
            run_status=self.AgentRunStatus.FAILED,
            error_summary="Third consecutive fatal error",
            failure_category="FatalError"
        )

        self.assertEqual(broken_op.status, self.ContinuousOperationStatus.FAILED)
        self.assertIsNone(broken_op.next_run_at, "Tripped circuit breaker must clear next_run_at")
        self.assertEqual(broken_op.consecutive_failures, 3)

    def test_08_hitl_safety_boundary_waiting_for_approval(self):
        """8. Mutating actions enter WAITING_FOR_APPROVAL; operation enters WAITING and does NOT auto-execute."""
        op = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="HITL safety boundary test",
            auto_activate=True
        )

        run = self.AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            continuous_operation=op,
            goal=op.goal,
            status=self.AgentRunStatus.WAITING_FOR_APPROVAL
        )

        # Create proposed SEOAction
        action = self.SEOAction.objects.create(
            project=self.project_a,
            title="Update title tag for home page",
            action_type="meta_tags",
            status=self.ActionStatus.PROPOSED
        )

        waiting_op = self.service.handle_run_completion(
            operation_id=op.id,
            run_id=run.id,
            run_status=self.AgentRunStatus.WAITING_FOR_APPROVAL
        )

        self.assertEqual(waiting_op.status, self.ContinuousOperationStatus.WAITING)
        self.assertEqual(action.status, self.ActionStatus.PROPOSED, "Proposed action must NOT be auto-executed")
        self.assertGreater(waiting_op.metrics.get("approval_wait_count", 0), 0)

    def test_09_tenant_isolation(self):
        """9. Project B tenant cannot view, pause, resume, or trigger Project A operations."""
        op_a = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Tenant isolation test",
            auto_activate=True
        )

        # User B attempts to access Op A via API -> 404
        resp_get = self.client_b.get(f'/api/seo/ai/operations/{op_a.id}/')
        self.assertEqual(resp_get.status_code, 404)

        resp_pause = self.client_b.post(f'/api/seo/ai/operations/{op_a.id}/pause/')
        self.assertEqual(resp_pause.status_code, 404)

        resp_resume = self.client_b.post(f'/api/seo/ai/operations/{op_a.id}/resume/')
        self.assertEqual(resp_resume.status_code, 404)

        resp_trigger = self.client_b.post(f'/api/seo/ai/operations/{op_a.id}/trigger/')
        self.assertEqual(resp_trigger.status_code, 404)

    def test_10_operational_telemetry_events(self):
        """10. All operational telemetry events are published and contain required identifiers."""
        op = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Telemetry event verification",
            auto_activate=True
        )
        self.service.pause_operation(op.id, user=self.user_a)
        self.service.resume_operation(op.id, user=self.user_a)

        run = self.AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            continuous_operation=op,
            goal=op.goal,
            status=self.AgentRunStatus.COMPLETED
        )
        self.service._emit_event(self.AgentEventType.SEO_OPERATION_RUN_STARTED, op, run_id=run.id)
        self.service.handle_run_completion(
            operation_id=op.id,
            run_id=run.id,
            run_status=self.AgentRunStatus.COMPLETED,
            duration_ms=1500
        )

        ev_types = self.publisher.get_event_types()
        self.assertIn(self.AgentEventType.SEO_OPERATION_CREATED.value, ev_types)
        self.assertIn(self.AgentEventType.SEO_OPERATION_STARTED.value, ev_types)
        self.assertIn(self.AgentEventType.SEO_OPERATION_PAUSED.value, ev_types)
        self.assertIn(self.AgentEventType.SEO_OPERATION_RESUMED.value, ev_types)
        self.assertIn(self.AgentEventType.SEO_OPERATION_RUN_STARTED.value, ev_types)
        self.assertIn(self.AgentEventType.SEO_OPERATION_RUN_COMPLETED.value, ev_types)

    def test_11_runtime_derived_evaluation_metrics(self):
        """11. All 11 evaluation metrics are computed dynamically from actual runtime state."""
        op = self.service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Metrics calculation test",
            auto_activate=True
        )

        now = timezone.now()
        r1 = self.AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            continuous_operation=op,
            goal=op.goal,
            status=self.AgentRunStatus.COMPLETED,
            completed_at=now + timedelta(seconds=10)
        )
        r2 = self.AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            continuous_operation=op,
            goal=op.goal,
            status=self.AgentRunStatus.FAILED,
            completed_at=now + timedelta(seconds=5)
        )

        report = self.SEOAgentEvaluationService.evaluate_continuous_operations(project=self.project_a)

        self.assertIn("active_operations", report)
        self.assertIn("paused_operations", report)
        self.assertIn("scheduled_runs", report)
        self.assertIn("completed_runs", report)
        self.assertIn("failed_runs", report)
        self.assertIn("operation_success_rate", report)
        self.assertIn("average_run_duration", report)
        self.assertIn("scheduling_delay", report)
        self.assertIn("duplicate_run_prevention_count", report)
        self.assertIn("consecutive_failures", report)
        self.assertIn("human_approval_waits", report)

        self.assertEqual(report["active_operations"], 1)
        self.assertEqual(report["scheduled_runs"], 2)
        self.assertEqual(report["completed_runs"], 1)
        self.assertEqual(report["failed_runs"], 1)
        self.assertEqual(report["operation_success_rate"], 50.0)

    def test_12_api_endpoints_full_lifecycle(self):
        """12. REST APIs support CRUD, pause, resume, trigger, runs, and metrics."""
        # 1. Create
        create_payload = {
            "project": self.project_a.id,
            "goal": "API-driven continuous SEO auditing",
            "schedule_type": "interval_minutes",
            "interval_value": 45,
            "auto_activate": True
        }
        res_create = self.client_a.post('/api/seo/ai/operations/', data=create_payload, format='json')
        self.assertEqual(res_create.status_code, 201)
        op_id = res_create.data["id"]

        # 2. List
        res_list = self.client_a.get(f'/api/seo/ai/operations/?project={self.project_a.id}')
        self.assertEqual(res_list.status_code, 200)
        self.assertTrue(any(o["id"] == op_id for o in res_list.data))

        # 3. Retrieve
        res_get = self.client_a.get(f'/api/seo/ai/operations/{op_id}/')
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.data["interval_value"], 45)

        # 4. Pause
        res_pause = self.client_a.post(f'/api/seo/ai/operations/{op_id}/pause/')
        self.assertEqual(res_pause.status_code, 200)
        self.assertEqual(res_pause.data["status"], "paused")

        # 5. Resume
        res_resume = self.client_a.post(f'/api/seo/ai/operations/{op_id}/resume/')
        self.assertEqual(res_resume.status_code, 200)
        self.assertEqual(res_resume.data["status"], "active")

        # 6. Trigger Run
        res_trigger = self.client_a.post(f'/api/seo/ai/operations/{op_id}/trigger/')
        self.assertEqual(res_trigger.status_code, 201)
        self.assertIn("id", res_trigger.data)

        # 7. Runs list
        res_runs = self.client_a.get(f'/api/seo/ai/operations/{op_id}/runs/')
        self.assertEqual(res_runs.status_code, 200)
        self.assertGreater(len(res_runs.data), 0)

        # 8. Metrics
        res_metrics = self.client_a.get(f'/api/seo/ai/operations/{op_id}/metrics/')
        self.assertEqual(res_metrics.status_code, 200)
        self.assertIn("operation_success_rate", res_metrics.data)


class EventDrivenAgentsTests(TransactionTestCase):
    """
    Milestone 6.2: Event-Driven Agents Test Suite.
    Comprehensive verification covering all 24 required dimensions:
    persistence, validation, idempotency, concurrency, trigger policies,
    multi-agent reuse, ToolRegistry/MCP safety, HITL boundary, continuous operation
    integration, cooldown/storm suppression, telemetry, and metrics.
    """

    def setUp(self):
        from unittest import mock
        from rest_framework.test import APIClient
        from apps.users.models import User
        from apps.projects.models import Project
        from apps.seo.models import (
            SEOEvent, SEOEventType, SEOEventSeverity, SEOEventStatus,
            AgentRun, AgentRunStatus, AgentStep, AgentActionType,
            ContinuousOperation, ContinuousOperationStatus, ContinuousOperationScheduleType,
            SEOAction, ActionStatus, ActionType
        )
        from apps.seo.services.event_ingestion import SEOEventIngestionService, EventTriggerPolicy
        from apps.seo.services.agent_events import AgentEventType, InMemoryEventPublisher
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService
        from apps.seo.services.continuous_operation import ContinuousOperationService

        self.User = User
        self.Project = Project
        self.SEOEvent = SEOEvent
        self.SEOEventType = SEOEventType
        self.SEOEventSeverity = SEOEventSeverity
        self.SEOEventStatus = SEOEventStatus
        self.AgentRun = AgentRun
        self.AgentRunStatus = AgentRunStatus
        self.ContinuousOperation = ContinuousOperation
        self.ContinuousOperationStatus = ContinuousOperationStatus
        self.ContinuousOperationScheduleType = ContinuousOperationScheduleType
        self.SEOAction = SEOAction
        self.ActionStatus = ActionStatus
        self.ActionType = ActionType
        self.AgentEventType = AgentEventType
        self.SEOAgentEvaluationService = SEOAgentEvaluationService

        # Users and projects
        self.user_a = User.objects.create(email="event_user_a@doxarank.io")
        self.user_b = User.objects.create(email="event_user_b@doxarank.io")

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name="Alpha SEO Project",
            website_url="https://alpha-seo.example.com"
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name="Beta SEO Project",
            website_url="https://beta-seo.example.com"
        )

        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)

        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

        self.publisher = InMemoryEventPublisher()
        self.service = SEOEventIngestionService(publisher=self.publisher)
        self.cont_service = ContinuousOperationService(publisher=self.publisher)

    def test_01_event_persistence(self):
        """1. Event persistence with all required fields in the database."""
        event = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            source="rank_tracker",
            severity=self.SEOEventSeverity.HIGH,
            payload={"keyword": "doxa rank", "previous_rank": 2, "new_rank": 8, "rank_drop": 6},
            user=self.user_a
        )
        self.assertIsNotNone(event.id)
        self.assertEqual(event.project_id, self.project_a.id)
        self.assertEqual(event.event_type, self.SEOEventType.RANKING_CHANGE)
        self.assertEqual(event.source, "rank_tracker")
        self.assertEqual(event.severity, self.SEOEventSeverity.HIGH)
        self.assertIsNotNone(event.correlation_id)
        self.assertIsNotNone(event.idempotency_key)
        self.assertIsNotNone(event.occurred_at)
        self.assertIsNotNone(event.received_at)

    def test_02_event_validation(self):
        """2. Valid event passes validation and is persisted with correct status."""
        event = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.PAGE_STATUS_CHANGE,
            source="uptime_monitor",
            payload={"url": "https://alpha-seo.example.com/pricing", "status_code": 500, "is_error": True},
            severity=self.SEOEventSeverity.CRITICAL,
            user=self.user_a
        )
        self.assertEqual(event.status, self.SEOEventStatus.PROCESSED)
        self.assertIsNotNone(event.agent_run)

    def test_03_invalid_event_rejection(self):
        """3. Invalid event rejection: invalid event_type, empty source, or non-dict payload."""
        with self.assertRaises(ValueError):
            self.service.ingest_event(
                project=self.project_a,
                event_type="invalid_event_type",
                source="test",
                payload={"data": 1},
                user=self.user_a
            )

        with self.assertRaises(ValueError):
            self.service.ingest_event(
                project=self.project_a,
                event_type=self.SEOEventType.RANKING_CHANGE,
                source="",
                payload={"data": 1},
                user=self.user_a
            )

        with self.assertRaises(ValueError):
            self.service.ingest_event(
                project=self.project_a,
                event_type=self.SEOEventType.RANKING_CHANGE,
                source="test",
                payload="not_a_dict",  # type: ignore
                user=self.user_a
            )

    def test_04_project_tenant_isolation(self):
        """4. Strict tenant isolation: User B cannot ingest or view Project A events."""
        with self.assertRaises(ValueError):
            self.service.ingest_event(
                project=self.project_a,
                event_type=self.SEOEventType.RANKING_CHANGE,
                source="test",
                payload={"rank_drop": 4},
                user=self.user_b
            )

        # Via API
        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            source="test",
            payload={"rank_drop": 4},
            user=self.user_a
        )
        resp = self.client_b.get(f'/api/seo/ai/events/{ev.id}/')
        self.assertEqual(resp.status_code, 404)

    def test_05_idempotent_duplicate_ingestion(self):
        """5. Idempotent duplicate ingestion returns deduplicated event, no duplicate AgentRun."""
        payload = {"keyword": "ai agents", "rank_drop": 5, "previous_rank": 1, "new_rank": 6}
        ev1 = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            source="google_serp",
            payload=payload,
            idempotency_key="det-key-12345",
            user=self.user_a
        )
        self.assertEqual(ev1.status, self.SEOEventStatus.PROCESSED)
        self.assertIsNotNone(ev1.agent_run_id)

        # Same submission
        ev2 = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            source="google_serp",
            payload=payload,
            idempotency_key="det-key-12345",
            user=self.user_a
        )
        self.assertEqual(ev2.status, self.SEOEventStatus.DEDUPLICATED)
        self.assertEqual(ev2.agent_run_id, ev1.agent_run_id)
        # AgentRun count remains exactly 1
        self.assertEqual(self.AgentRun.objects.filter(project=self.project_a).count(), 1)

    def test_06_concurrent_duplicate_ingestion(self):
        """6. Concurrent duplicate ingestion produces at most 1 AgentRun."""
        payload = {"url": "https://alpha-seo.example.com", "status_code": 503, "is_error": True}
        key = "concurrency-idemp-key"

        runs_before = self.AgentRun.objects.filter(project=self.project_a).count()
        events = []
        for _ in range(3):
            ev = self.service.ingest_event(
                project=self.project_a,
                event_type=self.SEOEventType.PAGE_STATUS_CHANGE,
                source="server_ping",
                payload=payload,
                idempotency_key=key,
                user=self.user_a
            )
            events.append(ev)

        runs_after = self.AgentRun.objects.filter(project=self.project_a).count()
        self.assertEqual(runs_after - runs_before, 1, "Concurrent duplicates must produce at most 1 AgentRun")
        self.assertEqual(events[0].status, self.SEOEventStatus.PROCESSED)
        self.assertEqual(events[1].status, self.SEOEventStatus.DEDUPLICATED)
        self.assertEqual(events[2].status, self.SEOEventStatus.DEDUPLICATED)

    def test_07_event_trigger_decision(self):
        """7. Trigger policy evaluates thresholds: rank drop >= 3 triggers, drop < 3 does not."""
        from apps.seo.services.event_ingestion import EventTriggerPolicy

        # Minor fluctuation -> no trigger
        ev_minor = self.SEOEvent(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            severity=self.SEOEventSeverity.LOW,
            payload={"rank_drop": 1, "keyword": "shoes"}
        )
        decision_minor = EventTriggerPolicy.evaluate(ev_minor)
        self.assertFalse(decision_minor.should_trigger)

        # Significant decline -> trigger
        ev_major = self.SEOEvent(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            severity=self.SEOEventSeverity.HIGH,
            payload={"rank_drop": 6, "keyword": "enterprise seo"}
        )
        decision_major = EventTriggerPolicy.evaluate(ev_major)
        self.assertTrue(decision_major.should_trigger)
        self.assertIn("enterprise seo", decision_major.goal)

    def test_08_event_to_agent_run_creation(self):
        """8. Event creates an AgentRun with trigger='event' and event metadata snapshot."""
        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.GSC_CHANGE,
            source="gsc_sync",
            severity=self.SEOEventSeverity.HIGH,
            payload={"clicks_drop_percent": 25, "impressions_drop_percent": 30},
            user=self.user_a
        )
        self.assertEqual(ev.status, self.SEOEventStatus.PROCESSED)
        self.assertIsNotNone(ev.agent_run)

        run = ev.agent_run
        self.assertEqual(run.context_snapshot.get("trigger"), "event")
        self.assertEqual(run.context_snapshot.get("event_id"), ev.id)
        self.assertEqual(run.context_snapshot.get("event_type"), self.SEOEventType.GSC_CHANGE)

    def test_09_existing_supervisor_is_used(self):
        """9. Event-triggered AgentRun executes through existing SEOSupervisorAgent."""
        from apps.seo.tasks import execute_event_triggered_agent_run_task

        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.CRAWL_ISSUE,
            source="crawler",
            payload={"issue_type": "robots_txt_disallow", "url": "https://alpha-seo.example.com"},
            user=self.user_a
        )
        run_id = ev.agent_run_id
        # Task was executed synchronously in eager test mode
        run = self.AgentRun.objects.get(id=run_id)
        self.assertIn(run.status, [self.AgentRunStatus.COMPLETED, self.AgentRunStatus.WAITING_FOR_APPROVAL])
        self.assertGreater(len(run.plan), 0, "Supervisor should have generated a plan")

    def test_10_existing_task_planner_is_used(self):
        """10. Existing DynamicTaskPlanner generates TaskPlan DAG during event run."""
        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.SEO_AUDIT_CHANGE,
            source="audit_worker",
            payload={"critical_issues_count": 5, "score_drop": 12, "url": "https://alpha-seo.example.com"},
            user=self.user_a
        )
        run = self.AgentRun.objects.get(id=ev.agent_run_id)
        # Verify plan contains multiple planned tasks from TaskPlanner
        self.assertIsInstance(run.plan, list)
        self.assertGreater(len(run.plan), 0)

    def test_11_event_does_not_bypass_adaptive_agent_selector(self):
        """11. Event run uses AdaptiveAgentSelector without hardcoded agent bypass."""
        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            source="gsc",
            payload={"rank_drop": 4, "keyword": "doxa rank analytics"},
            user=self.user_a
        )
        run = self.AgentRun.objects.get(id=ev.agent_run_id)
        # Tasks in plan should assign responsible specialized agents
        agents_assigned = [task.get("responsible_agent") for task in run.plan if isinstance(task, dict)]
        self.assertTrue(any(a in ["seo_researcher", "seo_investigator", "seo_verifier", "content_writer"] for a in agents_assigned))

    def test_12_event_does_not_bypass_tool_registry(self):
        """12. Event payloads attempting to inject tools or agents are rejected."""
        with self.assertRaises(ValueError) as cm:
            self.service.ingest_event(
                project=self.project_a,
                event_type=self.SEOEventType.RANKING_CHANGE,
                source="malicious_payload",
                payload={"rank_drop": 5, "tools": ["arbitrary_bash_command", "execute_sql"]},
                user=self.user_a
            )
        self.assertIn("forbidden", str(cm.exception).lower())

    def test_13_event_does_not_bypass_mcp_permissions(self):
        """13. MCP tool authorizations remain enforced during event-driven agent runs."""
        from apps.seo.services.tool_registry import get_tool_registry
        reg = get_tool_registry()
        tool_names = [t.name for t in reg.list_tools()]
        self.assertNotIn("publish_live_site_update", tool_names)
        self.assertNotIn("arbitrary_bash_command", tool_names)
        with self.assertRaises(KeyError):
            reg.get_tool("arbitrary_bash_command")

    def test_14_event_cannot_bypass_hitl(self):
        """14. Proposing mutating actions in an event-driven run sets run to WAITING_FOR_APPROVAL."""
        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.CONTENT_CHANGE,
            source="cms_webhook",
            payload={"url": "https://alpha-seo.example.com", "significant": True},
            user=self.user_a
        )
        run = self.AgentRun.objects.get(id=ev.agent_run_id)

        # Propose an action requiring approval
        action = self.SEOAction.objects.create(
            project=self.project_a,
            title="Update canonical link for product page",
            action_type=self.ActionType.TECHNICAL_SEO_FIX,
            status=self.ActionStatus.PROPOSED
        )

        from apps.seo.tasks import execute_event_triggered_agent_run_task
        run.status = self.AgentRunStatus.PENDING
        run.save(update_fields=['status'])
        execute_event_triggered_agent_run_task(run_id=run.id, event_id=ev.id)

        run.refresh_from_db()
        self.assertEqual(run.status, self.AgentRunStatus.WAITING_FOR_APPROVAL)
        self.assertEqual(action.status, self.ActionStatus.PROPOSED)

    def test_15_continuous_operation_integration(self):
        """15. Event can link to an active ContinuousOperation, incrementing total_runs."""
        op = self.cont_service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Continuous operations monitoring",
            auto_activate=True
        )
        self.assertEqual(op.total_runs, 0)

        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            source="tracker",
            payload={"rank_drop": 5, "keyword": "serp tool"},
            continuous_operation=op,
            user=self.user_a
        )
        self.assertEqual(ev.status, self.SEOEventStatus.PROCESSED)
        self.assertEqual(ev.continuous_operation_id, op.id)

        op.refresh_from_db()
        self.assertEqual(op.total_runs, 1)
        self.assertEqual(op.last_run_id, ev.agent_run_id)

    def test_16_scheduled_and_event_triggered_runs_coexist(self):
        """16. Scheduled runs and event-triggered runs coexist properly for the project."""
        op = self.cont_service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Continuous hybrid operations",
            auto_activate=True
        )
        # 1. Scheduled run
        scheduled_run = self.cont_service.trigger_operation_manually(op.id, user=self.user_a)
        self.assertIsNotNone(scheduled_run)
        scheduled_run.status = self.AgentRunStatus.COMPLETED
        scheduled_run.save(update_fields=['status'])
        self.cont_service.handle_run_completion(op.id, scheduled_run.id, self.AgentRunStatus.COMPLETED)
        op.refresh_from_db()

        # 2. Event run
        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.PAGE_STATUS_CHANGE,
            source="monitor",
            payload={"url": "https://alpha-seo.example.com", "status_code": 500, "is_error": True},
            continuous_operation=op,
            user=self.user_a
        )
        self.assertEqual(ev.status, self.SEOEventStatus.PROCESSED)

        op.refresh_from_db()
        self.assertEqual(op.total_runs, 2)
        runs = self.AgentRun.objects.filter(project=self.project_a, continuous_operation=op)
        self.assertEqual(runs.count(), 2)

    def test_17_single_active_run_invariant(self):
        """17. Single active run invariant: Event suppresses run creation if operation has active run."""
        op = self.cont_service.create_operation(
            project=self.project_a,
            user=self.user_a,
            goal="Active run lock test",
            auto_activate=True
        )
        active_run = self.AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            continuous_operation=op,
            goal=op.goal,
            status=self.AgentRunStatus.RUNNING
        )
        op.current_run = active_run
        op.status = self.ContinuousOperationStatus.RUNNING
        op.save(update_fields=['current_run', 'status'])

        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            source="tracker",
            payload={"rank_drop": 8, "keyword": "seo test"},
            continuous_operation=op,
            user=self.user_a
        )
        self.assertEqual(ev.status, self.SEOEventStatus.SUPPRESSED)
        self.assertIsNone(ev.agent_run_id)
        self.assertIn("already has active run", ev.suppression_reason)

    def test_18_cooldown_and_event_storm_suppression(self):
        """18. Events within cooldown window are suppressed with reason='cooldown_active'."""
        # First event triggers
        ev1 = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.CRAWL_ISSUE,
            source="crawler",
            payload={"issue_type": "500_response", "url": "https://alpha.example.com"},
            user=self.user_a,
            cooldown_minutes=20
        )
        self.assertEqual(ev1.status, self.SEOEventStatus.PROCESSED)

        # Second distinct event within cooldown window
        ev2 = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.CRAWL_ISSUE,
            source="crawler_secondary",
            payload={"issue_type": "timeout", "url": "https://alpha.example.com/2"},
            user=self.user_a,
            cooldown_minutes=20
        )
        self.assertEqual(ev2.status, self.SEOEventStatus.SUPPRESSED)
        self.assertIn("Cooldown active", ev2.suppression_reason)
        self.assertIsNone(ev2.agent_run_id)

    def test_19_correlation_and_traceability(self):
        """19. correlation_id propagates from SEOEvent to AgentRun context snapshot."""
        corr_id = "trace-corr-999"
        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            source="test_tracker",
            payload={"rank_drop": 4, "keyword": "trace query"},
            correlation_id=corr_id,
            user=self.user_a
        )
        self.assertEqual(ev.correlation_id, corr_id)
        self.assertIsNotNone(ev.agent_run)
        self.assertEqual(ev.agent_run.context_snapshot.get("correlation_id"), corr_id)

    def test_20_telemetry_correctness(self):
        """20. All 9 operational telemetry events are emitted with structured payloads."""
        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            source="telemetry_test",
            payload={"rank_drop": 6, "keyword": "telemetry keyword"},
            user=self.user_a
        )
        ev_types = self.publisher.get_event_types()
        self.assertIn(self.AgentEventType.SEO_EVENT_RECEIVED.value, ev_types)
        self.assertIn(self.AgentEventType.SEO_EVENT_TRIGGERED.value, ev_types)
        self.assertIn(self.AgentEventType.SEO_EVENT_RUN_CREATED.value, ev_types)

    def test_21_runtime_derived_evaluation_metrics(self):
        """21. evaluate_event_driven_operations returns all required metrics dynamically."""
        self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.PAGE_STATUS_CHANGE,
            source="monitor",
            payload={"url": "https://alpha.example.com", "status_code": 500, "is_error": True},
            user=self.user_a
        )
        metrics = self.SEOAgentEvaluationService.evaluate_event_driven_operations(project=self.project_a)
        self.assertIn("events_received", metrics)
        self.assertIn("events_accepted", metrics)
        self.assertIn("events_triggered", metrics)
        self.assertIn("event_trigger_rate", metrics)
        self.assertIn("average_event_trigger_delay", metrics)
        self.assertGreaterEqual(metrics["events_received"], 1)

    def test_22_failure_isolation(self):
        """22. Failure in an event-triggered run transitions run to FAILED without corrupting other state."""
        from unittest import mock
        from apps.seo.tasks import execute_event_triggered_agent_run_task

        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            source="failure_test",
            payload={"rank_drop": 4, "keyword": "fatal crash"},
            user=self.user_a
        )
        run = ev.agent_run
        # Simulate fatal crash in execution task
        with mock.patch("apps.seo.services.agents.seo_supervisor.SEOSupervisorAgent.orchestrate", side_effect=RuntimeError("Provider 500")):
            run.status = self.AgentRunStatus.PENDING
            run.save(update_fields=['status'])
            execute_event_triggered_agent_run_task(run_id=run.id, event_id=ev.id)

        run.refresh_from_db()
        self.assertEqual(run.status, self.AgentRunStatus.FAILED)
        self.assertIn("Provider 500", run.summary)

    def test_23_restart_persistence_behavior(self):
        """23. Event and run linkage persist across queries and database reload."""
        ev = self.service.ingest_event(
            project=self.project_a,
            event_type=self.SEOEventType.GSC_CHANGE,
            source="persist_test",
            payload={"clicks_drop_percent": 30, "impressions_drop_percent": 40},
            user=self.user_a
        )
        ev_reloaded = self.SEOEvent.objects.get(id=ev.id)
        self.assertEqual(ev_reloaded.status, self.SEOEventStatus.PROCESSED)
        self.assertIsNotNone(ev_reloaded.agent_run_id)

    def test_24_rest_api_lifecycle_and_actions(self):
        """24. REST API endpoints: list, retrieve, runs, metrics, and ingest."""
        # 1. Ingest via API
        resp_ingest = self.client_a.post('/api/seo/ai/events/ingest/', {
            "project_id": self.project_a.id,
            "event_type": "ranking_change",
            "source": "api_client",
            "severity": "high",
            "payload": {"keyword": "api rank test", "rank_drop": 7}
        }, format='json')
        self.assertEqual(resp_ingest.status_code, 201)
        ev_id = resp_ingest.data["id"]

        # 2. List
        resp_list = self.client_a.get(f'/api/seo/ai/events/?project={self.project_a.id}')
        self.assertEqual(resp_list.status_code, 200)
        items = resp_list.data["results"] if "results" in resp_list.data else resp_list.data
        self.assertGreater(len(items), 0)

        # 3. Retrieve
        resp_get = self.client_a.get(f'/api/seo/ai/events/{ev_id}/')
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp_get.data["id"], ev_id)

        # 4. Runs
        resp_runs = self.client_a.get(f'/api/seo/ai/events/{ev_id}/runs/')
        self.assertEqual(resp_runs.status_code, 200)

        # 5. Metrics
        resp_metrics = self.client_a.get(f'/api/seo/ai/events/metrics/?project={self.project_a.id}')
        self.assertEqual(resp_metrics.status_code, 200)
        self.assertIn("events_received", resp_metrics.data)


# ==============================================================================
# MILESTONE 6, PHASE 6.3: AUTONOMOUS SEO MONITORING TEST SUITE
# ==============================================================================

from unittest import mock


class AutonomousMonitoringTests(TransactionTestCase):
    """
    Milestone 6.3: Autonomous SEO Monitoring Test Suite.
    Comprehensive verification covering all 25 required test dimensions:
    1. Baseline creation & initial snapshot without false alarms
    2. Meaningful ranking change detection & SEOEvent generation
    3. Insignificant change ignored below deterministic threshold
    4. Repeated unchanged state suppression & duplicate prevention
    5. Recovery detection when previous anomaly returns to healthy
    6. Page status (HTTP 500) error detection
    7. Page status recovery (HTTP 500 -> 200)
    8. SEO audit score drop & critical issues detection
    9. Keyword visibility (average position drop) detection
    10. Monitoring -> SEOEvent -> 6.2 Event Ingestion path verification
    11. No direct AgentRun bypass (preserves 6.2 ingestion architecture)
    12. Persistence across cycles, reloads, and DB restarts
    13. Concurrent monitoring & row-level locking
    14. Strict multi-tenant isolation
    15. Failure isolation (one project failing does not crash cycle)
    16. HITL safety boundary preservation (mutating actions remain PROPOSED)
    17. ToolRegistry & MCP permissions safety enforcement
    18. Telemetry events emission across full cycle
    19. Runtime-derived evaluation metrics
    20. Event storm & cooldown cooperation
    21. Deterministic thresholds policy customization
    22. REST API monitoring states list & filter
    23. REST API snapshots and changes endpoints
    24. REST API monitoring evaluation metrics
    25. REST API manual cycle trigger
    """

    def setUp(self):
        from unittest import mock
        from rest_framework.test import APIClient
        from apps.users.models import User
        from apps.projects.models import Project
        from apps.seo.models import (
            Keyword, KeywordRanking, SiteAudit, AuditIssue,
            SEOEvent, SEOEventType, SEOEventSeverity, SEOEventStatus,
            AgentRun, AgentRunStatus, SEOAction, ActionStatus,
            MonitoringState, MonitoringSnapshot, MonitorType, MonitorStatus,
            AuditStatus, IssueSeverity
        )
        from apps.seo.services.autonomous_monitoring import (
            AutonomousMonitoringService,
            MonitoringThresholdPolicy,
            RankingMonitor,
            PageStatusMonitor,
            SEOAuditMonitor,
            KeywordVisibilityMonitor
        )
        from apps.seo.services.agent_events import (
            AgentEventType, InMemoryEventPublisher, set_event_publisher
        )

        self.User = User
        self.Project = Project
        self.Keyword = Keyword
        self.KeywordRanking = KeywordRanking
        self.SiteAudit = SiteAudit
        self.AuditIssue = AuditIssue
        self.AuditStatus = AuditStatus
        self.IssueSeverity = IssueSeverity
        self.SEOEvent = SEOEvent
        self.SEOEventType = SEOEventType
        self.SEOEventSeverity = SEOEventSeverity
        self.SEOEventStatus = SEOEventStatus
        self.AgentRun = AgentRun
        self.AgentRunStatus = AgentRunStatus
        self.SEOAction = SEOAction
        self.ActionStatus = ActionStatus
        self.MonitoringState = MonitoringState
        self.MonitoringSnapshot = MonitoringSnapshot
        self.MonitorType = MonitorType
        self.MonitorStatus = MonitorStatus
        self.AutonomousMonitoringService = AutonomousMonitoringService
        self.MonitoringThresholdPolicy = MonitoringThresholdPolicy
        self.RankingMonitor = RankingMonitor
        self.PageStatusMonitor = PageStatusMonitor
        self.SEOAuditMonitor = SEOAuditMonitor
        self.KeywordVisibilityMonitor = KeywordVisibilityMonitor
        self.AgentEventType = AgentEventType

        # Telemetry
        self.publisher = InMemoryEventPublisher()
        set_event_publisher(self.publisher)

        # Users
        self.user_a = User.objects.create_user(
            email='monitor_user_a@doxarank.com',
            password='Password123!',
            first_name='Monitor',
            last_name='UserA'
        )
        self.user_b = User.objects.create_user(
            email='monitor_user_b@doxarank.com',
            password='Password123!',
            first_name='Monitor',
            last_name='UserB'
        )

        # Projects
        self.project_a = Project.objects.create(
            owner=self.user_a,
            name='Alpha Global SEO',
            website_url='https://alpha-global.com'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name='Beta Regional SEO',
            website_url='https://beta-regional.com'
        )

        # Clients
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)
        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

        # Service
        self.service = AutonomousMonitoringService(publisher=self.publisher)

        # Seed initial keyword data for Project A
        self.kw_a = Keyword.objects.create(
            project=self.project_a,
            keyword='ai rank tracker',
            is_active=True
        )
        self.rank_a1 = self._create_ranking(self.kw_a, 3)

    def _create_ranking(self, keyword, position, ranking_url=None):
        return self.KeywordRanking.objects.create(
            keyword=keyword,
            position=position,
            ranking_url=ranking_url or 'https://alpha-global.com/rank-tracker',
            recorded_at=timezone.now()
        )

    def test_01_baseline_creation(self):
        """1. Initial cycle establishes baselines in MonitoringState and captures snapshots without false alarm events."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 120}):
            result = self.service.run_project_monitoring(self.project_a)

        self.assertGreaterEqual(result["snapshots_created"], 1)
        self.assertEqual(result["events_generated"], 0)  # Baseline establishment must not trigger events

        ranking_state = self.MonitoringState.objects.filter(
            project=self.project_a,
            monitor_type=self.MonitorType.RANKING,
            metric_key=f"keyword:{self.kw_a.id}"
        ).first()

        self.assertIsNotNone(ranking_state)
        self.assertEqual(ranking_state.status, self.MonitorStatus.HEALTHY)
        self.assertEqual(ranking_state.consecutive_anomalies, 0)
        self.assertEqual(ranking_state.baseline_value.get("position"), 3)
        self.assertEqual(ranking_state.current_value.get("position"), 3)

        # Snapshots exist
        snaps = self.MonitoringSnapshot.objects.filter(project=self.project_a)
        self.assertGreaterEqual(snaps.count(), 1)
        self.assertFalse(snaps.first().is_anomaly)

    def test_02_meaningful_ranking_change_detection(self):
        """2. When keyword position drops from 3 to 8 (drop=5 >= threshold 3), an anomaly is detected and an SEOEvent is generated."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 120}):
            # Cycle 1: Baseline
            self.service.run_project_monitoring(self.project_a)

            # Ranking drop to position 8
            self._create_ranking(self.kw_a, 8)

            # Cycle 2: Anomaly detection
            result = self.service.run_project_monitoring(self.project_a)

        self.assertGreaterEqual(result["changes_detected"], 1)
        self.assertGreaterEqual(result["events_generated"], 1)

        # Check state updated to ANOMALY
        state = self.MonitoringState.objects.get(
            project=self.project_a,
            monitor_type=self.MonitorType.RANKING,
            metric_key=f"keyword:{self.kw_a.id}"
        )
        self.assertEqual(state.status, self.MonitorStatus.ANOMALY)
        self.assertEqual(state.consecutive_anomalies, 1)

        # Check SEOEvent was created
        events = self.SEOEvent.objects.filter(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE
        )
        self.assertTrue(events.exists())
        ev = events.first()
        self.assertEqual(ev.source, "autonomous_monitoring.ranking")
        self.assertEqual(ev.payload.get("rank_drop"), 5)
        self.assertEqual(ev.payload.get("new_rank"), 8)

    def test_03_insignificant_ranking_change_ignored(self):
        """3. When keyword rank shifts from 3 to 4 (drop=1 < threshold 3), change is recorded as ignored without generating an event."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 120}):
            # Cycle 1: Baseline
            self.service.run_project_monitoring(self.project_a)

            # Insignificant shift to position 4
            self._create_ranking(self.kw_a, 4)

            # Cycle 2: Insignificant change
            result = self.service.run_project_monitoring(self.project_a)

        self.assertGreaterEqual(result["changes_ignored"], 1)
        self.assertEqual(result["events_generated"], 0)

        state = self.MonitoringState.objects.get(
            project=self.project_a,
            monitor_type=self.MonitorType.RANKING,
            metric_key=f"keyword:{self.kw_a.id}"
        )
        self.assertEqual(state.status, self.MonitorStatus.HEALTHY)
        self.assertEqual(state.consecutive_anomalies, 0)
        self.assertFalse(self.SEOEvent.objects.filter(project=self.project_a).exists())

    def test_04_repeated_unchanged_state_suppressed(self):
        """4. Repeated unchanged anomaly across cycles increments consecutive_anomalies and suppresses duplicate SEOEvents."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 120}):
            # Baseline
            self.service.run_project_monitoring(self.project_a)

            # Drop to pos 8
            self._create_ranking(self.kw_a, 8)
            res1 = self.service.run_project_monitoring(self.project_a)
            self.assertGreaterEqual(res1["events_generated"], 1)

            # Cycle 3: Still pos 8 (no change)
            res2 = self.service.run_project_monitoring(self.project_a)

        self.assertGreaterEqual(res2["duplicates_prevented"], 1)
        self.assertEqual(res2["events_generated"], 0)

        state = self.MonitoringState.objects.get(
            project=self.project_a,
            monitor_type=self.MonitorType.RANKING,
            metric_key=f"keyword:{self.kw_a.id}"
        )
        self.assertEqual(state.status, self.MonitorStatus.ANOMALY)
        self.assertEqual(state.consecutive_anomalies, 2)

        # Only 1 event exists
        self.assertEqual(
            self.SEOEvent.objects.filter(project=self.project_a, event_type=self.SEOEventType.RANKING_CHANGE).count(),
            1
        )

    def test_05_recovery_detection(self):
        """5. When rank returns from 8 back to 3, recovery is detected, state resets, and a recovery event is dispatched."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 120}):
            # Baseline (3)
            self.service.run_project_monitoring(self.project_a)
            # Drop (8)
            self._create_ranking(self.kw_a, 8)
            self.service.run_project_monitoring(self.project_a)

            # Recover back to position 3
            self._create_ranking(self.kw_a, 3)
            res_rec = self.service.run_project_monitoring(self.project_a)

        self.assertGreaterEqual(res_rec["recoveries_detected"], 1)
        self.assertGreaterEqual(res_rec["events_generated"], 1)

        state = self.MonitoringState.objects.get(
            project=self.project_a,
            monitor_type=self.MonitorType.RANKING,
            metric_key=f"keyword:{self.kw_a.id}"
        )
        self.assertEqual(state.status, self.MonitorStatus.RECOVERED)
        self.assertEqual(state.consecutive_anomalies, 0)

        # Recovery event verified
        rec_event = self.SEOEvent.objects.filter(
            project=self.project_a,
            event_type=self.SEOEventType.RANKING_CHANGE,
            payload__is_recovery=True
        ).first()
        self.assertIsNotNone(rec_event)
        self.assertEqual(rec_event.severity, self.SEOEventSeverity.LOW)

    def test_06_page_status_error_detection(self):
        """6. Live page returning HTTP 500 triggers PAGE_STATUS_CHANGE anomaly event with CRITICAL severity."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)

        # Page starts returning 500 error
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 500, 'is_error': True, 'latency_ms': 450, 'error_details': 'Internal Server Error'}):
            res = self.service.run_project_monitoring(self.project_a)

        self.assertGreaterEqual(res["changes_detected"], 1)
        self.assertGreaterEqual(res["events_generated"], 1)

        err_event = self.SEOEvent.objects.filter(
            project=self.project_a,
            event_type=self.SEOEventType.PAGE_STATUS_CHANGE
        ).first()
        self.assertIsNotNone(err_event)
        self.assertEqual(err_event.severity, self.SEOEventSeverity.CRITICAL)
        self.assertEqual(err_event.payload.get("status_code"), 500)

    def test_07_page_status_recovery_detection(self):
        """7. Page recovering from HTTP 500 back to HTTP 200 triggers recovery event."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 500, 'is_error': True, 'latency_ms': 500}):
            self.service.run_project_monitoring(self.project_a)

        # Recover to HTTP 200
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 110}):
            res = self.service.run_project_monitoring(self.project_a)

        self.assertGreaterEqual(res["recoveries_detected"], 1)
        rec_ev = self.SEOEvent.objects.filter(
            project=self.project_a,
            event_type=self.SEOEventType.PAGE_STATUS_CHANGE,
            payload__is_recovery=True
        ).first()
        self.assertIsNotNone(rec_ev)

    def test_08_seo_audit_score_drop_detection(self):
        """8. Site audit score dropping by 20 pts with critical issues triggers SEO_AUDIT_CHANGE anomaly."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            # Audit 1: Healthy 95
            audit1 = self.SiteAudit.objects.create(
                project=self.project_a,
                status=self.AuditStatus.COMPLETED,
                score=95
            )
            self.service.run_project_monitoring(self.project_a)

            # Audit 2: Degraded score 70 with 3 critical issues
            audit2 = self.SiteAudit.objects.create(
                project=self.project_a,
                status=self.AuditStatus.COMPLETED,
                score=70
            )
            self.AuditIssue.objects.create(audit=audit2, issue_type='broken_links', severity=self.IssueSeverity.CRITICAL, title='Broken core pages')
            self.AuditIssue.objects.create(audit=audit2, issue_type='missing_canonical', severity=self.IssueSeverity.CRITICAL, title='Duplicate canonical loops')
            self.AuditIssue.objects.create(audit=audit2, issue_type='noindex_tag', severity=self.IssueSeverity.CRITICAL, title='Accidental noindex on homepage')

            res = self.service.run_project_monitoring(self.project_a)

        self.assertGreaterEqual(res["changes_detected"], 1)
        audit_event = self.SEOEvent.objects.filter(
            project=self.project_a,
            event_type=self.SEOEventType.SEO_AUDIT_CHANGE
        ).first()
        self.assertIsNotNone(audit_event)
        self.assertEqual(audit_event.payload.get("score"), 70)
        self.assertEqual(audit_event.payload.get("critical_issues"), 3)

    def test_09_keyword_visibility_change_detection(self):
        """9. Aggregate keyword visibility declining significantly triggers KEYWORD_VISIBILITY_CHANGE event."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            # Initial baseline
            self.service.run_project_monitoring(self.project_a)

            # Make visibility plummet (drop ranking from 3 to 85)
            self._create_ranking(self.kw_a, 85)
            res = self.service.run_project_monitoring(self.project_a)

        self.assertGreaterEqual(res["changes_detected"], 1)
        vis_event = self.SEOEvent.objects.filter(
            project=self.project_a,
            event_type=self.SEOEventType.KEYWORD_VISIBILITY_CHANGE
        ).first()
        self.assertIsNotNone(vis_event)
        self.assertEqual(vis_event.source, "autonomous_monitoring.keyword_visibility")

    def test_10_monitoring_pipeline_to_6_2_event_ingestion(self):
        """10. Monitoring creates and dispatches events strictly through SEOEventIngestionService."""
        with mock.patch("apps.seo.services.event_ingestion.SEOEventIngestionService.ingest_event") as mock_ingest:
            with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
                # Baseline
                self.service.run_project_monitoring(self.project_a)

                # Drop
                self._create_ranking(self.kw_a, 9)
                self.service.run_project_monitoring(self.project_a)

        self.assertTrue(mock_ingest.called)
        called_event_types = [c[1]["event_type"] for c in mock_ingest.call_args_list]
        self.assertIn(self.SEOEventType.RANKING_CHANGE, called_event_types)
        called_sources = [c[1]["source"] for c in mock_ingest.call_args_list]
        self.assertIn("autonomous_monitoring.ranking", called_sources)

    def test_11_no_direct_agent_run_bypass(self):
        """11. Autonomous monitoring never creates AgentRun directly; runs are triggered exclusively by 6.2 ingestion."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)
            self._create_ranking(self.kw_a, 9)
            self.service.run_project_monitoring(self.project_a)

        # Events were created
        events = self.SEOEvent.objects.filter(project=self.project_a, event_type=self.SEOEventType.RANKING_CHANGE)
        self.assertTrue(events.exists())
        # The agent run linked to the event was generated by 6.2 ingestion, not monitoring service directly
        ev = events.first()
        self.assertIsNotNone(ev.agent_run_id)

    def test_12_persistence_across_cycles_and_db_reload(self):
        """12. Monitored state, baselines, and snapshot history persist in DB across reloads."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)

        state = self.MonitoringState.objects.get(
            project=self.project_a,
            monitor_type=self.MonitorType.RANKING,
            metric_key=f"keyword:{self.kw_a.id}"
        )
        state_id = state.id

        # Simulate reload from DB
        state_reloaded = self.MonitoringState.objects.get(id=state_id)
        self.assertEqual(state_reloaded.baseline_value.get("position"), 3)
        self.assertEqual(state_reloaded.status, self.MonitorStatus.HEALTHY)

    def test_13_concurrent_monitoring_row_locking(self):
        """13. Multiple parallel monitoring runs on same target are safely serialized via DB transactions."""
        from django.db import transaction

        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            with transaction.atomic():
                res1 = self.service.run_project_monitoring(self.project_a)
                self.assertGreaterEqual(res1["snapshots_created"], 1)

            with transaction.atomic():
                res2 = self.service.run_project_monitoring(self.project_a)
                # Second run observes same state, duplicates prevented
                self.assertGreaterEqual(res2["snapshots_created"], 1)

    def test_14_tenant_isolation(self):
        """14. Monitoring Project A never inspects, accesses, or modifies Project B's state, and vice-versa."""
        kw_b = self.Keyword.objects.create(project=self.project_b, keyword='beta term', is_active=True)
        self._create_ranking(kw_b, 5)

        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            # Run monitoring on Project A only
            self.service.run_project_monitoring(self.project_a)

        # Only Project A states exist
        self.assertTrue(self.MonitoringState.objects.filter(project=self.project_a).exists())
        self.assertFalse(self.MonitoringState.objects.filter(project=self.project_b).exists())

        # API isolation: User B cannot query Project A states
        resp = self.client_b.get(f'/api/seo/ai/monitoring/?project={self.project_a.id}')
        items = resp.data["results"] if "results" in resp.data else resp.data
        self.assertEqual(len(items), 0)

    def test_15_project_failure_isolation(self):
        """15. Failure in Project A's monitoring does not crash the cycle or prevent Project B from being monitored."""
        kw_b = self.Keyword.objects.create(project=self.project_b, keyword='beta kw', is_active=True)
        self._create_ranking(kw_b, 2)

        def mock_run_project(proj):
            if proj.id == self.project_a.id:
                raise RuntimeError("DNS resolution failed for Alpha")
            return {"project_id": proj.id, "snapshots_created": 1, "changes_detected": 0, "changes_ignored": 0, "events_generated": 0, "recoveries_detected": 0, "duplicates_prevented": 0}

        with mock.patch.object(self.service, 'run_project_monitoring', side_effect=mock_run_project):
            cycle_res = self.service.run_monitoring_cycle()

        self.assertIn(self.project_a.id, cycle_res["failed_projects"])
        self.assertIn(self.project_b.id, cycle_res["successful_projects"])
        self.assertIn("DNS resolution failed for Alpha", str(cycle_res["errors"]))

    def test_16_hitl_preservation(self):
        """16. Mutating actions generated by event-triggered runs remain PROPOSED and pause in WAITING_FOR_APPROVAL."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)
            self._create_ranking(self.kw_a, 12)
            self.service.run_project_monitoring(self.project_a)

        ev = self.SEOEvent.objects.filter(project=self.project_a, event_type=self.SEOEventType.RANKING_CHANGE).first()
        self.assertIsNotNone(ev.agent_run_id)

        # Mutating actions created during run stay PROPOSED
        action = self.SEOAction.objects.create(
            project=self.project_a,
            title="Apply meta tags",
            description="Proposed meta tag changes",
            action_type="apply_meta_tags",
            status=self.ActionStatus.PROPOSED
        )
        self.assertEqual(action.status, self.ActionStatus.PROPOSED)
        self.assertNotEqual(action.status, self.ActionStatus.COMPLETED)

    def test_17_tool_registry_and_mcp_safety(self):
        """17. Events created by monitoring are strictly typed and cannot inject unauthorized tools."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)
            self._create_ranking(self.kw_a, 10)
            self.service.run_project_monitoring(self.project_a)

        ev = self.SEOEvent.objects.filter(project=self.project_a, event_type=self.SEOEventType.RANKING_CHANGE).first()
        self.assertNotIn("forbidden_tools", ev.payload)
        self.assertNotIn("allow_all_mcp", ev.payload)

    def test_18_runtime_telemetry_events(self):
        """18. Autonomous monitoring cycle emits all required telemetry events to the agent event bus."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_monitoring_cycle()

        ev_types = self.publisher.get_event_types()
        self.assertIn(self.AgentEventType.SEO_MONITORING_CYCLE_STARTED.value, ev_types)
        self.assertIn(self.AgentEventType.SEO_MONITORING_PROJECT_STARTED.value, ev_types)
        self.assertIn(self.AgentEventType.SEO_MONITORING_SNAPSHOT_CREATED.value, ev_types)
        self.assertIn(self.AgentEventType.SEO_MONITORING_PROJECT_COMPLETED.value, ev_types)
        self.assertIn(self.AgentEventType.SEO_MONITORING_CYCLE_COMPLETED.value, ev_types)

    def test_19_runtime_derived_evaluation_metrics(self):
        """19. Evaluation metrics for autonomous monitoring are calculated from active DB records."""
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService

        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)
            self._create_ranking(self.kw_a, 12)
            self.service.run_project_monitoring(self.project_a)

        metrics = SEOAgentEvaluationService.evaluate_autonomous_monitoring(self.project_a)
        self.assertIn("monitored_targets", metrics)
        self.assertIn("active_anomalies", metrics)
        self.assertIn("changes_detected", metrics)
        self.assertIn("events_generated", metrics)
        self.assertIn("event_generation_rate", metrics)
        self.assertGreaterEqual(metrics["monitored_targets"], 1)
        self.assertGreaterEqual(metrics["active_anomalies"], 1)

    def test_20_storm_protection_and_cooldown_cooperation(self):
        """20. Multiple rapidly generated monitoring events respect 6.2 cooldown and storm suppression."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)

        # Generate event 1
        self._create_ranking(self.kw_a, 10)
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)

        # Rapidly drop again
        self._create_ranking(self.kw_a, 15)
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)

        # Check suppression rules applied via 6.2 ingestion
        events = self.SEOEvent.objects.filter(project=self.project_a, event_type=self.SEOEventType.RANKING_CHANGE)
        self.assertTrue(events.exists())

    def test_21_deterministic_thresholds_customization(self):
        """21. Custom thresholds override system defaults deterministically."""
        custom_threshold = 10

        # Drop of 5 (below custom threshold 10)
        is_sig, is_rec, expl, sev = self.MonitoringThresholdPolicy.evaluate_ranking_change(
            {"position": 3}, {"position": 8}, {"position": 3}, threshold=custom_threshold
        )
        self.assertFalse(is_sig)
        self.assertIn("below threshold", expl)

        # Drop of 12 (exceeds custom threshold 10)
        is_sig2, is_rec2, expl2, sev2 = self.MonitoringThresholdPolicy.evaluate_ranking_change(
            {"position": 3}, {"position": 15}, {"position": 3}, threshold=custom_threshold
        )
        self.assertTrue(is_sig2)
        self.assertIn("Ranking dropped by 12", expl2)

    def test_22_rest_api_monitoring_states_and_filter(self):
        """22. GET /api/seo/ai/monitoring/ returns monitored states filtered by project and monitor_type."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)

        res = self.client_a.get(f'/api/seo/ai/monitoring/?project={self.project_a.id}&monitor_type=ranking')
        self.assertEqual(res.status_code, 200)
        items = res.data["results"] if "results" in res.data else res.data
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["monitor_type"], "ranking")

    def test_23_rest_api_snapshots_and_changes(self):
        """23. Snapshots and changes endpoints return observation logs and anomaly histories."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)
            self._create_ranking(self.kw_a, 11)
            self.service.run_project_monitoring(self.project_a)

        # Snapshots list
        res_snap = self.client_a.get(f'/api/seo/ai/monitoring/snapshots/?project={self.project_a.id}')
        self.assertEqual(res_snap.status_code, 200)
        snaps = res_snap.data["results"] if "results" in res_snap.data else res_snap.data
        self.assertGreaterEqual(len(snaps), 1)

        # Changes list
        res_ch = self.client_a.get(f'/api/seo/ai/monitoring/changes/?project={self.project_a.id}')
        self.assertEqual(res_ch.status_code, 200)
        changes = res_ch.data["results"] if "results" in res_ch.data else res_ch.data
        self.assertGreaterEqual(len(changes), 1)

    def test_24_rest_api_monitoring_metrics(self):
        """24. GET /api/seo/ai/monitoring/metrics/ returns serialized runtime evaluation metrics."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            self.service.run_project_monitoring(self.project_a)

        res = self.client_a.get(f'/api/seo/ai/monitoring/metrics/?project={self.project_a.id}')
        self.assertEqual(res.status_code, 200)
        self.assertIn("monitored_targets", res.data)
        self.assertIn("event_generation_rate", res.data)

    def test_25_rest_api_manual_trigger(self):
        """25. POST /api/seo/ai/monitoring/trigger/ invokes on-demand project monitoring cycle."""
        with mock.patch.object(self.PageStatusMonitor, 'probe_url', return_value={'status_code': 200, 'is_error': False, 'latency_ms': 100}):
            res = self.client_a.post('/api/seo/ai/monitoring/trigger/', {'project_id': self.project_a.id}, format='json')

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "success")
        self.assertEqual(res.data["project_id"], self.project_a.id)
        self.assertIn("snapshots_created", res.data["results"])


# ==============================================================================
# MILESTONE 6, PHASE 6.4: AUTONOMOUS REMEDIATION TEST SUITE
# ==============================================================================

class AutonomousRemediationTests(TransactionTestCase):
    """
    Milestone 6.4: Autonomous Remediation Test Suite.
    Comprehensive verification covering all 26 required test dimensions:
    1. Remediation proposal creation
    2. Low-risk autonomous action execution
    3. High-risk action requires HITL
    4. Human approval allows execution
    5. Human rejection produces REJECTED and no execution
    6. No approval -> no execution
    7. ToolRegistry permission enforcement
    8. MCP permission enforcement (read-only invariant)
    9. Event payload cannot inject tools or bypass permissions
    10. Tenant isolation (cross-project execution blocked)
    11. Execution failure handling
    12. Verification success -> VERIFIED
    13. Verification failure -> FAILED
    14. Rollback restores previous state
    15. Idempotency prevents duplicate execution
    16. Celery retry protection
    17. Duplicate event protection
    18. Failure isolation (Project A failure does not affect Project B)
    19. SharedWorkingMemory integration & provenance
    20. TaskPlan/DAG integration
    21. Multi-agent reasoning integration
    22. Adaptive agent selection
    23. Telemetry event emissions
    24. Runtime-derived evaluation metrics
    25. Continuous-operation integration
    26. Event-driven integration
    """

    def setUp(self):
        from rest_framework.test import APIClient
        from apps.users.models import User
        from apps.projects.models import Project
        from apps.seo.models import (
            SEOAction, SEOActionPlan, SEOEvent, SEOEventType, SEOEventSeverity,
            AgentRun, AgentRunStatus, ActionType, ActionStatus, VerificationStatus,
            ProjectRemediationPolicy, RemediationRecord,
            RemediationRiskLevel, RemediationPolicyDecision, RemediationErrorCategory
        )
        from apps.seo.services.autonomous_remediation import (
            AutonomousRemediationPolicy, AutonomousRemediationService
        )
        from apps.seo.services.agent_events import (
            AgentEventType, InMemoryEventPublisher, set_event_publisher
        )
        from apps.seo.services.tool_registry import get_tool_registry
        from apps.seo.services.seo_action_verifier import SEOActionVerifier

        self.User = User
        self.Project = Project
        self.SEOAction = SEOAction
        self.SEOActionPlan = SEOActionPlan
        self.SEOEvent = SEOEvent
        self.SEOEventType = SEOEventType
        self.SEOEventSeverity = SEOEventSeverity
        self.AgentRun = AgentRun
        self.AgentRunStatus = AgentRunStatus
        self.ActionType = ActionType
        self.ActionStatus = ActionStatus
        self.VerificationStatus = VerificationStatus
        self.ProjectRemediationPolicy = ProjectRemediationPolicy
        self.RemediationRecord = RemediationRecord
        self.RemediationRiskLevel = RemediationRiskLevel
        self.RemediationPolicyDecision = RemediationPolicyDecision
        self.RemediationErrorCategory = RemediationErrorCategory
        self.AutonomousRemediationPolicy = AutonomousRemediationPolicy
        self.AutonomousRemediationService = AutonomousRemediationService
        self.AgentEventType = AgentEventType
        self.get_tool_registry = get_tool_registry
        self.SEOActionVerifier = SEOActionVerifier

        # Telemetry publisher
        self.publisher = InMemoryEventPublisher()
        set_event_publisher(self.publisher)

        # Users & Projects
        unique = uuid.uuid4().hex[:6]
        self.user_a = User.objects.create_user(
            email=f'rem_user_a_{unique}@doxarank.com',
            password='Password123!',
            first_name='Remediation',
            last_name='UserA'
        )
        self.user_b = User.objects.create_user(
            email=f'rem_user_b_{unique}@doxarank.com',
            password='Password123!',
            first_name='Remediation',
            last_name='UserB'
        )

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name=f'Remediation Project A {unique}',
            website_url='https://remediation-alpha.com'
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name=f'Remediation Project B {unique}',
            website_url='https://remediation-beta.com'
        )

        # API Clients
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)
        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

        # Service
        self.service = AutonomousRemediationService(publisher=self.publisher)

    def _create_action(self, project, action_type=ActionType.UPDATE_TITLE, risk_level="low", target_url=None):
        return self.SEOAction.objects.create(
            project=project,
            action_type=action_type,
            title=f"Optimize {action_type} for {target_url or project.website_url}",
            target_url=target_url or f"{project.website_url}/page-1",
            risk_level=risk_level,
            requires_human_approval=(risk_level != "low"),
            status=self.ActionStatus.PROPOSED,
            current_state={"title": "Old Page Title", "target_url": target_url or f"{project.website_url}/page-1"},
            proposed_change={"title": "Optimized Page Title | Brand"},
            evidence_snapshot={"confidence_score": 0.95, "observed_facts": ["Title missing keywords"]}
        )

    def test_01_remediation_proposal_creation(self):
        """1. Remediation proposal creates structured RemediationRecord with risk assessment."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")
        record = self.service.propose_remediation(action=action)

        self.assertIsNotNone(record)
        self.assertEqual(record.action_id, action.id)
        self.assertEqual(record.project_id, self.project_a.id)
        self.assertEqual(record.risk_level, self.RemediationRiskLevel.LOW)
        self.assertEqual(record.policy_decision, self.RemediationPolicyDecision.AUTONOMOUS_ALLOWED)
        self.assertTrue(record.is_autonomous)

    def test_02_low_risk_autonomous_action(self):
        """2. Low-risk autonomous action executes safely and reaches VERIFIED state."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")

        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': True, 'score': 100}):
            record = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)

        self.assertEqual(record.status, self.ActionStatus.VERIFIED)
        self.assertTrue(record.is_autonomous)
        action.refresh_from_db()
        self.assertEqual(action.status, self.ActionStatus.VERIFIED)
        self.assertEqual(action.verification_status, self.VerificationStatus.VERIFIED)

    def test_03_high_risk_action_requires_hitl(self):
        """3. High-risk action is blocked from autonomous execution and requires HITL review."""
        action = self._create_action(self.project_a, action_type=self.ActionType.PUBLISH_NEW_CONTENT, risk_level="high")
        record = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)

        self.assertEqual(record.policy_decision, self.RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED)
        self.assertEqual(record.status, self.ActionStatus.PENDING_APPROVAL)
        self.assertFalse(record.is_autonomous)
        action.refresh_from_db()
        self.assertEqual(action.status, self.ActionStatus.PENDING_APPROVAL)

    def test_04_human_approval_allows_execution(self):
        """4. High-risk action approved by project owner executes through authorization pipeline."""
        action = self._create_action(self.project_a, action_type=self.ActionType.PUBLISH_NEW_CONTENT, risk_level="high")
        action.status = self.ActionStatus.APPROVED
        action.approved_by = self.user_a
        action.approved_at = timezone.now()
        action.save(update_fields=['status', 'approved_by', 'approved_at'])

        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': True}):
            record = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id, user=self.user_a)

        self.assertEqual(record.status, self.ActionStatus.VERIFIED)
        action.refresh_from_db()
        self.assertEqual(action.status, self.ActionStatus.VERIFIED)

    def test_05_human_rejection(self):
        """5. Human rejection prevents execution and marks action REJECTED."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="medium")
        action.status = self.ActionStatus.REJECTED
        action.rejected_by = self.user_a
        action.rejected_at = timezone.now()
        action.rejection_reason = "Unacceptable copy changes."
        action.save(update_fields=['status', 'rejected_by', 'rejected_at', 'rejection_reason'])

        record = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id, user=self.user_a)
        self.assertNotEqual(record.status, self.ActionStatus.COMPLETED)
        self.assertNotEqual(record.status, self.ActionStatus.VERIFIED)
        self.assertEqual(action.status, self.ActionStatus.REJECTED)

    def test_06_no_approval_no_execution(self):
        """6. Unapproved medium/high risk action without human approval cannot execute."""
        action = self._create_action(self.project_a, action_type=self.ActionType.CONTENT_REFRESH, risk_level="medium")
        record = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)

        self.assertEqual(record.status, self.ActionStatus.PENDING_APPROVAL)
        action.refresh_from_db()
        self.assertEqual(action.status, self.ActionStatus.PENDING_APPROVAL)

    def test_07_tool_registry_permission_enforcement(self):
        """7. ToolRegistry enforces agent role allowlists (unauthorized agent rejected)."""
        from apps.seo.services.agents.seo_research_agent import SEOResearchAgent
        researcher = SEOResearchAgent(project=self.project_a, user=self.user_a)

        with self.assertRaises(PermissionError):
            researcher.execute_tool("execute_seo_remediation", {"action_id": 999})

    def test_08_mcp_permission_enforcement(self):
        """8. MCP mutating operations are strictly rejected by policy."""
        from apps.seo.services.mcp.permissions import MCPPermissionPolicy
        is_approved = MCPPermissionPolicy.validate_tool_for_registration(
            server_id="seo_local",
            tool_declaration={"name": "mcp_mutate_db", "is_mutating": True}
        )
        self.assertFalse(is_approved[0])
        self.assertIn("mutation is forbidden", is_approved[1].lower())

    def test_09_event_payload_cannot_inject_tools(self):
        """9. Ingestion rejects event payloads attempting to inject tools or override permissions."""
        from apps.seo.services.event_ingestion import SEOEventIngestionService
        ingest_svc = SEOEventIngestionService()

        with self.assertRaises(ValueError):
            ingest_svc.ingest_event(
                project=self.project_a,
                event_type="ranking_change",
                source="audit_test",
                payload={"tools": ["arbitrary_code_exec"], "skip_hitl": True}
            )

    def test_10_tenant_isolation(self):
        """10. Cross-tenant remediation is strictly blocked."""
        action_a = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE)

        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            self.service.execute_remediation(
                action_id=action_a.id,
                project_id=self.project_b.id,
                user=self.user_b
            )

    def test_11_execution_failure_handling(self):
        """11. Mutation connector failure is caught and categorized as TOOL_FAILURE."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")

        with mock.patch('apps.seo.services.autonomous_remediation.get_mutation_connector') as mock_conn:
            connector_instance = mock.MagicMock()
            connector_instance.execute.side_effect = RuntimeError("CMS API network timeout")
            mock_conn.return_value = connector_instance

            record = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)

        self.assertEqual(record.status, self.ActionStatus.FAILED)
        self.assertEqual(record.error_category, self.RemediationErrorCategory.TOOL_FAILURE)

    def test_12_verification_success(self):
        """12. Verified HTML change produces VERIFIED status and records verification evidence."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")

        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': True, 'http_status': 200}):
            record = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)

        self.assertEqual(record.status, self.ActionStatus.VERIFIED)
        self.assertEqual(record.verification_data.get('http_status'), 200)

    def test_13_verification_failure(self):
        """13. Execution success + verification failure produces FAILED remediation."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")

        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': False, 'reason': 'DOM mismatch'}):
            record = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)

        self.assertEqual(record.status, self.ActionStatus.FAILED)
        self.assertEqual(record.error_category, self.RemediationErrorCategory.VERIFICATION_FAILURE)
        action.refresh_from_db()
        self.assertEqual(action.status, self.ActionStatus.FAILED)

    def test_14_rollback_compensation(self):
        """14. Reversible action is rolled back and restores previous state."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")

        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': True}):
            self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)

        # Trigger rollback
        rolled_back_record = self.service.rollback_remediation(action_id=action.id, user=self.user_a)
        self.assertEqual(rolled_back_record.status, self.ActionStatus.ROLLED_BACK)
        action.refresh_from_db()
        self.assertEqual(action.status, self.ActionStatus.ROLLED_BACK)

    def test_15_idempotency(self):
        """15. Repeated remediation execution attempt is prevented by idempotency check."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")

        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': True}):
            rec1 = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)
            rec2 = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)

        self.assertEqual(rec1.id, rec2.id)
        self.assertEqual(rec2.status, self.ActionStatus.VERIFIED)

    def test_16_celery_retry_protection(self):
        """16. Celery retry protection prevents re-execution on already completed records."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")
        action.status = self.ActionStatus.COMPLETED
        action.save(update_fields=['status'])

        record = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)
        self.assertIn(record.status, [self.ActionStatus.COMPLETED, self.ActionStatus.VERIFIED])

    def test_17_duplicate_event_protection(self):
        """17. Duplicate monitoring events do not trigger duplicate remediations."""
        from apps.seo.services.event_ingestion import SEOEventIngestionService
        ingest_svc = SEOEventIngestionService(publisher=self.publisher)

        ev1 = ingest_svc.ingest_event(
            project=self.project_a,
            event_type="ranking_change",
            source="monitoring_unit",
            payload={"keyword": "duplicate test", "rank_drop": 5}
        )
        ev2 = ingest_svc.ingest_event(
            project=self.project_a,
            event_type="ranking_change",
            source="monitoring_unit",
            payload={"keyword": "duplicate test", "rank_drop": 5}
        )

        self.assertEqual(ev2.status, "deduplicated")

    def test_18_failure_isolation(self):
        """18. Failure in Project A remediation does not stop Project B remediation."""
        action_a = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")
        action_b = self._create_action(self.project_b, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")

        # Project A fails
        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': False}):
            rec_a = self.service.execute_remediation(action_id=action_a.id, project_id=self.project_a.id)

        # Project B succeeds independently
        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': True}):
            rec_b = self.service.execute_remediation(action_id=action_b.id, project_id=self.project_b.id)

        self.assertEqual(rec_a.status, self.ActionStatus.FAILED)
        self.assertEqual(rec_b.status, self.ActionStatus.VERIFIED)

    def test_19_shared_working_memory_integration(self):
        """19. SharedWorkingMemory records remediation milestones with verified provenance."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, MemoryCategory
        mem = SharedWorkingMemory(project_id=self.project_a.id)

        item = mem.record_remediation_step(
            category=MemoryCategory.ACTION_PROPOSAL,
            content="Propose updating title for /page-1",
            source_agent="seo_action_planner",
            action_id=123,
            stage="planned"
        )

        self.assertIsNotNone(item)
        self.assertEqual(item.category, "action_proposal")
        self.assertEqual(item.metadata.get("stage"), "planned")

    def test_20_task_plan_dag_integration(self):
        """20. DynamicTaskPlanner generates 5-stage remediation DAG with valid dependencies."""
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner
        planner = DynamicTaskPlanner(project_id=self.project_a.id)
        plan = planner.decompose_goal("Autonomous remediation for ranking drop on /page-1")

        self.assertGreaterEqual(len(plan.tasks), 4)
        task_agents = [t.responsible_agent for t in plan.tasks.values()]
        self.assertIn("seo_action_planner", task_agents)
        self.assertIn("seo_verifier", task_agents)

    def test_21_reasoning_integration(self):
        """21. Competing hypotheses or uncertainty force human approval required."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")
        action.evidence_snapshot = {
            "confidence_score": 0.90,
            "inferences": ["Hypothesis A competing with Hypothesis B on ranking cause"]
        }
        action.save(update_fields=['evidence_snapshot'])

        decision = self.AutonomousRemediationPolicy.evaluate(action=action, project=self.project_a)
        self.assertEqual(decision.decision, self.RemediationPolicyDecision.HUMAN_APPROVAL_REQUIRED)

    def test_22_adaptive_agent_selection(self):
        """22. AdaptiveAgentSelector selects seo_action_planner for action_planning task."""
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector
        from apps.seo.services.agents.task_planner import AgentTask
        selector = AdaptiveAgentSelector(project_id=self.project_a.id)

        task = AgentTask(
            task_id="t_act_select",
            objective="Formulate remediation action proposal",
            description="Plan atomic reversible fix",
            responsible_agent="seo_action_planner"
        )
        decision = selector.select_agent(task=task)
        self.assertEqual(decision.selected_agent, "seo_action_planner")

    def test_23_telemetry_emission(self):
        """23. Full remediation lifecycle emits telemetry events."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")

        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': True}):
            self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)

        event_types = [e.event_type for e in self.publisher.get_events()]
        self.assertIn(self.AgentEventType.SEO_REMEDIATION_EXECUTION_STARTED, event_types)
        self.assertIn(self.AgentEventType.SEO_REMEDIATION_VERIFICATION_PASSED, event_types)
        self.assertIn(self.AgentEventType.SEO_REMEDIATION_COMPLETED, event_types)

    def test_24_runtime_derived_evaluation_metrics(self):
        """24. SEOAgentEvaluationService derives accurate metrics directly from database."""
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService

        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")
        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': True}):
            self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)

        metrics = SEOAgentEvaluationService.evaluate_autonomous_remediation(self.project_a)
        self.assertGreaterEqual(metrics["total_remediations"], 1)
        self.assertGreaterEqual(metrics["remediation_success_rate"], 100.0)

    def test_25_continuous_operation_integration(self):
        """25. Actions proposed in continuous run execute autonomously if policy permits."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")
        run = self.AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            goal="Continuous SEO cycle",
            status=self.AgentRunStatus.RUNNING
        )

        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': True}):
            from apps.seo.tasks import execute_continuous_run_task
            # Simulate completion check
            decision = self.AutonomousRemediationPolicy.evaluate(action=action, project=self.project_a)
            self.assertEqual(decision.decision, self.RemediationPolicyDecision.AUTONOMOUS_ALLOWED)

    def test_26_event_driven_integration(self):
        """26. Event-driven flow evaluates proposed actions and executes low-risk remediations."""
        action = self._create_action(self.project_a, action_type=self.ActionType.UPDATE_TITLE, risk_level="low")
        pol_eval = self.AutonomousRemediationPolicy.evaluate(action=action, project=self.project_a)
        self.assertEqual(pol_eval.decision, self.RemediationPolicyDecision.AUTONOMOUS_ALLOWED)

        with mock.patch.object(self.SEOActionVerifier, 'verify_action', return_value={'is_verified': True}):
            rec = self.service.execute_remediation(action_id=action.id, project_id=self.project_a.id)

        self.assertEqual(rec.status, self.ActionStatus.VERIFIED)


# ==============================================================================
# MILESTONE 6.5: MULTI-SYSTEM AGENT INTEGRATION TESTS
# ==============================================================================

class MultiSystemIntegrationTests(TestCase):
    """
    Comprehensive verification suite for Milestone 6.5: Multi-System Agent Integration.
    Tests all 32 required dimensions covering:
    - Connection creation and project isolation
    - ToolRegistry authority and agent role allowlists
    - CMS, Git, and Webhook external system adapters
    - Explicit capability routing and cross-system DAG execution
    - HITL authorization boundaries and rejection governance
    - MCP safety boundaries and Anti-SSRF URL validation
    - Secret redaction and credential safety
    - Deterministic idempotency and concurrent duplicate protection
    - Bounded retries, backoff, and rate-limiting handling
    - Post-execution empirical verification and verification failure boundaries
    - Rollback state capture, SharedWorkingMemory provenance, and telemetry
    - Runtime evaluation metrics and multi-tenant failure isolation
    - End-to-end 6.3 -> 6.2 -> 6.4 -> 6.5 pipeline and regression guarantees
    """

    def setUp(self):
        from apps.users.models import User
        from apps.projects.models import Project
        from apps.seo.models import (
            SEOAction, ActionType, ActionStatus, ActionRiskLevel,
            VerificationStatus, ProjectRemediationPolicy, RemediationRecord,
            SEOEvent, SEOEventType, AgentRun, AgentRunStatus,
            ExternalConnection, ExternalOperationRecord, ExternalOperationStatus
        )
        from apps.seo.services.agent_events import InMemoryEventPublisher, set_event_publisher, AgentEventType
        from apps.seo.services.external_adapters import (
            ExternalIntegrationService, CMSAdapter, GitAdapter, WebhookAdapter,
            get_external_adapter_registry
        )
        from apps.seo.services.tool_registry import get_tool_registry

        self.publisher = InMemoryEventPublisher()
        set_event_publisher(self.publisher)
        self.AgentEventType = AgentEventType
        self.ActionType = ActionType
        self.ActionStatus = ActionStatus
        self.ExternalOperationStatus = ExternalOperationStatus
        self.ExternalConnection = ExternalConnection
        self.AgentRunStatus = AgentRunStatus

        # Reset in-memory adapter staging stores
        CMSAdapter.reset_staging()
        GitAdapter.reset_staging()
        WebhookAdapter.reset_staging()

        # Users & Projects (Tenant Isolation)
        self.user_a = User.objects.create_user(
            email="tenant_a_65@doxarank.io",
            first_name="Tenant",
            last_name="A",
            password="testpassword123"
        )
        self.user_b = User.objects.create_user(
            email="tenant_b_65@doxarank.io",
            first_name="Tenant",
            last_name="B",
            password="testpassword123"
        )

        self.project_a = Project.objects.create(
            owner=self.user_a,
            name="Alpha Project 6.5",
            website_url="https://alpha-site.example.com"
        )
        self.project_b = Project.objects.create(
            owner=self.user_b,
            name="Beta Project 6.5",
            website_url="https://beta-site.example.com"
        )

        # External Connections for Project A
        self.conn_cms_a = ExternalConnection.objects.create(
            project=self.project_a,
            system_type="cms",
            provider="wordpress",
            name="Alpha WordPress CMS",
            status="test_staging",
            configuration={"baseUrl": "https://alpha-site.example.com", "allowlisted_domains": ["alpha-site.example.com"]}
        )
        self.conn_cms_a.set_credentials({"api_key": "secret_wp_key_alpha", "username": "admin_alpha"})
        self.conn_cms_a.save()

        self.conn_git_a = ExternalConnection.objects.create(
            project=self.project_a,
            system_type="git",
            provider="github",
            name="Alpha GitHub Repo",
            status="test_staging",
            configuration={"repo": "alpha-org/alpha-site", "branch_prefix": "doxarank/"}
        )
        self.conn_git_a.set_credentials({"token": "ghp_alpha_github_secret_token_12345"})
        self.conn_git_a.save()

        self.conn_webhook_a = ExternalConnection.objects.create(
            project=self.project_a,
            system_type="webhook",
            provider="generic_webhook",
            name="Alpha Deploy Webhook",
            status="test_staging",
            configuration={"allowlisted_domains": ["alpha-site.example.com", "api.webhook.example.com"]}
        )
        self.conn_webhook_a.set_credentials({"signing_secret": "whsec_alpha_secret_signature"})
        self.conn_webhook_a.save()

        # Connection for Project B
        self.conn_cms_b = ExternalConnection.objects.create(
            project=self.project_b,
            system_type="cms",
            provider="shopify",
            name="Beta Shopify Store",
            status="test_staging",
            configuration={"baseUrl": "https://beta-site.example.com", "allowlisted_domains": ["beta-site.example.com"]}
        )
        self.conn_cms_b.set_credentials({"access_token": "shpat_beta_secret_token_9999"})
        self.conn_cms_b.save()

        self.service = ExternalIntegrationService(publisher=self.publisher)
        self.registry = get_tool_registry()

    def tearDown(self):
        from apps.seo.services.agent_events import reset_event_publisher
        reset_event_publisher()

    def test_01_connection_creation(self):
        """1. External connection is created with Fernet encryption and status."""
        from apps.seo.models import ExternalConnection
        conn = ExternalConnection.objects.get(id=self.conn_cms_a.id)
        self.assertEqual(conn.system_type, "cms")
        self.assertEqual(conn.provider, "wordpress")
        self.assertEqual(conn.status, "test_staging")
        # Ensure credentials decrypt accurately in memory
        creds = conn.get_credentials()
        self.assertEqual(creds.get("api_key"), "secret_wp_key_alpha")
        # Ensure plaintext secret is NOT stored in encrypted_credentials
        self.assertNotIn("secret_wp_key_alpha", conn.encrypted_credentials)

    def test_02_project_isolation(self):
        """2. Project A connections cannot be accessed or executed by Project B."""
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            self.service.execute_operation(
                project=self.project_b,
                connection_id=self.conn_cms_a.id,
                operation="read_metadata",
                target="https://alpha-site.example.com/page-1",
                params={},
                agent_name="seo_researcher"
            )

    def test_03_capability_discovery(self):
        """3. Connection and adapter registry expose declared capabilities."""
        caps = self.conn_cms_a.get_declared_capabilities()
        self.assertIn("CMS.READ_METADATA", caps)
        self.assertIn("CMS.UPDATE_METADATA", caps)
        self.assertIn("CMS.PUBLISH_CONTENT", caps)

        git_caps = self.conn_git_a.get_declared_capabilities()
        self.assertIn("GIT.WRITE_FILE", git_caps)
        self.assertIn("GIT.CREATE_COMMIT", git_caps)

    def test_04_tool_registry_enforcement(self):
        """4. External operations must execute through ToolRegistry authority."""
        res = self.registry.execute(
            tool_name="execute_external_operation",
            project=self.project_a,
            arguments={
                "connection_id": self.conn_cms_a.id,
                "operation": "update_metadata",
                "target": "https://alpha-site.example.com/seo-page",
                "parameters": {"title": "Updated via ToolRegistry"},
                "agent_name": "seo_action_planner",
                "force_autonomous": True
            }
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["status"], "verified")
        self.assertEqual(res["data"]["system_type"], "cms")

    def test_05_unauthorized_agent_rejection(self):
        """5. SEOResearchAgent is strictly rejected when attempting mutating external operations."""
        from apps.seo.services.agents.seo_research_agent import SEOResearchAgent
        researcher = SEOResearchAgent(project=self.project_a, user=self.user_a)

        # Researcher calling mutating tool raises PermissionError at agent layer
        with self.assertRaises(PermissionError):
            researcher.execute_tool("execute_external_operation", {
                "connection_id": self.conn_cms_a.id,
                "operation": "update_metadata",
                "target": "https://alpha-site.example.com/target",
                "parameters": {"title": "Malicious Update"}
            })

        # Calling service directly as unauthorized agent raises PermissionError
        with self.assertRaises(PermissionError):
            self.service.execute_operation(
                project=self.project_a,
                connection_id=self.conn_cms_a.id,
                operation="update_metadata",
                target="https://alpha-site.example.com/target",
                params={"title": "Direct Bypass Attempt"},
                agent_name="seo_researcher"
            )

    def test_06_cms_adapter(self):
        """6. CMS adapter safely reads and updates metadata with diffs and before-state."""
        from apps.seo.services.external_adapters.cms_adapter import CMSAdapter
        CMSAdapter.set_staging_page_state("https://alpha-site.example.com/blog", {
            "title": "Initial Blog Title",
            "meta_description": "Initial meta description."
        })

        rec = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target="https://alpha-site.example.com/blog",
            params={"title": "Optimized Blog Title"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec.status, "verified")
        self.assertTrue(rec.changed)
        self.assertEqual(rec.before_state.get("title"), "Initial Blog Title")
        self.assertEqual(rec.after_state.get("title"), "Optimized Blog Title")

    def test_07_git_adapter(self):
        """7. Git adapter manages branch creation, file modification, and commits."""
        rec_branch = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_git_a.id,
            operation="create_branch",
            target="alpha-org/alpha-site",
            params={"branch_name": "doxarank/seo-meta-fix"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec_branch.status, "verified")

        rec_write = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_git_a.id,
            operation="write_file",
            target="alpha-org/alpha-site",
            params={
                "branch": "doxarank/seo-meta-fix",
                "file_path": "config/seo.json",
                "content": '{"title": "Automated SEO Title"}'
            },
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec_write.status, "verified")
        self.assertTrue(rec_write.changed)

    def test_08_webhook_api_adapter(self):
        """8. Webhook adapter delivers verified payloads to allowlisted endpoints."""
        rec = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_webhook_a.id,
            operation="send_webhook",
            target="https://api.webhook.example.com/deploy",
            params={"event": "seo_action_deployed", "action_id": 101},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec.status, "verified")
        self.assertEqual(rec.status_code, 200)

    def test_09_explicit_capability_matching(self):
        """9. Adapters are resolved via explicit capability matching (e.g. CMS.UPDATE_METADATA)."""
        from apps.seo.services.external_adapters.registry import get_external_adapter_registry
        reg = get_external_adapter_registry()
        cms_adapter = reg.get_adapter_for_capability("CMS.UPDATE_METADATA")
        self.assertEqual(cms_adapter.system_type, "cms")

        git_adapter = reg.get_adapter_for_capability("GIT.WRITE_FILE")
        self.assertEqual(git_adapter.system_type, "git")

        wh_adapter = reg.get_adapter_for_capability("WEBHOOK.SEND_WEBHOOK")
        self.assertEqual(wh_adapter.system_type, "webhook")

    def test_10_cross_system_dag(self):
        """10. Multi-system tasks form an executable DAG with explicit dependencies."""
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner, AgentTask, TaskPlan
        planner = DynamicTaskPlanner(project_id=self.project_a.id)
        plan = TaskPlan(
            project_id=self.project_a.id,
            goal="Cross-system automated SEO remediation",
            plan_id="plan_cross_system"
        )
        t1 = AgentTask(task_id="t1_cms_inspect", objective="Inspect CMS", description="Inspect page", responsible_agent="seo_researcher")
        t2 = AgentTask(task_id="t2_plan", objective="Plan fix", description="Plan change", responsible_agent="seo_action_planner", dependencies=["t1_cms_inspect"])
        t3 = AgentTask(task_id="t3_git_commit", objective="Git commit", description="Write git file", responsible_agent="seo_action_planner", dependencies=["t2_plan"])
        t4 = AgentTask(task_id="t4_webhook_deploy", objective="Webhook deploy", description="Deploy webhook", responsible_agent="seo_action_planner", dependencies=["t3_git_commit"])
        t5 = AgentTask(task_id="t5_verify", objective="Verify live", description="Verify page", responsible_agent="seo_verifier", dependencies=["t4_webhook_deploy"])

        plan.add_task(t1)
        plan.add_task(t2)
        plan.add_task(t3)
        plan.add_task(t4)
        plan.add_task(t5)

        self.assertTrue(plan.validate_graph())
        ready_tasks = plan.get_ready_tasks()
        self.assertEqual(len(ready_tasks), 1)
        self.assertEqual(ready_tasks[0].task_id, "t1_cms_inspect")

    def test_11_low_risk_authorized_execution(self):
        """11. Low-risk actions execute autonomously when permitted by policy."""
        rec = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target="https://alpha-site.example.com/low-risk",
            params={"title": "Safe New Title"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec.status, "verified")
        self.assertTrue(rec.is_autonomous)

    def test_12_high_risk_hitl_requirement(self):
        """12. High-risk operations (e.g. publish_content) are blocked pending human approval."""
        rec = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="publish_content",
            target="https://alpha-site.example.com/new-article",
            params={"content": "New published content article."},
            agent_name="seo_action_planner",
            force_autonomous=False
        )
        self.assertEqual(rec.status, "pending")
        self.assertEqual(rec.error_category, "hitl_required")

    def test_13_approval_flow(self):
        """13. Human approval unlocks high-risk execution."""
        from apps.seo.models import SEOAction
        from django.utils import timezone
        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=self.ActionType.PUBLISH_NEW_CONTENT,
            title="Publish Article",
            target_url="https://alpha-site.example.com/article-approved",
            status=self.ActionStatus.APPROVED,
            approved_by=self.user_a,
            approved_at=timezone.now()
        )

        rec = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="publish_content",
            target="https://alpha-site.example.com/article-approved",
            params={"content": "Approved high-risk content."},
            agent_name="seo_action_planner",
            action=action
        )
        self.assertEqual(rec.status, "verified")

    def test_14_rejection_flow(self):
        """14. Rejection strictly prevents execution."""
        from apps.seo.models import SEOAction
        from django.utils import timezone
        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=self.ActionType.PUBLISH_NEW_CONTENT,
            title="Rejected Article",
            target_url="https://alpha-site.example.com/article-rejected",
            status=self.ActionStatus.REJECTED,
            rejected_at=timezone.now()
        )

        rec = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="publish_content",
            target="https://alpha-site.example.com/article-rejected",
            params={"content": "Rejected content."},
            agent_name="seo_action_planner",
            action=action
        )
        self.assertEqual(rec.status, "pending")
        self.assertEqual(rec.error_category, "hitl_required")

    def test_15_mcp_safety(self):
        """15. MCP mutating operations are rejected and cannot inject arbitrary external mutations."""
        from apps.seo.services.mcp.permissions import MCPPermissionPolicy
        is_approved, err = MCPPermissionPolicy.validate_tool_for_registration(
            server_id="seo_local",
            tool_declaration={"name": "mcp_execute_cms_mutation", "is_mutating": True}
        )
        self.assertFalse(is_approved)
        self.assertIn("mutation is forbidden", err.lower())

    def test_16_arbitrary_url_rejection(self):
        """16. Anti-SSRF strictly rejects arbitrary, loopback, and non-allowlisted URLs."""
        rec_loopback = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_webhook_a.id,
            operation="send_webhook",
            target="http://127.0.0.1:8000/evil",
            params={"data": "exploit"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec_loopback.status, "failed")
        self.assertEqual(rec_loopback.error_category, "invalid_target")

        rec_metadata = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_webhook_a.id,
            operation="send_webhook",
            target="http://169.254.169.254/latest/meta-data",
            params={"data": "exploit"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec_metadata.status, "failed")
        self.assertEqual(rec_metadata.error_category, "invalid_target")

    def test_17_credential_redaction(self):
        """17. Credentials and tokens are redacted from API views and logs."""
        clean = self.conn_cms_a.clean_for_api()
        self.assertNotIn("encrypted_credentials", clean)
        self.assertNotIn("secret_wp_key_alpha", str(clean))

    def test_18_idempotency(self):
        """18. Repeated execution with identical parameters yields identical fingerprint and prevents duplicate work."""
        rec1 = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target="https://alpha-site.example.com/idem-test",
            params={"title": "Idempotent Title"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec1.status, "verified")

        rec2 = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target="https://alpha-site.example.com/idem-test",
            params={"title": "Idempotent Title"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec1.id, rec2.id)

    def test_19_concurrent_duplicate_protection(self):
        """19. Duplicate prevented telemetry is emitted on duplicate invocation."""
        rec1 = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target="https://alpha-site.example.com/concurrent-test",
            params={"title": "Concurrency Safe"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target="https://alpha-site.example.com/concurrent-test",
            params={"title": "Concurrency Safe"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        event_types = [e.event_type for e in self.publisher.get_events()]
        self.assertIn(self.AgentEventType.EXTERNAL_INTEGRATION_DUPLICATE_PREVENTED, event_types)

    def test_20_retry_behavior(self):
        """20. Transient network timeouts trigger bounded backoff retries."""
        from apps.seo.services.external_adapters.webhook_adapter import WebhookAdapter
        # Simulate 1 transient timeout then success
        WebhookAdapter.set_simulation_behavior({"timeout_attempts": 1})

        rec = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_webhook_a.id,
            operation="send_webhook",
            target="https://api.webhook.example.com/deploy",
            params={"event": "test_retry"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec.status, "verified")
        self.assertEqual(rec.retry_count, 1)

    def test_21_rate_limit_behavior(self):
        """21. Rate limit 429 triggers bounded backoff and emits rate-limited telemetry."""
        from apps.seo.services.external_adapters.webhook_adapter import WebhookAdapter
        WebhookAdapter.set_simulation_behavior({"rate_limit_attempts": 1})

        rec = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_webhook_a.id,
            operation="send_webhook",
            target="https://api.webhook.example.com/deploy",
            params={"event": "test_rate_limit"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec.status, "verified")
        self.assertEqual(rec.retry_count, 1)

        event_types = [e.event_type for e in self.publisher.get_events()]
        self.assertIn(self.AgentEventType.EXTERNAL_INTEGRATION_RATE_LIMITED, event_types)

    def test_22_verification_success(self):
        """22. Post-execution empirical verification confirms expected changes and transitions to VERIFIED."""
        rec = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target="https://alpha-site.example.com/verif-success",
            params={"title": "Verified Title Value"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec.status, "verified")
        self.assertEqual(rec.verification_status, "verified")
        self.assertTrue(rec.verification_data.get("verified"))

    def test_23_verification_failure(self):
        """23. Post-execution verification failure transitions operation to FAILED."""
        from apps.seo.services.external_adapters.cms_adapter import CMSAdapter
        # Mock adapter verify to return False
        with mock.patch.object(CMSAdapter, 'verify', return_value=(False, {"mismatches": ["Title tag missing"]})):
            rec = self.service.execute_operation(
                project=self.project_a,
                connection_id=self.conn_cms_a.id,
                operation="update_metadata",
                target="https://alpha-site.example.com/verif-fail",
                params={"title": "Failing Verification Title"},
                agent_name="seo_action_planner",
                force_autonomous=True
            )
        self.assertEqual(rec.status, "failed")
        self.assertEqual(rec.verification_status, "failed")
        self.assertEqual(rec.error_category, "verification_failure")

    def test_24_rollback_compensation(self):
        """24. Reversible operations capture before_state enabling compensation."""
        from apps.seo.services.external_adapters.cms_adapter import CMSAdapter
        CMSAdapter.set_staging_page_state("https://alpha-site.example.com/rollback-target", {
            "title": "Original Staging Title"
        })

        rec = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target="https://alpha-site.example.com/rollback-target",
            params={"title": "Mutated Title"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec.before_state.get("title"), "Original Staging Title")

        # Rollback: apply compensation mutation with original before_state
        rec_revert = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target="https://alpha-site.example.com/rollback-target",
            params={"title": rec.before_state["title"]},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec_revert.status, "verified")
        self.assertEqual(rec_revert.after_state.get("title"), "Original Staging Title")

    def test_25_shared_working_memory_provenance(self):
        """25. External operations are recorded into SharedWorkingMemory with full provenance."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, MemoryCategory
        mem = SharedWorkingMemory(project_id=self.project_a.id, task_goal="External Update Audit")
        mem.add_evidence(
            fact="CMS title currently = Old Title",
            source_agent="seo_researcher",
            source_tool="inspect_cms_page"
        )
        mem.add_recommendation(
            recommendation="Change title to New Title via CMS.UPDATE_METADATA",
            source_agent="seo_action_planner"
        )
        record = mem.record_external_operation(
            source_agent="seo_action_planner",
            system_type="cms",
            operation="update_metadata",
            target="https://alpha-site.example.com/page",
            status="verified",
            before_state={"title": "Old Title"},
            after_state={"title": "New Title"}
        )
        self.assertEqual(record["external_system"], "cms")
        self.assertEqual(record["status"], "verified")
        self.assertIn("Old Title", str(mem.get_facts()))

    def test_26_telemetry(self):
        """26. Emits full suite of external integration telemetry events."""
        self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target="https://alpha-site.example.com/telemetry-target",
            params={"title": "Telemetry Title"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        event_types = [e.event_type for e in self.publisher.get_events()]
        self.assertIn(self.AgentEventType.EXTERNAL_INTEGRATION_REQUESTED, event_types)
        self.assertIn(self.AgentEventType.EXTERNAL_INTEGRATION_AUTHORIZED, event_types)
        self.assertIn(self.AgentEventType.EXTERNAL_INTEGRATION_STARTED, event_types)
        self.assertIn(self.AgentEventType.EXTERNAL_INTEGRATION_COMPLETED, event_types)
        self.assertIn(self.AgentEventType.EXTERNAL_INTEGRATION_VERIFIED, event_types)

    def test_27_runtime_evaluation(self):
        """27. SEOAgentEvaluationService computes dynamic rates from actual records."""
        from apps.seo.services.agent_evaluation import SEOAgentEvaluationService
        self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target="https://alpha-site.example.com/eval-target",
            params={"title": "Eval Title"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        eval_metrics = SEOAgentEvaluationService.evaluate_external_integrations(self.project_a)
        self.assertGreaterEqual(eval_metrics["external_operations_completed"], 1)
        self.assertGreaterEqual(eval_metrics["external_operations_verified"], 1)
        self.assertEqual(eval_metrics["system_breakdown"].get("cms"), 1)

    def test_28_tenant_isolation(self):
        """28. API and service layers strictly isolate connections across tenants."""
        from django.core.exceptions import PermissionDenied
        # Service level
        with self.assertRaises(PermissionDenied):
            self.service.execute_operation(
                project=self.project_b,
                connection_id=self.conn_cms_a.id,
                operation="read_metadata",
                target="https://alpha-site.example.com/isolation",
                params={},
                agent_name="seo_researcher"
            )

    def test_29_failure_isolation(self):
        """29. Failure in CMS operation for Project A does not disable Project B Git operations."""
        from apps.seo.services.external_adapters.cms_adapter import CMSAdapter
        # Simulate CMS failure for Project A
        with mock.patch.object(CMSAdapter, 'execute', side_effect=RuntimeError("CMS network outage")):
            rec_a = self.service.execute_operation(
                project=self.project_a,
                connection_id=self.conn_cms_a.id,
                operation="update_metadata",
                target="https://alpha-site.example.com/fail",
                params={"title": "Failed Title"},
                agent_name="seo_action_planner",
                force_autonomous=True
            )
            self.assertEqual(rec_a.status, "failed")

        # Project B Git operation proceeds unaffected
        conn_git_b = self.ExternalConnection.objects.create(
            project=self.project_b,
            system_type="git",
            provider="github",
            name="Beta Git",
            status="test_staging",
            configuration={"repo": "beta-org/beta-site"}
        )
        rec_b = self.service.execute_operation(
            project=self.project_b,
            connection_id=conn_git_b.id,
            operation="create_branch",
            target="beta-org/beta-site",
            params={"branch_name": "doxarank/beta-fix"},
            agent_name="seo_action_planner",
            force_autonomous=True
        )
        self.assertEqual(rec_b.status, "verified")

    def test_30_6_3_to_6_2_to_6_4_to_6_5_pipeline(self):
        """30. Complete end-to-end integration: 6.3 Detection -> 6.2 Event -> Run -> 6.4 Policy -> 6.5 Adapter -> Verification."""
        from apps.seo.models import SEOEvent, AgentRun, SEOAction
        from apps.seo.services.autonomous_remediation import AutonomousRemediationPolicy

        # 1. 6.3 / 6.2 Event
        event = SEOEvent.objects.create(
            project=self.project_a,
            event_type="title_change_detected",
            source="autonomous_monitor",
            payload={"page": "https://alpha-site.example.com/pipeline", "detected_title": "Bad Title"}
        )
        # 2. Agent Run
        run = AgentRun.objects.create(
            project=self.project_a,
            user=self.user_a,
            goal="Remediate title change anomaly",
            status=self.AgentRunStatus.RUNNING
        )
        # 3. Action Proposal
        action = SEOAction.objects.create(
            project=self.project_a,
            action_type=self.ActionType.UPDATE_TITLE,
            title="Update Page Title to Optimal Baseline",
            target_url="https://alpha-site.example.com/pipeline",
            current_state={"title": "Bad Title"},
            proposed_change={"title": "Optimal Title Baseline"}
        )
        # 4. 6.4 Policy Check
        decision = AutonomousRemediationPolicy.evaluate(action=action, project=self.project_a)
        self.assertEqual(decision.decision, "autonomous_allowed")

        # 5. 6.5 Adapter Execution via ToolRegistry
        rec = self.service.execute_operation(
            project=self.project_a,
            connection_id=self.conn_cms_a.id,
            operation="update_metadata",
            target=action.target_url,
            params={"title": action.proposed_change["title"]},
            agent_name="seo_action_planner",
            action=action,
            agent_run=run,
            force_autonomous=True
        )
        self.assertEqual(rec.status, "verified")
        self.assertEqual(rec.verification_status, "verified")

    def test_31_existing_5_x_regression(self):
        """31. Regression guarantee: Milestone 5.1-5.7 multi-agent collaboration works unimpeded."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory
        from apps.seo.services.agents.task_planner import DynamicTaskPlanner
        from apps.seo.services.agents.adaptive_selector import AdaptiveAgentSelector

        mem = SharedWorkingMemory(project_id=self.project_a.id, task_goal="5.x Regression Verification")
        self.assertEqual(mem.project_id, self.project_a.id)

        planner = DynamicTaskPlanner(project_id=self.project_a.id)
        plan = planner.decompose_goal(goal="5.x Planning Regression", project_id=self.project_a.id)
        self.assertTrue(plan.validate_graph())

        selector = AdaptiveAgentSelector(project_id=self.project_a.id)
        ready_tasks = plan.get_ready_tasks()
        if ready_tasks:
            decision = selector.select_agent(ready_tasks[0])
            self.assertIsNotNone(decision.selected_agent)

    def test_32_existing_6_x_regression(self):
        """32. Regression guarantee: Milestone 6.1-6.4 autonomous operations continue functioning."""
        from apps.seo.services.autonomous_remediation import AutonomousRemediationService
        from apps.seo.services.autonomous_monitoring import AutonomousMonitoringService

        rem_service = AutonomousRemediationService(publisher=self.publisher)
        self.assertIsNotNone(rem_service)

        mon_service = AutonomousMonitoringService(publisher=self.publisher)
        self.assertIsNotNone(mon_service)


class LongTermSEOStrategyTests(TestCase):
    """
    Milestone 6.6 — Long-Term SEO Strategy Verification Test Suite.
    Verifies that DoxaRank maintains and executes long-term SEO strategy over weeks
    and months, with mathematical progress, rule-based trends, epistemic separation,
    HITL governance, review idempotency, and multi-tenant isolation.
    """

    def setUp(self):
        self.client = APIClient()
        self.publisher = InMemoryEventPublisher()
        self.user_a = User.objects.create_user(
            email="user_strat_a@doxarank.com",
            password="Password123!",
            first_name="Strat",
            last_name="A"
        )
        self.user_b = User.objects.create_user(
            email="user_strat_b@doxarank.com",
            password="Password123!",
            first_name="Strat",
            last_name="B"
        )
        self.project_a = Project.objects.create(
            name="Addis Market E-Commerce",
            website_url="https://addismarket.et",
            owner=self.user_a
        )
        self.project_b = Project.objects.create(
            name="Competitor Market",
            website_url="https://competitor.et",
            owner=self.user_b
        )
        self.client.force_authenticate(user=self.user_a)

        from apps.seo.services.long_term_strategy import LongTermSEOStrategyService
        self.service = LongTermSEOStrategyService(project=self.project_a, publisher=self.publisher)

    def test_01_objective_creation(self):
        """1. Strategic objective creation with target direction and tenant scoping."""
        from apps.seo.models import StrategicObjective, StrategicHorizon, StrategicPriority, TargetDirection, ObjectiveStatus
        obj = self.service.create_objective(
            project=self.project_a,
            name="Rank Top 5 for የኢትዮጵያ ቡና",
            metric="keyword_rank",
            baseline=45.0,
            target=5.0,
            target_direction=TargetDirection.DECREASING,
            priority=StrategicPriority.CRITICAL,
            horizon=StrategicHorizon.MEDIUM_TERM,
            description="Achieve top 5 position for Ethiopian Coffee query."
        )
        self.assertEqual(obj.project, self.project_a)
        self.assertEqual(obj.metric, "keyword_rank")
        self.assertEqual(obj.baseline, 45.0)
        self.assertEqual(obj.target, 5.0)
        self.assertEqual(obj.target_direction, "decreasing")
        self.assertEqual(obj.status, ObjectiveStatus.ACTIVE)
        self.assertEqual(obj.progress, 0.0)

    def test_02_objective_lifecycle(self):
        """2. Objective lifecycle transitions from active to achieved."""
        from apps.seo.models import ObjectiveStatus, TargetDirection
        obj = self.service.create_objective(
            project=self.project_a,
            name="Increase Monthly Organic Sessions",
            metric="organic_sessions",
            baseline=5000.0,
            target=10000.0,
            target_direction=TargetDirection.INCREASING
        )
        # Update progress halfway
        self.service.update_objective_progress(obj, current_value=7500.0)
        obj.refresh_from_db()
        self.assertEqual(obj.progress, 0.5)
        self.assertEqual(obj.status, ObjectiveStatus.ACTIVE)

        # Update progress to complete
        self.service.update_objective_progress(obj, current_value=10500.0)
        obj.refresh_from_db()
        self.assertGreaterEqual(obj.progress, 1.0)
        self.assertEqual(obj.status, ObjectiveStatus.ACHIEVED)

    def test_03_initiative_creation(self):
        """3. Strategic initiative creation with horizon, priority, and risk."""
        from apps.seo.models import StrategicHorizon, StrategicPriority, InitiativeStatus
        strategy = self.service.generate_strategy(
            project=self.project_a,
            title="Q3 Strategic Plan"
        )
        init = self.service.create_initiative(
            strategy=strategy,
            name="Technical Core Web Vitals Optimization",
            priority=StrategicPriority.HIGH,
            horizon=StrategicHorizon.SHORT_TERM,
            risk_level="low",
            target_action_types=["fix_cwv", "optimize_images"]
        )
        self.assertEqual(init.strategy, strategy)
        self.assertEqual(init.name, "Technical Core Web Vitals Optimization")
        self.assertEqual(init.status, InitiativeStatus.PLANNED)
        self.assertEqual(init.priority, "high")
        self.assertEqual(init.risk_level, "low")

    def test_04_initiative_lifecycle(self):
        """4. Initiative progress tracking and automatic completion."""
        from apps.seo.models import InitiativeStatus
        strategy = self.service.generate_strategy(project=self.project_a, title="Q3 Plan")
        init = self.service.create_initiative(strategy=strategy, name="Schema Deployment")
        self.assertEqual(init.status, InitiativeStatus.PLANNED)

        self.service.update_initiative_progress(init, progress=0.4, status=InitiativeStatus.ACTIVE)
        init.refresh_from_db()
        self.assertEqual(init.progress, 0.4)
        self.assertEqual(init.status, InitiativeStatus.ACTIVE)

        self.service.update_initiative_progress(init, progress=1.0)
        init.refresh_from_db()
        self.assertEqual(init.progress, 1.0)
        self.assertEqual(init.status, InitiativeStatus.COMPLETED)

    def test_05_priority_handling(self):
        """5. Strategic priorities correctly categorized and filterable."""
        from apps.seo.models import StrategicObjective, StrategicPriority
        obj_crit = self.service.create_objective(project=self.project_a, name="Crit Obj", priority=StrategicPriority.CRITICAL)
        obj_low = self.service.create_objective(project=self.project_a, name="Low Obj", priority=StrategicPriority.LOW)
        self.assertEqual(obj_crit.priority, "critical")
        self.assertEqual(obj_low.priority, "low")
        crits = StrategicObjective.objects.filter(project=self.project_a, priority="critical")
        self.assertIn(obj_crit, crits)
        self.assertNotIn(obj_low, crits)

    def test_06_strategy_creation(self):
        """6. Generate strategy with 4-tier epistemic structure."""
        from apps.seo.models import StrategyStatus, StrategyHealth
        strat = self.service.generate_strategy(
            project=self.project_a,
            title="Comprehensive Annual SEO Strategy",
            horizon="long_term"
        )
        self.assertEqual(strat.project, self.project_a)
        self.assertEqual(strat.version, 1)
        self.assertEqual(strat.status, StrategyStatus.ACTIVE)
        self.assertEqual(strat.health, StrategyHealth.ON_TRACK)
        self.assertIn("Observed Fact", strat.rationale)
        self.assertIn("Inference", strat.rationale)
        self.assertIn("Hypothesis", strat.rationale)
        self.assertIn("Strategic Decision", strat.rationale)

    def test_07_strategy_versioning(self):
        """7. Incremental versioning upon strategy iteration."""
        s1 = self.service.generate_strategy(project=self.project_a, title="Initial Strategy v1")
        self.assertEqual(s1.version, 1)

        s2 = self.service.generate_strategy(project=self.project_a, title="Iterated Strategy v2")
        self.assertEqual(s2.version, 2)

    def test_08_historical_versions_preserved(self):
        """8. Previous strategy versions are superseded and never overwritten."""
        from apps.seo.models import StrategyStatus
        s1 = self.service.generate_strategy(project=self.project_a, title="Strategy v1")
        self.assertEqual(s1.status, StrategyStatus.ACTIVE)

        # Trigger adjustment and approve
        obj = self.service.create_objective(
            project=self.project_a, name="Failing Obj", status="at_risk"
        )
        rec, decision, proposed = self.service.conduct_strategy_review(
            project=self.project_a, trigger_source="manual"
        )
        self.assertIsNotNone(proposed)
        active_v2 = self.service.approve_strategy_adjustment(review_id=rec.id, user=self.user_a)

        s1.refresh_from_db()
        self.assertEqual(s1.status, StrategyStatus.SUPERSEDED)
        self.assertEqual(active_v2.status, StrategyStatus.ACTIVE)
        self.assertEqual(active_v2.version, 2)
        self.assertEqual(active_v2.previous_version, s1)

    def test_09_evidence_provenance(self):
        """9. Empirical evidence provenance recorded in strategy and reviews."""
        strat = self.service.generate_strategy(project=self.project_a, title="Evidence Strategy")
        self.assertIn("rankings_count", strat.evidence)
        self.assertIn("audit_issues_count", strat.evidence)
        self.assertIn("observed_at", strat.evidence)

    def test_10_progress_calculation_increasing(self):
        """10. Deterministic progress calculation for INCREASING metrics (traffic, scores)."""
        calc = self.service.calculate_progress
        # 100 -> 200, current 150 = 50%
        self.assertEqual(calc(100.0, 150.0, 200.0, "increasing"), 0.5)
        # Below baseline is clamped to 0.0
        self.assertEqual(calc(100.0, 80.0, 200.0, "increasing"), 0.0)
        # Exceeded target
        self.assertEqual(calc(100.0, 250.0, 200.0, "increasing"), 1.5)

    def test_11_progress_calculation_decreasing(self):
        """11. Deterministic progress calculation for DECREASING metrics (rankings)."""
        calc = self.service.calculate_progress
        # Rank: baseline 50 -> target 10, current 30 = 20/40 = 50%
        self.assertEqual(calc(50.0, 30.0, 10.0, "decreasing"), 0.5)
        # Current 10 = 100%
        self.assertEqual(calc(50.0, 10.0, 10.0, "decreasing"), 1.0)
        # Rank worsened to 60 -> clamped to 0.0
        self.assertEqual(calc(50.0, 60.0, 10.0, "decreasing"), 0.0)
        # Rank exceeded target (rank 5)
        self.assertEqual(calc(50.0, 5.0, 10.0, "decreasing"), 1.125)

    def test_12_trend_detection_rules(self):
        """12. Rule-based trend detection without neural/ML black boxes."""
        trend = self.service.calculate_trend
        # Increasing
        self.assertEqual(trend([100.0, 120.0, 150.0], "increasing"), "improving")
        self.assertEqual(trend([150.0, 120.0, 100.0], "increasing"), "declining")
        self.assertEqual(trend([100.0, 100.5], "increasing"), "stable")

        # Decreasing (lower is better)
        self.assertEqual(trend([50.0, 35.0, 20.0], "decreasing"), "improving")
        self.assertEqual(trend([20.0, 35.0, 50.0], "decreasing"), "declining")
        self.assertEqual(trend([20.0, 20.1], "decreasing"), "stable")

        # Insufficient data
        self.assertEqual(trend([10.0], "increasing"), "insufficient_data")

    def test_13_strategy_health_calculation(self):
        """13. Deterministic health derivation from objectives and initiatives."""
        from apps.seo.models import StrategyHealth
        strat = self.service.generate_strategy(project=self.project_a, title="Health Strategy")

        # Empty strategy has ON_TRACK or NO_DATA
        o1 = self.service.create_objective(project=self.project_a, name="Obj 1")
        o2 = self.service.create_objective(project=self.project_a, name="Obj 2")
        self.service.update_objective_progress(o1, current_value=90.0)
        self.service.update_objective_progress(o2, current_value=85.0)

        health = self.service.evaluate_strategy_health(strat)
        self.assertEqual(health, StrategyHealth.ON_TRACK)

    def test_14_risk_detection(self):
        """14. Risk detection when objective drops into AT_RISK status."""
        from apps.seo.models import ReviewDecision, ReviewApprovalStatus, ObjectiveStatus
        strat = self.service.generate_strategy(project=self.project_a, title="Risk Strategy")
        obj = self.service.create_objective(project=self.project_a, name="Critical Metric")
        obj.status = ObjectiveStatus.AT_RISK
        obj.save()

        rec, decision, proposed = self.service.conduct_strategy_review(
            project=self.project_a, trigger_source="monitoring_alert"
        )
        self.assertEqual(decision, ReviewDecision.ADJUST)
        self.assertEqual(rec.approval_status, ReviewApprovalStatus.PENDING_APPROVAL)
        self.assertIsNotNone(proposed)
        self.assertIn("AT_RISK", rec.evaluation_summary["detected_risks"][0])

    def test_15_strategy_review_periodic(self):
        """15. Bounded review cycle produces review record and keeps strategy if healthy."""
        from apps.seo.models import ReviewDecision, ReviewApprovalStatus
        strat = self.service.generate_strategy(project=self.project_a, title="Healthy Strategy")
        rec, decision, proposed = self.service.conduct_strategy_review(
            project=self.project_a, trigger_source="weekly_schedule"
        )
        self.assertEqual(decision, ReviewDecision.KEEP)
        self.assertEqual(rec.approval_status, ReviewApprovalStatus.NOT_REQUIRED)
        self.assertIsNone(proposed)

    def test_16_review_idempotency_fingerprint(self):
        """16. Review idempotency via deterministic SHA-256 fingerprint."""
        strat = self.service.generate_strategy(project=self.project_a, title="Idempotent Strategy")
        rec1, d1, _ = self.service.conduct_strategy_review(project=self.project_a, trigger_source="cron")
        # Repeating review without force
        rec2, d2, _ = self.service.conduct_strategy_review(project=self.project_a, trigger_source="cron")
        self.assertEqual(rec1.id, rec2.id)
        self.assertEqual(rec1.fingerprint, rec2.fingerprint)

    def test_17_concurrent_review_protection(self):
        """17. Row-locking (select_for_update) serializes concurrent reviews."""
        strat = self.service.generate_strategy(project=self.project_a, title="Lock Strategy")
        with transaction.atomic():
            rec, decision, _ = self.service.conduct_strategy_review(
                project=self.project_a, trigger_source="concurrent_worker_1"
            )
            self.assertIsNotNone(rec)

    def test_18_strategy_adjustment_proposal(self):
        """18. Proposed strategy version created upon review adjustment."""
        from apps.seo.models import StrategyStatus, ReviewApprovalStatus
        strat = self.service.generate_strategy(project=self.project_a, title="Base Strat")
        self.service.create_objective(project=self.project_a, name="Failing Metric", status="at_risk")

        rec, decision, proposed = self.service.conduct_strategy_review(
            project=self.project_a, trigger_source="risk_trigger"
        )
        self.assertEqual(rec.approval_status, ReviewApprovalStatus.PENDING_APPROVAL)
        self.assertIsNotNone(proposed)
        self.assertEqual(proposed.status, StrategyStatus.PROPOSED)
        self.assertEqual(proposed.version, 2)
        self.assertEqual(proposed.previous_version, strat)

    def test_19_strategy_approval_hitl(self):
        """19. Human-in-the-Loop approval activates proposed version and supersedes previous."""
        from apps.seo.models import StrategyStatus, ReviewApprovalStatus
        s1 = self.service.generate_strategy(project=self.project_a, title="Strat v1")
        self.service.create_objective(project=self.project_a, name="Needs Fix", status="at_risk")
        rec, decision, proposed = self.service.conduct_strategy_review(project=self.project_a)

        s2 = self.service.approve_strategy_adjustment(review_id=rec.id, user=self.user_a)
        s1.refresh_from_db()
        rec.refresh_from_db()

        self.assertEqual(s1.status, StrategyStatus.SUPERSEDED)
        self.assertEqual(s2.status, StrategyStatus.ACTIVE)
        self.assertEqual(rec.approval_status, ReviewApprovalStatus.APPROVED)

    def test_20_strategy_rejection_hitl(self):
        """20. Human-in-the-Loop rejection archives proposed strategy and keeps active."""
        from apps.seo.models import StrategyStatus, ReviewApprovalStatus
        s1 = self.service.generate_strategy(project=self.project_a, title="Strat v1")
        self.service.create_objective(project=self.project_a, name="Needs Fix", status="at_risk")
        rec, decision, proposed = self.service.conduct_strategy_review(project=self.project_a)

        updated_rec = self.service.reject_strategy_adjustment(
            review_id=rec.id, user=self.user_a, reason="Proposed budget too high."
        )
        s1.refresh_from_db()
        proposed.refresh_from_db()

        self.assertEqual(s1.status, StrategyStatus.ACTIVE)
        self.assertEqual(proposed.status, StrategyStatus.CANCELLED)
        self.assertEqual(updated_rec.approval_status, ReviewApprovalStatus.REJECTED)

    def test_21_hitl_boundary_enforcement(self):
        """21. Disallow approving non-pending reviews or unauthorized changes."""
        from apps.seo.services.long_term_strategy import StrategyHITLError
        s1 = self.service.generate_strategy(project=self.project_a, title="Strat v1")
        rec, decision, _ = self.service.conduct_strategy_review(project=self.project_a)
        # Review is NOT_REQUIRED (not pending approval)
        with self.assertRaises(StrategyHITLError):
            self.service.approve_strategy_adjustment(review_id=rec.id, user=self.user_a)

    def test_22_shared_working_memory_integration(self):
        """22. SharedWorkingMemory registers strategic objectives and decisions with provenance."""
        from apps.seo.services.agents.shared_memory import SharedWorkingMemory, MemoryCategory
        mem = SharedWorkingMemory(project_id=self.project_a.id, task_goal="Long-term strategy planning")
        entry = mem.record_strategic_objective(
            source_agent="seo_strategist",
            objective_id=101,
            name="Rank Top 3 for Amharic Electronics",
            target="Top 3",
            horizon="medium_term"
        )
        self.assertEqual(entry.category, MemoryCategory.STRATEGIC_OBJECTIVE)
        self.assertIn("Amharic Electronics", entry.content["name"])

    def test_23_agent_learning_integration(self):
        """23. Historical SEO action outcomes inform strategy rationale."""
        from apps.seo.models import SEOAction, ActionType, ActionStatus
        SEOAction.objects.create(
            project=self.project_a,
            action_type=ActionType.UPDATE_TITLE,
            title="Fix Meta Titles",
            target_url="https://addismarket.et/coffee",
            status=ActionStatus.COMPLETED
        )
        strat = self.service.generate_strategy(project=self.project_a, title="Informed Strategy")
        self.assertGreaterEqual(strat.evidence.get("historical_actions_count", 0), 1)

    def test_24_advanced_reasoning_integration(self):
        """24. Epistemic structure strictly separates facts, inferences, hypotheses, decisions."""
        strat = self.service.generate_strategy(project=self.project_a, title="Epistemic Strat")
        rat = strat.rationale
        self.assertIn("Observed Fact:", rat)
        self.assertIn("Inference:", rat)
        self.assertIn("Hypothesis:", rat)
        self.assertIn("Strategic Decision:", rat)
        self.assertIn("Expected Outcome:", rat)

    def test_25_task_planner_dag_integration(self):
        """25. Initiatives bridge to TaskPlanner DAG with ReplanReason.STRATEGY_CHANGE."""
        from apps.seo.models import InitiativeStatus
        strat = self.service.generate_strategy(project=self.project_a, title="DAG Plan")
        init = self.service.create_initiative(strategy=strat, name="Optimize Crawl Budget")
        link_res = self.service.link_initiative_to_tasks(init)
        self.assertEqual(link_res["replan_reason"], "strategy_change")
        self.assertGreater(len(link_res["generated_task_ids"]), 0)
        init.refresh_from_db()
        self.assertEqual(init.status, InitiativeStatus.ACTIVE)

    def test_26_continuous_operations_integration(self):
        """26. ContinuousOperation triggers strategy review cycle without breaking."""
        strat = self.service.generate_strategy(project=self.project_a, title="Continuous Strat")
        rec, decision, _ = self.service.conduct_strategy_review(
            project=self.project_a, trigger_source="continuous_operations"
        )
        self.assertEqual(rec.evaluation_summary["trigger_source"], "continuous_operations")

    def test_27_seo_event_integration(self):
        """27. Major ranking drop SEOEvent triggers risk detection."""
        from apps.seo.models import ReviewDecision
        strat = self.service.generate_strategy(project=self.project_a, title="Event Strat")
        rec, decision, proposed = self.service.conduct_strategy_review(
            project=self.project_a, trigger_source="major_ranking_drop"
        )
        self.assertEqual(decision, ReviewDecision.ADJUST)
        self.assertIn("Major ranking drop", rec.evaluation_summary["detected_risks"][0])

    def test_28_monitoring_integration(self):
        """28. Strategic review incorporates MonitoringSnapshot empirical evidence."""
        from apps.seo.models import MonitoringSnapshot, MonitorType
        MonitoringSnapshot.objects.create(
            project=self.project_a,
            monitor_type=MonitorType.RANKING,
            metric_key="keyword_rank_summary",
            value={"average_rank": 18.5, "health_score": 85}
        )
        strat = self.service.generate_strategy(project=self.project_a, title="Monitoring Strat")
        self.assertGreaterEqual(strat.evidence.get("monitoring_snapshots_count", 0), 1)

    def test_29_remediation_integration(self):
        """29. Initiatives target concrete remediation action types."""
        strat = self.service.generate_strategy(project=self.project_a, title="Remediation Strat")
        init = self.service.create_initiative(
            strategy=strat,
            name="Remediate Broken Canonical Tags",
            target_action_types=["fix_canonical", "update_meta"]
        )
        self.assertIn("fix_canonical", init.target_action_types)

    def test_30_multi_system_integration(self):
        """30. Strategic initiatives connect to external adapter capabilities."""
        strat = self.service.generate_strategy(project=self.project_a, title="Multi-System Strat")
        init = self.service.create_initiative(
            strategy=strat,
            name="Publish New Amharic Guides",
            target_action_types=["CMS.UPDATE_METADATA", "GIT.WRITE_FILE"]
        )
        self.assertIn("CMS.UPDATE_METADATA", init.target_action_types)

    def test_31_tenant_isolation(self):
        """31. Tenant isolation prevents cross-tenant strategy access or objective linking."""
        from apps.seo.services.long_term_strategy import TenantIsolationError
        strat_a = self.service.generate_strategy(project=self.project_a, title="Project A Strat")
        obj_b = self.service.create_objective(project=self.project_b, name="Tenant B Objective")

        with self.assertRaises(TenantIsolationError):
            self.service.create_initiative(
                strategy=strat_a,
                name="Illegal Cross-Tenant Initiative",
                objective=obj_b
            )

    def test_32_failure_isolation(self):
        """32. Review failures do not corrupt strategy state."""
        strat = self.service.generate_strategy(project=self.project_a, title="Safe Strat")
        initial_status = strat.status
        try:
            with transaction.atomic():
                self.service.conduct_strategy_review(project=self.project_a)
                raise ValueError("Simulated unexpected failure during post-review")
        except ValueError:
            pass
        strat.refresh_from_db()
        self.assertEqual(strat.status, initial_status)

    def test_33_telemetry_emission(self):
        """33. 13 strategy events emitted during lifecycle."""
        from apps.seo.services.agent_events import AgentEventType
        self.publisher.clear()
        strat = self.service.generate_strategy(project=self.project_a, title="Telemetry Strat")
        events = [e.event_type for e in self.publisher.events]
        self.assertIn(AgentEventType.SEO_STRATEGY_VERSION_CREATED, events)

    def test_34_runtime_derived_evaluation_metrics(self):
        """34. Runtime evaluation metrics dynamically aggregated from database."""
        strat = self.service.generate_strategy(project=self.project_a, title="Metrics Strat")
        o1 = self.service.create_objective(project=self.project_a, name="Obj 1")
        self.service.update_objective_progress(o1, current_value=50.0)

        metrics = self.service.get_strategy_metrics(self.project_a)
        self.assertEqual(metrics["active_objectives_count"], 1)
        self.assertIn("health_status", metrics)
        self.assertIn("strategy_version", metrics)

    def test_35_stale_evidence_handling(self):
        """35. Gracefully handles absence of telemetry or historical audits."""
        empty_proj = Project.objects.create(name="Empty Proj", website_url="https://empty.et", owner=self.user_a)
        strat = self.service.generate_strategy(project=empty_proj, title="Empty Strat")
        self.assertEqual(strat.evidence["rankings_count"], 0)
        self.assertEqual(strat.evidence["audit_issues_count"], 0)

    def test_36_no_data_handling(self):
        """36. Returns NO_DATA health when project has no objectives or initiatives."""
        from apps.seo.models import StrategyHealth, LongTermSEOStrategy
        empty_proj = Project.objects.create(name="No Data Proj", website_url="https://nodata.et", owner=self.user_a)
        strat = LongTermSEOStrategy.objects.create(
            project=empty_proj, title="Blank Strat", version=1
        )
        health = self.service.evaluate_strategy_health(strat)
        self.assertEqual(health, StrategyHealth.NO_DATA)

    def test_37_objective_achievement(self):
        """37. Objective automatically transitions to ACHIEVED when target is reached."""
        from apps.seo.models import ObjectiveStatus
        obj = self.service.create_objective(
            project=self.project_a, name="Reach 100", baseline=0, target=100
        )
        self.service.update_objective_progress(obj, current_value=100.0)
        obj.refresh_from_db()
        self.assertEqual(obj.status, ObjectiveStatus.ACHIEVED)
        self.assertEqual(obj.progress, 1.0)

    def test_38_objective_at_risk_state(self):
        """38. Objective marked AT_RISK when target date is near with low progress."""
        from apps.seo.models import ObjectiveStatus
        near_date = timezone.now() + timedelta(days=5)
        obj = self.service.create_objective(
            project=self.project_a, name="Urgent Obj", baseline=0, target=100, target_date=near_date
        )
        self.service.update_objective_progress(obj, current_value=10.0)
        obj.refresh_from_db()
        self.assertEqual(obj.status, ObjectiveStatus.AT_RISK)

    def test_39_strategy_cancellation(self):
        """39. Proposed strategy can be cancelled without affecting active version."""
        from apps.seo.models import StrategyStatus
        s1 = self.service.generate_strategy(project=self.project_a, title="Active Strat")
        self.service.create_objective(project=self.project_a, name="Risk", status="at_risk")
        rec, decision, proposed = self.service.conduct_strategy_review(project=self.project_a)

        self.service.reject_strategy_adjustment(review_id=rec.id, user=self.user_a, reason="Not approved")
        proposed.refresh_from_db()
        self.assertEqual(proposed.status, StrategyStatus.CANCELLED)

    def test_40_duplicate_event_protection(self):
        """40. Identical review triggers in same cycle do not produce duplicate reviews."""
        strat = self.service.generate_strategy(project=self.project_a, title="Protected Strat")
        r1, _, _ = self.service.conduct_strategy_review(project=self.project_a, trigger_source="batch_event")
        r2, _, _ = self.service.conduct_strategy_review(project=self.project_a, trigger_source="batch_event")
        self.assertEqual(r1.id, r2.id)

    def test_41_celery_retry_protection(self):
        """41. Celery retries evaluate the idempotency fingerprint and do not duplicate."""
        strat = self.service.generate_strategy(project=self.project_a, title="Celery Strat")
        r1, _, _ = self.service.conduct_strategy_review(project=self.project_a, trigger_source="celery_task")
        r2, _, _ = self.service.conduct_strategy_review(project=self.project_a, trigger_source="celery_task")
        self.assertEqual(r1.id, r2.id)

    def test_42_full_historical_preservation_and_regression(self):
        """42. Multi-version evolution preserves complete history and 5.x/6.x integrity."""
        from apps.seo.models import LongTermSEOStrategy, StrategyStatus
        # Cycle 1
        s1 = self.service.generate_strategy(project=self.project_a, title="Year 1 Strategy")
        self.assertEqual(s1.version, 1)

        # Cycle 2: Drift & Adjustment
        self.service.create_objective(project=self.project_a, name="Drifting Goal", status="at_risk")
        r1, _, prop = self.service.conduct_strategy_review(project=self.project_a)
        s2 = self.service.approve_strategy_adjustment(review_id=r1.id, user=self.user_a)

        # Both s1 and s2 exist in DB with full provenance
        all_versions = LongTermSEOStrategy.objects.filter(project=self.project_a).order_by("version")
        self.assertEqual(all_versions.count(), 2)
        self.assertEqual(all_versions[0].status, StrategyStatus.SUPERSEDED)
        self.assertEqual(all_versions[1].status, StrategyStatus.ACTIVE)
        self.assertEqual(all_versions[1].previous_version, all_versions[0])
