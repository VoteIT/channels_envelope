from __future__ import annotations

from abc import ABC
from typing import Set
from typing import List
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type

from django.utils.translation import gettext as _
from pydantic import BaseModel
from pydantic import validator

from envelope import Error
from envelope import INTERNAL
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.decorators import add_message
from envelope.messages import AsyncRunnable
from envelope.messages import Message
from envelope.messages.actions import DeferredJob
from envelope.signals import channel_left
from envelope.signals import channel_subscribed
from envelope.utils import AppState
from envelope.utils import get_channel_registry
from envelope.utils import get_error_type

if TYPE_CHECKING:
    from envelope.channels import ContextChannel
    from envelope.envelope import OutgoingEnvelopeSchema

    # from voteit.messaging.consumers import WebsocketDemuxConsumer


SUBSCRIBE = "channel.subscribe"
LEAVE = "channel.leave"

SUBSCRIBED = "channel.subscribed"
LEFT = "channel.left"


class ChannelSchema(BaseModel):
    pk: int
    channel_type: str

    @validator("channel_type", allow_reuse=True)
    def real_channel_type(cls, v):
        cr = get_channel_registry()
        v = v.lower()
        if v not in cr:  # pragma: no cover
            raise ValueError(f"'{v}' is not a valid channel")
        return v


class ChannelSubscription(ChannelSchema):
    """
    Track subscriptions to protected channels.
    """

    channel_name: str
    app_state: Optional[List[OutgoingEnvelopeSchema]]


class BaseChannelCommand(DeferredJob, ABC):
    schema = ChannelSchema
    data: ChannelSchema

    def get_channel(
        self, channel_type: str, pk: int, consumer_name: str
    ) -> ContextChannel:
        cr = get_channel_registry()
        # This may cause errors right?
        return cr[channel_type](pk, consumer_name)


@add_message(WS_INCOMING)
class Subscribe(BaseChannelCommand):
    name = SUBSCRIBE

    def get_app_state(self, channel: ContextChannel) -> Optional[list]:
        """
        Dispatch signal to populate app_state object, and return as list object or None
        """
        app_state = AppState()
        channel_subscribed.send(
            sender=channel.__class__,
            context=channel.context,
            user=self.user,
            app_state=app_state,
        )
        if app_state:
            return list(app_state)

    def run_job(self) -> Subscribed:
        channel = self.get_channel(
            self.data.channel_type, self.data.pk, self.mm.consumer_name
        )
        if channel.allow_subscribe(self.user):
            channel.subscribe()
            app_state = self.get_app_state(channel)
            msg = Subscribed.from_message(
                self,
                channel_name=channel.channel_name,
                app_state=app_state,
                **self.data.dict(),
            )
            msg.send_outgoing(self.mm.consumer_name, success=True)
            return msg
        else:
            raise get_error_type(Error.SUBSCRIBE).from_message(
                self,
                channel_name=channel.channel_name,
            )


@add_message(WS_INCOMING)
class Leave(BaseChannelCommand):
    name = LEAVE

    def run_job(self) -> Left:
        # This is without permission checks since there's no reason to go Hotel California on consumers.
        channel = self.get_channel(
            self.data.channel_type, self.data.pk, self.mm.consumer_name
        )
        channel.leave()
        msg = Left.from_message(
            self, channel_name=channel.channel_name, **self.data.dict()
        )
        msg.send_outgoing(self.mm.consumer_name, success=True)
        channel_left.send(
            sender=channel.__class__, context=channel.context, user=self.user
        )
        return msg


@add_message(WS_OUTGOING)
class Subscribed(AsyncRunnable):
    name = SUBSCRIBED
    schema = ChannelSubscription
    data: ChannelSubscription

    async def run(self, consumer):
        subscription = ChannelSchema(**self.data.dict())
        consumer.mark_subscribed(subscription)


@add_message(WS_OUTGOING)
class Left(AsyncRunnable):
    name = LEFT
    schema = ChannelSubscription
    data: ChannelSubscription

    async def run(self, consumer):
        consumer.mark_left(self.data)


class RecheckSubscriptionsSchema(BaseModel):
    subscriptions: Set[ChannelSchema] = []
    consumer_name: Optional[str]


@add_message(INTERNAL)
class RecheckChannelSubscriptions(DeferredJob):
    """
    Send this as an internal message to ask the consumer to
    recheck that it's authorized to subscribe to different channels.

    This is not the same as logging out, rather this is something you may want
    to do when a specific user has new permissions.
    """

    name = "channel.recheck"
    schema = RecheckSubscriptionsSchema
    data: RecheckSubscriptionsSchema

    async def pre_queue(self, consumer):
        self.data.consumer_name = (
            consumer.channel_name
        )  # It might be sent by someone else
        self.data.subscriptions.update(consumer.subscriptions)

    @property
    def should_run(self) -> bool:
        return bool(self.data.subscriptions)

    def run_job(self):
        registry = get_channel_registry()
        # We don't really know if someone is subscribing due to how channels work, but we won't resubscribe
        for channel_info in self.data.subscriptions:
            channel_info: ChannelSchema
            ch_class: Type[ContextChannel] = registry[channel_info.channel_type]
            if not issubclass(ch_class, ContextChannel):
                continue
            ch = ch_class(channel_info.pk, consumer_channel=self.data.consumer_name)
            if not ch.allow_subscribe(self.user):
                ch.leave()
                msg = Left.from_message(
                    self,
                    channel_name=ch.channel_name,
                    channel_type=channel_info.channel_type,
                    pk=channel_info.pk,
                )
                msg.send_outgoing(self.mm.consumer_name, success=True, on_commit=False)
