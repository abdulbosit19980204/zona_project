"""ASGI: HTTP (Django) + WebSocket (Channels). runserver (daphne) va ishlab chiqarish shu faylni ishlatadi:
    daphne -b 0.0.0.0 -p 8000 config.asgi:application
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_app = get_asgi_application()  # modellar yuklanishi uchun avval

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from zona.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_app,
    "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),
})
