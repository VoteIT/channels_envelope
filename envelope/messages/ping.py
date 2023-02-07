from __future__ import annotations
from typing import TYPE_CHECKING

from envelope import INTERNAL
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.decorators import add_message
from envelope.core.message import AsyncRunnable
from envelope.core.message import Message

if TYPE_CHECKING:
    from envelope.consumer.websocket import WebsocketConsumer


@add_message(WS_INCOMING, WS_OUTGOING)
class Ping(AsyncRunnable):
    name = "s.ping"

    async def run(self, *, consumer: WebsocketConsumer, **kwargs):
        assert consumer
        if self.mm.registry != WS_OUTGOING:
            response = Pong.from_message(self, state=self.SUCCESS)
            await consumer.send_ws_message(response)


@add_message(WS_INCOMING, WS_OUTGOING, INTERNAL)
class Pong(Message):
    name = "s.pong"
