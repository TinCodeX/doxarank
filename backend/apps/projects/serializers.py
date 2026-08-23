from rest_framework import serializers
from .models import Project
from urllib.parse import urlparse


class ProjectSerializer(serializers.ModelSerializer):
    """
    Serializer for the Project model.
    Exposes project details while keeping ownership read-only and automatically assigned.
    """
    owner_email = serializers.EmailField(source='owner.email', read_only=True)

    class Meta:
        model = Project
        fields = (
            'id',
            'name',
            'website_url',
            'owner_email',
            'created_at',
            'updated_at'
        )
        read_only_fields = ('id', 'owner_email', 'created_at', 'updated_at')

    def validate_name(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Project name cannot be empty.")
        if len(trimmed) < 2:
            raise serializers.ValidationError("Project name must be at least 2 characters.")
        return trimmed

    def validate_website_url(self, value):
        trimmed = value.strip()
        parsed = urlparse(trimmed)
        if not parsed.scheme or parsed.scheme not in ('http', 'https'):
            raise serializers.ValidationError("Website URL must start with http:// or https://")
        if not parsed.netloc:
            raise serializers.ValidationError("Please provide a valid domain name (e.g., https://example.com).")
        return trimmed
