from unittest.mock import patch

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.urls import re_path
from rq import Queue

from envelope.decorators import add_message

from envelope.core.message import AsyncRunnable
from envelope.core.message import Message
from envelope.core.registry import MessageRegistry
from envelope.core.registry import HandlerRegistry
from envelope.core.registry import ChannelRegistry


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


async def mk_communicator(user, queue: Queue = None):
    """
    A logged in user is required for this consumer.
    But async/sync doesn't mix well so we'll patch the user
    """
    from envelope.consumers.websocket import WebsocketConsumer

    init_kwargs = {}
    if queue:
        assert isinstance(queue, Queue)
        init_kwargs["connection_queue"] = queue
        init_kwargs["timestamp_queue"] = queue

    websocket_urlpatterns = [
        re_path(r"testws/$", WebsocketConsumer.as_asgi(**init_kwargs))
    ]
    application = ProtocolTypeRouter(
        {"websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns))}
    )
    communicator = WebsocketCommunicator(application, "/testws/")
    with patch.object(WebsocketConsumer, "get_user", return_value=user):
        connected, subprotocol = await communicator.connect()
        assert connected
    return communicator
