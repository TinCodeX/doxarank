from django.contrib import admin
from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'website_url', 'owner', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('name', 'website_url', 'owner__email', 'owner__first_name', 'owner__last_name')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
