import logging
from typing import Tuple, Dict, Any, Optional
from datetime import date
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    Plan,
    Subscription,
    ToolUsage,
    PlanCode,
    SubscriptionStatus,
    FeatureCode,
    PLAN_DEFAULTS,
)
from .exceptions import PlanLimitReachedException, FeatureNotEntitledException

logger = logging.getLogger(__name__)


class SubscriptionService:
    """
    Core management service for Plans and User Subscriptions.
    """

    @classmethod
    def bootstrap_default_plans(cls) -> Dict[str, Plan]:
        """
        Ensure FREE, STARTER, and AGENCY plans exist in the database with canonical parameters.
        Safe to call multiple times (idempotent).
        """
        created_or_updated = {}
        for code, defaults in PLAN_DEFAULTS.items():
            plan, _ = Plan.objects.update_or_create(
                code=code,
                defaults={
                    'name': defaults['name'],
                    'monthly_price': defaults['monthly_price'],
                    'currency': defaults['currency'],
                    'max_projects': defaults['max_projects'],
                    'max_keywords': defaults['max_keywords'],
                    'basic_tool_daily_limit': defaults['basic_tool_daily_limit'],
                    'features': defaults['features'],
                    'is_active': True,
                }
            )
            created_or_updated[code] = plan
        return created_or_updated

    @classmethod
    def get_or_create_user_subscription(cls, user) -> Subscription:
        """
        Retrieve or automatically initialize a subscription for the given user.
        Unassigned users default to the FREE tier.
        """
        if not user or not user.is_authenticated:
            raise ValueError("Authenticated user required for subscription check.")

        try:
            return user.subscription
        except Subscription.DoesNotExist:
            pass

        # Ensure default plans exist
        free_plan = Plan.objects.filter(code=PlanCode.FREE).first()
        if not free_plan:
            plans = cls.bootstrap_default_plans()
            free_plan = plans[PlanCode.FREE]

        with transaction.atomic():
            sub, _ = Subscription.objects.get_or_create(
                user=user,
                defaults={
                    'plan': free_plan,
                    'status': SubscriptionStatus.ACTIVE,
                    'started_at': timezone.now(),
                    'current_period_end': None,
                }
            )
        return sub

    @classmethod
    def assign_plan(
        cls,
        user,
        plan_code: str,
        status: str = SubscriptionStatus.ACTIVE,
        current_period_end=None
    ) -> Subscription:
        """
        Explicitly assign a user to a target plan tier (e.g. for testing, upgrade, or admin action).
        """
        plan = Plan.objects.filter(code=plan_code, is_active=True).first()
        if not plan:
            # Ensure bootstrap if not loaded yet
            cls.bootstrap_default_plans()
            plan = Plan.objects.get(code=plan_code)

        subscription = cls.get_or_create_user_subscription(user)
        subscription.plan = plan
        subscription.status = status
        subscription.current_period_end = current_period_end
        subscription.save(update_fields=['plan', 'status', 'current_period_end', 'updated_at'])
        logger.info(f"Assigned user {user.email} to plan {plan.code} (status={status})")
        return subscription

    @classmethod
    def get_user_plan(cls, user) -> Plan:
        """
        Return the user's active Plan object, falling back to FREE.
        """
        if not user or not user.is_authenticated:
            free_plan = Plan.objects.filter(code=PlanCode.FREE).first()
            if not free_plan:
                plans = cls.bootstrap_default_plans()
                free_plan = plans[PlanCode.FREE]
            return free_plan

        sub = cls.get_or_create_user_subscription(user)
        return sub.plan


class PlanEntitlementService:
    """
    Centralized entitlement and quota verification service.
    Reusable by Projects, SEO Keywords, Site Audits, Tools, Integrations, and Reports.
    """

    @classmethod
    def get_project_usage(cls, user) -> Tuple[int, int]:
        """Return (current_project_count, max_allowed_projects)."""
        from apps.projects.models import Project
        plan = SubscriptionService.get_user_plan(user)
        current = Project.objects.filter(owner=user).count()
        return current, plan.max_projects

    @classmethod
    def can_create_project(cls, user) -> Tuple[bool, int, int]:
        """
        Returns (can_create, current_count, limit).
        """
        current, limit = cls.get_project_usage(user)
        return (current < limit), current, limit

    @classmethod
    def check_can_create_project(cls, user):
        """
        Raises PlanLimitReachedException if user has reached their project quota.
        """
        allowed, current, limit = cls.can_create_project(user)
        if not allowed:
            plan = SubscriptionService.get_user_plan(user)
            raise PlanLimitReachedException(
                resource='projects',
                current=current,
                limit=limit,
                plan_code=plan.code,
                message=f"You have reached your limit of {limit} website/project on the {plan.name} plan. Upgrade to add more websites."
            )

    @classmethod
    def get_keyword_usage(cls, user) -> Tuple[int, int]:
        """Return (current_keyword_count_across_all_projects, max_allowed_keywords)."""
        from apps.seo.models import Keyword
        plan = SubscriptionService.get_user_plan(user)
        current = Keyword.objects.filter(project__owner=user).count()
        return current, plan.max_keywords

    @classmethod
    def can_add_keyword(cls, user, additional_count: int = 1) -> Tuple[bool, int, int]:
        """
        Returns (can_add, current_count, limit).
        """
        current, limit = cls.get_keyword_usage(user)
        return (current + additional_count <= limit), current, limit

    @classmethod
    def check_can_add_keyword(cls, user, additional_count: int = 1):
        """
        Raises PlanLimitReachedException if user has reached their tracked keyword quota.
        """
        allowed, current, limit = cls.can_add_keyword(user, additional_count=additional_count)
        if not allowed:
            plan = SubscriptionService.get_user_plan(user)
            raise PlanLimitReachedException(
                resource='keywords',
                current=current,
                limit=limit,
                plan_code=plan.code,
                message=f"You have reached your limit of {limit} tracked keywords on the {plan.name} plan. Upgrade to track more keywords."
            )

    @classmethod
    def can_use_feature(cls, user, feature_code: str) -> bool:
        """
        Check if the user's active plan includes the requested feature entitlement.
        """
        plan = SubscriptionService.get_user_plan(user)
        return plan.has_feature(feature_code)

    @classmethod
    def check_can_use_feature(cls, user, feature_code: str):
        """
        Raises FeatureNotEntitledException if the user's active plan does not include the feature.
        """
        if not cls.can_use_feature(user, feature_code):
            plan = SubscriptionService.get_user_plan(user)
            raise FeatureNotEntitledException(
                feature=feature_code,
                plan_code=plan.code
            )


class UsageLimitService:
    """
    Concurrency-safe daily tool execution tracking and rate-limiting service.
    """

    @classmethod
    def get_today_tool_usage(cls, user, tool_code: str, target_date: Optional[date] = None) -> int:
        """Return the number of times the user invoked tool_code on target_date."""
        target_date = target_date or timezone.localdate()
        usage = ToolUsage.objects.filter(
            user=user,
            tool_code=tool_code,
            usage_date=target_date
        ).first()
        return usage.count if usage else 0

    @classmethod
    def can_use_tool(cls, user, tool_code: str, target_date: Optional[date] = None) -> Tuple[bool, int, int]:
        """
        Evaluates whether a user can execute tool_code today.
        Returns: (can_use: bool, current_usage: int, daily_limit: int)
        Where daily_limit == 0 indicates unlimited access (e.g. Starter/Agency tiers).
        """
        plan = SubscriptionService.get_user_plan(user)

        # 1. First ensure user has basic SEO tools entitlement
        if not plan.has_feature(FeatureCode.BASIC_SEO_TOOLS):
            return False, 0, 0

        # 2. Check if plan provides unlimited tool usage (0 means unlimited)
        daily_limit = plan.basic_tool_daily_limit
        target_date = target_date or timezone.localdate()
        current_usage = cls.get_today_tool_usage(user, tool_code, target_date)

        if daily_limit == 0:
            return True, current_usage, 0

        # 3. Free plan quota evaluation
        allowed = (current_usage < daily_limit)
        return allowed, current_usage, daily_limit

    @classmethod
    def check_and_record_tool_usage(
        cls,
        user,
        tool_code: str,
        target_date: Optional[date] = None
    ) -> ToolUsage:
        """
        Atomically inspect and increment daily tool usage under a database lock.
        Raises PlanLimitReachedException if the daily quota is exhausted.
        Ensures concurrent requests cannot exceed the limit.
        """
        plan = SubscriptionService.get_user_plan(user)
        PlanEntitlementService.check_can_use_feature(user, FeatureCode.BASIC_SEO_TOOLS)

        target_date = target_date or timezone.localdate()
        daily_limit = plan.basic_tool_daily_limit

        with transaction.atomic():
            # Acquire row-level lock or create clean entry for today
            usage, _ = ToolUsage.objects.select_for_update().get_or_create(
                user=user,
                tool_code=tool_code,
                usage_date=target_date,
                defaults={'count': 0}
            )

            # Check quota if not unlimited
            if daily_limit > 0 and usage.count >= daily_limit:
                raise PlanLimitReachedException(
                    resource=f"tool_daily_limit:{tool_code}",
                    current=usage.count,
                    limit=daily_limit,
                    plan_code=plan.code,
                    message=f"You have reached your daily limit of {daily_limit} runs for {tool_code} on the {plan.name} plan. Limit resets tomorrow."
                )

            # Atomic increment
            ToolUsage.objects.filter(pk=usage.pk).update(
                count=F('count') + 1,
                updated_at=timezone.now()
            )
            usage.refresh_from_db()
            return usage


def get_user_subscription_summary(user) -> Dict[str, Any]:
    """
    Produce a full serializable snapshot of the user's active plan, quotas, and current consumption.
    """
    sub = SubscriptionService.get_or_create_user_subscription(user)
    plan = sub.plan

    from apps.projects.models import Project
    from apps.seo.models import Keyword

    proj_count = Project.objects.filter(owner=user).count()
    kw_count = Keyword.objects.filter(project__owner=user).count()

    today = timezone.localdate()
    today_usages = list(
        ToolUsage.objects.filter(user=user, usage_date=today)
        .values('tool_code', 'count')
    )

    return {
        'plan': {
            'code': plan.code,
            'name': plan.name,
            'monthly_price': str(plan.monthly_price),
            'currency': plan.currency,
            'basic_tool_daily_limit': plan.basic_tool_daily_limit,
            'is_tool_unlimited': plan.is_tool_unlimited,
            'features': plan.features or [],
        },
        'subscription': {
            'status': sub.status,
            'started_at': sub.started_at,
            'current_period_end': sub.current_period_end,
            'is_active': sub.is_active_subscription,
        },
        'usage': {
            'projects': {
                'current': proj_count,
                'limit': plan.max_projects,
                'remaining': max(0, plan.max_projects - proj_count),
            },
            'keywords': {
                'current': kw_count,
                'limit': plan.max_keywords,
                'remaining': max(0, plan.max_keywords - kw_count),
            },
            'tools_today': today_usages,
        }
    }
