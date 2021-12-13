from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.decorators import add_message
from envelope.messages.base import AsyncRunnable
from envelope.messages.base import Message
from envelope.messages.base import AsyncRunnable


@add_message(WS_INCOMING, WS_OUTGOING)
class Ping(AsyncRunnable):
    name = "s.ping"

    async def run(self, consumer):
        if self.message.mm.registry != WS_OUTGOING:
            response = Pong.from_message(self)
            consumer.send(response, state=self.SUCCESS)


@add_message(WS_INCOMING, WS_OUTGOING)
class Pong(Message):
    name = "s.pong"
