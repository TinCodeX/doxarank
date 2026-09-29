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


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """
    Serializer representing a payment transaction record.
    Security: internal payment provider credentials and secret keys are never exposed.
    """
    plan = PlanSerializer(read_only=True)
    plan_code = serializers.CharField(source='plan.code', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)

    class Meta:
        from .models import PaymentTransaction
        model = PaymentTransaction
        fields = (
            'id',
            'checkout_reference',
            'plan',
            'plan_code',
            'plan_name',
            'amount',
            'currency',
            'provider',
            'provider_transaction_id',
            'status',
            'checkout_url',
            'metadata',
            'error_message',
            'paid_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class CheckoutRequestSerializer(serializers.Serializer):
    """
    Input payload for initiating a subscription checkout.
    """
    plan_code = serializers.CharField(max_length=50, required=True)
    return_url = serializers.CharField(required=False, allow_blank=True, default='')
    cancel_url = serializers.CharField(required=False, allow_blank=True, default='')
    provider = serializers.CharField(max_length=50, required=False, default='doxa')


class PaymentVerificationSerializer(serializers.Serializer):
    """
    Input payload for triggering manual or client-assisted payment verification.
    """
    payload = serializers.DictField(required=False, default=dict)

