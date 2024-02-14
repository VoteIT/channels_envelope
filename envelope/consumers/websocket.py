from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING

from channels.auth import get_user
from channels.exceptions import DenyConnection
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import AnonymousUser
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import activate
from pydantic import ValidationError

from envelope import ERRORS
from envelope import Error
from envelope import INTERNAL
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.async_signals import consumer_connected
from envelope.async_signals import consumer_closed
from envelope.consumers.utils import get_language
from envelope.logging import getEventLogger
from envelope.schemas import MessageMeta
from envelope.utils import get_envelope
from envelope.utils import get_error_type

if TYPE_CHECKING:
    from envelope.core.message import ErrorMessage
    from envelope.core.message import Message
    from envelope.messages.errors import ValidationErrorMsg
    from envelope.channels.schemas import ChannelSchema
    from envelope.logging import EventLoggerAdapter

__all__ = ("WebsocketConsumer",)

default_event_logger = getEventLogger(__name__ + ".event")


class WebsocketConsumer(AsyncWebsocketConsumer):
    # User model, don't trust this since it will be wiped during logout procedure.
    user: AbstractUser | AnonymousUser = AnonymousUser()
    # The users pk associated with the connection. No anon connections are allowed at this time.
    # This will remain even if the user logs out. (The consumer will die shortly after logout)
    user_pk: int | None = None
    # The specific connections own channel. Use this to send messages to one
    # specific connection or as id when subscribing to other channels.
    channel_name: str
    # Last sent, received
    last_sent: datetime | None = None
    last_received: datetime | None = None
    last_error: datetime | None = None
    # Last job dispatched - will update connection status
    last_job: datetime | None = None
    # Number of seconds to wait before dispatching a connection update job.
    connection_update_interval: timedelta | None = None
    subscriptions: set[ChannelSchema]
    language: str | None = None
    allow_unauthenticated: bool = False
    event_logger: EventLoggerAdapter

    def __init__(
        self,
        event_logger: EventLoggerAdapter = default_event_logger,
        **kwargs,  # Default to setting,
    ):
        super().__init__(**kwargs)
        self.event_logger = event_logger
        self.subscriptions = set()
        seconds = getattr(settings, "ENVELOPE_CONNECTION_UPDATE_INTERVAL", 180)
        if seconds:
            self.connection_update_interval = timedelta(seconds=180)
        # Set timestamps
        self.last_job = self.last_sent = self.last_received = now()
        self.allow_unauthenticated = (
            getattr(settings, "ENVELOPE_ALLOW_UNAUTHENTICATED", False) is True
        )

    @cached_property
    def base_error(self) -> type[ErrorMessage]:
        from envelope.core.message import ErrorMessage

        return ErrorMessage

    @cached_property
    def validation_err_msg(self) -> type[ValidationErrorMsg]:
        return get_error_type(Error.VALIDATION)

    async def connect(self):
        self.language = get_language(self.scope)
        activate(self.language)  # FIXME: Safe here?
        self.user = await self.get_user()
        self.user_pk = self.user.pk
        if self.user.is_anonymous:
            if not self.allow_unauthenticated:
                self.event_logger.info(
                    "Connection denied - unauthenticated", consumer=self
                )
                raise DenyConnection()
            if self.user_pk is not None:
                raise Exception("user_pk wasn't None for anonymous user")
            self.event_logger.debug(
                "Unauthenticated connection accepted",
                consumer=self,
                extra=dict(lang=self.language),
            )
        else:
            self.event_logger.info("Authenticated connection accepted", consumer=self)
        await self.accept()
        await consumer_connected.send(sender=self.__class__, consumer=self)

    async def disconnect(self, close_code):
        # https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent
        await consumer_closed.send(
            sender=self.__class__, consumer=self, close_code=close_code
        )

    # NOTE! database_sync_to_async doesn't work in tests - use mock to override
    async def get_user(self) -> AbstractUser | AnonymousUser:
        return await get_user(self.scope)

    def get_msg_meta(self, **kwargs) -> MessageMeta:
        """
        Return values meant to be attached to the message meta information,
        """
        kwargs["consumer_name"] = self.channel_name
        kwargs["user_pk"] = self.user_pk
        kwargs.setdefault("language", self.language)
        return MessageMeta(**kwargs)

    async def send(self, text_data=None, bytes_data=None, close=False):
        self.last_sent = now()
        await super().send(text_data, bytes_data, close)

    async def receive(self, text_data=None, bytes_data=None):
        """
        Websocket receive
        """
        if text_data is None:  # pragma:no cover
            self.event_logger.debug("Ignoring binary data", consumer=self)
            return
        incoming = get_envelope(WS_INCOMING)
        try:
            data = incoming.parse(text_data)
        except ValidationError as exc:
            # FIXME: Count errors
            error = self.validation_err_msg(errors=exc.errors())
            return await self.send_ws_error(error)
        try:
            message = incoming.unpack(data, consumer=self)
        except self.base_error as error:
            return await self.send_ws_error(error)
        self.last_received = now()
        incoming.logger.debug("Received", consumer=self, message=message)
        # Catch exceptions here?
        if incoming.message_signal:
            await incoming.message_signal.send(
                sender=message.__class__, message=message, consumer=self
            )

    async def send_ws_error(self, error: ErrorMessage):
        self.last_error = now()
        errors = get_envelope(ERRORS)
        if errors.message_signal:
            await errors.message_signal.send(
                sender=error.__class__, message=error, consumer=self
            )
        envelope_data = errors.pack(error)
        self.event_logger.info("Sending error", consumer=self, message=error)
        text_data = envelope_data.json()
        await self.send(text_data=text_data)

    async def send_ws_message(self, message: Message):
        outgoing = get_envelope(WS_OUTGOING)
        self.event_logger.debug("Sending ws", consumer=self, message=message)
        if outgoing.message_signal:
            await outgoing.message_signal.send(
                sender=message.__class__, message=message, consumer=self
            )
        envelope_data = outgoing.pack(message)
        text_data = envelope_data.json()
        await self.send(text_data=text_data)

    async def websocket_send(self, event: dict):
        """
        Handle event received from channels and delegate to websocket.
        Any channels message with the type "websocket.send" will end up here.
        """
        self.last_sent = now()
        outgoing = get_envelope(WS_OUTGOING)
        msg_class = outgoing.registry.get(event["t"])
        if outgoing.message_signal and outgoing.message_signal.has_listeners(msg_class):
            data = outgoing.parse(event["text_data"])
            message = outgoing.unpack(data, consumer=self)
            self.event_logger.debug("websocket_send", consumer=self, message=message)
            await outgoing.message_signal.send(
                sender=message.__class__, message=message, consumer=self
            )
        else:
            self.event_logger.debug(
                f"websocket_send message type {event['t']} without listeners",
                consumer=self,
            )
        # text_data = data.json()
        await self.send(text_data=event["text_data"])

    async def ws_error_send(self, event: dict):
        """
        Handle event received from channels and delegate to websocket.
        Any channels message with the type "ws.error.send" will end up here.
        """
        self.last_error = self.last_sent = now()
        errors = get_envelope(ERRORS)
        data = errors.schema(**event)
        msg_class = errors.registry.get(data.t)
        if errors.message_signal and errors.message_signal.has_listeners(msg_class):
            message = errors.unpack(data, consumer=self)
            self.event_logger.debug("ws_error_send", consumer=self, message=message)
            await errors.message_signal.send(
                sender=message.__class__, message=message, consumer=self
            )
        else:
            self.event_logger.debug(
                f"ws_error_send message type {data.t} without listeners",
                consumer=self,
            )
        text_data = data.json()
        await self.send(text_data=text_data)

    # async def send_internal(self, message: Message):
    #     internal = get_envelope_from_message(message)
    #     self.event_logger.debug("Sending internal", consumer=self, message=message)
    #     if internal.message_signal:
    #         await internal.message_signal.send(
    #             sender=message.__class__, message=message, consumer=self
    #         )
    #     envelope_data = internal.pack(message)
    #     text_data = envelope_data.json()
    #     await self.base_send({"type": "internal.msg", "text": text_data})

    async def internal_msg(self, event: dict):
        """
        A message sent to the consumer itself. These may be initiated by the user,
        bot more likely some kind of system message like logged out.
        """
        internal = get_envelope(INTERNAL)
        data = internal.schema(**event)
        message = internal.unpack(data, consumer=self)
        self.event_logger.debug("internal_msg", consumer=self, message=message)
        if internal.message_signal:
            await internal.message_signal.send(
                sender=message.__class__, message=message, consumer=self
            )
