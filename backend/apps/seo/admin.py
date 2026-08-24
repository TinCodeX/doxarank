from django.contrib import admin
from .models import Keyword, KeywordRanking, SiteAudit, AuditIssue



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

