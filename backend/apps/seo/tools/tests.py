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
from apps.seo.tools.robots import RobotsTxtGenerator, RobotsTxtTester
from apps.seo.tools.sitemap import XmlSitemapGenerator, XmlSitemapValidator
from apps.seo.tools.hreflang import HreflangBuilder

User = get_user_model()


# =====================================================================
# BATCH 1 UNIT TESTS (Tools 1 - 3)
# =====================================================================

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


# =====================================================================
# BATCH 2 UNIT TESTS (Tools 4 - 6)
# =====================================================================

class RobotsTxtGeneratorUnitTests(TestCase):
    def test_valid_robots_generation(self):
        groups = [
            {
                'user_agent': '*',
                'disallow': ['/admin/', '/private/'],
                'allow': ['/public/', '/blog/'],
                'crawl_delay': 5,
            },
            {
                'user_agent': 'Googlebot',
                'disallow': ['/no-google/'],
            }
        ]
        sitemaps = ['https://example.com/sitemap.xml', 'https://example.com/sitemap-images.xml']
        res = RobotsTxtGenerator.generate(groups=groups, sitemaps=sitemaps, host='example.com')
        content = res['content']

        self.assertIn("User-agent: *", content)
        self.assertIn("Disallow: /admin/", content)
        self.assertIn("Disallow: /private/", content)
        self.assertIn("Allow: /public/", content)
        self.assertIn("Crawl-delay: 5", content)
        self.assertIn("User-agent: Googlebot", content)
        self.assertIn("Disallow: /no-google/", content)
        self.assertIn("Sitemap: https://example.com/sitemap.xml", content)
        self.assertIn("Host: example.com", content)
        self.assertEqual(res['metrics']['group_count'], 2)
        self.assertEqual(res['metrics']['sitemap_count'], 2)

    def test_malformed_path_rejection(self):
        groups = [{'user_agent': '*', 'disallow': ['no-leading-slash']}]
        with self.assertRaises(ValueError) as ctx:
            RobotsTxtGenerator.generate(groups=groups)
        self.assertIn("must start with '/'", str(ctx.exception))

    def test_empty_groups_rejection(self):
        with self.assertRaises(ValueError):
            RobotsTxtGenerator.generate(groups=[])

    def test_warnings_detection(self):
        # Full site block warning
        res = RobotsTxtGenerator.generate(groups=[{'user_agent': '*', 'disallow': ['/']}])
        self.assertTrue(any("blocks entire site" in w for w in res['warnings']))

        # Conflicting allow/disallow warning
        res2 = RobotsTxtGenerator.generate(groups=[{'user_agent': '*', 'allow': ['/test/'], 'disallow': ['/test/']}])
        self.assertTrue(any("identical Allow and Disallow" in w for w in res2['warnings']))


class RobotsTxtTesterUnitTests(TestCase):
    def setUp(self):
        self.robots_sample = """User-agent: *
Disallow: /admin/
Disallow: /private/
Allow: /public/

User-agent: Googlebot
Disallow: /no-google/
"""

    def test_allow_and_disallow_matching(self):
        res_allowed = RobotsTxtTester.test(
            robots_content=self.robots_sample,
            path='/public/info.html',
            user_agent='*'
        )
        self.assertTrue(res_allowed['allowed'])
        self.assertEqual(res_allowed['status'], 'ALLOWED')

        res_blocked = RobotsTxtTester.test(
            robots_content=self.robots_sample,
            path='/admin/users/',
            user_agent='*'
        )
        self.assertFalse(res_blocked['allowed'])
        self.assertEqual(res_blocked['status'], 'BLOCKED')
        self.assertIn("Disallow: /admin/", res_blocked['reason'])

    def test_user_agent_specific_rule(self):
        # /no-google/ is blocked for Googlebot but allowed for other bots
        res_google = RobotsTxtTester.test(
            robots_content=self.robots_sample,
            path='/no-google/page.html',
            user_agent='Googlebot'
        )
        self.assertFalse(res_google['allowed'])

        res_other = RobotsTxtTester.test(
            robots_content=self.robots_sample,
            path='/no-google/page.html',
            user_agent='Bingbot'
        )
        self.assertTrue(res_other['allowed'])

    def test_empty_content_validation(self):
        with self.assertRaises(ValueError):
            RobotsTxtTester.test(robots_content="", path="/test")


class XmlSitemapGeneratorUnitTests(TestCase):
    def test_valid_sitemap_generation(self):
        entries = [
            {
                'loc': 'https://example.com/',
                'lastmod': '2026-09-24',
                'changefreq': 'daily',
                'priority': '1.0'
            },
            {
                'loc': 'https://example.com/blog',
                'lastmod': '2026-09-20',
                'changefreq': 'weekly',
                'priority': '0.8'
            }
        ]
        res = XmlSitemapGenerator.generate(entries)
        xml = res['xml']
        self.assertIn('<?xml version="1.0" encoding="UTF-8"?>', xml)
        self.assertIn('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', xml)
        self.assertIn('<loc>https://example.com/</loc>', xml)
        self.assertIn('<lastmod>2026-09-24</lastmod>', xml)
        self.assertIn('<changefreq>daily</changefreq>', xml)
        self.assertIn('<priority>1.0</priority>', xml)
        self.assertEqual(res['metrics']['url_count'], 2)

    def test_xml_escaping_in_loc(self):
        entries = [{'loc': 'https://example.com/search?category=coffee&origin=ethiopia'}]
        res = XmlSitemapGenerator.generate(entries)
        self.assertIn('https://example.com/search?category=coffee&amp;origin=ethiopia', res['xml'])

    def test_invalid_entries_rejection(self):
        with self.assertRaises(ValueError):
            XmlSitemapGenerator.generate([])
        with self.assertRaises(ValueError):
            XmlSitemapGenerator.generate([{'loc': 'ftp://invalid'}])
        with self.assertRaises(ValueError):
            XmlSitemapGenerator.generate([{'loc': 'https://example.com', 'priority': '1.5'}])


class XmlSitemapValidatorUnitTests(TestCase):
    def test_valid_xml_sitemap_validation(self):
        valid_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/</loc>
    <lastmod>2026-09-24</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>"""
        res = XmlSitemapValidator.validate(valid_xml)
        self.assertTrue(res['is_valid'])
        self.assertEqual(res['url_count'], 1)
        self.assertEqual(len(res['errors']), 0)

    def test_syntax_error_detection(self):
        bad_xml = "<urlset><url><loc>https://example.com"  # Unclosed tags
        res = XmlSitemapValidator.validate(bad_xml)
        self.assertFalse(res['is_valid'])
        self.assertTrue(any("XML Parsing Error" in e for e in res['errors']))

    def test_invalid_root_tag_detection(self):
        bad_root = "<html><body><h1>Not a sitemap</h1></body></html>"
        res = XmlSitemapValidator.validate(bad_root)
        self.assertFalse(res['is_valid'])
        self.assertTrue(any("Invalid root element" in e for e in res['errors']))

    def test_missing_loc_tag_detection(self):
        no_loc = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><lastmod>2026-09-24</lastmod></url>
</urlset>"""
        res = XmlSitemapValidator.validate(no_loc)
        self.assertFalse(res['is_valid'])
        self.assertTrue(any("missing required <loc>" in e for e in res['errors']))


class HreflangBuilderUnitTests(TestCase):
    def test_valid_ethiopian_hreflang_generation(self):
        entries = [
            {'lang': 'en', 'url': 'https://example.com/en/'},
            {'lang': 'am', 'url': 'https://example.com/am/'},
            {'lang': 'om', 'url': 'https://example.com/om/'},
        ]
        res = HreflangBuilder.generate(entries, x_default='https://example.com/')
        html = res['html']
        self.assertIn('<link rel="alternate" hreflang="en" href="https://example.com/en/" />', html)
        self.assertIn('<link rel="alternate" hreflang="am" href="https://example.com/am/" />', html)
        self.assertIn('<link rel="alternate" hreflang="om" href="https://example.com/om/" />', html)
        self.assertIn('<link rel="alternate" hreflang="x-default" href="https://example.com/" />', html)

        # Check XML format
        self.assertIn('<xhtml:link rel="alternate" hreflang="am" href="https://example.com/am/"/>', res['xml_snippet'])

        # Check HTTP Header format
        self.assertIn('<https://example.com/en/>; rel="alternate"; hreflang="en"', res['http_header'])
        self.assertTrue(res['metrics']['has_english'])
        self.assertTrue(res['metrics']['has_amharic'])
        self.assertTrue(res['metrics']['has_oromo'])
        self.assertTrue(res['metrics']['has_x_default'])

    def test_invalid_language_code(self):
        entries = [{'lang': 'invalid_123', 'url': 'https://example.com/'}]
        with self.assertRaises(ValueError) as ctx:
            HreflangBuilder.generate(entries)
        self.assertIn("Invalid hreflang code", str(ctx.exception))

    def test_duplicate_language_code(self):
        entries = [
            {'lang': 'en', 'url': 'https://example.com/1'},
            {'lang': 'en', 'url': 'https://example.com/2'}
        ]
        with self.assertRaises(ValueError) as ctx:
            HreflangBuilder.generate(entries)
        self.assertIn("Duplicate language code", str(ctx.exception))


# =====================================================================
# API INTEGRATION TESTS (All 6 Tools)
# =====================================================================

class SEOToolsAPITests(TestCase):
    def setUp(self):
        SubscriptionService.bootstrap_default_plans()
        self.user = User.objects.create_user(
            email='testuser@doxarank.com',
            password='TestPassword123!'
        )
        self.client = APIClient()

    def test_unauthenticated_requests_blocked(self):
        for endpoint in ('/api/seo/tools/meta/', '/api/seo/tools/robots/', '/api/seo/tools/sitemap/', '/api/seo/tools/hreflang/'):
            resp = self.client.post(endpoint, {}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

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

    def test_robots_generate_and_test_api(self):
        self.client.force_authenticate(user=self.user)
        # Generate
        gen_payload = {
            'action': 'generate',
            'groups': [{'user_agent': '*', 'disallow': ['/admin/'], 'allow': ['/']}],
            'sitemaps': ['https://example.com/sitemap.xml']
        }
        gen_res = self.client.post('/api/seo/tools/robots/', gen_payload, format='json')
        self.assertEqual(gen_res.status_code, status.HTTP_200_OK)
        self.assertIn("User-agent: *", gen_res.data['content'])
        self.assertEqual(gen_res.data['usage']['used_today'], 1)

        # Test
        test_payload = {
            'action': 'test',
            'robots_content': gen_res.data['content'],
            'path': '/admin/secret',
            'user_agent': '*'
        }
        test_res = self.client.post('/api/seo/tools/robots/', test_payload, format='json')
        self.assertEqual(test_res.status_code, status.HTTP_200_OK)
        self.assertFalse(test_res.data['allowed'])
        self.assertEqual(test_res.data['status'], 'BLOCKED')
        self.assertEqual(test_res.data['usage']['used_today'], 2)

    def test_sitemap_generate_and_validate_api(self):
        self.client.force_authenticate(user=self.user)
        # Generate
        gen_payload = {
            'action': 'generate',
            'entries': [{'loc': 'https://example.com/home', 'changefreq': 'daily', 'priority': '0.9'}]
        }
        gen_res = self.client.post('/api/seo/tools/sitemap/', gen_payload, format='json')
        self.assertEqual(gen_res.status_code, status.HTTP_200_OK)
        self.assertIn('<loc>https://example.com/home</loc>', gen_res.data['xml'])
        self.assertEqual(gen_res.data['usage']['used_today'], 1)

        # Validate
        val_payload = {
            'action': 'validate',
            'xml_content': gen_res.data['xml']
        }
        val_res = self.client.post('/api/seo/tools/sitemap/', val_payload, format='json')
        self.assertEqual(val_res.status_code, status.HTTP_200_OK)
        self.assertTrue(val_res.data['is_valid'])
        self.assertEqual(val_res.data['url_count'], 1)
        self.assertEqual(val_res.data['usage']['used_today'], 2)

    def test_hreflang_builder_api(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'entries': [
                {'lang': 'en', 'url': 'https://example.com/en/'},
                {'lang': 'am', 'url': 'https://example.com/am/'},
                {'lang': 'om', 'url': 'https://example.com/om/'},
            ],
            'x_default': 'https://example.com/'
        }
        res = self.client.post('/api/seo/tools/hreflang/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('hreflang="am"', res.data['html'])
        self.assertIn('hreflang="om"', res.data['html'])
        self.assertEqual(res.data['usage']['used_today'], 1)

    def test_quota_status_endpoint_returns_all_6_tools(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.get('/api/seo/tools/status/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        tools = res.data['tools']
        self.assertIn('meta_tag_generator', tools)
        self.assertIn('schema_generator', tools)
        self.assertIn('open_graph_previewer', tools)
        self.assertIn('robots_txt_tool', tools)
        self.assertIn('xml_sitemap_tool', tools)
        self.assertIn('hreflang_builder', tools)

    def test_free_user_daily_limit_enforced_at_5(self):
        self.client.force_authenticate(user=self.user)
        for i in range(1, 6):
            resp = self.client.post('/api/seo/tools/meta/', {
                'title': f'Title {i}',
                'description': f'Description {i}'
            }, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(resp.data['usage']['used_today'], i)

        # 6th call should be blocked with 403 Forbidden
        blocked_resp = self.client.post('/api/seo/tools/meta/', {
            'title': 'Title 6',
            'description': 'Description 6'
        }, format='json')
        self.assertEqual(blocked_resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(blocked_resp.data['code'], 'PLAN_LIMIT_REACHED')
        self.assertTrue(blocked_resp.data['upgrade_required'])

    def test_starter_plan_is_unmetered(self):
        SubscriptionService.assign_plan(self.user, PlanCode.STARTER)
        self.client.force_authenticate(user=self.user)

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

        self.client.force_authenticate(user=self.user)
        for i in range(3):
            self.client.post('/api/seo/tools/meta/', {'title': f'A {i}', 'description': f'Desc {i}'}, format='json')

        self.client.force_authenticate(user=user_b)
        resp_b = self.client.post('/api/seo/tools/meta/', {'title': 'B 1', 'description': 'Desc B'}, format='json')
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_b.data['usage']['used_today'], 1)
        self.assertEqual(resp_b.data['usage']['remaining_today'], 4)
