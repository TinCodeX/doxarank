from django.test import TestCase
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
    SEORecommendation, RecommendationType, RecommendationPriority, RecommendationStatus
)
from apps.seo.services.seo_intelligence import SEOIntelligenceService
from apps.seo.services.ai_providers import MockAIProvider
from apps.seo.services.ai_seo_agent import AISeoAgentService

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





