from django.test import TestCase
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
from apps.seo.services.seo_intelligence import SEOIntelligenceService
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

    def test_default_registry_has_all_8_tools(self):
        """1. Default ToolRegistry is populated with exactly the 8 core tools."""
        expected_tools = [
            'get_keyword_rankings',
            'get_search_console_analytics',
            'get_audit_issues',
            'run_intelligence_analysis',
            'generate_recommendation',
            'generate_content_brief',
            'generate_content_draft',
            'propose_seo_action'
        ]
        registered_names = [t.name for t in self.registry.list_tools()]
        self.assertEqual(len(registered_names), 8)
        for tool_name in expected_tools:
            self.assertIn(tool_name, registered_names)
            tool = self.registry.get(tool_name)
            self.assertIsNotNone(tool)
            self.assertEqual(tool.name, tool_name)

    def test_tool_definitions_and_schema_export(self):
        """2. Tool definitions export standard provider-neutral JSON schemas."""
        schemas = self.registry.get_schemas()
        self.assertEqual(len(schemas), 8)

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
        for name in ['get_keyword_rankings', 'get_search_console_analytics', 'get_audit_issues']:
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








