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
            'run_intelligence_analysis',
            'generate_recommendation',
            'generate_content_brief',
            'generate_content_draft',
            'propose_seo_action'
        ]
        registered_names = [t.name for t in self.registry.list_tools()]
        self.assertEqual(len(registered_names), 16)
        for tool_name in expected_tools:
            self.assertIn(tool_name, registered_names)
            tool = self.registry.get(tool_name)
            self.assertIsNotNone(tool)
            self.assertEqual(tool.name, tool_name)

    def test_tool_definitions_and_schema_export(self):
        """2. Tool definitions export standard provider-neutral JSON schemas."""
        schemas = self.registry.get_schemas()
        self.assertEqual(len(schemas), 16)

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
