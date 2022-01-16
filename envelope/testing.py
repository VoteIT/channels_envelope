from unittest.mock import patch

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.urls import re_path

from envelope.decorators import add_message

from envelope.messages import AsyncRunnable
from envelope.messages import Message
from envelope.registry import MessageRegistry
from envelope.registry import HandlerRegistry
from envelope.registry import ChannelRegistry


testing_messages = MessageRegistry("testing")
testing_handlers = HandlerRegistry("testing")
testing_channels = ChannelRegistry("testing")


@add_message("testing")
class WebsocketHello(AsyncRunnable):
    name = "testing.hello"

    async def run(self, consumer):
        pass


@add_message("testing")
class WebsocketWorld(Message):
    name = "testing.world"


async def mk_communicator(user):
    """
    A logged in user is required for this consumer.
    But async/sync doesn't mix well so we'll patch the user
    """
    from envelope.consumers.websocket import EnvelopeWebsocketConsumer

    websocket_urlpatterns = [re_path(r"testws/$", EnvelopeWebsocketConsumer.as_asgi())]
    application = ProtocolTypeRouter(
        {"websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns))}
    )
    communicator = WebsocketCommunicator(application, "/testws/")
    with patch.object(EnvelopeWebsocketConsumer, "get_user", return_value=user):
        connected, subprotocol = await communicator.connect()
        assert connected
    return communicator
