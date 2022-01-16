from __future__ import annotations
from typing import Optional
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.dispatch import receiver

from envelope.app.online_channel.channel import OnlineChannel
from envelope.signals import client_close
from envelope.signals import client_connect

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


@receiver(client_connect)
def subscribe_client_to_online_channel(user: AbstractUser, consumer_name: str, **kw):
    ch = OnlineChannel(consumer_channel=consumer_name)
    async_to_sync(ch.subscribe)()


@receiver(client_close)
def cleanup_online_channel(
    user: Optional[AbstractUser],
    consumer_name: str,
    user_pk: int,
    close_code: Optional[int],
    **kw
):
    ch = OnlineChannel(consumer_channel=consumer_name)
    async_to_sync(ch.leave)()
