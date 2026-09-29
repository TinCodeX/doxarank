import logging
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import Subscription, SubscriptionStatus, Plan, PlanCode

logger = logging.getLogger(__name__)


@shared_task(name='apps.subscriptions.tasks.expire_subscriptions')
def expire_subscriptions() -> str:
    """
    Periodic Celery task to inspect paid subscriptions that have reached or passed
    their current_period_end timestamp.

    Safely transitions expired subscriptions and restores users to the default
    FREE tier entitlement.
    Preserves perpetual / free accounts (where current_period_end is None).
    """
    now = timezone.now()
    # Only target subscriptions with an explicit end date in the past
    expired_subs = Subscription.objects.filter(
        status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING],
        current_period_end__isnull=False,
        current_period_end__lt=now
    ).exclude(plan__code=PlanCode.FREE)

    free_plan = Plan.objects.filter(code=PlanCode.FREE).first()
    if not free_plan:
        from .services import SubscriptionService
        plans = SubscriptionService.bootstrap_default_plans()
        free_plan = plans[PlanCode.FREE]

    processed_count = 0
    for sub in expired_subs:
        with transaction.atomic():
            old_plan_code = sub.plan.code
            user_email = sub.user.email

            # Restore user to Free tier entitlements
            sub.plan = free_plan
            sub.status = SubscriptionStatus.EXPIRED
            sub.current_period_end = None
            sub.save(update_fields=['plan', 'status', 'current_period_end', 'updated_at'])

            processed_count += 1
            logger.info(
                f"Subscription expired for {user_email}: downgraded from {old_plan_code} to {PlanCode.FREE}."
            )

    msg = f"Processed {processed_count} expired subscription(s)."
    logger.info(msg)
    return msg
