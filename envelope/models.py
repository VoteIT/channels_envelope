from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class Connection(models.Model):
    """
    These are created on websocket connect, and marked as online=False when client disconnects.
    Since channels doesn't handle any kind of cleanup, it's important to check these now and then.
    """

    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="connections",
    )
    # device_id = models.CharField(max_lenght=100)
    channel_name: str = models.CharField(
        verbose_name="Consumers own channel name", max_length=100
    )
    # Is this considered to be online?
    online: bool = models.BooleanField(default=True)
    # Did this connection disappear without closing properly?
    awol: bool = models.BooleanField(default=False)
    # IP?
    first_seen = models.DateTimeField(
        auto_now_add=True, verbose_name="When the connection was made"
    )
    # Note that last_action is not done automatically, so this is an estimate
    last_action = models.DateTimeField(auto_now=True, verbose_name="Last action")
    last_query = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Last time we sent a message to the consumer to check if it's online.",
    )

    class Meta:
        unique_together = (("user", "channel_name"),)

    # Annotations
    objects: models.Manager
