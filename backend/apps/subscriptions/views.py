import logging
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.generics import ListAPIView

from .models import Plan, SubscriptionStatus, PaymentTransaction
from .serializers import (
    PlanSerializer,
    ToolUsageCheckSerializer,
    PaymentTransactionSerializer,
    CheckoutRequestSerializer,
    PaymentVerificationSerializer,
)
from .services import (
    SubscriptionService,
    PlanEntitlementService,
    UsageLimitService,
    PaymentService,
    get_user_subscription_summary,
)
from .exceptions import InvalidPlanException, PaymentTransactionNotFoundException
from .providers.doxa import WebhookSecurityError

logger = logging.getLogger(__name__)


class PlanListView(ListAPIView):
    """
    GET /api/subscriptions/plans/
    Public list of all available subscription plans and their feature matrices.
    """
    queryset = Plan.objects.filter(is_active=True).order_by('monthly_price')
    serializer_class = PlanSerializer
    permission_classes = [permissions.AllowAny]


class UserSubscriptionSummaryView(APIView):
    """
    GET /api/subscriptions/me/
    Returns the authenticated user's current subscription, plan, quotas, and remaining limits.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        summary = get_user_subscription_summary(request.user)
        return Response(summary, status=status.HTTP_200_OK)


class ToolUsageCheckView(APIView):
    """
    POST /api/subscriptions/tools/check/
    Check or atomically record execution of a tool against daily usage limits.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ToolUsageCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tool_code = serializer.validated_data['tool_code']
        record = serializer.validated_data.get('record', True)

        if record:
            usage = UsageLimitService.check_and_record_tool_usage(request.user, tool_code)
            plan = SubscriptionService.get_user_plan(request.user)
            return Response(
                {
                    'allowed': True,
                    'tool_code': tool_code,
                    'current_usage': usage.count,
                    'daily_limit': plan.basic_tool_daily_limit,
                    'is_unlimited': plan.is_tool_unlimited,
                    'message': 'Tool execution authorized and recorded.'
                },
                status=status.HTTP_200_OK
            )
        else:
            allowed, current_usage, daily_limit = UsageLimitService.can_use_tool(request.user, tool_code)
            return Response(
                {
                    'allowed': allowed,
                    'tool_code': tool_code,
                    'current_usage': current_usage,
                    'daily_limit': daily_limit,
                    'is_unlimited': (daily_limit == 0),
                },
                status=status.HTTP_200_OK
            )


class SubscriptionPlanAssignView(APIView):
    """
    POST /api/subscriptions/assign/
    Allows administrative staff (or user testing) to switch plans.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        plan_code = request.data.get('plan_code')
        if not plan_code:
            return Response({'detail': 'plan_code is required.'}, status=status.HTTP_400_BAD_REQUEST)

        target_user = request.user
        sub = SubscriptionService.assign_plan(target_user, plan_code=plan_code)
        summary = get_user_subscription_summary(target_user)
        return Response(summary, status=status.HTTP_200_OK)


class CheckoutView(APIView):
    """
    POST /api/subscriptions/checkout/
    Initiate a subscription payment session.
    Server-side price enforcement ensures the frontend cannot falsify amounts.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan_code = serializer.validated_data['plan_code']
        return_url = serializer.validated_data.get('return_url')
        cancel_url = serializer.validated_data.get('cancel_url')
        provider = serializer.validated_data.get('provider', 'doxa')

        tx = PaymentService.create_checkout_session(
            user=request.user,
            plan_code=plan_code,
            return_url=return_url,
            cancel_url=cancel_url,
            provider_name=provider
        )

        response_data = PaymentTransactionSerializer(tx).data
        return Response(response_data, status=status.HTTP_201_CREATED)


class PaymentDetailView(APIView):
    """
    GET /api/subscriptions/payments/<id>/
    Tenant-isolated inspection of a payment transaction record.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk_or_ref):
        if str(pk_or_ref).isdigit():
            tx = PaymentTransaction.objects.filter(id=int(pk_or_ref)).first()
        else:
            tx = PaymentTransaction.objects.filter(checkout_reference=str(pk_or_ref)).first()

        if not tx:
            return Response(
                {'detail': 'Payment transaction not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Enforce tenant isolation
        if tx.user_id != request.user.id:
            return Response(
                {'detail': 'Payment transaction not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = PaymentTransactionSerializer(tx)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PaymentVerifyView(APIView):
    """
    POST /api/subscriptions/payments/<id>/verify/
    Verifies payment with external provider or confirms callback.
    Idempotent and concurrency-safe.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk_or_ref):
        if str(pk_or_ref).isdigit():
            tx = PaymentTransaction.objects.filter(id=int(pk_or_ref)).first()
        else:
            tx = PaymentTransaction.objects.filter(checkout_reference=str(pk_or_ref)).first()

        if not tx:
            return Response(
                {'detail': 'Payment transaction not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Enforce tenant isolation
        if tx.user_id != request.user.id:
            return Response(
                {'detail': 'Payment transaction not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = PaymentVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data.get('payload', {})

        processed_tx = PaymentService.verify_and_process_payment(
            transaction_id_or_ref=tx.id,
            payload=payload
        )

        return Response(
            PaymentTransactionSerializer(processed_tx).data,
            status=status.HTTP_200_OK
        )


class PaymentListView(APIView):
    """
    GET /api/subscriptions/payments/
    Returns the authenticated user's recent payment transactions history.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        transactions = PaymentTransaction.objects.filter(
            user=request.user
        ).order_by('-created_at')[:30]

        serializer = PaymentTransactionSerializer(transactions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DoxaWebhookView(APIView):
    """
    POST /api/subscriptions/webhooks/doxa/
    Public receiver endpoint for Doxa Payments gateway webhook callbacks.
    Security: HMAC-SHA256 signature verification, strict tenant and price validation.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        raw_body = request.body
        headers = {k: v for k, v in request.META.items() if isinstance(v, str)}
        payload = request.data

        if not isinstance(payload, dict):
            return Response(
                {'error': 'Invalid JSON webhook payload.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            tx, status_str = PaymentService.handle_webhook(
                provider_name='doxa',
                payload=payload,
                raw_body=raw_body,
                headers=headers
            )
            return Response(
                {
                    'status': 'success',
                    'reference': tx.checkout_reference,
                    'transaction_status': tx.status,
                    'result': status_str,
                },
                status=status.HTTP_200_OK
            )
        except WebhookSecurityError as sec_err:
            logger.warning(f"Webhook security rejection: {sec_err}")
            return Response(
                {'error': str(sec_err)},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except (PaymentTransactionNotFoundException, ValueError) as val_err:
            logger.warning(f"Webhook data validation rejection: {val_err}")
            return Response(
                {'error': str(val_err)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as exc:
            logger.error(f"Unexpected error processing Doxa Payments webhook: {exc}", exc_info=True)
            return Response(
                {'error': 'Internal webhook processing error.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

