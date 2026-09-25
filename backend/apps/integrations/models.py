from typing import Optional
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.seo.services.encryption import encrypt_token, decrypt_token


class IntegrationProvider(models.TextChoices):
    GOOGLE = 'google', 'Google'
    MICROSOFT = 'microsoft', 'Microsoft'


class IntegrationStatus(models.TextChoices):
    CONNECTED = 'connected', 'Connected'
    DISCONNECTED = 'disconnected', 'Disconnected'
    EXPIRED = 'expired', 'Expired'
    ERROR = 'error', 'Error'


class IntegrationConnection(models.Model):
    """
    Stores authenticated third-party provider accounts (e.g. Google, Microsoft)
    connected to a specific DoxaRank tenant user.
    
    Tokens are symmetrically encrypted at rest using AES-128 via Fernet.
    Tokens are never logged or exposed in raw form through API serializers.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='integration_connections',
        help_text='The DoxaRank user who owns this provider connection.'
    )
    provider = models.CharField(
        max_length=50,
        choices=IntegrationProvider.choices,
        default=IntegrationProvider.GOOGLE,
        help_text='Third-party identity or service provider.'
    )
    status = models.CharField(
        max_length=30,
        choices=IntegrationStatus.choices,
        default=IntegrationStatus.CONNECTED,
        help_text='Current operational status of this integration.'
    )
    account_email = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Email address of the connected third-party account.'
    )
    account_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Display name of the connected third-party account.'
    )
    account_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Unique identifier (e.g. Google subject ID) from provider.'
    )
    encrypted_access_token = models.TextField(
        blank=True,
        null=True,
        help_text='Encrypted OAuth2 access token.'
    )
    encrypted_refresh_token = models.TextField(
        blank=True,
        null=True,
        help_text='Encrypted OAuth2 refresh token.'
    )
    token_expires_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text='Expiration timestamp of the active access token.'
    )
    scopes = models.JSONField(
        default=list,
        blank=True,
        help_text='List of granted OAuth scopes.'
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Provider-specific metadata and settings.'
    )
    connected_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the connection was initially established.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp of last token refresh or connection update.'
    )

    class Meta:
        db_table = 'integrations_connections'
        verbose_name = 'Integration Connection'
        verbose_name_plural = 'Integration Connections'
        unique_together = ('user', 'provider')
        indexes = [
            models.Index(fields=['user', 'provider'], name='int_user_provider_idx'),
            models.Index(fields=['provider', 'status'], name='int_provider_status_idx'),
        ]
        ordering = ['-connected_at']

    def __str__(self):
        return f"{self.user.email} - {self.get_provider_display()} ({self.account_email or 'No email'})"

    def set_access_token(self, raw_token: Optional[str]) -> None:
        """Encrypt and store OAuth access token."""
        self.encrypted_access_token = encrypt_token(raw_token)

    def get_access_token(self) -> Optional[str]:
        """Decrypt and return plaintext OAuth access token."""
        return decrypt_token(self.encrypted_access_token)

    def set_refresh_token(self, raw_token: Optional[str]) -> None:
        """Encrypt and store OAuth refresh token."""
        self.encrypted_refresh_token = encrypt_token(raw_token)

    def get_refresh_token(self) -> Optional[str]:
        """Decrypt and return plaintext OAuth refresh token."""
        return decrypt_token(self.encrypted_refresh_token)

    def is_token_expired(self, buffer_seconds: int = 60) -> bool:
        """
        Check if the access token is expired or will expire within the buffer window.
        """
        if not self.token_expires_at:
            return True
        return timezone.now() >= (self.token_expires_at - timezone.timedelta(seconds=buffer_seconds))

    @property
    def has_valid_credentials(self) -> bool:
        """Check if connection is active with stored refresh token."""
        return bool(
            self.status == IntegrationStatus.CONNECTED
            and self.encrypted_refresh_token
            and self.encrypted_refresh_token.strip()
        )

    def has_scope(self, scope: str) -> bool:
        """Check if a specific scope is included in granted scopes."""
        if not self.scopes or not isinstance(self.scopes, (list, tuple)):
            return False
        return scope in self.scopes

    @property
    def has_analytics_scope(self) -> bool:
        """Check if connection includes Google Analytics read-only scope."""
        return self.has_scope('https://www.googleapis.com/auth/analytics.readonly')


class ProjectGA4Connection(models.Model):
    """
    Links a DoxaRank Project to an associated Google Analytics 4 (GA4) property.
    Relationship: Project 1 <---> 1 ProjectGA4Connection (OneToOne)
    Ownership: project.owner (tenant isolation)
    """
    project = models.OneToOneField(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='ga4_connection',
        help_text='The project linked to this GA4 property.'
    )
    property_id = models.CharField(
        max_length=100,
        help_text='The GA4 property ID (e.g. "123456789").'
    )
    display_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Display name of the GA4 property.'
    )
    account_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='The Google Analytics account ID.'
    )
    is_connected = models.BooleanField(
        default=True,
        help_text='Whether this project is actively connected to GA4.'
    )
    connected_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the GA4 property was associated.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp of last update.'
    )

    class Meta:
        db_table = 'integrations_ga4_connections'
        verbose_name = 'Project GA4 Connection'
        verbose_name_plural = 'Project GA4 Connections'
        ordering = ['-connected_at']

    def __str__(self):
        return f"GA4: {self.property_id} ({self.project.name})"


class ProjectClarityConnection(models.Model):
    """
    Links a DoxaRank Project to an associated Microsoft Clarity project/site.
    Relationship: Project 1 <---> 1 ProjectClarityConnection (OneToOne)
    Ownership: project.owner (tenant isolation)
    """
    project = models.OneToOneField(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='clarity_connection',
        help_text='The project linked to this Microsoft Clarity project.'
    )
    clarity_project_id = models.CharField(
        max_length=100,
        help_text='The Microsoft Clarity project/site ID (e.g. "k9xyz123").'
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Display name of the Clarity project.'
    )
    website_url = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text='Website URL configured in Clarity.'
    )
    encrypted_api_token = models.TextField(
        blank=True,
        null=True,
        help_text='Encrypted Clarity Data Export API token if configured.'
    )
    is_connected = models.BooleanField(
        default=True,
        help_text='Whether this project is actively connected to Microsoft Clarity.'
    )
    connected_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Timestamp when the Clarity project was associated.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Timestamp of last update.'
    )

    class Meta:
        db_table = 'integrations_clarity_connections'
        verbose_name = 'Project Clarity Connection'
        verbose_name_plural = 'Project Clarity Connections'
        ordering = ['-connected_at']

    def __str__(self):
        return f"Clarity: {self.clarity_project_id} ({self.project.name})"

    def set_api_token(self, raw_token: Optional[str]) -> None:
        """Encrypt and store Clarity API token."""
        self.encrypted_api_token = encrypt_token(raw_token) if raw_token else None

    def get_api_token(self) -> Optional[str]:
        """Decrypt and return plaintext Clarity API token."""
        return decrypt_token(self.encrypted_api_token) if self.encrypted_api_token else None
