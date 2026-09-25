import logging
from typing import Any, Dict, List, Optional
from google.oauth2.credentials import Credentials
import googleapiclient.discovery
from googleapiclient.errors import HttpError

from apps.integrations.models import (
    IntegrationConnection,
    IntegrationProvider,
    IntegrationStatus,
)
from apps.integrations.services.google_oauth import (
    GoogleOAuthIntegrationService,
    GoogleOAuthExchangeError,
)
from apps.projects.models import Project
from apps.seo.models import (
    SearchConsoleConnection as ProjectGSCConnection,
    SearchConsolePermission,
    SearchConsoleSyncStatus,
)

logger = logging.getLogger(__name__)


class SearchConsoleError(Exception):
    """Base exception for Search Console service operations."""
    pass


class SearchConsoleNotConnectedError(SearchConsoleError):
    """Raised when user has no active Google connection."""
    pass


class SearchConsoleCredentialsError(SearchConsoleError):
    """Raised when Google credentials cannot be validated or refreshed."""
    pass


class SearchConsoleApiError(SearchConsoleError):
    """Raised when the Google Search Console API returns an error."""
    pass


class SearchConsoleIntegrationService:
    """
    Service for retrieving and managing Google Search Console properties
    for an authenticated DoxaRank user.
    """

    @classmethod
    def get_user_connection(cls, user: Any) -> IntegrationConnection:
        """
        Retrieve and validate active Google IntegrationConnection for the user.
        Raises SearchConsoleNotConnectedError or SearchConsoleCredentialsError.
        """
        if not user or not user.is_authenticated:
            raise SearchConsoleNotConnectedError("User must be authenticated.")

        connection = IntegrationConnection.objects.filter(
            user=user,
            provider=IntegrationProvider.GOOGLE
        ).first()

        if not connection or connection.status != IntegrationStatus.CONNECTED:
            raise SearchConsoleNotConnectedError(
                "Google account is not connected. Please connect your Google account in Settings."
            )

        if not connection.has_valid_credentials:
            raise SearchConsoleCredentialsError(
                "Google account credentials have expired or are missing. Please reconnect your account."
            )

        return connection

    @classmethod
    def get_credentials(cls, connection: IntegrationConnection) -> Credentials:
        """
        Build Google OAuth2 Credentials object from connection, automatically
        refreshing access token if expired.
        """
        # Ensure fresh access token
        try:
            connection = GoogleOAuthIntegrationService.refresh_connection_tokens(connection)
        except GoogleOAuthExchangeError as exc:
            raise SearchConsoleCredentialsError(str(exc))

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
        Construct Google Search Console API client.
        """
        if not credentials:
            if not user:
                raise SearchConsoleError("Credentials or User context required to build client.")
            connection = cls.get_user_connection(user)
            credentials = cls.get_credentials(connection)

        try:
            return googleapiclient.discovery.build(
                'searchconsole',
                'v1',
                credentials=credentials,
                cache_discovery=False
            )
        except Exception as exc:
            logger.error(f"[SearchConsoleService] Failed to build Search Console client: {exc}")
            raise SearchConsoleApiError(f"Failed to initialize Google Search Console client: {str(exc)}")

    @classmethod
    def list_properties(cls, user: Any) -> List[Dict[str, str]]:
        """
        Retrieve and normalize user's verified Search Console properties from Google.
        Returns:
            [
                {
                    "site_url": "https://example.com/",
                    "permission_level": "siteOwner"
                },
                ...
            ]
        """
        connection = cls.get_user_connection(user)
        credentials = cls.get_credentials(connection)
        client = cls.get_client(credentials=credentials)

        try:
            # sites().list() is the canonical Google Search Console endpoint for listing sites
            response = client.sites().list().execute()
        except HttpError as exc:
            status_code = exc.resp.status if hasattr(exc, 'resp') else 500
            error_details = str(exc)
            logger.error(f"[SearchConsoleService] Google API HttpError ({status_code}): {error_details}")
            if status_code in (401, 403):
                raise SearchConsoleCredentialsError(
                    "Google Search Console API permission denied. Please reconnect your account."
                )
            raise SearchConsoleApiError(f"Google Search Console API error: {error_details}")
        except Exception as exc:
            logger.error(f"[SearchConsoleService] Unexpected error listing sites: {exc}")
            raise SearchConsoleApiError(f"Failed to fetch Search Console properties: {str(exc)}")

        raw_entries = response.get('siteEntry', []) if isinstance(response, dict) else []
        if not raw_entries:
            return []

        normalized_properties: List[Dict[str, str]] = []
        for entry in raw_entries:
            site_url = entry.get('siteUrl')
            permission_level = entry.get('permissionLevel', 'siteOwner')
            if site_url:
                normalized_properties.append({
                    'site_url': site_url,
                    'permission_level': permission_level,
                })

        return normalized_properties

    @classmethod
    def associate_project_property(
        cls,
        user: Any,
        project_id: int,
        site_url: str,
        permission_level: str = 'siteOwner'
    ) -> Dict[str, Any]:
        """
        Associate a verified Google Search Console property with a user's DoxaRank Project.
        Enforces:
        1. User owns the project.
        2. Property exists in the user's connected Search Console account.
        3. No cross-user access.
        """
        try:
            project = Project.objects.get(id=project_id, owner=user)
        except Project.DoesNotExist:
            raise SearchConsoleError("Project not found or you do not have permission to access it.")

        # Verify property exists in user's GSC account
        available_properties = cls.list_properties(user)
        matching = next((p for p in available_properties if p['site_url'].rstrip('/') == site_url.rstrip('/')), None)
        if not matching:
            raise SearchConsoleError(
                f"The property '{site_url}' was not found in your connected Google Search Console account."
            )

        connection = cls.get_user_connection(user)
        refresh_token = connection.get_refresh_token()

        # Valid permission level
        valid_perm = matching.get('permission_level', permission_level)
        if valid_perm not in dict(SearchConsolePermission.choices):
            valid_perm = SearchConsolePermission.SITE_OWNER

        # Create or update project SearchConsoleConnection
        project_conn, created = ProjectGSCConnection.objects.get_or_create(
            project=project,
            defaults={
                'property_url': site_url,
                'permission_level': valid_perm,
                'is_connected': True,
                'google_account_email': connection.account_email,
                'scopes': connection.scopes,
                'token_expires_at': connection.token_expires_at,
                'sync_status': SearchConsoleSyncStatus.IDLE,
            }
        )

        if not created:
            project_conn.property_url = site_url
            project_conn.permission_level = valid_perm
            project_conn.is_connected = True
            project_conn.google_account_email = connection.account_email
            project_conn.scopes = connection.scopes
            project_conn.token_expires_at = connection.token_expires_at
            project_conn.error_message = None

        if refresh_token:
            project_conn.set_refresh_token(refresh_token)

        project_conn.save()

        return {
            'project_id': project.id,
            'project_name': project.name,
            'property_url': project_conn.property_url,
            'permission_level': project_conn.permission_level,
            'is_connected': project_conn.is_connected,
            'google_account_email': project_conn.google_account_email,
        }
