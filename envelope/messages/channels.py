from __future__ import annotations

from abc import ABC
from typing import List
from typing import Optional
from typing import TYPE_CHECKING

from django.utils.translation import gettext as _
from pydantic import BaseModel
from pydantic import validator
from voteit.messaging import signals
from voteit.messaging.abcs import AbstractObjectChannel
from voteit.messaging.abcs import AsyncRunnable
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.envelopes import BaseEnvelope
from voteit.messaging.errors import NotFoundError
from voteit.messaging.errors import UnauthorizedError
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.registries import incoming_messages
from voteit.messaging.registries import outgoing_messages
from voteit.messaging.utils import get_channel_registry

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


SUBSCRIBE = "channel.subscribe"
LEAVE = "channel.leave"

SUBSCRIBED = "channel.subscribed"
LEFT = "channel.left"


class ChannelSchema(BaseModel):
    pk: int
    channel_type: str

    @validator("channel_type")
    def real_channel_type(cls, v):
        cr = get_channel_registry()
        v = v.lower()
        if v not in cr:  # pragma: no cover
            raise ValueError(f"'{v}' is not a valid channel")
        return v


class ChannelSubscription(ChannelSchema):
    """Track subscriptions to protected channels."""

    channel_name: str
    app_state: Optional[List[BaseEnvelope]]


class BaseChannelCommand(BaseIncomingMessage, ABC):
    def get_channel(
        self, channel_type: str, pk: int, consumer_name: str
    ) -> AbstractObjectChannel:
        cr = get_channel_registry()
        # This may cause errors right?
        return cr[channel_type](pk, consumer_name)


@incoming_messages
class Subscribe(BaseChannelCommand, DeferredJob):
    name = SUBSCRIBE
    schema = ChannelSchema
    data: ChannelSchema

    def get_app_state(self, channel: AbstractObjectChannel) -> Optional[list]:
        """ Dispatch signal to populate app_state object, and return as list object or None """
        app_state = AppState()
        signals.channel_subscribed.send(
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
            raise UnauthorizedError.from_message(self)


@incoming_messages
class Leave(BaseChannelCommand, DeferredJob):
    name = LEAVE
    schema = ChannelSchema
    data: ChannelSchema

    def run_job(self) -> Left:
        channel = self.get_channel(
            self.data.channel_type, self.data.pk, self.mm.consumer_name
        )
        if channel.context is None:
            raise NotFoundError.from_message(self, msg=_("Context doesn't exist"))
        if channel.allow_leave(self.user):
            channel.leave()
            msg = Left.from_message(
                self, channel_name=channel.channel_name, **self.data.dict()
            )
            msg.send_outgoing(self.mm.consumer_name, success=True)
            # No app state when leaving channel
            signals.channel_left.send(
                sender=channel.__class__, context=channel.context, user=self.user
            )
            return msg
        else:
            raise UnauthorizedError.from_message(
                self,
                permission=None,  # We don't know here, add perm?
                msg=_(
                    "You're not allowed to leave to this channel"
                ),  # Hotel California...
            )


@outgoing_messages
class Subscribed(BaseOutgoingMessage, AsyncRunnable):
    name = SUBSCRIBED
    schema = ChannelSubscription
    data: ChannelSubscription

    async def run(self, consumer: WebsocketDemuxConsumer):
        consumer.mark_subscribed(self.data)


@outgoing_messages
class Left(BaseOutgoingMessage, AsyncRunnable):
    name = LEFT
    schema = ChannelSubscription
    data: ChannelSubscription

    async def run(self, consumer: WebsocketDemuxConsumer):
        consumer.mark_left(self.data)


class RecheckSubscriptionsSchema(BaseModel):
    subscriptions: List[ChannelSubscription] = []
    consumer_name: Optional[str]


@outgoing_messages
class RecheckChannelSubscriptions(BaseOutgoingMessage, DeferredJob):
    """Send this as an internal message to ask the consumer to
    recheck that it's authorized to subscribe to different channels.
    """

    name = "channel.recheck"
    schema = RecheckSubscriptionsSchema
    data: RecheckSubscriptionsSchema

    async def pre_queue(self, consumer: WebsocketDemuxConsumer):
        self.data.consumer_name = (
            consumer.channel_name
        )  # It might be sent by someone else
        self.data.subscriptions.extend(consumer.protected_subscriptions.values())

    @property
    def should_run(self) -> bool:
        return bool(self.data.subscriptions)

    def run_job(self):
        cr = get_channel_registry()
        # We don't really know if someone is subscribing due to how channels work, but we won't resubscribe
        for cs in self.data.subscriptions:
            ch_class = cr[cs.channel_type]
            if not issubclass(ch_class, AbstractObjectChannel):
                continue
            ch = ch_class.from_pk(cs.pk, self.data.consumer_name)
            if not ch.allow_subscribe(self.user):
                ch.leave()
                msg = Left.from_message(
                    self,
                    channel_name=ch.channel_name,
                    channel_type=cs.channel_type,
                    pk=cs.pk,
                )
                msg.send_outgoing(self.mm.consumer_name, success=True, on_commit=False)
