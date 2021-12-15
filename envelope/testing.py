from envelope.decorators import add_message

from envelope.messages.base import AsyncRunnable
from envelope.messages.base import Message
from envelope.registry import MessageRegistry
from envelope.registry import HandlerRegistry


testing_messages = MessageRegistry("testing")
testing_handlers = HandlerRegistry("testing")


@add_message("testing")
class WebsocketHello(AsyncRunnable):
    name = "testing.hello"

    async def run(self, consumer):
        pass


@add_message("testing")
class WebsocketWorld(Message):
    name = "testing.world"
