import logging
from typing import Any, Dict, List, Optional
from google.oauth2.credentials import Credentials
import googleapiclient.discovery
from googleapiclient.errors import HttpError

from apps.integrations.models import (
    IntegrationConnection,
    IntegrationProvider,
    IntegrationStatus,
    ProjectGA4Connection,
)
from apps.integrations.services.google_oauth import (
    GoogleOAuthIntegrationService,
    GoogleOAuthExchangeError,
)
from apps.projects.models import Project

logger = logging.getLogger(__name__)

GA4_ANALYTICS_SCOPE = 'https://www.googleapis.com/auth/analytics.readonly'


class GA4Error(Exception):
    """Base exception for GA4 integration operations."""
    pass


class GA4NotConnectedError(GA4Error):
    """Raised when user has no active Google connection."""
    pass


class GA4ScopeMissingError(GA4Error):
    """Raised when Google account is connected but lacks Google Analytics permissions."""
    pass


class GA4CredentialsError(GA4Error):
    """Raised when Google OAuth credentials cannot be validated or refreshed."""
    pass


class GA4RateLimitError(GA4Error):
    """Raised when Google Analytics API quota or rate limits are reached."""
    pass


class GA4ApiError(GA4Error):
    """Raised when the Google Analytics Admin API returns an error."""
    pass


class GA4IntegrationService:
    """
    Dedicated service for Google Analytics 4 (GA4) property discovery,
    credential management, and project association.
    """

    @classmethod
    def get_user_connection(cls, user: Any, enforce_scope: bool = True) -> IntegrationConnection:
        """
        Retrieve and validate active Google IntegrationConnection for the user.
        Raises GA4NotConnectedError, GA4CredentialsError, or GA4ScopeMissingError.
        """
        if not user or not user.is_authenticated:
            raise GA4NotConnectedError("User must be authenticated.")

        connection = IntegrationConnection.objects.filter(
            user=user,
            provider=IntegrationProvider.GOOGLE
        ).first()

        if not connection or connection.status != IntegrationStatus.CONNECTED:
            raise GA4NotConnectedError(
                "Google account is not connected. Please connect your Google account in Settings."
            )

        if not connection.has_valid_credentials:
            raise GA4CredentialsError(
                "Google account credentials have expired or are missing. Please reconnect your account."
            )

        if enforce_scope and not connection.has_analytics_scope:
            raise GA4ScopeMissingError(
                "Google Analytics read permissions are not granted on your connected Google account. "
                "Please reconnect your Google account to grant Google Analytics access."
            )

        return connection

    @classmethod
    def get_credentials(cls, connection: IntegrationConnection) -> Credentials:
        """
        Build Google OAuth2 Credentials object from connection, automatically
        refreshing access token if expired.
        """
        try:
            connection = GoogleOAuthIntegrationService.refresh_connection_tokens(connection)
        except GoogleOAuthExchangeError as exc:
            raise GA4CredentialsError(str(exc))

        access_token = connection.get_access_token()
        refresh_token = connection.get_refresh_token()
        oauth_config = GoogleOAuthIntegrationService.get_oauth_config()

        return Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=GoogleOAuthIntegrationService.GOOGLE_TOKEN_URL,
            client_id=oauth_config['client_id'],
            client_secret=oauth_config['client_secret'],
            scopes=oauth_config['scopes']
        )

    @classmethod
    def get_client(cls, credentials: Optional[Credentials] = None, user: Optional[Any] = None) -> Any:
        """
        Construct Google Analytics Admin API client (analyticsadmin v1beta).
        """
        if not credentials:
            if not user:
                raise GA4Error("Credentials or User context required to build client.")
            connection = cls.get_user_connection(user)
            credentials = cls.get_credentials(connection)

        try:
            return googleapiclient.discovery.build(
                'analyticsadmin',
                'v1beta',
                credentials=credentials,
                cache_discovery=False
            )
        except Exception as exc:
            logger.error(f"[GA4IntegrationService] Failed to build Analytics client: {exc}")
            raise GA4ApiError(f"Failed to initialize Google Analytics client: {str(exc)}")

    @classmethod
    def list_properties(cls, user: Any) -> List[Dict[str, str]]:
        """
        Retrieve accessible GA4 properties via the Google Analytics Admin API.
        Normalizes response to:
            [
                {
                    "property_id": "123456789",
                    "display_name": "Example Website",
                    "property_type": "GA4"
                }
            ]
        """
        connection = cls.get_user_connection(user, enforce_scope=True)
        credentials = cls.get_credentials(connection)
        client = cls.get_client(credentials=credentials)

        try:
            # accountSummaries().list() is the canonical single call to discover accounts + properties
            response = client.accountSummaries().list().execute()
        except HttpError as exc:
            status_code = exc.resp.status if hasattr(exc, 'resp') else 500
            error_details = str(exc)
            logger.error(f"[GA4IntegrationService] Google API HttpError ({status_code}): {error_details}")
            if status_code in (401, 403):
                raise GA4CredentialsError(
                    "Google Analytics API permission denied or revoked. Please reconnect your account."
                )
            if status_code == 429:
                raise GA4RateLimitError("Google Analytics API rate limit exceeded. Please try again later.")
            raise GA4ApiError(f"Google Analytics API error: {error_details}")
        except Exception as exc:
            logger.error(f"[GA4IntegrationService] Unexpected error listing GA4 properties: {exc}")
            raise GA4ApiError(f"Failed to fetch Google Analytics properties: {str(exc)}")

        normalized: List[Dict[str, str]] = []

        # Parse accountSummaries structure
        if isinstance(response, dict) and 'accountSummaries' in response:
            for account in response.get('accountSummaries', []):
                for prop in account.get('propertySummaries', []):
                    raw_property = prop.get('property', '')
                    # Format is typically "properties/123456789"
                    clean_id = raw_property.split('/')[-1] if '/' in raw_property else raw_property
                    display_name = prop.get('displayName') or f"Property {clean_id}"
                    if clean_id:
                        normalized.append({
                            'property_id': clean_id,
                            'display_name': display_name,
                            'property_type': 'GA4',
                        })

        # Fallback to direct properties list if accountSummaries is empty or alternative structure
        elif isinstance(response, dict) and 'properties' in response:
            for prop in response.get('properties', []):
                raw_name = prop.get('name', '')
                clean_id = raw_name.split('/')[-1] if '/' in raw_name else raw_name
                display_name = prop.get('displayName') or f"Property {clean_id}"
                if clean_id:
                    normalized.append({
                        'property_id': clean_id,
                        'display_name': display_name,
                        'property_type': 'GA4',
                    })

        return normalized

    @classmethod
    def associate_project_property(
        cls,
        user: Any,
        project_id: int,
        property_id: str,
        display_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Associate a verified GA4 property with a user's DoxaRank Project.
        Enforces:
        1. User owns the project.
        2. Property exists in user's accessible GA4 properties.
        3. No cross-user access.
        """
        try:
            project = Project.objects.get(id=project_id, owner=user)
        except Project.DoesNotExist:
            raise GA4Error("Project not found or you do not have permission to access it.")

        # Verify property exists in user's GA4 account
        available_properties = cls.list_properties(user)
        matching = next(
            (p for p in available_properties if p['property_id'] == str(property_id).strip()),
            None
        )
        if not matching:
            raise GA4Error(
                f"The GA4 property ID '{property_id}' was not found in your connected Google account."
            )

        resolved_name = display_name or matching.get('display_name') or f"GA4 Property {property_id}"

        # Create or update ProjectGA4Connection
        project_conn, created = ProjectGA4Connection.objects.get_or_create(
            project=project,
            defaults={
                'property_id': str(property_id).strip(),
                'display_name': resolved_name,
                'is_connected': True,
            }
        )

        if not created:
            project_conn.property_id = str(property_id).strip()
            project_conn.display_name = resolved_name
            project_conn.is_connected = True
            project_conn.save()

        return {
            'project_id': project.id,
            'project_name': project.name,
            'property_id': project_conn.property_id,
            'display_name': project_conn.display_name,
            'is_connected': project_conn.is_connected,
        }

    @classmethod
    def get_project_connection(cls, user: Any, project_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve existing GA4 connection for a project owned by user.
        """
        try:
            project = Project.objects.get(id=project_id, owner=user)
        except Project.DoesNotExist:
            return None

        conn = ProjectGA4Connection.objects.filter(project=project, is_connected=True).first()
        if not conn:
            return None

        return {
            'project_id': project.id,
            'project_name': project.name,
            'property_id': conn.property_id,
            'display_name': conn.display_name,
            'is_connected': conn.is_connected,
            'connected_at': conn.connected_at,
        }
