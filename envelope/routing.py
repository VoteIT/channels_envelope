from django.urls import re_path

from envelope.consumers.websocket import WebsocketConsumer

websocket_urlpatterns = [
    re_path(r"ws/$", WebsocketConsumer.as_asgi()),
]
