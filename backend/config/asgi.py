"""
ASGI config for DoxaRank project.

It exposes the ASGI callable as a module-level variable named ``application``.
Routes standard HTTP traffic to Django ASGI application and WebSocket traffic
to Django Channels with JWT authentication.
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from apps.seo.routing import websocket_urlpatterns
from apps.seo.middleware import JWTAuthMiddlewareStack

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
