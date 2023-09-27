from __future__ import annotations
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.dispatch import receiver

from envelope.app.online_channel.channel import OnlineChannel
from envelope.signals import connection_closed
from envelope.signals import connection_created

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


@receiver(connection_created)
def subscribe_client_to_online_channel(user: AbstractUser, consumer_name: str, **kw):
    ch = OnlineChannel(consumer_channel=consumer_name)
    async_to_sync(ch.subscribe)()


@receiver(connection_closed)
def cleanup_online_channel(
    user: AbstractUser | None,
    consumer_name: str,
    user_pk: int,
    close_code: int | None,
    **kw,
):
    ch = OnlineChannel(consumer_channel=consumer_name)
    async_to_sync(ch.leave)()
