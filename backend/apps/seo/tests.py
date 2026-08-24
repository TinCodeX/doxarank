from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from apps.projects.models import Project
from apps.seo.models import (
    Keyword, KeywordRanking, SearchEngine, Country, Language, Device,
    SiteAudit, AuditIssue, AuditStatus, IssueSeverity,
    SearchConsoleConnection, SearchConsolePermission, SearchConsoleSyncStatus
)

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


