from __future__ import annotations
from typing import TYPE_CHECKING

from async_signals import receiver

from envelope.app.online_channel.channel import OnlineChannel
from envelope.async_signals import consumer_connected
from envelope.async_signals import consumer_closed

if TYPE_CHECKING:
    from envelope.consumers.websocket import WebsocketConsumer


@receiver(consumer_connected)
async def subscribe_on_connect(*, consumer: WebsocketConsumer, **kw):
    ch = OnlineChannel(consumer_channel=consumer.channel_name)
    await ch.subscribe()


@receiver(consumer_closed)
async def leave_on_disconnect(
    *,
    consumer: WebsocketConsumer,
    **kw,
):
    ch = OnlineChannel(consumer_channel=consumer.channel_name)
    await ch.leave()
