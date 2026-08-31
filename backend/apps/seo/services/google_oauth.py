"""
Google Search Console OAuth2 Service for DoxaRank.

Handles:
1. Cryptographically secure, tamper-proof, time-bound, and replay-resistant OAuth2 state generation/validation.
2. Building standard Google OAuth2 authorization URLs requesting Search Console + identity scopes with offline consent.
3. Exchanging authorization codes for access and refresh tokens.
4. Retrieving verified Google user identity (email/profile).
5. Associating credentials securely with SearchConsoleConnection models via AES encryption at rest.
"""

import logging
import secrets
import time
from datetime import timedelta
from typing import Optional, Tuple, Dict, Any, List
from urllib.parse import urlencode, urlparse

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.projects.models import Project
from apps.seo.models import (
    SearchConsoleConnection,
    SearchConsolePermission,
    SearchConsoleSyncStatus
)

logger = logging.getLogger(__name__)
User = get_user_model()


class InvalidOAuthStateError(Exception):
    """Raised when an OAuth state parameter is invalid, forged, expired, or replayed."""
    pass


class GoogleOAuthExchangeError(Exception):
    """Raised when the Google OAuth authorization code exchange or identity fetch fails."""
    pass


class OAuthStateService:
    """
    Manages generation and validation of cryptographic state parameters for OAuth2 flows.
    Ensures protection against CSRF, replay attacks, cross-tenant forgery, and expired requests.
    """
    STATE_SALT = 'google_oauth_state'
    DEFAULT_MAX_AGE_SECONDS = 600  # 10 minutes TTL

    @classmethod
    def get_signer(cls) -> TimestampSigner:
        return TimestampSigner(salt=cls.STATE_SALT)

    @classmethod
    def generate_state(cls, user: Any, project: Project) -> str:
        """
        Generate a cryptographically signed state token embedding user ID, project ID,
        issued timestamp, and a single-use random cryptographic nonce.
        """
        nonce = secrets.token_urlsafe(24)
        payload = {
            'user_id': user.id,
            'project_id': project.id,
            'nonce': nonce,
            'ts': int(time.time())
        }
        signer = cls.get_signer()
        return signer.sign_object(payload)

    @classmethod
    def verify_state(
        cls,
        raw_state: Optional[str],
        expected_user: Optional[Any] = None,
        max_age: int = DEFAULT_MAX_AGE_SECONDS
    ) -> Tuple[Project, Any]:
        """
        Verify the signature, expiration, and replay status of the given state token.
        Returns the resolved (Project, User) tuple upon success.
        Raises InvalidOAuthStateError if verification fails.
        """
        if not raw_state or not isinstance(raw_state, str) or not raw_state.strip():
            raise InvalidOAuthStateError("OAuth state parameter is missing or empty.")

        signer = cls.get_signer()
        try:
            payload = signer.unsign_object(raw_state.strip(), max_age=max_age)
        except SignatureExpired:
            raise InvalidOAuthStateError("OAuth authorization state has expired. Please try connecting again.")
        except (BadSignature, Exception) as exc:
            logger.warning(f"[OAuthStateService] Bad signature on state token: {exc}")
            raise InvalidOAuthStateError("Invalid or forged OAuth authorization state.")

        if not isinstance(payload, dict):
            raise InvalidOAuthStateError("Malformed OAuth state payload.")

        user_id = payload.get('user_id')
        project_id = payload.get('project_id')
        nonce = payload.get('nonce')

        if not user_id or not project_id or not nonce:
            raise InvalidOAuthStateError("Incomplete OAuth state payload.")

        # Replay protection: Check if nonce was already consumed
        nonce_cache_key = f"gsc_oauth_nonce_used:{nonce}"
        if cache.get(nonce_cache_key):
            logger.warning(f"[OAuthStateService] Replay attack detected for nonce: {nonce[:8]}...")
            raise InvalidOAuthStateError("This OAuth authorization state has already been used.")

        # Mark nonce as consumed for max_age window
        cache.set(nonce_cache_key, True, timeout=max_age)

        # Resolve User & Project
        user = User.objects.filter(id=user_id).first()
        if not user:
            raise InvalidOAuthStateError("User associated with OAuth state no longer exists.")

        if expected_user and expected_user.is_authenticated and expected_user.id != user.id:
            raise InvalidOAuthStateError("OAuth state user does not match the currently authenticated user.")

        project = Project.objects.filter(id=project_id, owner=user).first()
        if not project:
            raise InvalidOAuthStateError("Project associated with OAuth state does not exist or is not owned by user.")

        return project, user


class GoogleOAuthService:
    """
    Service for orchestrating the Google OAuth2 authorization URL generation,
    code exchange, identity verification, and SearchConsoleConnection persistence.
    """
    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    @classmethod
    def get_oauth_config(cls) -> Dict[str, Any]:
        """
        Validate and retrieve Google OAuth settings.
        Raises ValueError if required settings are unconfigured.
        """
        client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '').strip()
        client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
        redirect_uri = getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', '').strip()
        scopes = getattr(settings, 'GOOGLE_OAUTH_SCOPES', [
            'https://www.googleapis.com/auth/webmasters.readonly',
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile',
        ])

        if not client_id:
            raise ValueError("GOOGLE_OAUTH_CLIENT_ID is not configured.")

        return {
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'scopes': scopes,
        }

    @classmethod
    def get_authorization_url(cls, project: Project, user: Any) -> str:
        """
        Generate a fully formed Google OAuth2 authorization URL with signed state.
        """
        config = cls.get_oauth_config()
        state = OAuthStateService.generate_state(user=user, project=project)

        scopes_str = " ".join(config['scopes']) if isinstance(config['scopes'], (list, tuple)) else str(config['scopes'])

        params = {
            'client_id': config['client_id'],
            'redirect_uri': config['redirect_uri'],
            'response_type': 'code',
            'scope': scopes_str,
            'state': state,
            'access_type': 'offline',
            'prompt': 'consent',
            'include_granted_scopes': 'true',
        }

        return f"{cls.GOOGLE_AUTH_URL}?{urlencode(params)}"

    @classmethod
    def exchange_code(
        cls,
        code: str,
        redirect_uri: Optional[str] = None,
        session: Optional[requests.Session] = None
    ) -> Dict[str, Any]:
        """
        Exchange an OAuth2 authorization code with Google for tokens.
        Never leaks client secrets in logs or exception messages.
        """
        if not code or not code.strip():
            raise GoogleOAuthExchangeError("Authorization code is required.")

        config = cls.get_oauth_config()
        target_redirect_uri = redirect_uri or config['redirect_uri']

        payload = {
            'code': code.strip(),
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'redirect_uri': target_redirect_uri,
            'grant_type': 'authorization_code',
        }

        http = session or requests.Session()
        try:
            response = http.post(cls.GOOGLE_TOKEN_URL, data=payload, timeout=15)
        except Exception as exc:
            logger.error(f"[GoogleOAuthService] Network error during token exchange: {exc}")
            raise GoogleOAuthExchangeError("Unable to reach Google OAuth services. Please try again.")

        try:
            data = response.json()
        except Exception:
            data = {}

        if response.status_code != 200 or 'error' in data:
            raw_error = data.get('error_description') or data.get('error') or f"HTTP {response.status_code}"
            # Sanitize error message to ensure no tokens or secrets leak
            sanitized_error = str(raw_error).replace(config['client_secret'], '[REDACTED]') if config['client_secret'] else str(raw_error)
            logger.warning(f"[GoogleOAuthService] Token exchange rejected by Google: {sanitized_error}")
            raise GoogleOAuthExchangeError(f"Google token exchange failed: {sanitized_error}")

        access_token = data.get('access_token')
        if not access_token:
            raise GoogleOAuthExchangeError("Google token exchange response did not include an access token.")

        return data

    @classmethod
    def fetch_user_identity(
        cls,
        access_token: str,
        id_token: Optional[str] = None,
        session: Optional[requests.Session] = None
    ) -> Dict[str, Any]:
        """
        Retrieve verified Google user email and identity details.
        """
        if not access_token:
            raise GoogleOAuthExchangeError("Access token required to fetch user identity.")

        http = session or requests.Session()
        headers = {'Authorization': f'Bearer {access_token}'}

        try:
            response = http.get(cls.GOOGLE_USERINFO_URL, headers=headers, timeout=10)
        except Exception as exc:
            logger.error(f"[GoogleOAuthService] Network error fetching userinfo: {exc}")
            raise GoogleOAuthExchangeError("Failed to fetch verified Google user identity.")

        if response.status_code != 200:
            logger.warning(f"[GoogleOAuthService] Google userinfo returned status {response.status_code}")
            raise GoogleOAuthExchangeError("Unable to verify Google user identity with the access token.")

        try:
            user_data = response.json()
        except Exception:
            user_data = {}

        email = user_data.get('email')
        if not email:
            raise GoogleOAuthExchangeError("Google account email could not be retrieved.")

        return {
            'email': email,
            'name': user_data.get('name', ''),
            'verified_email': user_data.get('email_verified', False),
            'picture': user_data.get('picture', ''),
        }

    @classmethod
    def complete_oauth_connection(
        cls,
        project: Project,
        token_data: Dict[str, Any],
        user_identity: Dict[str, Any]
    ) -> SearchConsoleConnection:
        """
        Create or update the SearchConsoleConnection for the specified project.
        Encrypts refresh token at rest and associates verified Google account metadata.
        """
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in')
        raw_scope = token_data.get('scope', '')

        # Parse scopes list
        if isinstance(raw_scope, str):
            scopes_list = [s.strip() for s in raw_scope.split(' ') if s.strip()]
        elif isinstance(raw_scope, list):
            scopes_list = raw_scope
        else:
            scopes_list = []

        token_expires_at = None
        if expires_in:
            try:
                token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))
            except (ValueError, TypeError):
                pass

        email = user_identity.get('email')

        # Check for existing connection for this project
        connection = SearchConsoleConnection.objects.filter(project=project).first()

        if connection:
            # Update existing connection
            if refresh_token:
                connection.set_refresh_token(refresh_token)
            elif not connection.has_oauth_token:
                # No new refresh token and none exists currently
                raise GoogleOAuthExchangeError(
                    "No refresh token was returned by Google and no previous token exists. "
                    "Please disconnect and reconnect with consent to allow offline access."
                )

            connection.google_account_email = email
            connection.scopes = scopes_list
            connection.token_expires_at = token_expires_at
            connection.is_connected = True
            connection.error_message = None
            connection.sync_status = SearchConsoleSyncStatus.IDLE
            connection.save()
            return connection

        # Create new connection
        if not refresh_token:
            raise GoogleOAuthExchangeError(
                "No refresh token was returned by Google. "
                "Please reconnect and grant offline access permissions."
            )

        # Construct default property URL from project website_url
        default_property = cls._derive_property_url(project.website_url)

        connection = SearchConsoleConnection(
            project=project,
            property_url=default_property,
            permission_level=SearchConsolePermission.SITE_OWNER,
            is_connected=True,
            google_account_email=email,
            scopes=scopes_list,
            token_expires_at=token_expires_at,
            sync_status=SearchConsoleSyncStatus.IDLE,
            error_message=None
        )
        connection.set_refresh_token(refresh_token)
        connection.save()
        return connection

    @classmethod
    def _derive_property_url(cls, website_url: Optional[str]) -> str:
        """
        Derive standard Google Search Console property format from website URL.
        """
        if not website_url:
            return "sc-domain:example.com"

        cleaned = website_url.strip()
        if not cleaned.startswith(('http://', 'https://')):
            cleaned = f"https://{cleaned}"

        try:
            parsed = urlparse(cleaned)
            hostname = parsed.hostname or cleaned
            hostname = hostname.replace('www.', '')
            return f"sc-domain:{hostname}"
        except Exception:
            return f"sc-domain:{cleaned}"
