from __future__ import annotations

from typing import TYPE_CHECKING
from asgiref.sync import async_to_sync
from pydantic import BaseModel

from envelope import Error
from envelope import INTERNAL
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.channels.models import AppState
from envelope.channels.models import ContextChannel
from envelope.channels.schemas import ChannelSchema
from envelope.channels.schemas import ChannelSubscription
from envelope.channels.utils import get_context_channel
from envelope.channels.utils import get_context_channel_registry
from envelope.core.message import AsyncRunnable
from envelope.decorators import add_message
from envelope.core.message import Message
from envelope.deferred_jobs.message import DeferredJob
from envelope.signals import channel_subscribed
from envelope.utils import get_error_type
from envelope.utils import websocket_send

if TYPE_CHECKING:
    from envelope.consumers.websocket import WebsocketConsumer

SUBSCRIBE = "channel.subscribe"
LEAVE = "channel.leave"
LIST_SUBSCRIPTIONS = "channel.list_subscriptions"

SUBSCRIBED = "channel.subscribed"
LEFT = "channel.left"
SUBSCRIPTIONS = "channel.subscriptions"


class ChannelCommand:
    """
    Note that channel commands are only for ContextChannels!
    """

    schema = ChannelSchema
    data: ChannelSchema

    def get_channel(
        self, channel_type: str, pk: int, consumer_name: str
    ) -> ContextChannel:
        ch = get_context_channel(channel_type)
        # This may cause errors right?
        return ch(pk, consumer_channel=consumer_name)


@add_message(WS_INCOMING, INTERNAL)
class Subscribe(ChannelCommand, DeferredJob):
    name = SUBSCRIBE
    ttl = 20
    job_timeout = 20

    def get_app_state(self, channel: ContextChannel) -> list | None:
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

    async def pre_queue(self, consumer: WebsocketConsumer, **kwargs) -> Subscribed:
        if self.mm.consumer_name is None:
            self.mm.consumer_name = consumer.channel_name
        channel = self.get_channel(
            self.data.channel_type, self.data.pk, self.mm.consumer_name
        )
        msg = Subscribed.from_message(
            self,
            state=self.QUEUED,
            channel_name=channel.channel_name,
            **self.data.dict(),
        )
        await consumer.send_ws_message(msg)
        return msg  # For testing

    def run_job(self) -> Subscribed:
        channel = self.get_channel(
            self.data.channel_type, self.data.pk, self.mm.consumer_name
        )
        if channel.allow_subscribe(self.user):
            async_to_sync(channel.subscribe)()
            app_state = self.get_app_state(channel)
            msg = Subscribed.from_message(
                self,
                state=self.SUCCESS,
                channel_name=channel.channel_name,
                app_state=app_state,
                **self.data.dict(),
            )
            websocket_send(msg)
            return msg
        else:
            raise get_error_type(Error.SUBSCRIBE).from_message(
                self,
                channel_name=channel.channel_name,
            )


@add_message(WS_INCOMING)
class Leave(ChannelCommand, AsyncRunnable):
    name = LEAVE

    async def run(self, *, consumer: WebsocketConsumer, **kwargs) -> Left:
        # This is without permission checks since there's no reason to go Hotel California on consumers.
        # Users may only run leave commands on their own consumer anyway
        assert consumer
        channel = self.get_channel(
            self.data.channel_type, self.data.pk, self.mm.consumer_name
        )
        await channel.leave()
        msg = Left.from_message(
            self,
            state=self.SUCCESS,
            channel_name=channel.channel_name,
            **self.data.dict(),
        )
        await consumer.send_ws_message(msg)
        return msg


@add_message(WS_INCOMING)
class ListSubscriptions(AsyncRunnable):
    name = LIST_SUBSCRIPTIONS

    async def run(self, *, consumer: WebsocketConsumer, **kwargs):
        assert consumer
        response = Subscriptions.from_message(
            self, state=self.SUCCESS, subscriptions=list(consumer.subscriptions)
        )
        await consumer.send_ws_message(response)
        return response


@add_message(WS_OUTGOING)
class Subscribed(AsyncRunnable):
    name = SUBSCRIBED
    schema = ChannelSubscription
    data: ChannelSubscription

    async def run(self, *, consumer: WebsocketConsumer, **kwargs):
        assert consumer
        subscription = ChannelSchema(**self.data.dict())
        consumer.subscriptions.add(subscription)


@add_message(WS_OUTGOING)
class Left(AsyncRunnable):
    name = LEFT
    schema = ChannelSchema
    data: ChannelSchema

    async def run(self, *, consumer: WebsocketConsumer, **kwargs):
        assert consumer
        if self.data in consumer.subscriptions:
            consumer.subscriptions.remove(self.data)


class SubscriptionsSchema(BaseModel):
    """
    >>> from envelope.testing import serialization_check
    >>> data = SubscriptionsSchema(subscriptions=[{'pk': '1', 'channel_type': 'user'}])
    >>> serialization_check(data)
    '{"subscriptions": [{"pk": 1, "channel_type": "user"}]}'
    """

    subscriptions: list[ChannelSchema] = ()


@add_message(WS_OUTGOING)
class Subscriptions(Message):
    name = SUBSCRIPTIONS
    schema = SubscriptionsSchema
    data: SubscriptionsSchema


class RecheckSubscriptionsSchema(SubscriptionsSchema):
    consumer_name: str = ""  # Added later


@add_message(INTERNAL)
class RecheckChannelSubscriptions(DeferredJob):
    """
    Send this as an internal message to ask the consumer to
    recheck that it's authorized to subscribe to different channels.

    This is not the same as logging out, rather this is something you may want
    to do when a specific user has new permissions.

    Note that data will be populated by pre_queue method. Calling this without kwargs is the
    expected behaviour.
    """

    name = "channel.recheck"
    schema = RecheckSubscriptionsSchema
    data: RecheckSubscriptionsSchema
    job_timeout = 20

    async def pre_queue(self, consumer: WebsocketConsumer = None, **kwargs):
        assert consumer
        assert consumer.channel_name
        # It might be sent by someone else
        self.data.consumer_name = consumer.channel_name
        self.data.subscriptions.extend(consumer.subscriptions)

    @property
    def should_run(self) -> bool:
        return bool(self.data.subscriptions)

    def run_job(self) -> list[ChannelSchema]:
        registry = get_context_channel_registry()
        # We don't really know if someone is subscribing due to how channels work, but we won't resubscribe
        results = []  # The returned data is meant for unit-testing and similar
        for channel_info in self.data.subscriptions:
            channel_info: ChannelSchema
            ch_class: type[ContextChannel] = registry[channel_info.channel_type]
            if not issubclass(ch_class, ContextChannel):
                continue
            if not self.data.consumer_name:
                raise ValueError("consumer_name shouldn't be none here")
            ch = ch_class(channel_info.pk, consumer_channel=self.data.consumer_name)
            if not ch.allow_subscribe(self.user):
                async_to_sync(ch.leave)()
                msg = Left.from_message(
                    self,
                    state=self.SUCCESS,
                    channel_name=ch.channel_name,
                    channel_type=channel_info.channel_type,
                    pk=channel_info.pk,
                )
                websocket_send(msg, channel_name=self.data.consumer_name)
                results.append(channel_info)
        return results
