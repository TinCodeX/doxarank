from typing import Dict, Any, Optional
from apps.subscriptions.services import UsageLimitService, SubscriptionService
from apps.subscriptions.models import FeatureCode
from .meta import MetaTagGenerator
from .schema import SchemaGenerator
from .social import SocialPreviewGenerator
from .robots import RobotsTxtGenerator, RobotsTxtTester
from .sitemap import XmlSitemapGenerator, XmlSitemapValidator
from .hreflang import HreflangBuilder
from .serp_snippet import SerpSnippetAnalyzer
from .pagespeed import PageSpeedAnalyzer
from .broken_links import SinglePageBrokenLinkChecker
from .amharic import AmharicNormalizerTool


TOOL_CODE_META = 'meta_tag_generator'
TOOL_CODE_SCHEMA = 'schema_generator'
TOOL_CODE_SOCIAL = 'open_graph_previewer'
TOOL_CODE_ROBOTS = 'robots_txt_tool'
TOOL_CODE_SITEMAP = 'xml_sitemap_tool'
TOOL_CODE_HREFLANG = 'hreflang_builder'
TOOL_CODE_SERP = 'serp_snippet_checker'
TOOL_CODE_PAGESPEED = 'pagespeed_analyzer'
TOOL_CODE_BROKEN_LINKS = 'broken_link_checker'
TOOL_CODE_AMHARIC = 'amharic_normalizer'


def _build_usage_meta(user, tool_code: str, usage_count: int) -> Dict[str, Any]:
    plan = SubscriptionService.get_user_plan(user)
    limit = plan.basic_tool_daily_limit
    is_unlimited = (limit == 0)
    remaining = None if is_unlimited else max(0, limit - usage_count)

    return {
        'tool_code': tool_code,
        'plan_code': plan.code,
        'used_today': usage_count,
        'daily_limit': 'unlimited' if is_unlimited else limit,
        'remaining_today': 'unlimited' if is_unlimited else remaining,
    }


class SEOToolsService:
    """
    Orchestrates business logic for standalone SEO tools.
    Enforces subscription feature entitlement (BASIC_SEO_TOOLS) and
    atomically tracks / enforces daily usage limits for Free users.
    """

    # --- 1. META TAG GENERATOR ---
    @classmethod
    def generate_meta_tags(cls, user, params: Dict[str, Any]) -> Dict[str, Any]:
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_META)
        result = MetaTagGenerator.generate(
            title=params.get('title'),
            description=params.get('description'),
            canonical_url=params.get('canonical_url'),
            robots=params.get('robots', 'index, follow'),
            author=params.get('author'),
            keywords=params.get('keywords'),
            viewport=params.get('viewport', 'width=device-width, initial-scale=1.0'),
        )
        result['usage'] = _build_usage_meta(user, TOOL_CODE_META, usage.count)
        return result

    # --- 2. SCHEMA GENERATOR ---
    @classmethod
    def generate_schema(cls, user, schema_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_SCHEMA)
        result = SchemaGenerator.generate(
            schema_type=schema_type,
            data=data,
        )
        result['usage'] = _build_usage_meta(user, TOOL_CODE_SCHEMA, usage.count)
        return result

    # --- 3. SOCIAL PREVIEW GENERATOR ---
    @classmethod
    def generate_social_preview(cls, user, params: Dict[str, Any]) -> Dict[str, Any]:
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_SOCIAL)
        result = SocialPreviewGenerator.generate(
            title=params.get('title'),
            description=params.get('description'),
            url=params.get('url'),
            image_url=params.get('image_url'),
            site_name=params.get('site_name'),
            og_type=params.get('og_type', 'website'),
            twitter_card=params.get('twitter_card', 'summary_large_image'),
            twitter_site=params.get('twitter_site'),
            twitter_creator=params.get('twitter_creator'),
        )
        result['usage'] = _build_usage_meta(user, TOOL_CODE_SOCIAL, usage.count)
        return result

    # --- 4. ROBOTS.TXT GENERATOR & TESTER ---
    @classmethod
    def process_robots_tool(cls, user, params: Dict[str, Any]) -> Dict[str, Any]:
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_ROBOTS)
        action = params.get('action', 'generate')

        if action == 'test':
            result = RobotsTxtTester.test(
                robots_content=params.get('robots_content', ''),
                path=params.get('path', ''),
                user_agent=params.get('user_agent', '*'),
            )
        else:
            result = RobotsTxtGenerator.generate(
                groups=params.get('groups', []),
                sitemaps=params.get('sitemaps'),
                host=params.get('host'),
            )

        result['action'] = action
        result['usage'] = _build_usage_meta(user, TOOL_CODE_ROBOTS, usage.count)
        return result

    # --- 5. XML SITEMAP GENERATOR & VALIDATOR ---
    @classmethod
    def process_sitemap_tool(cls, user, params: Dict[str, Any]) -> Dict[str, Any]:
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_SITEMAP)
        action = params.get('action', 'generate')

        if action == 'validate':
            result = XmlSitemapValidator.validate(
                xml_content=params.get('xml_content', '')
            )
        else:
            result = XmlSitemapGenerator.generate(
                entries=params.get('entries', [])
            )

        result['action'] = action
        result['usage'] = _build_usage_meta(user, TOOL_CODE_SITEMAP, usage.count)
        return result

    # --- 6. HREFLANG BUILDER ---
    @classmethod
    def generate_hreflang(cls, user, params: Dict[str, Any]) -> Dict[str, Any]:
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_HREFLANG)
        result = HreflangBuilder.generate(
            entries=params.get('entries', []),
            x_default=params.get('x_default'),
        )
        result['usage'] = _build_usage_meta(user, TOOL_CODE_HREFLANG, usage.count)
        return result

    # --- 7. SERP SNIPPET PREVIEW / PIXEL-LENGTH CHECKER ---
    @classmethod
    def analyze_serp_snippet(cls, user, params: Dict[str, Any]) -> Dict[str, Any]:
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_SERP)
        result = SerpSnippetAnalyzer.analyze(
            title=params.get('title', ''),
            description=params.get('description', ''),
            url=params.get('url', ''),
            device=params.get('device', 'desktop'),
        )
        result['usage'] = _build_usage_meta(user, TOOL_CODE_SERP, usage.count)
        return result

    # --- 8. PAGESPEED / CORE WEB VITALS ANALYZER ---
    @classmethod
    def analyze_pagespeed(cls, user, params: Dict[str, Any]) -> Dict[str, Any]:
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_PAGESPEED)
        result = PageSpeedAnalyzer.analyze(
            url=params.get('url', ''),
            strategy=params.get('strategy', 'mobile'),
        )
        result['usage'] = _build_usage_meta(user, TOOL_CODE_PAGESPEED, usage.count)
        return result

    # --- 9. SINGLE-PAGE BROKEN LINK CHECKER ---
    @classmethod
    def check_broken_links(cls, user, params: Dict[str, Any]) -> Dict[str, Any]:
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_BROKEN_LINKS)
        result = SinglePageBrokenLinkChecker.check_page(
            url=params.get('url', ''),
        )
        result['usage'] = _build_usage_meta(user, TOOL_CODE_BROKEN_LINKS, usage.count)
        return result

    # --- 10. AMHARIC FIDEL KEYWORD NORMALIZER ---
    @classmethod
    def normalize_amharic(cls, user, params: Dict[str, Any]) -> Dict[str, Any]:
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_AMHARIC)
        result = AmharicNormalizerTool.normalize(
            text=params.get('text', ''),
            comparison_text=params.get('comparison_text'),
        )
        result['usage'] = _build_usage_meta(user, TOOL_CODE_AMHARIC, usage.count)
        return result

    # --- QUOTA STATUS ---
    @classmethod
    def get_user_tool_quota_status(cls, user) -> Dict[str, Any]:
        """
        Return the current day's usage and limits for all 10 basic tools without consuming quota.
        """
        plan = SubscriptionService.get_user_plan(user)
        limit = plan.basic_tool_daily_limit
        is_unlimited = (limit == 0)

        tool_codes = [
            TOOL_CODE_META,
            TOOL_CODE_SCHEMA,
            TOOL_CODE_SOCIAL,
            TOOL_CODE_ROBOTS,
            TOOL_CODE_SITEMAP,
            TOOL_CODE_HREFLANG,
            TOOL_CODE_SERP,
            TOOL_CODE_PAGESPEED,
            TOOL_CODE_BROKEN_LINKS,
            TOOL_CODE_AMHARIC,
        ]

        tools_status = {}
        for code in tool_codes:
            cnt = UsageLimitService.get_today_tool_usage(user, code)
            tools_status[code] = {
                'used_today': cnt,
                'remaining': 'unlimited' if is_unlimited else max(0, limit - cnt),
            }

        return {
            'plan_code': plan.code,
            'daily_limit': 'unlimited' if is_unlimited else limit,
            'tools': tools_status,
        }
