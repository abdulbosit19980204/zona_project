"""WebSocket manzillari. Xost loyihaning asgi.py faylida ulanadi (backend/config/asgi.py ga qarang)."""
from django.urls import path

from .realtime import EventsConsumer, JWTAuthMiddleware

websocket_urlpatterns = [
    path("ws/events/", JWTAuthMiddleware(EventsConsumer.as_asgi())),
]
