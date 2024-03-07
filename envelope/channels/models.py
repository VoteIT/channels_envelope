from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from collections import UserList
from typing import TYPE_CHECKING

from channels import DEFAULT_CHANNEL_LAYER
from channels.layers import get_channel_layer
from django.db import models
from django.utils.functional import cached_property

from envelope import Error
from envelope import WS_OUTGOING
from envelope.utils import SenderUtil
from envelope.utils import get_error_type
from envelope.utils import get_or_create_txn_sender

if TYPE_CHECKING:
    from envelope.core.message import Message
    from django.db.models import Model


class PubSubChannel(ABC):
    """
    A generic publish/subscribe that works with channels groups.
    """

    consumer_channel: str | None
    # Override to support different channel layers
    envelope_name = WS_OUTGOING
    layer_name = DEFAULT_CHANNEL_LAYER

    @property
    @abstractmethod
    def name(self) -> str:
        """
        The name of the channel factory, not the specific channel name.
        """

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """
        Return name of this channel. Must be unique for each channel.
        """

    def __init__(
        self,
        consumer_channel: str | None = None,
        *,
        envelope_name: str | None = None,
        layer_name: str | None = None,
    ):
        self.consumer_channel = consumer_channel
        if envelope_name:
            self.envelope_name = envelope_name
        if layer_name:
            self.layer_name = layer_name

    async def subscribe(self):
        if not self.consumer_channel:  # pragma: no coverage
            raise ValueError("No consumer_channel specified")
        layer = get_channel_layer(self.layer_name)
        await layer.group_add(self.channel_name, self.consumer_channel)

    async def leave(self):
        assert self.consumer_channel
        layer = get_channel_layer(self.layer_name)
        await layer.group_discard(self.channel_name, self.consumer_channel)

    async def publish(self, message: Message):
        sender = self.create_sender(message)
        await sender.async_send()

    def sync_publish(self, message: Message, on_commit=True):
        sender = self.create_sender(message)
        if on_commit:
            txn_sender = get_or_create_txn_sender()
            if txn_sender is None:
                sender()
            else:
                txn_sender.add(sender)
        else:
            sender()

    def create_sender(self, message: Message) -> SenderUtil:
        return SenderUtil(
            message,
            channel_name=self.channel_name,
            envelope=self.envelope_name,
            group=True,
        )


class ContextChannel(PubSubChannel, ABC):
    """
    A channel that has to do with a specific object. For instance a logger in user.
    Context channels can check permissions against their context.
    """

    pk: int  # Primary key of the object that this channel is about

    def __init__(
        self,
        pk: int,
        consumer_channel: str | None = None,
        *,
        envelope_name: str | None = None,
        layer_name: str | None = None,
    ):
        self.pk = pk
        super().__init__(
            consumer_channel=consumer_channel,
            envelope_name=envelope_name,
            layer_name=layer_name,
        )

    @property
    def channel_name(self) -> str:
        """
        Default naming - use a unique name and the objects pk.
        """
        return f"{self.name}_{self.pk}"

    @property
    @abstractmethod
    def model(self) -> type[models.Model]:
        """
        Set as property on subclass. Model should be the type of model this object channel is for.
        """

    @property
    @abstractmethod
    def permission(self) -> str | None:
        """
        Set as property on subclass. The permission to evaluate subscribe commands against.
        If None is set, permission checks will be skipped.
        """

    @classmethod
    def from_instance(
        cls,
        instance: models.Model,
        consumer_channel: str | None = None,
        *,
        envelope_name: str | None = None,
        layer_name: str | None = None,
    ) -> ContextChannel:
        assert isinstance(instance, cls.model), f"Instance must be a {cls.model}"
        inst = cls(
            instance.pk,
            consumer_channel=consumer_channel,
            envelope_name=envelope_name,
            layer_name=layer_name,
        )
        # Set context straight away to avoid lookup
        inst.context = instance
        return inst

    @cached_property
    def context(self) -> models.Model:
        try:
            return self.model.objects.get(pk=self.pk)
        except self.model.DoesNotExist:
            mm = {"consumer_name": self.consumer_channel}  # May not exist
            raise get_error_type(Error.NOT_FOUND)(
                mm=mm, model=self.model, key="pk", value=self.pk
            )

    def allow_subscribe(self, user):
        """
        Call this before subscribing. Due to sync/async and the complexity of
        permissions this won't be enforced before calling subscribe.
        """
        if self.permission is None:
            return True
        if user is None:
            return False
        if self.context is None:
            return False
        return user.has_perm(self.permission, self.context)


class AppState(UserList):
    """
    Attach several messages to a subscribed response. It's built for websocket application states.
    """

    def append(self, item: Message) -> None:
        """
        Append an outgoing message to another message. Used by pubsub and similar.
        """
        super().append(
            dict(
                t=item.name,
                p=item.data,
            )
        )
