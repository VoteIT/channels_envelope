"""
Note - these are the sync signals - there are async signals too!
"""

from django.contrib.auth import user_logged_out
from django.dispatch import receiver

from envelope import INTERNAL
from envelope.app.user_channel.channel import UserChannel
from envelope.messages.common import CloseConnection


@receiver(user_logged_out)
def send_close_connection(*, user, **kwargs):
    if user_pk := getattr(user, "pk", None):
        ch = UserChannel(user_pk, envelope_name=INTERNAL)
        msg = CloseConnection()
        ch.sync_publish(msg)
