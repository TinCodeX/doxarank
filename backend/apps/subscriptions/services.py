import logging
import uuid
from decimal import Decimal
from datetime import date, timedelta
from typing import Tuple, Dict, Any, Optional
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    Plan,
    Subscription,
    ToolUsage,
    PaymentTransaction,
    PlanCode,
    SubscriptionStatus,
    PaymentStatus,
    FeatureCode,
    PLAN_DEFAULTS,
)
from .exceptions import (
    PlanLimitReachedException,
    FeatureNotEntitledException,
    InvalidPlanException,
    PaymentTransactionNotFoundException,
)
from .providers import get_payment_provider

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
            sub = Subscription.objects.select_related('plan').get(user=user)
            try:
                user.subscription = sub
            except Exception:
                pass
            return sub
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
        Return the user's active Plan object, falling back to FREE if not authenticated
        or if their current subscription period has expired.
        """
        if not user or not user.is_authenticated:
            free_plan = Plan.objects.filter(code=PlanCode.FREE).first()
            if not free_plan:
                plans = cls.bootstrap_default_plans()
                free_plan = plans[PlanCode.FREE]
            return free_plan

        sub = cls.get_or_create_user_subscription(user)
        if not sub.is_active_subscription:
            free_plan = Plan.objects.filter(code=PlanCode.FREE).first()
            if not free_plan:
                plans = cls.bootstrap_default_plans()
                free_plan = plans[PlanCode.FREE]
            return free_plan

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
    plan = SubscriptionService.get_user_plan(user)

    from apps.projects.models import Project
    from apps.seo.models import Keyword

    proj_count = Project.objects.filter(owner=user).count()
    kw_count = Keyword.objects.filter(project__owner=user).count()

    today = timezone.localdate()
    today_usages = list(
        ToolUsage.objects.filter(user=user, usage_date=today)
        .values('tool_code', 'count')
    )

    latest_tx = PaymentTransaction.objects.filter(user=user).order_by('-created_at').first()

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
        },
        'latest_payment': {
            'id': latest_tx.id,
            'checkout_reference': latest_tx.checkout_reference,
            'status': latest_tx.status,
            'amount': str(latest_tx.amount),
            'currency': latest_tx.currency,
            'paid_at': latest_tx.paid_at,
            'plan_code': latest_tx.plan.code,
            'checkout_url': latest_tx.checkout_url,
        } if latest_tx else None
    }


class PaymentService:
    """
    Core orchestration service for Doxa Payments checkout, verification,
    webhook processing, and idempotent subscription lifecycle transitions.
    """

    PURCHASABLE_PLANS = [PlanCode.STARTER, PlanCode.AGENCY]

    @classmethod
    def create_checkout_session(
        cls,
        user,
        plan_code: str,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
        provider_name: str = 'doxa'
    ) -> PaymentTransaction:
        """
        Validate plan, create a pending payment transaction, invoke provider checkout,
        and return the transaction record containing the provider checkout URL.
        Server-side pricing is strictly enforced.
        """
        if not user or not user.is_authenticated:
            raise ValueError("Authenticated user required for checkout.")

        plan_code = (plan_code or '').strip().upper()

        if plan_code == PlanCode.FREE:
            raise InvalidPlanException(
                "The Free plan does not require payment. You already have access to the Free tier."
            )

        if plan_code not in cls.PURCHASABLE_PLANS:
            raise InvalidPlanException(
                f"Plan '{plan_code}' is not valid for purchase. Purchasable plans are: {', '.join(cls.PURCHASABLE_PLANS)}."
            )

        plan = Plan.objects.filter(code=plan_code, is_active=True).first()
        if not plan:
            plans = SubscriptionService.bootstrap_default_plans()
            plan = plans.get(plan_code)

        if not plan:
            raise InvalidPlanException(f"Plan with code '{plan_code}' not found.")

        # Server-side authoritative pricing (frontend price input is ignored)
        amount = plan.monthly_price
        currency = plan.currency

        # Generate unique internal tracking reference
        checkout_ref = f"doxa_chk_{uuid.uuid4().hex[:16]}"

        with transaction.atomic():
            tx = PaymentTransaction.objects.create(
                user=user,
                plan=plan,
                amount=amount,
                currency=currency,
                provider=provider_name,
                checkout_reference=checkout_ref,
                status=PaymentStatus.PENDING,
                metadata={
                    'plan_name': plan.name,
                    'initiated_by': user.email,
                }
            )

        # Connect to provider abstraction
        provider = get_payment_provider(provider_name)
        checkout_res = provider.create_checkout(
            transaction=tx,
            return_url=return_url,
            cancel_url=cancel_url
        )

        tx.checkout_url = checkout_res.checkout_url
        if checkout_res.metadata:
            tx.metadata.update(checkout_res.metadata)
        tx.save(update_fields=['checkout_url', 'metadata', 'updated_at'])

        logger.info(
            f"Created pending checkout {tx.checkout_reference} for {user.email} (Plan: {plan.code}, Amount: {amount} {currency})"
        )
        return tx

    @classmethod
    def verify_and_process_payment(
        cls,
        transaction_id_or_ref,
        payload: Optional[Dict[str, Any]] = None,
        provider_name: Optional[str] = None
    ) -> PaymentTransaction:
        """
        Idempotent, concurrency-safe payment verification and subscription activation.
        Guarantees that duplicate callbacks, repeated webhooks, or repeated verifications
        do not re-activate or duplicate subscription extensions.
        """
        with transaction.atomic():
            # Query transaction with database lock
            query = PaymentTransaction.objects.select_for_update()
            if isinstance(transaction_id_or_ref, int) or (isinstance(transaction_id_or_ref, str) and transaction_id_or_ref.isdigit()):
                tx = query.filter(id=int(transaction_id_or_ref)).first()
            else:
                tx = query.filter(checkout_reference=str(transaction_id_or_ref)).first()

            if not tx:
                raise PaymentTransactionNotFoundException(
                    f"Payment transaction with identifier '{transaction_id_or_ref}' was not found."
                )

            # Idempotency check: if transaction has already succeeded, return immediately
            if tx.status == PaymentStatus.SUCCESS:
                logger.info(
                    f"Payment transaction {tx.checkout_reference} is already SUCCESS. Returning idempotently."
                )
                return tx

            provider = get_payment_provider(provider_name or tx.provider)
            verification = provider.verify_payment(tx, payload)

            # Security validation: amount check
            if verification.amount is not None:
                if Decimal(str(verification.amount)) != Decimal(str(tx.amount)):
                    tx.status = PaymentStatus.FAILED
                    tx.error_message = (
                        f"Amount mismatch security rejection: expected {tx.amount}, provider verified {verification.amount}"
                    )
                    tx.save(update_fields=['status', 'error_message', 'updated_at'])
                    logger.warning(
                        f"SECURITY ALERT: Amount mismatch on transaction {tx.checkout_reference}. Marked FAILED."
                    )
                    return tx

            # Security validation: currency check
            if verification.currency:
                if verification.currency.upper() != tx.currency.upper():
                    tx.status = PaymentStatus.FAILED
                    tx.error_message = (
                        f"Currency mismatch security rejection: expected {tx.currency}, provider verified {verification.currency}"
                    )
                    tx.save(update_fields=['status', 'error_message', 'updated_at'])
                    logger.warning(
                        f"SECURITY ALERT: Currency mismatch on transaction {tx.checkout_reference}. Marked FAILED."
                    )
                    return tx

            if verification.is_successful and verification.status == PaymentStatus.SUCCESS:
                tx.status = PaymentStatus.SUCCESS
                tx.paid_at = timezone.now()
                if verification.provider_transaction_id:
                    tx.provider_transaction_id = verification.provider_transaction_id
                if verification.metadata:
                    tx.metadata.update(verification.metadata)

                # Safe subscription transition & renewal calculation
                sub = SubscriptionService.get_or_create_user_subscription(tx.user)
                now = timezone.now()

                # If renewing an active subscription on the same plan, extend from existing period end
                if (
                    sub.plan_id == tx.plan_id
                    and sub.is_active_subscription
                    and sub.current_period_end
                    and sub.current_period_end > now
                ):
                    new_period_end = sub.current_period_end + timedelta(days=30)
                else:
                    new_period_end = now + timedelta(days=30)
                    sub.started_at = now

                sub.plan = tx.plan
                sub.status = SubscriptionStatus.ACTIVE
                sub.current_period_end = new_period_end
                sub.save(update_fields=['plan', 'status', 'started_at', 'current_period_end', 'updated_at'])

                tx.subscription = sub
                tx.save(update_fields=['status', 'paid_at', 'provider_transaction_id', 'metadata', 'subscription', 'updated_at'])
                logger.info(
                    f"Payment verified for {tx.user.email}: Plan {tx.plan.code} activated through {new_period_end}."
                )
            elif verification.status in (PaymentStatus.FAILED, PaymentStatus.CANCELLED):
                tx.status = verification.status
                tx.error_message = verification.error_message or 'Payment was declined or failed.'
                tx.save(update_fields=['status', 'error_message', 'updated_at'])
                logger.info(f"Payment transaction {tx.checkout_reference} marked as {tx.status}.")
            else:
                if verification.error_message:
                    tx.error_message = verification.error_message
                    tx.save(update_fields=['error_message', 'updated_at'])

            return tx

    @classmethod
    def handle_webhook(
        cls,
        provider_name: str,
        payload: Dict[str, Any],
        raw_body: bytes,
        headers: Dict[str, str]
    ) -> Tuple[PaymentTransaction, str]:
        """
        Verify incoming webhook signature and process payment idempotently.
        """
        provider = get_payment_provider(provider_name)
        verification = provider.handle_webhook(payload, raw_body, headers)

        ref = (
            payload.get('checkout_reference')
            or payload.get('reference')
            or payload.get('tx_ref')
        )
        if not ref:
            raise ValueError("Webhook missing transaction reference.")

        # Check transaction existence
        tx = PaymentTransaction.objects.filter(checkout_reference=ref).first()
        if not tx:
            raise PaymentTransactionNotFoundException(f"Transaction with reference '{ref}' not found.")

        if tx.status == PaymentStatus.SUCCESS:
            return tx, "already_processed"

        processed_tx = cls.verify_and_process_payment(
            transaction_id_or_ref=tx.id,
            payload=payload,
            provider_name=provider_name
        )
        return processed_tx, "processed"
