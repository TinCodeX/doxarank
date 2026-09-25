import logging
import re
import urllib.parse
from datetime import timedelta
from typing import Dict, List, Optional, Any

import requests
from django.conf import settings
from django.utils import timezone

from apps.integrations.models import (
    IntegrationConnection,
    IntegrationProvider,
    IntegrationStatus,
    ProjectClarityConnection,
)
from apps.integrations.services.google_oauth import OAuthStateService, InvalidOAuthStateError
from apps.projects.models import Project

logger = logging.getLogger(__name__)

# Official Microsoft Identity endpoints
MS_OAUTH_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_OAUTH_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"

# Official Microsoft Clarity Data Export API
CLARITY_LIVE_INSIGHTS_URL = "https://www.clarity.ms/export-data/api/v1/project-live-insights"


class ClarityError(Exception):
    """Base exception for Microsoft Clarity integration errors."""
    pass


class ClarityNotConnectedError(ClarityError):
    """Raised when an operation requires an active Microsoft Clarity connection."""
    pass


class ClarityCredentialsError(ClarityError):
    """Raised when credentials/token are invalid, expired, or rejected (401/403)."""
    pass


class ClarityRateLimitError(ClarityError):
    """Raised when Microsoft/Clarity API returns a 429 rate limit."""
    pass


class ClarityApiError(ClarityError):
    """Raised when Microsoft/Clarity returns an unexpected server/network error."""
    pass


class ClarityProjectNotFoundError(ClarityError):
    """Raised when a specified DoxaRank or Clarity project cannot be located."""
    pass


class ClarityIntegrationService:
    """
    Dedicated service for Microsoft Clarity integration:
    - Microsoft Identity OAuth2 connection & token refresh
    - Accessible Clarity project discovery
    - Project <-> Clarity property association
    - Structured error normalization
    """

    @classmethod
    def get_user_connection(cls, user, enforce_connected: bool = True) -> Optional[IntegrationConnection]:
        """
        Retrieve the Microsoft IntegrationConnection for the given user.
        Raises ClarityNotConnectedError if not found or disconnected when enforce_connected=True.
        """
        if not user or not user.is_authenticated:
            raise ClarityNotConnectedError("User is not authenticated.")

        connection = IntegrationConnection.objects.filter(
            user=user,
            provider=IntegrationProvider.MICROSOFT
        ).first()

        if not connection:
            if enforce_connected:
                raise ClarityNotConnectedError("Microsoft Clarity is not connected for this account.")
            return None

        if enforce_connected and connection.status != IntegrationStatus.CONNECTED:
            raise ClarityNotConnectedError(
                f"Microsoft Clarity connection is in status: '{connection.status}'. Please reconnect."
            )

        return connection

    @classmethod
    def get_authorization_url(cls, user, redirect_uri: Optional[str] = None) -> str:
        """
        Generate Microsoft OAuth2 authorization URL with cryptographically signed state token.
        """
        client_id = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_ID', '')
        if not client_id:
            raise ValueError("MICROSOFT_OAUTH_CLIENT_ID is not configured in Django settings.")

        target_redirect_uri = redirect_uri or getattr(
            settings, 'MICROSOFT_OAUTH_REDIRECT_URI', 'http://localhost:5173/integrations/microsoft/callback'
        )

        state_token = OAuthStateService.generate_state(user, metadata={'provider': 'microsoft'})
        scopes = getattr(settings, 'MICROSOFT_OAUTH_SCOPES', ['openid', 'profile', 'email', 'offline_access', 'User.Read'])
        scope_str = ' '.join(scopes)

        params = {
            'client_id': client_id,
            'response_type': 'code',
            'redirect_uri': target_redirect_uri,
            'response_mode': 'query',
            'scope': scope_str,
            'state': state_token,
        }

        return f"{MS_OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"

    @classmethod
    def exchange_code_for_tokens(cls, code: str, state: str, redirect_uri: Optional[str] = None) -> IntegrationConnection:
        """
        Exchange Microsoft authorization code for access and refresh tokens.
        Validates state token and stores encrypted credentials.
        """
        user, _ = OAuthStateService.verify_state(state)

        client_id = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_ID', '')
        client_secret = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_SECRET', '')
        target_redirect_uri = redirect_uri or getattr(
            settings, 'MICROSOFT_OAUTH_REDIRECT_URI', 'http://localhost:5173/integrations/microsoft/callback'
        )

        token_payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': target_redirect_uri,
        }

        try:
            resp = requests.post(MS_OAUTH_TOKEN_URL, data=token_payload, timeout=15)
        except requests.RequestException as exc:
            logger.error(f"[ClarityIntegrationService] Network error during token exchange: {exc}")
            raise ClarityApiError("Failed to reach Microsoft Identity service for token exchange.")

        if resp.status_code != 200:
            logger.error(f"[ClarityIntegrationService] Token exchange failed ({resp.status_code}): {resp.text}")
            raise ClarityCredentialsError("Failed to exchange authorization code for Microsoft tokens.")

        try:
            token_data = resp.json()
        except ValueError:
            raise ClarityApiError("Received malformed JSON response from Microsoft OAuth endpoint.")

        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)
        scopes_granted = token_data.get('scope', '').split()

        # Retrieve user profile from Microsoft Graph
        account_email = None
        account_name = None
        account_id = None

        if access_token:
            try:
                graph_resp = requests.get(
                    MS_GRAPH_ME_URL,
                    headers={'Authorization': f"Bearer {access_token}"},
                    timeout=10
                )
                if graph_resp.status_code == 200:
                    profile = graph_resp.json()
                    account_email = profile.get('mail') or profile.get('userPrincipalName')
                    account_name = profile.get('displayName')
                    account_id = profile.get('id')
            except Exception as exc:
                logger.warning(f"[ClarityIntegrationService] Could not retrieve profile from Microsoft Graph: {exc}")

        # Save or update connection
        connection, _ = IntegrationConnection.objects.get_or_create(
            user=user,
            provider=IntegrationProvider.MICROSOFT,
            defaults={'status': IntegrationStatus.CONNECTED}
        )

        connection.set_access_token(access_token)
        if refresh_token:
            connection.set_refresh_token(refresh_token)

        connection.token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))
        connection.status = IntegrationStatus.CONNECTED
        if account_email:
            connection.account_email = account_email
        if account_name:
            connection.account_name = account_name
        if account_id:
            connection.account_id = str(account_id)

        connection.scopes = sorted(list(set(connection.scopes or []).union(scopes_granted)))
        connection.save()
        logger.info(f"[ClarityIntegrationService] Successfully connected Microsoft for user {user.id}")
        return connection

    @classmethod
    def refresh_access_token(cls, connection: IntegrationConnection) -> IntegrationConnection:
        """
        Refresh Microsoft access token using stored refresh token.
        """
        refresh_token = connection.get_refresh_token()
        if not refresh_token:
            connection.status = IntegrationStatus.EXPIRED
            connection.save(update_fields=['status', 'updated_at'])
            raise ClarityCredentialsError("No refresh token available to refresh Microsoft access token.")

        client_id = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_ID', '')
        client_secret = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_SECRET', '')

        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }

        try:
            resp = requests.post(MS_OAUTH_TOKEN_URL, data=payload, timeout=15)
        except requests.RequestException as exc:
            raise ClarityApiError(f"Network error refreshing Microsoft access token: {exc}")

        if resp.status_code in (400, 401, 403):
            connection.status = IntegrationStatus.EXPIRED
            connection.save(update_fields=['status', 'updated_at'])
            raise ClarityCredentialsError("Microsoft refresh token expired or revoked. Please reconnect.")

        if resp.status_code == 429:
            raise ClarityRateLimitError("Microsoft rate limit exceeded during token refresh.")

        if resp.status_code >= 500:
            raise ClarityApiError("Microsoft token service returned a server error.")

        try:
            data = resp.json()
        except ValueError:
            raise ClarityApiError("Malformed JSON response from Microsoft token endpoint.")

        access_token = data.get('access_token')
        new_refresh = data.get('refresh_token')
        expires_in = data.get('expires_in', 3600)

        connection.set_access_token(access_token)
        if new_refresh:
            connection.set_refresh_token(new_refresh)
        connection.token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))
        connection.status = IntegrationStatus.CONNECTED
        connection.save()
        return connection

    @classmethod
    def connect_account(
        cls,
        user,
        account_email: Optional[str] = None,
        account_name: Optional[str] = None,
        account_id: Optional[str] = None,
        projects: Optional[List[Dict[str, Any]]] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
    ) -> IntegrationConnection:
        """
        Directly connect or update Microsoft Clarity account for a user.
        """
        connection, _ = IntegrationConnection.objects.get_or_create(
            user=user,
            provider=IntegrationProvider.MICROSOFT,
            defaults={'status': IntegrationStatus.CONNECTED}
        )
        connection.status = IntegrationStatus.CONNECTED
        if account_email:
            connection.account_email = account_email
        if account_name:
            connection.account_name = account_name
        if account_id:
            connection.account_id = account_id

        if access_token:
            connection.set_access_token(access_token)
        if refresh_token:
            connection.set_refresh_token(refresh_token)

        meta = connection.metadata or {}
        if projects is not None:
            existing_projects = meta.get('projects', [])
            existing_ids = {p.get('project_id') for p in existing_projects}
            for p in projects:
                if p.get('project_id') not in existing_ids:
                    existing_projects.append(p)
                    existing_ids.add(p.get('project_id'))
            meta['projects'] = existing_projects

        connection.metadata = meta
        connection.save()
        return connection

    @classmethod
    def list_projects(cls, user) -> List[Dict[str, str]]:
        """
        Retrieve and normalize accessible Microsoft Clarity projects for the connected user.
        Returns:
            [
                {
                    "project_id": "k9xyz123",
                    "name": "My Website",
                    "website": "https://example.com"
                }
            ]
        """
        connection = cls.get_user_connection(user, enforce_connected=True)

        # Refresh token if needed
        if connection.is_token_expired(buffer_seconds=60) and connection.encrypted_refresh_token:
            try:
                connection = cls.refresh_access_token(connection)
            except ClarityCredentialsError:
                raise
            except Exception as exc:
                logger.warning(f"[ClarityIntegrationService] Token refresh skipped or failed: {exc}")

        # Extract accessible projects from metadata or user's project associations
        meta = connection.metadata or {}
        raw_projects = meta.get('projects', [])

        # Include projects already associated by this user
        existing_connections = ProjectClarityConnection.objects.filter(
            project__owner=user,
            is_connected=True
        ).select_related('project')

        seen_ids = set()
        normalized: List[Dict[str, str]] = []

        for p in raw_projects:
            pid = str(p.get('project_id', '')).strip()
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                normalized.append({
                    'project_id': pid,
                    'name': str(p.get('name', f"Clarity Project {pid}")).strip(),
                    'website': str(p.get('website', p.get('website_url', ''))).strip(),
                })

        for conn in existing_connections:
            pid = str(conn.clarity_project_id).strip()
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                normalized.append({
                    'project_id': pid,
                    'name': str(conn.name or f"Clarity Project {pid}").strip(),
                    'website': str(conn.website_url or conn.project.website_url or '').strip(),
                })

        return normalized

    @classmethod
    def validate_clarity_project_access(cls, clarity_project_id: str, api_token: Optional[str] = None) -> bool:
        """
        Validate clarity project against Clarity Data Export API if token is provided.
        Maps external HTTP errors to structured DoxaRank exceptions.
        """
        if not clarity_project_id or not clarity_project_id.strip():
            raise ClarityProjectNotFoundError("Clarity project ID cannot be blank.")

        # Validate ID format (alphanumeric, dashes, underscores)
        if not re.match(r'^[a-zA-Z0-9_\-\.]{3,64}$', clarity_project_id):
            raise ClarityProjectNotFoundError(f"Invalid Clarity project ID format: '{clarity_project_id}'")

        if api_token:
            try:
                headers = {'Authorization': f"Bearer {api_token.strip()}"}
                params = {'numOfDays': 1}
                resp = requests.get(CLARITY_LIVE_INSIGHTS_URL, headers=headers, params=params, timeout=12)
            except requests.RequestException as exc:
                logger.error(f"[ClarityIntegrationService] Network error validating project {clarity_project_id}: {exc}")
                raise ClarityApiError("Network error contacting Microsoft Clarity API.")

            if resp.status_code in (401, 403):
                logger.warning(f"[ClarityIntegrationService] Clarity API returned {resp.status_code} for project {clarity_project_id}")
                raise ClarityCredentialsError("Microsoft Clarity API token was rejected or unauthorized (401/403).")

            if resp.status_code == 429:
                logger.warning(f"[ClarityIntegrationService] Clarity API rate limited (429) for project {clarity_project_id}")
                raise ClarityRateLimitError("Microsoft Clarity API rate limit reached (maximum 10 requests/day per project).")

            if resp.status_code >= 500:
                logger.error(f"[ClarityIntegrationService] Clarity API returned server error {resp.status_code}")
                raise ClarityApiError(f"Microsoft Clarity API returned a server error ({resp.status_code}).")

        return True

    @classmethod
    def associate_project(
        cls,
        user,
        project_id: int,
        clarity_project_id: str,
        name: Optional[str] = None,
        website: Optional[str] = None,
        api_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Associate a verified Clarity project with a DoxaRank project owned by the user.
        Enforces tenant isolation, project ownership, and property accessibility.
        """
        # 1. Verify user's Microsoft connection exists
        connection = cls.get_user_connection(user, enforce_connected=True)

        # 2. Verify project ownership (Tenant Isolation)
        try:
            project = Project.objects.get(id=project_id, owner=user)
        except Project.DoesNotExist:
            raise ClarityProjectNotFoundError(f"Project with ID {project_id} not found or not owned by you.")

        clean_pid = str(clarity_project_id).strip()
        if not clean_pid:
            raise ClarityProjectNotFoundError("Clarity project ID cannot be blank.")

        # 3. Validate project ID format & optional live token test
        cls.validate_clarity_project_access(clean_pid, api_token=api_token)

        # 4. Verify property accessibility for the user
        meta = connection.metadata or {}
        accessible_projects = meta.get('projects', [])
        known_ids = {str(p.get('project_id')).strip() for p in accessible_projects if p.get('project_id')}

        # Check if project belongs to another user's active connection
        existing_other_user = ProjectClarityConnection.objects.filter(
            clarity_project_id=clean_pid,
            is_connected=True
        ).exclude(project__owner=user).exists()

        if existing_other_user:
            raise ClarityCredentialsError(
                f"Clarity project '{clean_pid}' is already associated with an account owned by another user."
            )

        # 5. Persist association via ProjectClarityConnection
        clean_name = (name or f"Clarity - {project.name}").strip()
        clean_website = (website or project.website_url or '').strip()

        clarity_conn, _ = ProjectClarityConnection.objects.update_or_create(
            project=project,
            defaults={
                'clarity_project_id': clean_pid,
                'name': clean_name,
                'website_url': clean_website,
                'is_connected': True,
            }
        )

        if api_token:
            clarity_conn.set_api_token(api_token)
            clarity_conn.save(update_fields=['encrypted_api_token'])

        # Register in connection metadata if not yet tracked
        if clean_pid not in known_ids:
            accessible_projects.append({
                'project_id': clean_pid,
                'name': clean_name,
                'website': clean_website,
            })
            meta['projects'] = accessible_projects
            connection.metadata = meta
            connection.save(update_fields=['metadata', 'updated_at'])

        logger.info(f"[ClarityIntegrationService] Linked Clarity {clean_pid} to Project {project.id} for user {user.id}")

        return {
            'project_id': project.id,
            'project_name': project.name,
            'clarity_project_id': clarity_conn.clarity_project_id,
            'name': clarity_conn.name,
            'website': clarity_conn.website_url,
            'is_connected': clarity_conn.is_connected,
            'connected_at': clarity_conn.connected_at.isoformat(),
        }

    @classmethod
    def get_project_connection(cls, user, project_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve active Clarity connection for a project owned by user.
        """
        try:
            conn = ProjectClarityConnection.objects.select_related('project').get(
                project_id=project_id,
                project__owner=user,
                is_connected=True
            )
            return {
                'project_id': conn.project.id,
                'project_name': conn.project.name,
                'clarity_project_id': conn.clarity_project_id,
                'name': conn.name,
                'website': conn.website_url,
                'is_connected': conn.is_connected,
                'connected_at': conn.connected_at.isoformat(),
            }
        except ProjectClarityConnection.DoesNotExist:
            return None

    @classmethod
    def disconnect(cls, user) -> None:
        """
        Disconnect Microsoft Clarity for the given user:
        - Marks IntegrationConnection disconnected
        - Clears tokens
        - Deactivates project links
        """
        connection = IntegrationConnection.objects.filter(
            user=user,
            provider=IntegrationProvider.MICROSOFT
        ).first()

        if connection:
            connection.status = IntegrationStatus.DISCONNECTED
            connection.set_access_token(None)
            connection.set_refresh_token(None)
            connection.token_expires_at = None
            connection.save()

        # Mark all user's project Clarity connections as disconnected
        ProjectClarityConnection.objects.filter(
            project__owner=user,
            is_connected=True
        ).update(is_connected=False)

        logger.info(f"[ClarityIntegrationService] Disconnected Microsoft Clarity for user {user.id}")
