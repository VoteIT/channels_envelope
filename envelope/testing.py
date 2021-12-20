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
