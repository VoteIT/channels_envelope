from __future__ import annotations
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.dispatch import receiver

from envelope.signals import connection_closed
from envelope.signals import connection_created
from envelope.app.user_channel.channel import UserChannel

if TYPE_CHECKING:
    from envelope.models import Connection


@receiver(connection_created)
def subscribe_client_to_users_channel(*, instance: Connection, **kw):
    user_channel = UserChannel.from_instance(
        instance.user, consumer_channel=instance.channel_name
    )
    async_to_sync(user_channel.subscribe)()


@receiver(connection_closed)
def leave_users_channel(
    *,
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
