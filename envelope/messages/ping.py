from __future__ import annotations
from typing import TYPE_CHECKING

from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.decorators import add_message
from envelope.messages import AsyncRunnable
from envelope.messages import Message

if TYPE_CHECKING:
    from envelope.consumers.websocket import EnvelopeWebsocketConsumer


@add_message(WS_INCOMING, WS_OUTGOING)
class Ping(AsyncRunnable):
    name = "s.ping"

    async def run(self, consumer: EnvelopeWebsocketConsumer):
        if self.mm.registry != WS_OUTGOING:
            response = Pong.from_message(self)
            await consumer.send_ws_message(response, state=self.SUCCESS)


@add_message(WS_INCOMING, WS_OUTGOING)
class Pong(Message):
    name = "s.pong"
