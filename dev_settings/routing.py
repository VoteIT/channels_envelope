from django.core.asgi import get_asgi_application

from django.urls import re_path

# Fetch Django ASGI application early to ensure AppRegistry is populated
# before importing consumers and AuthMiddlewareStack that may import ORM
# models.
django_asgi_app = get_asgi_application()

# from envelope.consumers.websocket import WebsocketConsumer
from envelope.consumers.websocket import WebsocketConsumer
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter


websocket_urlpatterns = [
    re_path(r"ws/$", WebsocketConsumer.as_asgi()),
]


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
