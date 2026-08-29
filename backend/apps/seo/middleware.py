"""
JWT Authentication Middleware for Django Channels WebSockets in DoxaRank.

Enables secure WebSocket authentication via:
1. Query string: ws://.../?token=<jwt_access_token>
2. Authorization header: Authorization: Bearer <jwt_access_token>
"""

import logging
from urllib.parse import parse_qs
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware

logger = logging.getLogger(__name__)
User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_str: str):
    """
    Validate SimpleJWT access token and retrieve corresponding User.
    Returns AnonymousUser if token is missing, expired, or invalid.
    """
    if not token_str:
        return AnonymousUser()
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken(token_str)
        user_id = token.get("user_id")
        if user_id:
            return User.objects.get(id=user_id)
    except Exception as exc:
        logger.debug(f"[JWTAuthMiddleware] Token validation failed: {exc}")
    return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Channels middleware that extracts and validates JWT tokens from WebSocket handshakes.
    """

    async def __call__(self, scope, receive, send):
        # Preserve user if already set and authenticated (e.g., in unit tests)
        user = scope.get("user")
        if user and user.is_authenticated:
            return await super().__call__(scope, receive, send)

        token = None

        # 1. Check query string: ?token=<jwt_token>
        query_string = scope.get("query_string", b"").decode("utf-8")
        if query_string:
            qs_params = parse_qs(query_string)
            token_list = qs_params.get("token")
            if token_list:
                token = token_list[0]

        # 2. Check headers: Authorization: Bearer <jwt_token>
        if not token:
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode("utf-8")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()

        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            if "user" not in scope or not scope["user"]:
                scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    """Convenience wrapper for JWT WebSocket authentication middleware."""
    return JWTAuthMiddleware(inner)
