from __future__ import annotations

from channels.exceptions import DenyConnection
from django.utils.timezone import now
from django.utils.translation import activate
from pydantic import ValidationError

from envelope import ERRORS
from envelope import INTERNAL
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.consumers.utils import get_language
from envelope.core.consumer import BaseWebsocketConsumer
from envelope.core.message import ErrorMessage
from envelope.core.message import Message
from envelope.jobs import mark_connection_action
from envelope.jobs import signal_websocket_close
from envelope.jobs import signal_websocket_connect
from envelope.logging import getEventLogger
from envelope.messages.errors import ValidationErrorMsg
from envelope.utils import get_envelope_registry

__all__ = ("WebsocketConsumer",)


event_logger = getEventLogger(__name__ + ".event")


class WebsocketConsumer(BaseWebsocketConsumer):
    event_logger = event_logger

    def __init__(
        self,
        *,
        enable_connection_signals=True,
        connect_signal_job=signal_websocket_connect,
        close_signal_job=signal_websocket_close,
        incoming_envelope=WS_INCOMING,
        outgoing_envelope=WS_OUTGOING,
        error_envelope=ERRORS,
        internal_envelope=INTERNAL,
        **kwargs,
    ):
        super().__init__(
            enable_connection_signals=enable_connection_signals,
            connect_signal_job=connect_signal_job,
            close_signal_job=close_signal_job,
            **kwargs,
        )
        # Set envelope classes
        envelopes = get_envelope_registry()
        self.incoming_envelope = envelopes[incoming_envelope]
        self.outgoing_envelope = envelopes[outgoing_envelope]
        self.error_envelope = envelopes[error_envelope]
        self.internal_envelope = envelopes[internal_envelope]

    async def connect(self):
        self.language = get_language(self.scope)
        activate(self.language)  # FIXME: Safe here?
        self.user = await self.get_user()
        if self.user is None:
            # FIXME: Allow anon connections?
            self.event_logger.info("Connection denied", consumer=self)
            raise DenyConnection()
        self.user_pk = self.user.pk
        await self.accept()
        self.event_logger.info(
            "Connection accepted", consumer=self, extra=dict(lang=self.language)
        )
        if self.enable_connection_signals:
            # The connect signal even will be fired in a worker instead,
            # since the sync calls to db aren't great to mix with async code.
            # Currently, channels testing doesn't work very well with database_sync_to_async either since
            # we'll have problems with new threads etc
            self.last_job = now()
            return self.connection_queue.enqueue(
                self.connect_signal_job,
                user_pk=self.user_pk,
                consumer_name=self.channel_name,
                language=self.language,
                online_at=now(),
            )

    async def disconnect(self, close_code):
        # https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent
        if self.user_pk:
            self.event_logger.info(
                "Disconnected",
                consumer=self,
                extra=dict(close_code=close_code),
            )
            # We only need to signal disconnect for an actual user
            if self.enable_connection_signals:
                self.last_job = now()  # We probably don't need to care about this :)
                return self.connection_queue.enqueue(
                    self.close_signal_job,
                    user_pk=self.user_pk,
                    consumer_name=self.channel_name,
                    close_code=close_code,
                    language=self.language,
                    offline_at=now(),
                )
        else:
            self.event_logger.info(
                "Disconnected anonymous",
                consumer=self,
                extra=dict(close_code=close_code),
            )

    def update_connection(self):
        if self.connection_update_interval is not None:
            if (
                self.last_job is None
                or now() - self.last_job > self.connection_update_interval
            ):
                self.event_logger.debug("Queued conn update", consumer=self)
                return self.timestamp_queue.enqueue(
                    mark_connection_action,
                    action_at=now(),
                    consumer_name=self.channel_name,
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
        else:  # pragma: no cover
            self.event_logger.debug("Ignoring binary data", consumer=self)
            return
        self.last_received = now()
        self.event_logger.debug("Received", consumer=self, message=message)
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

    async def send_ws_error(self, error: ErrorMessage):
        # self.logger.debug("%s sending error %s", self.channel_name, error.name)
        self.last_error = now()
        if isinstance(error, ErrorMessage):
            if error.mm.registry != ERRORS:
                error.mm.registry = ERRORS
            await self.handle_message(error)
            envelope = error.envelope.pack(error)
        else:
            raise TypeError("error is not an ErrorMessage instance")
        self.event_logger.info("Sending error", consumer=self, message=error)
        await self.send(envelope=envelope)

    async def send_ws_message(self, message, state=None):
        if isinstance(message, Message):
            if message.mm.registry != WS_OUTGOING:
                message.mm.registry = WS_OUTGOING
            await self.handle_message(message)
            envelope = message.envelope.pack(message)
        else:
            raise TypeError("message is not a Message instance")
        self.event_logger.debug(
            "Sending ws", consumer=self, message=message, state=state
        )
        if state:
            envelope.data.s = state
        # JSON dumps methods should be set on the envelope to make them compatible with more types
        await self.send(envelope=envelope)

    async def websocket_send(self, event: dict):
        """
        Handle event received from channels and delegate to websocket.
        Any channels message with the type "websocket.send" will end up here.

        This is meant to handle messages send from other parts of the application.
        No validation will be done unless debug mode is on.
        """
        if event.get("run_handlers", False):
            envelope = self.outgoing_envelope.parse(event["text_data"])
            msg = envelope.unpack(consumer=self)
            msg.validate()  # Die here, application error not caused by the user
            self.event_logger.debug(
                "websocket_send",
                consumer=self,
                message=msg,
                handlers=True,
            )
            await self.handle_message(msg)
        else:
            self.event_logger.debug(
                "websocket_send",
                consumer=self,
                handlers=False,
                extra=dict(
                    i=event.get("i"),
                    t=event.get("t"),
                    s=event.get("s"),
                ),
            )
        self.last_sent = now()
        await self.send(text_data=event["text_data"])

    async def ws_error_send(self, event: dict):
        """
        Handle event received from channels and delegate to websocket.
        Any channels message with the type "ws.error.send" will end up here.

        This is meant to handle messages send from other parts of the application.
        No validation will be done unless debug mode is on.
        """
        if event.get("run_handlers", False):
            envelope = self.error_envelope.parse(event["text_data"])
            msg = envelope.unpack(consumer=self)
            msg.validate()  # Die here, application error not caused by the user
            await self.handle_message(msg)
            self.event_logger.debug(
                "ws_error_send",
                consumer=self,
                message=msg,
                handlers=True,
            )
        else:
            self.event_logger.debug(
                "ws_error_send",
                consumer=self,
                handlers=False,
                extra=dict(
                    i=event.get("i"),
                    t=event.get("t"),
                    s=event.get("s"),
                ),
            )
        self.last_error = now()
        self.last_sent = now()
        await self.send(text_data=event["text_data"])

    async def internal_msg(self, event: dict):
        """
        Handle incoming internal message
        """
        envelope = self.internal_envelope(consumer=self, **event)
        msg = envelope.unpack(consumer=self)
        # Die here, application error not caused by the user
        msg.validate()
        self.event_logger.debug(
            "internal_msg",
            consumer=self,
            message=msg,
            handlers=True,
        )
        # Should we catch errors from handle message?
        # These are internal messages so any error should be from already validated
        # data sent by the application - i.e. our fault.
        await self.handle_message(msg)
