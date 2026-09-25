import logging
import secrets
import time
from datetime import timedelta
from typing import Optional, Tuple, Dict, Any, List
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.integrations.models import (
    IntegrationConnection,
    IntegrationProvider,
    IntegrationStatus,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class InvalidOAuthStateError(Exception):
    """Raised when an OAuth state parameter is invalid, forged, expired, or replayed."""
    pass


class GoogleOAuthExchangeError(Exception):
    """Raised when Google OAuth token exchange, profile retrieval, or refresh fails."""
    pass


class OAuthStateService:
    """
    Cryptographic state generation and validation service for OAuth2 flows.
    Ensures protection against CSRF, replay attacks, tenant forgery, and tampering.
    """
    STATE_SALT = 'google_oauth_user_state'
    DEFAULT_MAX_AGE_SECONDS = 600  # 10 minutes TTL

    @classmethod
    def get_signer(cls) -> TimestampSigner:
        return TimestampSigner(salt=cls.STATE_SALT)

    @classmethod
    def generate_state(cls, user: Any, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate a cryptographically signed state token embedding user ID,
        random cryptographic nonce, and issue timestamp.
        """
        nonce = secrets.token_urlsafe(24)
        payload = {
            'user_id': user.id,
            'nonce': nonce,
            'ts': int(time.time()),
            'meta': metadata or {}
        }
        signer = cls.get_signer()
        return signer.sign_object(payload)

    @classmethod
    def verify_state(
        cls,
        raw_state: Optional[str],
        expected_user: Optional[Any] = None,
        max_age: int = DEFAULT_MAX_AGE_SECONDS
    ) -> Tuple[Any, Dict[str, Any]]:
        """
        Verify the signature, expiration, and replay status of the given state token.
        Returns the resolved (User, metadata) tuple upon success.
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
        nonce = payload.get('nonce')
        meta = payload.get('meta', {})

        if not user_id or not nonce:
            raise InvalidOAuthStateError("Incomplete OAuth state payload.")

        # Replay protection: Check if nonce was already consumed
        nonce_cache_key = f"google_oauth_nonce_used:{nonce}"
        if cache.get(nonce_cache_key):
            logger.warning(f"[OAuthStateService] Replay attack detected for nonce: {nonce[:8]}...")
            raise InvalidOAuthStateError("This OAuth authorization state has already been used.")

        # Mark nonce as consumed for max_age window
        cache.set(nonce_cache_key, True, timeout=max_age)

        # Resolve User
        user = User.objects.filter(id=user_id).first()
        if not user:
            raise InvalidOAuthStateError("User associated with OAuth state no longer exists.")

        if expected_user and expected_user.is_authenticated and expected_user.id != user.id:
            raise InvalidOAuthStateError("OAuth state user does not match the currently authenticated user.")

        return user, meta


class GoogleOAuthIntegrationService:
    """
    Reusable service for managing Google OAuth2 connections across DoxaRank.
    Provides authorization URL generation, code exchange, token encryption at rest,
    profile retrieval, token refresh, and safe disconnection.
    """
    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
    GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

    @classmethod
    def get_oauth_config(cls) -> Dict[str, Any]:
        """
        Validate and retrieve Google OAuth settings.
        Accepts either GOOGLE_CLIENT_ID or GOOGLE_OAUTH_CLIENT_ID conventions.
        """
        client_id = (
            getattr(settings, 'GOOGLE_CLIENT_ID', None)
            or getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
        ).strip()
        client_secret = (
            getattr(settings, 'GOOGLE_CLIENT_SECRET', None)
            or getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '')
        ).strip()
        redirect_uri = (
            getattr(settings, 'GOOGLE_REDIRECT_URI', None)
            or getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:5173/integrations/google/callback')
        ).strip()
        scopes = getattr(settings, 'GOOGLE_OAUTH_SCOPES', [
            'https://www.googleapis.com/auth/webmasters.readonly',
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile',
        ])

        if not client_id:
            raise ValueError("GOOGLE_CLIENT_ID is not configured in settings.")

        return {
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'scopes': scopes,
        }

    @classmethod
    def get_authorization_url(
        cls,
        user: Any,
        redirect_uri: Optional[str] = None,
        extra_scopes: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a fully formed Google OAuth2 authorization URL with signed state.
        """
        config = cls.get_oauth_config()
        state = OAuthStateService.generate_state(user=user, metadata=metadata)

        scopes = list(config['scopes'])
        if extra_scopes:
            for s in extra_scopes:
                if s not in scopes:
                    scopes.append(s)

        scopes_str = " ".join(scopes)
        target_redirect_uri = redirect_uri or config['redirect_uri']

        params = {
            'client_id': config['client_id'],
            'redirect_uri': target_redirect_uri,
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
        Exchange an OAuth2 authorization code with Google for access and refresh tokens.
        Never logs client secrets or raw tokens.
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
            logger.error(f"[GoogleOAuthIntegration] Network error during token exchange: {exc}")
            raise GoogleOAuthExchangeError("Unable to reach Google OAuth services. Please try again.")

        try:
            data = response.json()
        except Exception:
            data = {}

        if response.status_code != 200 or 'error' in data:
            raw_error = data.get('error_description') or data.get('error') or f"HTTP {response.status_code}"
            sanitized = str(raw_error).replace(config['client_secret'], '[REDACTED]') if config['client_secret'] else str(raw_error)
            logger.warning(f"[GoogleOAuthIntegration] Token exchange rejected: {sanitized}")
            raise GoogleOAuthExchangeError(f"Google token exchange failed: {sanitized}")

        access_token = data.get('access_token')
        if not access_token:
            raise GoogleOAuthExchangeError("Google token exchange did not return an access token.")

        return data

    @classmethod
    def fetch_user_identity(
        cls,
        access_token: str,
        session: Optional[requests.Session] = None
    ) -> Dict[str, Any]:
        """
        Retrieve verified Google user profile and email.
        """
        if not access_token:
            raise GoogleOAuthExchangeError("Access token required to fetch user identity.")

        http = session or requests.Session()
        headers = {'Authorization': f'Bearer {access_token}'}

        try:
            response = http.get(cls.GOOGLE_USERINFO_URL, headers=headers, timeout=10)
        except Exception as exc:
            logger.error(f"[GoogleOAuthIntegration] Network error fetching userinfo: {exc}")
            raise GoogleOAuthExchangeError("Failed to fetch verified Google user identity.")

        if response.status_code != 200:
            logger.warning(f"[GoogleOAuthIntegration] Google userinfo returned status {response.status_code}")
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
            'id': user_data.get('sub', ''),
            'verified_email': user_data.get('email_verified', False),
            'picture': user_data.get('picture', ''),
        }

    @classmethod
    def save_or_update_connection(
        cls,
        user: Any,
        token_data: Dict[str, Any],
        user_identity: Dict[str, Any]
    ) -> IntegrationConnection:
        """
        Create or update the user's Google IntegrationConnection record.
        Encrypts access and refresh tokens symmetrically at rest.
        """
        access_token = token_data.get('access_token')
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
        name = user_identity.get('name', '')
        sub_id = user_identity.get('id', '')

        connection, created = IntegrationConnection.objects.get_or_create(
            user=user,
            provider=IntegrationProvider.GOOGLE,
            defaults={
                'status': IntegrationStatus.CONNECTED,
                'account_email': email,
                'account_name': name,
                'account_id': sub_id,
                'token_expires_at': token_expires_at,
                'scopes': scopes_list,
                'metadata': {'picture': user_identity.get('picture', '')}
            }
        )

        if not created:
            connection.status = IntegrationStatus.CONNECTED
            connection.account_email = email
            connection.account_name = name
            connection.account_id = sub_id
            connection.token_expires_at = token_expires_at
            if scopes_list:
                connection.scopes = scopes_list
            connection.metadata = {'picture': user_identity.get('picture', '')}

        # Handle tokens
        if access_token:
            connection.set_access_token(access_token)

        if refresh_token:
            connection.set_refresh_token(refresh_token)
        elif not connection.get_refresh_token():
            logger.warning(
                f"[GoogleOAuthIntegration] No refresh token returned for user #{user.id}. "
                "Offline access may require re-consent."
            )

        connection.save()
        logger.info(f"[GoogleOAuthIntegration] Successfully connected Google account ({email}) for user #{user.id}")
        return connection

    @classmethod
    def disconnect(cls, user: Any) -> bool:
        """
        Disconnect user's Google integration, revoke tokens if possible,
        and clear sensitive credentials from storage.
        """
        connection = IntegrationConnection.objects.filter(
            user=user,
            provider=IntegrationProvider.GOOGLE
        ).first()

        if not connection:
            return False

        # Attempt token revocation at Google (best effort)
        token_to_revoke = connection.get_refresh_token() or connection.get_access_token()
        if token_to_revoke:
            try:
                requests.post(
                    cls.GOOGLE_REVOKE_URL,
                    params={'token': token_to_revoke},
                    headers={'content-type': 'application/x-www-form-urlencoded'},
                    timeout=5
                )
            except Exception as exc:
                logger.warning(f"[GoogleOAuthIntegration] Token revocation request failed (ignored): {exc}")

        connection.status = IntegrationStatus.DISCONNECTED
        connection.encrypted_access_token = None
        connection.encrypted_refresh_token = None
        connection.token_expires_at = None
        connection.save(update_fields=[
            'status',
            'encrypted_access_token',
            'encrypted_refresh_token',
            'token_expires_at',
            'updated_at'
        ])
        logger.info(f"[GoogleOAuthIntegration] Disconnected Google account for user #{user.id}")
        return True

    @classmethod
    def refresh_connection_tokens(
        cls,
        connection: IntegrationConnection,
        session: Optional[requests.Session] = None
    ) -> IntegrationConnection:
        """
        Refresh access token using the stored encrypted refresh token if expired.
        Updates connection with fresh access token and new expiry timestamp.
        """
        if not connection.is_token_expired(buffer_seconds=120) and connection.get_access_token():
            return connection

        raw_refresh_token = connection.get_refresh_token()
        if not raw_refresh_token:
            connection.status = IntegrationStatus.EXPIRED
            connection.save(update_fields=['status', 'updated_at'])
            raise GoogleOAuthExchangeError("Google refresh token is missing. Please reconnect Google account.")

        config = cls.get_oauth_config()
        payload = {
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'refresh_token': raw_refresh_token,
            'grant_type': 'refresh_token',
        }

        http = session or requests.Session()
        try:
            response = http.post(cls.GOOGLE_TOKEN_URL, data=payload, timeout=15)
        except Exception as exc:
            logger.error(f"[GoogleOAuthIntegration] Failed to refresh token: {exc}")
            raise GoogleOAuthExchangeError("Network error while refreshing Google access token.")

        try:
            data = response.json()
        except Exception:
            data = {}

        if response.status_code != 200 or 'error' in data:
            error_desc = data.get('error_description') or data.get('error') or f"HTTP {response.status_code}"
            logger.warning(f"[GoogleOAuthIntegration] Google rejected token refresh: {error_desc}")
            connection.status = IntegrationStatus.EXPIRED
            connection.save(update_fields=['status', 'updated_at'])
            raise GoogleOAuthExchangeError("Google authorization has expired or been revoked. Please reconnect.")

        new_access_token = data.get('access_token')
        expires_in = data.get('expires_in', 3600)

        if not new_access_token:
            raise GoogleOAuthExchangeError("Token refresh did not return an access token.")

        connection.set_access_token(new_access_token)
        connection.token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))

        # Some providers rotate the refresh token
        new_refresh = data.get('refresh_token')
        if new_refresh:
            connection.set_refresh_token(new_refresh)

        connection.status = IntegrationStatus.CONNECTED
        connection.save(update_fields=[
            'encrypted_access_token',
            'encrypted_refresh_token',
            'token_expires_at',
            'status',
            'updated_at'
        ])
        return connection
