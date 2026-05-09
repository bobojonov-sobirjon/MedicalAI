"""
ASGI config: HTTP (Django) + WebSocket (Channels) для уведомлений в реальном времени.
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

from config.middleware.tokenauth_middleware import TokenAuthMiddleware
from config.routing import websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": TokenAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
