import logging
from typing import Any, Dict, List, Optional
from google.oauth2.credentials import Credentials
import googleapiclient.discovery
from googleapiclient.errors import HttpError

from apps.integrations.models import (
    IntegrationConnection,
    IntegrationProvider,
    IntegrationStatus,
    ProjectGTMConnection,
)
from apps.integrations.services.google_oauth import (
    GoogleOAuthIntegrationService,
    GoogleOAuthExchangeError,
)
from apps.projects.models import Project

logger = logging.getLogger(__name__)

GTM_SCOPE = 'https://www.googleapis.com/auth/tagmanager.readonly'


class GTMError(Exception):
    """Base exception for GTM integration operations."""
    pass


class GTMNotConnectedError(GTMError):
    """Raised when user has no active Google connection."""
    pass


class GTMScopeMissingError(GTMError):
    """Raised when Google account is connected but lacks Google Tag Manager permissions."""
    pass


class GTMCredentialsError(GTMError):
    """Raised when Google OAuth credentials cannot be validated or refreshed."""
    pass


class GTMRateLimitError(GTMError):
    """Raised when Google Tag Manager API quota or rate limits are reached."""
    pass


class GTMApiError(GTMError):
    """Raised when the Google Tag Manager API returns an error."""
    pass


class GTMProjectNotFoundError(GTMError):
    """Raised when the target DoxaRank project cannot be found or is not owned by the user."""
    pass


class GTMIntegrationService:
    """
    Dedicated service for Google Tag Manager (GTM) account/container discovery,
    credential management, and project association.
    """

    @classmethod
    def get_user_connection(cls, user: Any, enforce_scope: bool = True) -> IntegrationConnection:
        """
        Retrieve and validate active Google IntegrationConnection for the user.
        Raises GTMNotConnectedError, GTMCredentialsError, or GTMScopeMissingError.
        """
        if not user or not user.is_authenticated:
            raise GTMNotConnectedError("User must be authenticated.")

        connection = IntegrationConnection.objects.filter(
            user=user,
            provider=IntegrationProvider.GOOGLE
        ).first()

        if not connection or connection.status != IntegrationStatus.CONNECTED:
            raise GTMNotConnectedError(
                "Google account is not connected. Please connect your Google account in Settings."
            )

        if not connection.has_valid_credentials:
            raise GTMCredentialsError(
                "Google account credentials have expired or are missing. Please reconnect your account."
            )

        if enforce_scope and not connection.has_gtm_scope:
            raise GTMScopeMissingError(
                "Google Tag Manager read permissions are not granted on your connected Google account. "
                "Please reconnect your Google account to grant Google Tag Manager access."
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
            raise GTMCredentialsError(str(exc))

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
        Construct Google Tag Manager API client (tagmanager v2).
        """
        if not credentials:
            if not user:
                raise GTMError("Credentials or User context required to build client.")
            connection = cls.get_user_connection(user)
            credentials = cls.get_credentials(connection)

        try:
            return googleapiclient.discovery.build(
                'tagmanager',
                'v2',
                credentials=credentials,
                cache_discovery=False
            )
        except Exception as exc:
            logger.error(f"[GTMIntegrationService] Failed to build GTM client: {exc}")
            raise GTMApiError(f"Failed to initialize Google Tag Manager client: {str(exc)}")

    @classmethod
    def list_containers(cls, user: Any) -> List[Dict[str, Any]]:
        """
        Retrieve accessible GTM containers via the Google Tag Manager API.
        Iterates over all accessible GTM accounts and retrieves their containers.
        Normalizes response to:
            [
                {
                    "account_id": "123456",
                    "account_name": "My Account",
                    "container_id": "789012",
                    "public_id": "GTM-XXXXXX",
                    "name": "My Web Container",
                    "usage_context": ["web"]
                }
            ]
        """
        connection = cls.get_user_connection(user, enforce_scope=True)
        credentials = cls.get_credentials(connection)
        client = cls.get_client(credentials=credentials)

        try:
            accounts_resp = client.accounts().list().execute()
        except HttpError as exc:
            status_code = exc.resp.status if hasattr(exc, 'resp') else 500
            error_details = str(exc)
            logger.error(f"[GTMIntegrationService] Google API HttpError listing accounts ({status_code}): {error_details}")
            if status_code in (401, 403):
                raise GTMCredentialsError(
                    "Google Tag Manager API permission denied or revoked. Please reconnect your account."
                )
            if status_code == 429:
                raise GTMRateLimitError("Google Tag Manager API rate limit exceeded. Please try again later.")
            raise GTMApiError(f"Google Tag Manager API error: {error_details}")
        except Exception as exc:
            logger.error(f"[GTMIntegrationService] Unexpected error listing GTM accounts: {exc}")
            raise GTMApiError(f"Failed to fetch Google Tag Manager accounts: {str(exc)}")

        accounts = accounts_resp.get('account', []) if isinstance(accounts_resp, dict) else []
        normalized_containers: List[Dict[str, Any]] = []

        for account in accounts:
            account_id = account.get('accountId')
            account_name = account.get('name') or f"Account {account_id}"
            if not account_id:
                continue

            try:
                containers_resp = client.accounts().containers().list(
                    parent=f"accounts/{account_id}"
                ).execute()
                containers = containers_resp.get('container', []) if isinstance(containers_resp, dict) else []
                for container in containers:
                    c_id = str(container.get('containerId', ''))
                    public_id = container.get('publicId') or (f"GTM-{c_id}" if c_id else '')
                    name = container.get('name') or f"Container {public_id}"
                    usage_context = container.get('usageContext', [])
                    if c_id:
                        normalized_containers.append({
                            'account_id': str(account_id),
                            'account_name': account_name,
                            'container_id': c_id,
                            'public_id': public_id,
                            'name': name,
                            'usage_context': usage_context if isinstance(usage_context, list) else [usage_context],
                        })
            except HttpError as exc:
                status_code = exc.resp.status if hasattr(exc, 'resp') else 500
                logger.warning(
                    f"[GTMIntegrationService] Failed listing containers for account {account_id} ({status_code}): {exc}"
                )
                if status_code in (401, 403):
                    raise GTMCredentialsError(
                        "Google Tag Manager API permission denied or revoked. Please reconnect your account."
                    )
                if status_code == 429:
                    raise GTMRateLimitError("Google Tag Manager API rate limit exceeded. Please try again later.")
                # Non-fatal error for a single account can be logged and continue or re-raise
                continue
            except Exception as exc:
                logger.warning(f"[GTMIntegrationService] Unexpected error for account {account_id}: {exc}")
                continue

        return normalized_containers

    @classmethod
    def associate_project_container(
        cls,
        user: Any,
        project_id: int,
        container_id: str,
        account_id: Optional[str] = None,
        container_public_id: Optional[str] = None,
        name: Optional[str] = None,
        usage_context: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Associate a verified GTM container with a user's DoxaRank Project.
        Enforces:
        1. User owns the project.
        2. Container exists in user's accessible GTM containers.
        3. No cross-user access.
        """
        try:
            project = Project.objects.get(id=project_id, owner=user)
        except Project.DoesNotExist:
            raise GTMProjectNotFoundError("Project not found or you do not have permission to access it.")

        # Verify container exists in user's accessible GTM accounts
        available_containers = cls.list_containers(user)
        clean_target = str(container_id).strip()
        matching = next(
            (
                c for c in available_containers
                if c['container_id'] == clean_target or c['public_id'] == clean_target
            ),
            None
        )
        if not matching:
            raise GTMError(
                f"The GTM container '{container_id}' was not found in your connected Google account."
            )

        resolved_account_id = matching.get('account_id') or account_id or ''
        resolved_container_id = matching.get('container_id') or clean_target
        resolved_public_id = matching.get('public_id') or container_public_id or resolved_container_id
        resolved_name = name or matching.get('name') or resolved_public_id
        resolved_usage = usage_context if usage_context is not None else matching.get('usage_context', [])

        # Create or update ProjectGTMConnection
        project_conn, created = ProjectGTMConnection.objects.get_or_create(
            project=project,
            defaults={
                'account_id': resolved_account_id,
                'container_id': resolved_container_id,
                'container_public_id': resolved_public_id,
                'name': resolved_name,
                'usage_context': resolved_usage,
                'is_connected': True,
            }
        )

        if not created:
            project_conn.account_id = resolved_account_id
            project_conn.container_id = resolved_container_id
            project_conn.container_public_id = resolved_public_id
            project_conn.name = resolved_name
            project_conn.usage_context = resolved_usage
            project_conn.is_connected = True
            project_conn.save()

        return {
            'project_id': project.id,
            'project_name': project.name,
            'account_id': project_conn.account_id,
            'container_id': project_conn.container_id,
            'container_public_id': project_conn.container_public_id,
            'name': project_conn.name,
            'usage_context': project_conn.usage_context,
            'is_connected': project_conn.is_connected,
            'connected_at': project_conn.connected_at,
        }

    @classmethod
    def get_project_connection(cls, user: Any, project_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve existing GTM connection for a project owned by user.
        """
        try:
            project = Project.objects.get(id=project_id, owner=user)
        except Project.DoesNotExist:
            return None

        conn = ProjectGTMConnection.objects.filter(project=project, is_connected=True).first()
        if not conn:
            return None

        return {
            'project_id': project.id,
            'project_name': project.name,
            'account_id': conn.account_id,
            'container_id': conn.container_id,
            'container_public_id': conn.container_public_id,
            'name': conn.name,
            'usage_context': conn.usage_context,
            'is_connected': conn.is_connected,
            'connected_at': conn.connected_at,
        }

    @classmethod
    def disconnect_project(cls, user: Any, project_id: int) -> bool:
        """
        Disconnect GTM from a project.
        """
        try:
            project = Project.objects.get(id=project_id, owner=user)
        except Project.DoesNotExist:
            raise GTMProjectNotFoundError("Project not found or you do not have permission to access it.")

        conn = ProjectGTMConnection.objects.filter(project=project).first()
        if conn:
            conn.is_connected = False
            conn.save()
            return True
        return False
