from __future__ import annotations
from typing import TYPE_CHECKING

from async_signals import receiver
from django.conf import settings

from envelope import INTERNAL
from envelope.async_signals import consumer_connected
from envelope.async_signals import consumer_closed
from envelope.app.user_channel.channel import UserChannel
from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed
from envelope.utils import get_envelope

if TYPE_CHECKING:
    from envelope.consumers.websocket import WebsocketConsumer


@receiver(consumer_connected)
async def subscribe_client_to_users_channel(*, consumer: WebsocketConsumer, **kw):
    if consumer.user_pk:
        ch = UserChannel(consumer.user_pk, consumer_channel=consumer.channel_name)
        await ch.subscribe()
        # Subscribe message or just add?
        if getattr(settings, "ENVELOPE_USER_CHANNEL_SEND_SUBSCRIBE", None):
            mm = consumer.get_msg_meta()
            mm.env = INTERNAL
            msg = Subscribe(
                mm=mm,
                channel_type=UserChannel.name,
                pk=consumer.user_pk,
            )
            envelope = get_envelope(INTERNAL)
            await consumer.signal_message(msg, envelope=envelope)
        else:
            # Avoid subscribe message, simply add to channel
            msg = Subscribed(
                channel_name=ch.channel_name, pk=consumer.user_pk, channel_type=ch.name
            )
            await consumer.send_ws_message(msg)


@receiver(consumer_closed)
async def leave_users_channel_on_disconnect(
    *,
    consumer: WebsocketConsumer,
    **kw,
):
    """
    Cleanup will probably be after the user object has been removed from the consumer.
    """
    if consumer.user_pk:
        ch = UserChannel(consumer.user_pk, consumer_channel=consumer.channel_name)
        await ch.leave()
