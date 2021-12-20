from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Optional
from typing import Set
from typing import TYPE_CHECKING

from channels.layers import get_channel_layer
from django.db import models
from django.db import transaction
from django.utils.functional import cached_property

from envelope import Error
from envelope import WS_SEND_TRANSPORT
from envelope.utils import SenderUtil
from envelope.utils import get_error_type

if TYPE_CHECKING:
    from envelope.messages import Message
    from envelope.envelope import Envelope


class PubSubChannel(ABC):
    """
    A generic publish/subscribe that works with channels groups.

    """

    consumer_channel: Optional[str]
    envelope: Envelope
    # Expect transported messages in dict or string format?
    dict_transport: bool = False
    # Override to set another kind of transport
    # Note that the consumer needs a method corresponding to the transport type.
    # See channels docs
    transport: str = WS_SEND_TRANSPORT
    # Override to support different channel layers
    channel_layer = get_channel_layer()

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
        consumer_channel: Optional[str] = None,
    ):

        self.consumer_channel = consumer_channel

    def __init_subclass__(cls, **kwargs):
        cls.__registries = set()
        super().__init_subclass__(**kwargs)

    @classmethod
    def registries(cls) -> Set:
        return cls.__registries

    @classmethod
    def from_consumer(cls, consumer):
        return cls(consumer_channel=consumer.channel_name)

    async def subscribe(self):
        assert self.consumer_channel
        await self.channel_layer.group_add(self.channel_name, self.consumer_channel)

    async def leave(self):
        assert self.consumer_channel
        await self.channel_layer.group_discard(self.channel_name, self.consumer_channel)

    async def publish(self, message: Message):
        sender = self.create_sender(message)
        await sender.async_send()

    def sync_publish(self, message: Message, on_commit=True):
        sender = self.create_sender(message)
        if on_commit:
            transaction.on_commit(sender)
        else:
            sender()

    def create_sender(self, message: Message) -> SenderUtil:
        self.envelope.is_compatible(message, exception=True)
        envelope = self.envelope.pack(message)
        return SenderUtil(
            envelope,
            self.channel_name,
            group=True,
            transport=self.transport,
            as_dict=False,
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
        consumer_channel: Optional[str] = None,
    ):
        self.pk = pk
        super().__init__(consumer_channel)

    @property
    def channel_name(self) -> str:
        """
        Default naming - use a unique name and the objects pk.
        """
        return f"{self.name}_{self.pk}"

    @property
    @abstractmethod
    def model(self) -> models.Model:
        """
        Set as property on subclass. Model should be the type of model this object channel is for.
        """

    @property
    @abstractmethod
    def permission(self) -> Optional[str]:
        """
        Set as property on subclass. The permission to evaluate subscribe commands against.
        If None is set, permission checks will be skipped.
        """

    @classmethod
    def from_instance(
        cls, instance: models.Model, consumer_channel: Optional[str] = None
    ) -> ContextChannel:
        assert isinstance(instance, cls.model), f"Instance must be a {cls.model}"
        inst = cls(instance.pk, consumer_channel)
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
