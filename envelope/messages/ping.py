from __future__ import annotations
from typing import TYPE_CHECKING

from envelope import INTERNAL
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.decorators import add_message
from envelope.core.message import AsyncRunnable
from envelope.core.message import Message

if TYPE_CHECKING:
    from envelope.consumers.websocket import WebsocketConsumer


@add_message(WS_INCOMING, INTERNAL)
class Ping(AsyncRunnable):
    name = "s.ping"

    async def run(self, *, consumer: WebsocketConsumer, **kwargs):
        assert consumer
        response = Pong.from_message(self, state=self.SUCCESS)
        await consumer.send_ws_message(response)


@add_message(WS_OUTGOING)
class Pong(Message):
    name = "s.pong"
