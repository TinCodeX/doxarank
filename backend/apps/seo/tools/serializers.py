from rest_framework import serializers
from .meta import SUPPORTED_ROBOTS_DIRECTIVES
from .schema import SUPPORTED_SCHEMA_TYPES
from .social import SUPPORTED_OG_TYPES, SUPPORTED_TWITTER_CARDS


class MetaTagInputSerializer(serializers.Serializer):
    title = serializers.CharField(
        required=True,
        max_length=500,
        trim_whitespace=True,
        error_messages={'required': 'Page title is required.', 'blank': 'Page title cannot be blank.'}
    )
    description = serializers.CharField(
        required=True,
        max_length=2000,
        trim_whitespace=True,
        error_messages={'required': 'Meta description is required.', 'blank': 'Meta description cannot be blank.'}
    )
    canonical_url = serializers.URLField(
        required=False,
        allow_blank=True,
        max_length=1000,
        error_messages={'invalid': 'Canonical URL must be a valid URL (e.g. https://example.com/page).'}
    )
    robots = serializers.ChoiceField(
        choices=SUPPORTED_ROBOTS_DIRECTIVES,
        default='index, follow',
        error_messages={'invalid_choice': f'Invalid robots directive. Supported: {", ".join(SUPPORTED_ROBOTS_DIRECTIVES)}'}
    )
    author = serializers.CharField(required=False, allow_blank=True, max_length=200)
    keywords = serializers.CharField(required=False, allow_blank=True, max_length=500)
    viewport = serializers.CharField(required=False, default='width=device-width, initial-scale=1.0', max_length=200)


class SchemaInputSerializer(serializers.Serializer):
    schema_type = serializers.ChoiceField(
        choices=SUPPORTED_SCHEMA_TYPES,
        required=True,
        error_messages={'invalid_choice': f'Invalid schema type. Supported: {", ".join(SUPPORTED_SCHEMA_TYPES)}'}
    )
    data = serializers.DictField(
        required=True,
        error_messages={'required': 'Schema data object is required.', 'null': 'Schema data cannot be null.'}
    )


class SocialPreviewInputSerializer(serializers.Serializer):
    title = serializers.CharField(
        required=True,
        max_length=500,
        trim_whitespace=True,
        error_messages={'required': 'Title is required for social preview.', 'blank': 'Title cannot be blank.'}
    )
    description = serializers.CharField(
        required=True,
        max_length=2000,
        trim_whitespace=True,
        error_messages={'required': 'Description is required for social preview.', 'blank': 'Description cannot be blank.'}
    )
    url = serializers.URLField(
        required=False,
        allow_blank=True,
        max_length=1000,
        error_messages={'invalid': 'Target URL must be a valid HTTP or HTTPS URL.'}
    )
    image_url = serializers.URLField(
        required=False,
        allow_blank=True,
        max_length=1000,
        error_messages={'invalid': 'Image URL must be a valid HTTP or HTTPS URL.'}
    )
    site_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    og_type = serializers.ChoiceField(
        choices=SUPPORTED_OG_TYPES,
        default='website',
        error_messages={'invalid_choice': f'Invalid og_type. Supported: {", ".join(SUPPORTED_OG_TYPES)}'}
    )
    twitter_card = serializers.ChoiceField(
        choices=SUPPORTED_TWITTER_CARDS,
        default='summary_large_image',
        error_messages={'invalid_choice': f'Invalid twitter_card. Supported: {", ".join(SUPPORTED_TWITTER_CARDS)}'}
    )
    twitter_site = serializers.CharField(required=False, allow_blank=True, max_length=100)
    twitter_creator = serializers.CharField(required=False, allow_blank=True, max_length=100)
