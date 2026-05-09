from django.urls import path

from apps.medic.consumers import NotificationConsumer

websocket_urlpatterns = [
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]
