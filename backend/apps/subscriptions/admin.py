from django.contrib import admin
from .models import Plan, Subscription, ToolUsage


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'name',
        'monthly_price',
        'currency',
        'max_projects',
        'max_keywords',
        'basic_tool_daily_limit',
        'is_active',
        'created_at',
    )
    list_filter = ('is_active', 'currency')
    search_fields = ('code', 'name')
    ordering = ('monthly_price', 'code')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'plan',
        'status',
        'started_at',
        'current_period_end',
        'is_active_subscription',
        'created_at',
    )
    list_filter = ('status', 'plan')
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
    ordering = ('-created_at',)
    autocomplete_fields = ('user', 'plan')


@admin.register(ToolUsage)
class ToolUsageAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'tool_code',
        'usage_date',
        'count',
        'updated_at',
    )
    list_filter = ('tool_code', 'usage_date')
    search_fields = ('user__email', 'tool_code')
    ordering = ('-usage_date', '-count')
    readonly_fields = ('created_at', 'updated_at')
