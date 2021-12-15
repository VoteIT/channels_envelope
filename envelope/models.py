from datetime import datetime
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now


class Connection(models.Model):
    """
    These are created on websocket connect, and marked as online=False when client disconnects.
    Since channels doesn't handle any kind of cleanup, it's important to check these now and then.

    FIXME: we don't have any data checking on values like offline before online or the online bool setting.
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
    online_at: datetime = models.DateTimeField(
        verbose_name="Connection timestamp", default=now
    )
    offline_at: Optional[datetime] = models.DateTimeField(
        verbose_name="Disconnect timestamp", null=True, blank=True
    )
    # Note that last_action is not done automatically, so this is an estimate
    last_action: Optional[datetime] = models.DateTimeField(
        verbose_name="Last action", null=True, blank=True
    )

    class Meta:
        unique_together = (("user", "channel_name"),)

    # Annotations
    objects: models.Manager
