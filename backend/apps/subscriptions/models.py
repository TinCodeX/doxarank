from typing import List
from django.db import models
from django.conf import settings
from django.utils import timezone


class PlanCode(models.TextChoices):
    FREE = 'FREE', 'Free'
    STARTER = 'STARTER', 'Starter'
    AGENCY = 'AGENCY', 'Agency'


class SubscriptionStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    TRIALING = 'trialing', 'Trialing'
    PAST_DUE = 'past_due', 'Past Due'
    CANCELED = 'canceled', 'Canceled'
    EXPIRED = 'expired', 'Expired'


class FeatureCode(models.TextChoices):
    BASIC_SEO_TOOLS = 'BASIC_SEO_TOOLS', 'Basic SEO Tools'
    RANK_TRACKING = 'RANK_TRACKING', 'Rank Tracking'
    GSC = 'GSC', 'Google Search Console'
    GA4 = 'GA4', 'Google Analytics 4'
    CLARITY = 'CLARITY', 'Microsoft Clarity'
    GTM = 'GTM', 'Google Tag Manager'
    TECHNICAL_CRAWLER = 'TECHNICAL_CRAWLER', 'Technical Site Crawler'
    COMPETITOR_SNAPSHOTS = 'COMPETITOR_SNAPSHOTS', 'Competitor Snapshots'
    WHITE_LABEL_REPORTS = 'WHITE_LABEL_REPORTS', 'White-Label Reports'


# Default feature bundle definitions for bootstrap and reference
PLAN_DEFAULTS = {
    PlanCode.FREE: {
        'name': 'Free',
        'monthly_price': 0.00,
        'currency': 'ETB',
        'max_projects': 1,
        'max_keywords': 3,
        'basic_tool_daily_limit': 5,
        'features': [
            FeatureCode.BASIC_SEO_TOOLS,
        ],
    },
    PlanCode.STARTER: {
        'name': 'Starter',
        'monthly_price': 1500.00,
        'currency': 'ETB',
        'max_projects': 3,
        'max_keywords': 50,
        'basic_tool_daily_limit': 0,  # 0 indicates unlimited daily tool usage
        'features': [
            FeatureCode.BASIC_SEO_TOOLS,
            FeatureCode.RANK_TRACKING,
            FeatureCode.GSC,
            FeatureCode.GA4,
            FeatureCode.CLARITY,
            FeatureCode.GTM,
            FeatureCode.TECHNICAL_CRAWLER,
        ],
    },
    PlanCode.AGENCY: {
        'name': 'Agency',
        'monthly_price': 6000.00,
        'currency': 'ETB',
        'max_projects': 20,
        'max_keywords': 500,
        'basic_tool_daily_limit': 0,  # 0 indicates unlimited daily tool usage
        'features': [
            FeatureCode.BASIC_SEO_TOOLS,
            FeatureCode.RANK_TRACKING,
            FeatureCode.GSC,
            FeatureCode.GA4,
            FeatureCode.CLARITY,
            FeatureCode.GTM,
            FeatureCode.TECHNICAL_CRAWLER,
            FeatureCode.COMPETITOR_SNAPSHOTS,
            FeatureCode.WHITE_LABEL_REPORTS,
        ],
    },
}


class Plan(models.Model):
    """
    Plan definition model representing a DoxaRank subscription tier.
    Stores pricing, quotas, and feature flags without hardcoded business logic.
    """
    code = models.CharField(
        max_length=50,
        unique=True,
        choices=PlanCode.choices,
        db_index=True,
        help_text='Unique identifier code for the plan (e.g. FREE, STARTER, AGENCY).'
    )
    name = models.CharField(
        max_length=100,
        help_text='User-facing display name for the plan.'
    )
    monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text='Monthly price for the plan (e.g. 0, 1500, 6000).'
    )
    currency = models.CharField(
        max_length=10,
        default='ETB',
        help_text='Currency code (default ETB).'
    )
    max_projects = models.PositiveIntegerField(
        default=1,
        help_text='Maximum allowed websites/projects a user on this plan can track.'
    )
    max_keywords = models.PositiveIntegerField(
        default=3,
        help_text='Maximum total keywords across all projects a user on this plan can track.'
    )
    basic_tool_daily_limit = models.PositiveIntegerField(
        default=5,
        help_text='Daily execution limit for basic SEO tools. 0 represents unlimited daily usage.'
    )
    features = models.JSONField(
        default=list,
        help_text='List of FeatureCode strings entitled for users on this plan.'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this plan is currently active and available.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions_plan'
        verbose_name = 'plan'
        verbose_name_plural = 'plans'
        ordering = ['monthly_price', 'code']

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.monthly_price} {self.currency}/mo"

    def has_feature(self, feature_code: str) -> bool:
        """Return True if this plan includes the requested feature entitlement."""
        return feature_code in (self.features or [])

    @property
    def is_tool_unlimited(self) -> bool:
        """Return True if basic tools have no daily quota restriction."""
        return self.basic_tool_daily_limit == 0


class Subscription(models.Model):
    """
    Subscription model linking a User to an active Plan tier.
    Tracks validity, periods, and status.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription',
        help_text='The user who owns this subscription.'
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name='subscriptions',
        help_text='The active plan tier for this user.'
    )
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
        db_index=True,
        help_text='Current billing/subscription status.'
    )
    started_at = models.DateTimeField(
        default=timezone.now,
        help_text='Timestamp when the subscription period began.'
    )
    current_period_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp when the current billing period expires (null for lifetime/free).'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions_subscription'
        verbose_name = 'subscription'
        verbose_name_plural = 'subscriptions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} -> {self.plan.name} [{self.status}]"

    @property
    def is_active_subscription(self) -> bool:
        """
        Check if the subscription is currently active and within its valid time window.
        """
        if self.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
            return False
        if self.current_period_end and self.current_period_end < timezone.now():
            return False
        return True


class ToolUsage(models.Model):
    """
    Tracks daily tool executions per user to enforce fair-use and free-tier daily quotas.
    Resets automatically on a new calendar date.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tool_usages',
        help_text='The user who performed the tool action.'
    )
    tool_code = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Identifier code of the tool (e.g. meta_generator, sitemap_validator).'
    )
    usage_date = models.DateField(
        default=timezone.localdate,
        db_index=True,
        help_text='Calendar date of usage (UTC/local date).'
    )
    count = models.PositiveIntegerField(
        default=0,
        help_text='Number of times the tool was invoked on this date.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions_tool_usage'
        verbose_name = 'tool usage'
        verbose_name_plural = 'tool usages'
        ordering = ['-usage_date', '-count']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'tool_code', 'usage_date'],
                name='unique_user_tool_daily_usage'
            )
        ]

    def __str__(self):
        return f"{self.user.email} - {self.tool_code} ({self.usage_date}): {self.count}"
