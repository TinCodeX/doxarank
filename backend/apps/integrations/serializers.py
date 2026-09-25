from rest_framework import serializers
from apps.integrations.models import IntegrationConnection


class IntegrationStatusSerializer(serializers.ModelSerializer):
    """
    Public representation of an integration connection.
    Never exposes plaintext or encrypted tokens.
    """
    has_valid_credentials = serializers.BooleanField(read_only=True)
    has_analytics_scope = serializers.BooleanField(read_only=True)

    class Meta:
        model = IntegrationConnection
        fields = [
            'id',
            'provider',
            'status',
            'account_email',
            'account_name',
            'account_id',
            'scopes',
            'connected_at',
            'updated_at',
            'token_expires_at',
            'has_valid_credentials',
            'has_analytics_scope',
        ]
        read_only_fields = fields


class SearchConsolePropertySerializer(serializers.Serializer):
    """
    Normalized Google Search Console verified property representation.
    """
    site_url = serializers.CharField()
    permission_level = serializers.CharField(default='siteOwner')


class SearchConsoleAssociateSerializer(serializers.Serializer):
    """
    Payload for associating a verified GSC property with a DoxaRank project.
    """
    project_id = serializers.IntegerField(required=True)
    site_url = serializers.CharField(required=True, max_length=500)
    permission_level = serializers.CharField(required=False, default='siteOwner', max_length=50)


class GA4PropertySerializer(serializers.Serializer):
    """
    Normalized Google Analytics 4 (GA4) property representation.
    """
    property_id = serializers.CharField()
    display_name = serializers.CharField()
    property_type = serializers.CharField(default='GA4')


class GA4AssociateSerializer(serializers.Serializer):
    """
    Payload for associating a discovered GA4 property with a DoxaRank project.
    """
    project_id = serializers.IntegerField(required=True)
    property_id = serializers.CharField(required=True, max_length=100)
    display_name = serializers.CharField(required=False, allow_blank=True, default='')


class OAuthCallbackRequestSerializer(serializers.Serializer):
    """
    Incoming parameters for the OAuth callback endpoint.
    """
    code = serializers.CharField(required=False, allow_blank=True, default='')
    state = serializers.CharField(required=False, allow_blank=True, default='')
    error = serializers.CharField(required=False, allow_blank=True, default='')
    error_description = serializers.CharField(required=False, allow_blank=True, default='')
    redirect_uri = serializers.CharField(required=False, allow_blank=True, default='')
