from __future__ import annotations

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
from django.utils.timezone import now
from django.utils.translation import activate
from pydantic import ValidationError

from envelope.consumers.utils import get_language
from envelope.envelope import ErrorEnvelope
from envelope.envelope import IncomingWebsocketEnvelope
from envelope.envelope import OutgoingWebsocketEnvelope
from envelope import InternalTransport
from envelope.jobs import mark_connection_action
from envelope.jobs import signal_websocket_close
from envelope.jobs import signal_websocket_connect
from envelope.messages.base import ErrorMessage
from envelope.messages.base import Message
from envelope.messages.errors import ValidationErrorMsg
from envelope.utils import get_handler_registry

if TYPE_CHECKING:
    pass


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
    last_recv: datetime = None
    last_error: Optional[datetime] = None
    # Last time we sent something to a queue which will update this consumers
    # connection status within the db. See models.Connection
    last_job: Optional[datetime] = None
    # Number of seconds to wait before despatching a connection update job.
    connection_update_interval: Optional[timedelta] = None
    # protected_subscriptions: Dict[str, ChannelSubscription]
    # Send and queue connection signals?
    # They're a bad idea in most unit tests since they muck about with threading and db-access,
    # which causes the async tests to fail or start in another threads async event loop.
    enable_connection_signals: bool = True
    language: Optional[str] = None
    incoming_envelope = IncomingWebsocketEnvelope
    outgoing_envelope = OutgoingWebsocketEnvelope
    error_envelope = ErrorEnvelope

    def __init__(self, *args, enable_connection_signals=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.protected_subscriptions = {}
        self.enable_connection_signals = enable_connection_signals
        seconds = getattr(settings, "ENVELOPE_CONNECTION_UPDATE_INTERVAL", 180)
        if seconds:
            self.connection_update_interval = timedelta(seconds=seconds)
        # Set timestamps
        self.last_job = self.last_sent = self.last_recv = now()

    async def connect(self):
        self.language = get_language(self.scope)
        activate(self.language)  # FIXME: Safe here?
        self.user = await self.refresh_user()
        if self.user is None:
            # FIXME: Allow anon connections?
            logger.debug("Invalid token, closing connection")
            raise DenyConnection()
        logger.debug("Connection for user: %s", self.user)
        await self.accept()
        logger.debug(
            "Connection accepted for user %s (%s) with lang %s",
            self.user,
            self.user.pk,
            self.language,
        )
        if self.enable_connection_signals:
            self.dispatch_connect()

    async def disconnect(self, close_code):
        # https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent
        if self.user_pk:
            logger.debug(
                "Disconnect user pk %s with close code %s", self.user_pk, close_code
            )
            # We only need to signal disconnect for an actual user
            if self.enable_connection_signals:
                self.last_job = now()  # We probably don't need to care about this :)
                self.dispatch_close(close_code)
        else:
            logger.debug("Disconnect was from anon, close code %s", close_code)

    # NOTE! database_sync_to_async doesn't work in tests - use mock to override
    async def refresh_user(self) -> Optional[AbstractUser]:
        user = await get_user(self.scope)
        if user.pk is not None:
            self.user_pk = user.pk
            self.user = user
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
        WebSocket receive
        """
        if text_data is not None:
            try:
                env = self.incoming_envelope.parse(text_data)
            except ValidationError as exc:
                # Very early exception, this should only happen
                # if someone is manually mucking about or during development
                error = ValidationErrorMsg(errors=exc.errors())
                return self.send_ws_error(error)
            try:
                message = env.unpack(consumer=self)
            except ErrorMessage as error:
                return await self.send_ws_error(error)
        else:
            logger.debug("Ignoring binary data")
            return
        self.last_recv = now()
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

    async def websocket_send(self, event: InternalTransport):
        """
        Push data to the websocket. Any channels message with the type "websocket.send" will end up here.

        This is meant to handle messages send from other parts of the application.
        No validation will be done unless debug mode is on.
        """
        # FIXME: Other setting?
        if settings.DEBUG:
            if event.get("error", None):
                env_class = self.error_envelope
            else:
                env_class = self.outgoing_envelope
                self.last_error = now()
            envelope = env_class.parse(event["text_data"])
            msg = envelope.unpack(consumer=self)
            msg.validate()  # Die here, application error not caused by the user
        self.last_sent = now()
        await self.send(text_data=event["text_data"])

    # async def internal_receive(self, event: Dict):
    #     """
    #     Handle incoming internal messages.
    #     Incoming messages are dicts corresponding to InternalEnvelope.
    #     """
    #     inc_p = event.get("p", None)
    #     if inc_p and isinstance(inc_p, str):
    #         event["p"] = json.loads(inc_p)
    #     envelope = InternalEnvelope(**event)
    #     # This may cause validation errors, but that message shouldn't exist in that case it was resent from
    #     # backend and not from the user.
    #     # Crash and burn is okay here...
    #     if envelope.incoming:
    #         message = BaseIncomingMessage.from_consumer(self, envelope)
    #     else:
    #         message = BaseOutgoingMessage.from_consumer(self, envelope)
    #     await self.handle_message(message)

    def dispatch_connect(self):
        """
        The connect signal even will be fired in a worker instead,
        since the sync calls to db aren't great to mix with async code.
        Currently channels testing doesn't work very well with database_sync_to_async either since
        we'll have problems with new threads etc
        """
        return signal_websocket_connect.delay(
            user_pk=self.user_pk,
            consumer_name=self.channel_name,
            language=self.language,
            online_at=now(),
        )

    def dispatch_close(self, close_code):
        """
        Ask a worker to signal instead of doing it here.
        """
        return signal_websocket_close.delay(
            user_pk=self.user_pk,
            consumer_name=self.channel_name,
            close_code=close_code,
            language=self.language,
            offline_at=now(),
        )

    # def mark_subscribed(self, subscription: ChannelSubscription):
    #     self.protected_subscriptions[subscription.channel_name] = subscription
    #
    # def mark_left(self, subscription: ChannelSubscription):
    #     self.protected_subscriptions.pop(subscription.channel_name, None)
