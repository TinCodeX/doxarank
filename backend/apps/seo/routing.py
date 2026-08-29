"""
WebSocket URL routing for DoxaRank SEO app.

Maps WebSocket endpoints for agent execution live event streaming.
"""

from django.urls import re_path
from apps.seo.consumers import AgentEventConsumer

websocket_urlpatterns = [
    re_path(r"^ws/seo/ai/agent/runs/(?P<run_id>\d+)/?$", AgentEventConsumer.as_asgi()),
    re_path(r"^ws/api/seo/ai/agent/runs/(?P<run_id>\d+)/?$", AgentEventConsumer.as_asgi()),
    re_path(r"^ws/agent/runs/(?P<run_id>\d+)/?$", AgentEventConsumer.as_asgi()),
]
