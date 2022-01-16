from __future__ import annotations
from typing import Optional
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.dispatch import receiver

from envelope.signals import client_close
from envelope.signals import client_connect
from envelope.app.user_channel.channel import UserChannel

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


@receiver(client_connect)
def subscribe_client_to_users_channel(user: AbstractUser, consumer_name: str, **kw):
    user_channel = UserChannel.from_instance(user, consumer_channel=consumer_name)
    async_to_sync(user_channel.subscribe)()


@receiver(client_close)
def cleanup_users_channel(
    user: Optional[AbstractUser],
    consumer_name: str,
    user_pk: int,
    close_code: Optional[int],
    **kw
):
    """
    Cleanup will probably be after the user object has been removed from the consumer,
    so don't trust the user arg here!
    """
    user_channel = UserChannel(pk=user_pk, consumer_channel=consumer_name)
    async_to_sync(user_channel.leave)()
