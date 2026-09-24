from rest_framework import serializers
from .models import Plan, Subscription, ToolUsage


class PlanSerializer(serializers.ModelSerializer):
    """
    Public representation of available DoxaRank subscription plans.
    """
    is_tool_unlimited = serializers.BooleanField(read_only=True)

    class Meta:
        model = Plan
        fields = (
            'id',
            'code',
            'name',
            'monthly_price',
            'currency',
            'max_projects',
            'max_keywords',
            'basic_tool_daily_limit',
            'is_tool_unlimited',
            'features',
            'is_active',
        )
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer representing a user's subscription record.
    """
    plan = PlanSerializer(read_only=True)
    is_active_subscription = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = (
            'id',
            'plan',
            'status',
            'started_at',
            'current_period_end',
            'is_active_subscription',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class ToolUsageCheckSerializer(serializers.Serializer):
    """
    Payload to check or record an execution for a tool.
    """
    tool_code = serializers.CharField(max_length=100, required=True)
    record = serializers.BooleanField(default=True, help_text="Whether to atomically record the usage or just check quota")
