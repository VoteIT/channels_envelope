from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel
from envelope import WS_INCOMING
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from envelope import WS_OUTGOING
from envelope import INTERNAL
from envelope.core.message import AsyncRunnable
from envelope.core.message import Message
from envelope.decorators import add_message


if TYPE_CHECKING:
    from envelope.consumers.websocket import WebsocketConsumer

if not settings.DEBUG:
    raise ImproperlyConfigured(
        "%s should never be imported unless DEBUG mode is on." % __name__
    )


@add_message(INTERNAL, WS_INCOMING)
class SendClientInfo(AsyncRunnable):
    name = "s.send_client_info"

    async def run(self, *, consumer: WebsocketConsumer, **kwargs):
        response = ClientInfo.from_message(
            self, consumer_name=consumer.channel_name, lang=consumer.language
        )
        await consumer.send_ws_message(response)
        return response


class ClientInfoSchema(BaseModel):
    consumer_name: str
    lang: str | None


@add_message(WS_OUTGOING)
class ClientInfo(Message):
    data: ClientInfoSchema
    schema = ClientInfoSchema
    name = "s.client_info"
