from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.generics import ListAPIView

from .models import Plan, SubscriptionStatus
from .serializers import PlanSerializer, ToolUsageCheckSerializer
from .services import (
    SubscriptionService,
    PlanEntitlementService,
    UsageLimitService,
    get_user_subscription_summary
)


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
            # check_and_record_tool_usage atomically checks and increments,
            # or raises PlanLimitReachedException if limit is reached
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

        # Allow staff or allow user self-assign in test/dev
        target_user = request.user
        sub = SubscriptionService.assign_plan(target_user, plan_code=plan_code)
        summary = get_user_subscription_summary(target_user)
        return Response(summary, status=status.HTTP_200_OK)
