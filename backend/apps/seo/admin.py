from django.contrib import admin
from .models import Keyword, KeywordRanking


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
