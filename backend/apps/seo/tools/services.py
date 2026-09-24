from typing import Dict, Any, Optional
from apps.subscriptions.services import UsageLimitService, SubscriptionService
from apps.subscriptions.models import FeatureCode
from .meta import MetaTagGenerator
from .schema import SchemaGenerator
from .social import SocialPreviewGenerator


TOOL_CODE_META = 'meta_tag_generator'
TOOL_CODE_SCHEMA = 'schema_generator'
TOOL_CODE_SOCIAL = 'open_graph_previewer'


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

    @classmethod
    def generate_meta_tags(cls, user, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and generate HTML meta tags, incrementing user daily usage quota upon execution.
        """
        # 1. Atomic usage check & record (raises PlanLimitReachedException if limit reached)
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_META)

        # 2. Pure domain generation
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

    @classmethod
    def generate_schema(cls, user, schema_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and generate Schema.org JSON-LD, incrementing user daily usage quota.
        """
        usage = UsageLimitService.check_and_record_tool_usage(user, TOOL_CODE_SCHEMA)

        result = SchemaGenerator.generate(
            schema_type=schema_type,
            data=data,
        )

        result['usage'] = _build_usage_meta(user, TOOL_CODE_SCHEMA, usage.count)
        return result

    @classmethod
    def generate_social_preview(cls, user, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and generate Open Graph & Twitter Card tags and preview model,
        incrementing user daily usage quota.
        """
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

    @classmethod
    def get_user_tool_quota_status(cls, user) -> Dict[str, Any]:
        """
        Return the current day's usage and limits for the 3 basic tools without consuming quota.
        """
        plan = SubscriptionService.get_user_plan(user)
        limit = plan.basic_tool_daily_limit
        is_unlimited = (limit == 0)

        meta_count = UsageLimitService.get_today_tool_usage(user, TOOL_CODE_META)
        schema_count = UsageLimitService.get_today_tool_usage(user, TOOL_CODE_SCHEMA)
        social_count = UsageLimitService.get_today_tool_usage(user, TOOL_CODE_SOCIAL)

        return {
            'plan_code': plan.code,
            'daily_limit': 'unlimited' if is_unlimited else limit,
            'tools': {
                TOOL_CODE_META: {
                    'used_today': meta_count,
                    'remaining': 'unlimited' if is_unlimited else max(0, limit - meta_count),
                },
                TOOL_CODE_SCHEMA: {
                    'used_today': schema_count,
                    'remaining': 'unlimited' if is_unlimited else max(0, limit - schema_count),
                },
                TOOL_CODE_SOCIAL: {
                    'used_today': social_count,
                    'remaining': 'unlimited' if is_unlimited else max(0, limit - social_count),
                },
            }
        }
