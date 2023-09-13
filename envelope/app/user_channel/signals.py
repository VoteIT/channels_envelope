from __future__ import annotations
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.dispatch import receiver

from envelope.signals import client_close
from envelope.signals import client_connect
from envelope.app.user_channel.channel import UserChannel

if TYPE_CHECKING:
    from envelope.models import Connection


@receiver(client_connect)
def subscribe_client_to_users_channel(instance: Connection, **kw):
    user_channel = UserChannel.from_instance(
        instance.user, consumer_channel=instance.channel_name
    )
    async_to_sync(user_channel.subscribe)()


@receiver(client_close)
def leave_users_channel(
    instance: Connection,
    close_code: int | None,
    **kw,
):
    """
    Cleanup will probably be after the user object has been removed from the consumer.
    """
    user_channel = UserChannel.from_instance(
        instance.user, consumer_channel=instance.channel_name
    )
    async_to_sync(user_channel.leave)()
