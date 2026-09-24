import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Subscription, Plan, PlanCode, SubscriptionStatus

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_default_user_subscription(sender, instance, created, **kwargs):
    """
    Automatically attach a FREE subscription when a new user registers.
    """
    if created:
        try:
            free_plan = Plan.objects.filter(code=PlanCode.FREE).first()
            if not free_plan:
                from .services import SubscriptionService
                plans = SubscriptionService.bootstrap_default_plans()
                free_plan = plans.get(PlanCode.FREE)

            if free_plan:
                Subscription.objects.get_or_create(
                    user=instance,
                    defaults={
                        'plan': free_plan,
                        'status': SubscriptionStatus.ACTIVE,
                    }
                )
        except Exception as exc:
            logger.warning(f"Could not auto-create subscription for user {instance.email}: {exc}")
