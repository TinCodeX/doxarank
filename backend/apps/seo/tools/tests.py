import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from apps.subscriptions.models import Plan, PlanCode, FeatureCode, Subscription, ToolUsage
from apps.subscriptions.services import SubscriptionService, UsageLimitService
from apps.seo.tools.meta import MetaTagGenerator
from apps.seo.tools.schema import SchemaGenerator
from apps.seo.tools.social import SocialPreviewGenerator

User = get_user_model()


class MetaTagGeneratorUnitTests(TestCase):
    def test_valid_meta_generation(self):
        res = MetaTagGenerator.generate(
            title="DoxaRank SEO Platform",
            description="Autonomous SEO agent and rank tracking platform for modern marketing teams.",
            canonical_url="https://doxarank.com/platform",
            robots="index, follow"
        )
        self.assertIn('<title>DoxaRank SEO Platform</title>', res['html'])
        self.assertIn('<meta name="description" content="Autonomous SEO agent and rank tracking platform for modern marketing teams.">', res['html'])
        self.assertIn('<link rel="canonical" href="https://doxarank.com/platform">', res['html'])
        self.assertIn('<meta name="robots" content="index, follow">', res['html'])
        self.assertEqual(res['metrics']['title_length'], len("DoxaRank SEO Platform"))

    def test_missing_required_fields(self):
        with self.assertRaises(ValueError):
            MetaTagGenerator.generate(title="", description="Valid description")
        with self.assertRaises(ValueError):
            MetaTagGenerator.generate(title="Valid title", description="")

    def test_unsupported_robots_directive(self):
        with self.assertRaises(ValueError) as ctx:
            MetaTagGenerator.generate(title="Title", description="Desc", robots="all, archive, unsafe")
        self.assertIn("Unsupported robots directive", str(ctx.exception))

    def test_invalid_canonical_url(self):
        with self.assertRaises(ValueError) as ctx:
            MetaTagGenerator.generate(title="Title", description="Desc", canonical_url="ftp://invalid-scheme")
        self.assertIn("Canonical URL must be a valid HTTP or HTTPS URL", str(ctx.exception))

    def test_html_escaping_for_xss_safety(self):
        res = MetaTagGenerator.generate(
            title='Test <script>alert("xss")</script> & "quotes"',
            description='A description with <img src=x onerror=alert(1)> and "special" chars.',
            robots="index, follow"
        )
        self.assertNotIn('<script>', res['html'])
        self.assertIn('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;', res['html'])
        self.assertNotIn('<img', res['html'])


class SchemaGeneratorUnitTests(TestCase):
    def test_unsupported_schema_type(self):
        with self.assertRaises(ValueError) as ctx:
            SchemaGenerator.generate("CustomBogusType", {})
        self.assertIn("Unsupported schema type", str(ctx.exception))

    def test_local_business_schema(self):
        data = {
            'name': 'DoxaRank Agency',
            'url': 'https://doxarank.com',
            'telephone': '+251911000000',
            'priceRange': '$$',
            'address': {
                'streetAddress': 'Bole Medhanialem',
                'addressLocality': 'Addis Ababa',
                'addressCountry': 'ET'
            },
            'openingHours': ['Mo-Fr 08:30-17:30']
        }
        res = SchemaGenerator.generate('LocalBusiness', data)
        json_ld = res['json_ld']
        self.assertEqual(json_ld['@context'], 'https://schema.org')
        self.assertEqual(json_ld['@type'], 'LocalBusiness')
        self.assertEqual(json_ld['name'], 'DoxaRank Agency')
        self.assertEqual(json_ld['address']['@type'], 'PostalAddress')
        self.assertIn('<script type="application/ld+json">', res['script_tag'])

    def test_article_schema(self):
        data = {
            'headline': 'Modern SEO Strategies with AI Agents',
            'author': 'Bizrat',
            'datePublished': '2026-09-24',
            'description': 'How autonomous AI agents revolutionize organic growth.',
            'url': 'https://doxarank.com/blog/ai-seo',
            'publisher_name': 'DoxaRank Press'
        }
        res = SchemaGenerator.generate('Article', data)
        json_ld = res['json_ld']
        self.assertEqual(json_ld['@context'], 'https://schema.org')
        self.assertEqual(json_ld['@type'], 'Article')
        self.assertEqual(json_ld['headline'], 'Modern SEO Strategies with AI Agents')
        self.assertEqual(json_ld['author']['@type'], 'Person')
        self.assertEqual(json_ld['publisher']['@type'], 'Organization')

    def test_product_schema(self):
        data = {
            'name': 'DoxaRank Starter Plan',
            'description': 'SEO toolkit for startups',
            'brand': 'DoxaRank',
            'sku': 'DX-STARTER',
            'price': '49.00',
            'priceCurrency': 'USD'
        }
        res = SchemaGenerator.generate('Product', data)
        json_ld = res['json_ld']
        self.assertEqual(json_ld['@type'], 'Product')
        self.assertEqual(json_ld['offers']['price'], '49.00')
        self.assertEqual(json_ld['offers']['priceCurrency'], 'USD')

    def test_faq_schema(self):
        data = {
            'items': [
                {'question': 'What is DoxaRank?', 'answer': 'An autonomous SEO rank tracking platform.'},
                {'question': 'Does it track Ethiopian queries?', 'answer': 'Yes, with native Amharic and google.com.et support.'}
            ]
        }
        res = SchemaGenerator.generate('FAQ', data)
        json_ld = res['json_ld']
        self.assertEqual(json_ld['@type'], 'FAQPage')
        self.assertEqual(len(json_ld['mainEntity']), 2)
        self.assertEqual(json_ld['mainEntity'][0]['@type'], 'Question')
        self.assertEqual(json_ld['mainEntity'][0]['acceptedAnswer']['@type'], 'Answer')

    def test_faq_empty_items_rejection(self):
        with self.assertRaises(ValueError) as ctx:
            SchemaGenerator.generate('FAQ', {'items': []})
        self.assertIn("at least one question and answer pair", str(ctx.exception))

    def test_breadcrumb_list_schema(self):
        data = {
            'items': [
                {'name': 'Home', 'item': 'https://doxarank.com'},
                {'name': 'Tools', 'item': 'https://doxarank.com/tools'},
                {'name': 'Meta Generator', 'item': 'https://doxarank.com/tools/meta'}
            ]
        }
        res = SchemaGenerator.generate('BreadcrumbList', data)
        json_ld = res['json_ld']
        self.assertEqual(json_ld['@type'], 'BreadcrumbList')
        self.assertEqual(len(json_ld['itemListElement']), 3)
        self.assertEqual(json_ld['itemListElement'][0]['position'], 1)
        self.assertEqual(json_ld['itemListElement'][1]['position'], 2)
        self.assertEqual(json_ld['itemListElement'][2]['position'], 3)


class SocialPreviewGeneratorUnitTests(TestCase):
    def test_valid_social_generation(self):
        res = SocialPreviewGenerator.generate(
            title="DoxaRank Social Share",
            description="The leading SEO intelligence suite.",
            url="https://doxarank.com/preview",
            image_url="https://doxarank.com/assets/og-image.png",
            site_name="DoxaRank",
            og_type="website",
            twitter_card="summary_large_image",
            twitter_site="@doxarank"
        )
        self.assertIn('<meta property="og:title" content="DoxaRank Social Share">', res['html'])
        self.assertIn('<meta property="og:image" content="https://doxarank.com/assets/og-image.png">', res['html'])
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', res['html'])
        self.assertIn('<meta name="twitter:site" content="@doxarank">', res['html'])
        self.assertEqual(res['preview']['domain'], 'doxarank.com')

    def test_invalid_social_inputs(self):
        with self.assertRaises(ValueError):
            SocialPreviewGenerator.generate(title="", description="desc")
        with self.assertRaises(ValueError):
            SocialPreviewGenerator.generate(title="title", description="", og_type="invalid_type")


class SEOToolsAPITests(TestCase):
    def setUp(self):
        SubscriptionService.bootstrap_default_plans()
        self.user = User.objects.create_user(
            email='testuser@doxarank.com',
            password='TestPassword123!'
        )
        self.client = APIClient()

    def test_unauthenticated_requests_blocked(self):
        response = self.client.post('/api/seo/tools/meta/', {
            'title': 'Test Title',
            'description': 'Test Description'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_free_user_can_generate_meta_tags(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/seo/tools/meta/', {
            'title': 'Awesome SEO Title',
            'description': 'A comprehensive description for optimal organic search click-through rate.',
            'canonical_url': 'https://example.com/awesome',
            'robots': 'index, follow'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('<title>Awesome SEO Title</title>', response.data['html'])
        self.assertEqual(response.data['usage']['used_today'], 1)
        self.assertEqual(response.data['usage']['daily_limit'], 5)
        self.assertEqual(response.data['usage']['remaining_today'], 4)

    def test_schema_api_generation(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'schema_type': 'FAQ',
            'data': {
                'items': [
                    {'question': 'How does ranking work?', 'answer': 'By indexing search engine result pages.'}
                ]
            }
        }
        response = self.client.post('/api/seo/tools/schema/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['schema_type'], 'FAQ')
        self.assertIn('<script type="application/ld+json">', response.data['script_tag'])
        self.assertEqual(response.data['usage']['used_today'], 1)

    def test_social_preview_api_generation(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'title': 'New Feature Announcement',
            'description': 'Discover our new AI-driven keyword intelligence tools.',
            'url': 'https://example.com/announcement',
            'image_url': 'https://example.com/img.jpg',
            'og_type': 'article',
            'twitter_card': 'summary_large_image',
            'twitter_site': 'doxarank'
        }
        response = self.client.post('/api/seo/tools/social-preview/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('og_tags', response.data)
        self.assertEqual(response.data['preview']['twitter_site'], '@doxarank')
        self.assertEqual(response.data['usage']['used_today'], 1)

    def test_quota_status_endpoint_does_not_consume_limit(self):
        self.client.force_authenticate(user=self.user)
        res1 = self.client.get('/api/seo/tools/status/')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.data['tools']['meta_tag_generator']['used_today'], 0)

        # Generate 1 meta tag
        self.client.post('/api/seo/tools/meta/', {
            'title': 'Title 1',
            'description': 'Desc 1'
        }, format='json')

        # Check status again
        res2 = self.client.get('/api/seo/tools/status/')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['tools']['meta_tag_generator']['used_today'], 1)
        self.assertEqual(res2.data['tools']['meta_tag_generator']['remaining'], 4)

    def test_free_user_daily_limit_enforced_at_5(self):
        self.client.force_authenticate(user=self.user)
        # Execute 5 times (limit is 5)
        for i in range(1, 6):
            resp = self.client.post('/api/seo/tools/meta/', {
                'title': f'Title {i}',
                'description': f'Description {i}'
            }, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(resp.data['usage']['used_today'], i)

        # 6th call should be blocked with 403 Forbidden (PlanLimitReachedException)
        blocked_resp = self.client.post('/api/seo/tools/meta/', {
            'title': 'Title 6',
            'description': 'Description 6'
        }, format='json')
        self.assertEqual(blocked_resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(blocked_resp.data['code'], 'PLAN_LIMIT_REACHED')
        self.assertTrue(blocked_resp.data['upgrade_required'])

    def test_starter_plan_is_unmetered(self):
        # Upgrade user to STARTER plan
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.client.force_authenticate(user=self.user)

        # Starter has basic_tool_daily_limit = 0 (unlimited)
        for i in range(1, 8):
            resp = self.client.post('/api/seo/tools/meta/', {
                'title': f'Starter Title {i}',
                'description': f'Starter Description {i}'
            }, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(resp.data['usage']['daily_limit'], 'unlimited')

    def test_tenant_isolation_of_tool_quotas(self):
        user_b = User.objects.create_user(
            email='user_b@doxarank.com',
            password='TestPassword123!'
        )

        # User A makes 3 calls
        self.client.force_authenticate(user=self.user)
        for i in range(3):
            self.client.post('/api/seo/tools/meta/', {'title': f'A {i}', 'description': f'Desc {i}'}, format='json')

        # User B makes 1 call
        self.client.force_authenticate(user=user_b)
        resp_b = self.client.post('/api/seo/tools/meta/', {'title': 'B 1', 'description': 'Desc B'}, format='json')
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_b.data['usage']['used_today'], 1)
        self.assertEqual(resp_b.data['usage']['remaining_today'], 4)
