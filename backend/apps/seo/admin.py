from django.contrib import admin
from .models import (
    Keyword, KeywordRanking, SiteAudit, AuditIssue,
    SearchConsoleConnection, SearchAnalyticsData,
    SEOInsight, SEORecommendation
)



@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'keyword',
        'project',
        'search_engine',
        'country',
        'language',
        'device',
        'is_active',
        'created_at'
    )
    list_filter = (
        'search_engine',
        'country',
        'language',
        'device',
        'is_active',
        'created_at'
    )
    search_fields = (
        'keyword',
        'project__name',
        'project__website_url',
        'project__owner__email'
    )
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(KeywordRanking)
class KeywordRankingAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'keyword',
        'position',
        'ranking_url',
        'search_engine',
        'country',
        'language',
        'device',
        'recorded_at',
        'created_at'
    )
    list_filter = (
        'search_engine',
        'country',
        'language',
        'device',
        'recorded_at',
        'created_at'
    )
    search_fields = (
        'keyword__keyword',
        'keyword__project__name',
        'keyword__project__owner__email',
        'ranking_url'
    )
    readonly_fields = ('created_at',)
    ordering = ('-recorded_at',)


@admin.register(SiteAudit)
class SiteAuditAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'project',
        'status',
        'score',
        'created_at',
        'completed_at'
    )
    list_filter = (
        'status',
        'created_at',
        'completed_at'
    )
    search_fields = (
        'project__name',
        'project__website_url',
        'project__owner__email',
        'error_message'
    )
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(AuditIssue)
class AuditIssueAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'audit',
        'severity',
        'issue_type',
        'title',
        'created_at'
    )
    list_filter = (
        'severity',
        'issue_type',
        'created_at'
    )
    search_fields = (
        'title',
        'description',
        'page_url',
        'recommendation',
        'audit__project__name',
        'audit__project__owner__email'
    )
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(SearchConsoleConnection)
class SearchConsoleConnectionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'project',
        'property_url',
        'permission_level',
        'is_connected',
        'sync_status',
        'last_synced_at',
        'created_at'
    )
    list_filter = (
        'is_connected',
        'sync_status',
        'permission_level',
        'created_at',
        'last_synced_at'
    )
    search_fields = (
        'property_url',
        'project__name',
        'project__website_url',
        'project__owner__email',
        'error_message'
    )
    readonly_fields = ('connected_at', 'created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(SearchAnalyticsData)
class SearchAnalyticsDataAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'connection',
        'date',
        'query',
        'page',
        'country',
        'device',
        'search_appearance',
        'clicks',
        'impressions',
        'ctr',
        'position',
        'created_at'
    )
    list_filter = (
        'date',
        'country',
        'device',
        'search_appearance',
        'connection__project',
        'created_at'
    )
    search_fields = (
        'query',
        'page',
        'country',
        'device',
        'search_appearance',
        'connection__property_url',
        'connection__project__name',
        'connection__project__owner__email'
    )
    date_hierarchy = 'date'
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-date', '-clicks')


@admin.register(SEOInsight)
class SEOInsightAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'project',
        'severity',
        'insight_type',
        'title',
        'status',
        'source',
        'related_keyword',
        'detected_at'
    )
    list_filter = (
        'severity',
        'status',
        'source',
        'insight_type',
        'detected_at',
        'created_at'
    )
    search_fields = (
        'title',
        'description',
        'recommendation',
        'project__name',
        'project__owner__email',
        'related_keyword__keyword',
        'related_url'
    )
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-detected_at',)


@admin.register(SEORecommendation)
class SEORecommendationAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'project',
        'priority',
        'recommendation_type',
        'title',
        'status',
        'affected_keyword',
        'created_at'
    )
    list_filter = (
        'priority',
        'status',
        'recommendation_type',
        'created_at'
    )
    search_fields = (
        'title',
        'summary',
        'explanation',
        'recommended_action',
        'expected_impact',
        'project__name',
        'project__owner__email',
        'affected_keyword',
        'affected_url'
    )
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)





