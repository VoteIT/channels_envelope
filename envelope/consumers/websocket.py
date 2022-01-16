from __future__ import annotations

from typing import Set
from datetime import datetime
from datetime import timedelta
from logging import getLogger
from typing import Optional
from typing import TYPE_CHECKING

from channels.auth import get_user
from channels.exceptions import DenyConnection
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth.models import AbstractUser

# from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import activate
from pydantic import ValidationError

from envelope.consumers.utils import get_language
from envelope.jobs import mark_connection_action
from envelope.jobs import signal_websocket_close
from envelope.jobs import signal_websocket_connect
from envelope.messages.base import ErrorMessage
from envelope.messages.base import Message
from envelope.messages.errors import ValidationErrorMsg
from envelope.utils import get_handler_registry

if TYPE_CHECKING:
    from envelope.messages.channels import ChannelSchema


logger = getLogger(__name__)


class EnvelopeWebsocketConsumer(AsyncWebsocketConsumer):

    # User model, don't trust this since it will be wiped during logout procedure.
    user: Optional[AbstractUser] = None
    # The users pk associated with the connection. No anon connections are allowed at this time.
    # This will remain even if the user logs out. (The consumer will die shortly after logout)
    user_pk: Optional[int] = None
    # The specific connections own channel. Use this to send messages to one
    # specific connection or as id when subscribing to other channels.
    channel_name: str
    # Errors count, when these stack the sane response would be to simply disconnect
    message_errors: int = 0
    # Last sent, received
    last_sent: datetime = None
    last_received: datetime = None
    last_error: Optional[datetime] = None
    # Last time we sent something to a queue which will update this consumers
    # connection status within the db. See models.Connection
    last_job: Optional[datetime] = None
    # Number of seconds to wait before despatching a connection update job.
    connection_update_interval: Optional[timedelta] = None
    subscriptions: Set[ChannelSchema]
    # Send and queue connection signals?
    # They're a bad idea in most unit tests since they muck about with threading and db-access,
    # which causes the async tests to fail or start in another threads async event loop.
    language: Optional[str] = None
    # Connection signals - deferred to job so we can use sync code
    enable_connection_signals: bool = True
    connect_signal_job = None
    close_signal_job = None

    def __init__(
        self,
        *args,
        enable_connection_signals=True,
        connect_signal_job=signal_websocket_connect,
        close_signal_job=signal_websocket_close,
        incoming_envelope=None,
        outgoing_envelope=None,
        error_envelope=None,
        internal_envelope=None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.subscriptions = set()
        seconds = getattr(settings, "ENVELOPE_CONNECTION_UPDATE_INTERVAL", 180)
        if seconds:
            self.connection_update_interval = timedelta(seconds=seconds)

        # Set timestamps
        self.last_job = self.last_sent = self.last_received = now()

        # Set envelope classes
        if incoming_envelope is None:
            from envelope.envelope import IncomingWebsocketEnvelope

            self.incoming_envelope = IncomingWebsocketEnvelope
        if outgoing_envelope is None:
            from envelope.envelope import OutgoingWebsocketEnvelope

            self.outgoing_envelope = OutgoingWebsocketEnvelope
        if error_envelope is None:
            from envelope.envelope import ErrorEnvelope

            self.error_envelope = ErrorEnvelope

        if internal_envelope is None:
            from envelope.envelope import InternalEnvelope

            self.internal_envelope = InternalEnvelope

        # Connection signals / jobs
        self.enable_connection_signals = enable_connection_signals
        if connect_signal_job:
            self.connect_signal_job = connect_signal_job
        if close_signal_job:
            self.close_signal_job = close_signal_job

    async def connect(self):
        self.language = get_language(self.scope)
        activate(self.language)  # FIXME: Safe here?
        self.user = await self.get_user()
        if self.user is None:
            # FIXME: Allow anon connections?
            logger.debug("Invalid token, closing connection")
            raise DenyConnection()
        self.user_pk = self.user.pk
        logger.debug("Connection for user: %s", self.user)
        await self.accept()
        logger.debug(
            "Connection accepted for user %s (%s) with lang %s",
            self.user,
            self.user.pk,
            self.language,
        )
        if self.enable_connection_signals:
            # The connect signal even will be fired in a worker instead,
            # since the sync calls to db aren't great to mix with async code.
            # Currently channels testing doesn't work very well with database_sync_to_async either since
            # we'll have problems with new threads etc
            return self.connect_signal_job.delay(
                user_pk=self.user_pk,
                consumer_name=self.channel_name,
                language=self.language,
                online_at=now(),
            )

    async def disconnect(self, close_code):
        # https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent
        if self.user_pk:
            logger.debug(
                "Disconnect user pk %s with close code %s", self.user_pk, close_code
            )
            # We only need to signal disconnect for an actual user
            if self.enable_connection_signals:
                self.last_job = now()  # We probably don't need to care about this :)
                return self.close_signal_job.delay(
                    user_pk=self.user_pk,
                    consumer_name=self.channel_name,
                    close_code=close_code,
                    language=self.language,
                    offline_at=now(),
                )
        else:
            logger.debug("Disconnect was from anon, close code %s", close_code)

    # NOTE! database_sync_to_async doesn't work in tests - use mock to override
    async def get_user(self) -> Optional[AbstractUser]:
        user = await get_user(self.scope)
        if user.pk is not None:
            return user

    def get_msg_meta(self) -> dict:
        """
        Return values meant to be attached to the message meta information,
        """
        return dict(
            consumer_name=self.channel_name,
            language=self.language,
            user_pk=self.user and self.user.pk or None,
        )

    def update_connection(self):
        if self.connection_update_interval is not None:
            if now() - self.last_job > self.connection_update_interval:
                mark_connection_action.delay(
                    action_at=now(), consumer_name=self.channel_name
                )

    async def receive(self, text_data=None, bytes_data=None):
        """
        Websocket receive
        """
        if text_data is not None:
            try:
                env = self.incoming_envelope.parse(text_data)
            except ValidationError as exc:
                # Very early exception, this should only happen
                # if someone is manually mucking about or during development
                error = ValidationErrorMsg(errors=exc.errors())
                return await self.send_ws_error(error)
            try:
                message = env.unpack(consumer=self)
            except ErrorMessage as error:
                return await self.send_ws_error(error)
        else:
            logger.debug("Ignoring binary data")
            return
        self.last_received = now()
        try:
            await self.handle_message(message)
        # FIXME Other recoverable errors?
        except ValidationError as exc:
            error = ValidationErrorMsg.from_message(message, errors=exc.errors())
            await self.send_ws_error(error)
        except ErrorMessage as exc:
            # A message-aware exception can simply be sent directly
            await self.send_ws_error(exc)
        # And finally decide if we should mark connection as active,
        # or if other actions from incoming messages have already sorted that out
        self.update_connection()

    async def handle_message(self, message):
        """
        Make sure this is wrapped in try/except to catch any errors we want to handle
        """
        activate(self.language)  # FIXME: Every time...?
        message.validate()
        if message.mm.registry:
            try:
                reg = get_handler_registry(message.mm.registry)
            except KeyError:
                logger.debug(
                    "No handler registry called %s, won't handle %s"
                    % (message.mm.registry, message)
                )
                return
            await reg.apply(message, consumer=self)
        else:
            logger.debug("%s has no mm.registry value, won't handle" % message)

    async def send_ws_error(self, error: ErrorMessage):
        self.last_error = now()
        if isinstance(error, ErrorMessage):
            error.validate()  # Errors also need a proper payload to be recoverable by the frontend client
            self.error_envelope.is_compatible(error, exception=True)
            envelope = self.error_envelope.pack(error)
        else:
            raise TypeError("error is not an ErrorMessage instance")
        await self.send(envelope=envelope)

    async def send_ws_message(self, message, state=None):
        if isinstance(message, Message):
            self.outgoing_envelope.is_compatible(message, exception=True)
            message.validate()  # This is not a user error in case it goes wrong, so we shouldn't catch this
            envelope = self.outgoing_envelope.pack(message)
        else:
            raise TypeError("message is not a Message instance")
        if state:
            envelope.data.s = state
        # JSON dumps methods should be set on the envelope to make them compatible with more types
        await self.send(envelope=envelope)

    async def send(self, text_data=None, bytes_data=None, envelope=None, close=False):
        if bool(text_data) == bool(envelope):
            raise ValueError("envelope or text_data must be specified")
        if envelope:
            text_data = envelope.data.json()
        self.last_sent = now()
        await super().send(text_data, bytes_data, close)

    async def websocket_send(self, event: dict):
        """
        Handle event received from channels and delegate to websocket.
        Any channels message with the type "websocket.send" will end up here.

        This is meant to handle messages send from other parts of the application.
        No validation will be done unless debug mode is on.
        """
        # FIXME: Other setting?
        # if settings.DEBUG:
        envelope = self.outgoing_envelope.parse(event["text_data"])
        msg = envelope.unpack(consumer=self)
        msg.validate()  # Die here, application error not caused by the user
        await self.handle_message(msg)
        self.last_sent = now()
        await self.send(text_data=event["text_data"])

    async def ws_error_send(self, event: dict):
        """
        Handle event received from channels and delegate to websocket.
        Any channels message with the type "ws.error.send" will end up here.

        This is meant to handle messages send from other parts of the application.
        No validation will be done unless debug mode is on.
        """
        if settings.DEBUG:
            envelope = self.error_envelope.parse(event["text_data"])
            msg = envelope.unpack(consumer=self)
            msg.validate()  # Die here, application error not caused by the user
        self.last_error = now()
        self.last_sent = now()
        await self.send(text_data=event["text_data"])

    async def internal_msg(self, event: dict):
        """
        Handle incoming internal message
        """
        envelope = self.internal_envelope(self, **event)
        msg = envelope.unpack(consumer=self)
        # Die here, application error not caused by the user
        msg.validate()
        # Should we catch errors from handle message?
        # These are internal messages so any error should be from already validated
        # data sent by the application - i.e. our fault.
        await self.handle_message(msg)

    def mark_subscribed(self, subscription: ChannelSchema):
        self.subscriptions.add(subscription)

    def mark_left(self, subscription: ChannelSchema):
        self.subscriptions.pop(subscription, None)
