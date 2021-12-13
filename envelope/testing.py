from envelope.decorators import add_message

# from envelope.decorators import add_message
from envelope.messages.base import AsyncRunnable
from envelope.messages.base import Message
from envelope.registry import MessageRegistry


# class TestingMessageRegistry(MessageRegistry):
#     global_registry = {}  # Override to they don't end up in global reg


testing_registry = MessageRegistry("testing")


@add_message("testing")
class WebsocketHello(AsyncRunnable):
    name = "testing.hello"

    async def run(self, consumer):
        pass


@add_message("testing")
class WebsocketWorld(Message):
    name = "testing.world"
