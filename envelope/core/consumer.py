from abc import ABC
from abc import abstractmethod
from datetime import datetime
from datetime import timedelta
from logging import Logger
from logging import getLogger
from typing import Optional
from typing import Set
from typing import Union

from channels.auth import get_user
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.utils.timezone import now
from django.utils.translation import activate
from django_rq import get_queue
from rq import Queue

from envelope.messages.channels import ChannelSchema
from envelope.queues import get_connection_queue
from envelope.queues import get_timestamp_queue
from envelope.utils import get_handler_registry


class BaseWebsocketConsumer(AsyncWebsocketConsumer, ABC):

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
    # Number of seconds to wait before dispatching a connection update job.
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
    # Logger, so we can override it
    logger: Logger = getLogger(__name__)
    # Queues for RQ tasks
    connection_queue: Queue
    timestamp_queue: Queue

    def __init__(
        self,
        *,
        enable_connection_signals=True,
        connect_signal_job=None,
        close_signal_job=None,
        internal_envelope=None,
        logger: Logger = None,
        connection_queue: Union[str, Queue] = None,
        timestamp_queue: Union[str, Queue] = None,
        **kwargs,  # Default to setting,
    ):
        super().__init__(**kwargs)
        self.subscriptions = set()
        seconds = getattr(settings, "ENVELOPE_CONNECTION_UPDATE_INTERVAL", 180)
        if seconds:
            self.connection_update_interval = timedelta(seconds=seconds)

        # Set timestamps
        self.last_job = self.last_sent = self.last_received = now()

        if internal_envelope is None:
            from envelope.envelope import InternalEnvelope

            self.internal_envelope = InternalEnvelope

        # Connection signals / jobs
        self.enable_connection_signals = enable_connection_signals
        if connect_signal_job:
            self.connect_signal_job = connect_signal_job
        else:  # pragma: no cover
            if enable_connection_signals:
                raise ValueError(
                    "Consumer has 'enable_connection_signals' without specifying 'connect_signal_job'"
                )
        if close_signal_job:
            self.close_signal_job = close_signal_job
        else:  # pragma: no cover
            if enable_connection_signals:
                raise ValueError(
                    "Consumer has 'enable_connection_signals' without specifying 'close_signal_job'"
                )
        if logger:  # pragma: no cover
            self.logger = logger

        self.connection_queue = get_connection_queue(connection_queue)
        self.timestamp_queue = get_timestamp_queue(timestamp_queue)

    @abstractmethod
    async def connect(self):
        ...

    @abstractmethod
    async def disconnect(self, close_code):
        # https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent
        ...

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

    @abstractmethod
    def update_connection(self):
        ...

    @abstractmethod
    async def receive(self, text_data=None, bytes_data=None):
        ...

    async def handle_message(self, message):
        """
        Make sure this is wrapped in try/except to catch any errors we want to handle
        """
        activate(self.language)  # FIXME: Every time...?
        message.validate()
        if message.mm.registry:
            # We'll probably want to die on key erorr here since it's a programming mistake
            reg = get_handler_registry(message.mm.registry)
            await reg.apply(message, consumer=self)
        else:
            self.logger.debug("%s has no mm.registry value, won't handle" % message)

    async def send(self, text_data=None, bytes_data=None, envelope=None, close=False):
        if bool(text_data) == bool(envelope):
            raise ValueError("envelope or text_data must be specified")
        if envelope:
            text_data = envelope.data.json()
        self.last_sent = now()
        await super().send(text_data, bytes_data, close)

    def mark_subscribed(self, subscription: ChannelSchema):
        assert isinstance(subscription, ChannelSchema)
        self.subscriptions.add(subscription)

    def mark_left(self, subscription: ChannelSchema):
        assert isinstance(subscription, ChannelSchema)
        if subscription in self.subscriptions:
            self.subscriptions.remove(subscription)
