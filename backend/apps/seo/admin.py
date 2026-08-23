from django.contrib import admin
from .models import Keyword


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
