from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now


if TYPE_CHECKING:
    from envelope.utils import SenderUtil


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


class TransactionSender:
    def __init__(self):
        self.data = []

    def __call__(self):
        self.batch_messages()
        for x in self:
            x()

    def batch_messages(self):
        """
        Go through all messages and batch them if possible
        """
        # Probably configurable later on
        from envelope.messages.common import Batch
        from envelope.utils import SenderUtil

        regrouped = defaultdict(list)
        for util in self.data:
            regrouped[util.group_key].append(util)
        for k, items in regrouped.items():
            if len(items) < 3 or not items[0].batch:
                continue
            initial_util = items.pop(0)
            batch = Batch.start(initial_util.msg)
            for util in items:
                batch.append(util.msg)
            items[:] = [
                SenderUtil(
                    batch,
                    channel_name=initial_util.channel_name,
                    group=initial_util.group,
                    as_dict=initial_util.as_dict,
                    run_handlers=initial_util.run_handlers,
                    state=initial_util.state,
                )
            ]
        data = []
        for v in regrouped.values():
            data.extend(v)
        self.data = data

    def add(self, sender_util: SenderUtil):
        self.data.append(sender_util)

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)
