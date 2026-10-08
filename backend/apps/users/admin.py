from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, ContactMessage


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active', 'created_at')
    list_filter = ('is_staff', 'is_active', 'created_at')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-created_at',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    readonly_fields = ('created_at', 'updated_at', 'last_login')

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password', 'first_name', 'last_name', 'is_staff', 'is_active'),
        }),
    )


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'domain', 'email_sent', 'is_resolved', 'created_at')
    list_filter = ('email_sent', 'is_resolved', 'created_at')
    search_fields = ('name', 'email', 'domain', 'message')
    readonly_fields = ('created_at', 'updated_at', 'ip_address', 'user_agent', 'email_sent', 'email_error')
    ordering = ('-created_at',)
    actions = ['mark_resolved', 'mark_unresolved']

    @admin.action(description='Mark selected messages as resolved')
    def mark_resolved(self, request, queryset):
        queryset.update(is_resolved=True)

    @admin.action(description='Mark selected messages as unresolved')
    def mark_unresolved(self, request, queryset):
        queryset.update(is_resolved=False)

