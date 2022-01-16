from __future__ import annotations

from collections import UserList
from datetime import datetime
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.db.models import Model
from django.db.models import QuerySet
from django.utils.functional import cached_property

from envelope import DEFAULT_CHANNELS
from envelope import INTERNAL_TRANSPORT
from envelope import WS_SEND_ERROR_TRANSPORT
from envelope import WS_SEND_TRANSPORT
from pydantic import ValidationError
from envelope import DEFAULT_ERRORS
from envelope import Error
from envelope.messages.base import ErrorMessage
from envelope.messages.base import Message
from envelope.models import Connection
from envelope.signals import connection_terminated

if TYPE_CHECKING:
    from envelope.registry import HandlerRegistry
    from envelope.registry import MessageRegistry
    from envelope.registry import ChannelRegistry
    from envelope.envelope import Envelope


channel_layer = get_channel_layer()


def update_connection_status(
    user: AbstractUser,
    channel_name: str,
    online: Optional[bool] = True,
    awol: Optional[bool] = None,
    online_at: Optional[datetime] = None,
    offline_at: Optional[datetime] = None,
    last_action: Optional[datetime] = None,
) -> Connection:
    """
    This is sync-only code so don't call this in any async context!
    """
    conn, created = Connection.objects.get_or_create(
        user=user, channel_name=channel_name
    )
    conn: Connection
    send_terminated = False
    if online is not None:  # We might not know
        if conn.online == True and online == False:
            send_terminated = True
        conn.online = online
    if awol is not None:
        conn.awol = awol
    if online_at:
        conn.online_at = online_at
    if offline_at:
        conn.offline_at = offline_at
    if last_action:
        conn.last_action = last_action
    conn.save()
    if send_terminated:
        connection_terminated.send(sender=Connection, connection=conn, awol=conn.awol)
    return conn


def get_message_registry(name: str) -> MessageRegistry:
    from envelope.registry import global_message_registry

    return global_message_registry[name]


def get_handler_registry(name: str) -> HandlerRegistry:
    from envelope.registry import global_handler_registry

    return global_handler_registry[name]


def get_channel_registry(name: str = DEFAULT_CHANNELS) -> ChannelRegistry:
    from envelope.registry import global_channel_registry

    return global_channel_registry[name]


class SenderUtil:
    """
    Takes care of sending data to channels.
    Made callable so it can be added to the on_commit hook in django.
    """

    # FIXME: Allow channel layer specification?
    def __init__(
        self,
        envelope: Envelope,
        channel_name: str,
        group: bool = False,
        transport: str = None,
        as_dict: bool = False,
    ):
        self.envelope = envelope
        self.channel_name = channel_name
        self.group = group
        assert transport
        self.transport = transport
        self.as_dict = as_dict

    def __call__(self):
        async_to_sync(self.async_send)()

    async def async_send(self):
        if self.as_dict:
            payload = self.envelope.as_dict_transport(self.transport)
        else:
            payload = self.envelope.as_text_transport(self.transport)
        if self.group:
            await channel_layer.group_send(self.channel_name, payload)
        else:
            await channel_layer.send(self.channel_name, payload)


def websocket_send(
    message: Message,
    channel_name: str,
    state: Optional[str] = None,
    on_commit: bool = True,
    group: bool = False,
):
    """
    From sync world outside of the websocket consumer - send a message to a group or a specific consumer.
    """
    from envelope.envelope import OutgoingWebsocketEnvelope

    assert isinstance(message, Message)
    try:
        message.validate()
    except ValidationError as exc:
        error = get_error_type(Error.VALIDATION).from_message(
            message, errors=exc.errors()
        )
        raise error
        # OR send?
        # return websocket_send_error(error, channel_name, group=group)
    OutgoingWebsocketEnvelope.is_compatible(message, exception=True)
    envelope = OutgoingWebsocketEnvelope.pack(message)
    if state:
        envelope.data.s = state
    sender = SenderUtil(
        envelope, channel_name, group=group, transport=WS_SEND_TRANSPORT
    )
    if on_commit:
        # FIXME: Option to disable commit?
        # if on_commit and not self.is_on_commit_disabled:
        transaction.on_commit(sender)
    else:
        sender()


def internal_send(
    message: Message,
    channel_name: str,
    state: Optional[str] = None,
    on_commit: bool = True,
    group: bool = False,
):
    """
    From sync world outside of the consumer - send an internal message to a group or a specific consumer.
    """
    from envelope.envelope import InternalEnvelope

    assert isinstance(message, Message)
    try:
        message.validate()
    except ValidationError as exc:
        # These messages will probably not get caught since they're a programming error and not due to user input
        error = get_error_type(Error.VALIDATION).from_message(
            message, errors=exc.errors()
        )
        raise error
    InternalEnvelope.is_compatible(message, exception=True)
    envelope = InternalEnvelope.pack(message)
    if state:
        envelope.data.s = state
    sender = SenderUtil(
        envelope, channel_name, group=group, transport=INTERNAL_TRANSPORT, as_dict=True
    )
    if on_commit:
        # FIXME: Option to disable commit?
        # if on_commit and not self.is_on_commit_disabled:
        transaction.on_commit(sender)
    else:
        sender()


def websocket_send_error(error: ErrorMessage, channel_name: str, group: bool = False):
    """
    Send an error to a group or a specific consumer. Errors can't be a part of transactions since
    there's a high probability that the transaction won't commit. (Depending on the error of course)
    """
    from envelope.envelope import ErrorEnvelope

    assert isinstance(error, ErrorMessage)

    ErrorEnvelope.is_compatible(error, exception=True)
    envelope = ErrorEnvelope.pack(error)
    sender = SenderUtil(
        envelope, channel_name, group=group, transport=WS_SEND_ERROR_TRANSPORT
    )
    sender()


def get_message_type(message_name: str, _registry: str) -> Type[Message]:
    reg = get_message_registry(_registry)
    return reg[message_name]


def get_error_type(
    error_name: str, _registry: str = DEFAULT_ERRORS
) -> Type[ErrorMessage]:
    reg = get_message_registry(_registry)
    klass = reg[error_name]
    assert issubclass(klass, ErrorMessage)
    return klass


class AppState(UserList):
    """
    Attach several messages to a subscribed response. It's built for websocket application states.
    """

    @cached_property
    def envelope(self):
        from envelope.envelope import OutgoingWebsocketEnvelope

        return OutgoingWebsocketEnvelope

    def append(self, item: Message) -> None:
        """Insert outgoing message into envelope 👅"""
        self.envelope.is_compatible(item, exception=True)

        super().append(
            self.envelope(
                t=item.name,
                p=item.data,
            )
        )

    def append_from(
        self,
        instance: Model,
        serializer_class,  #: Type[ModelSerializer],
        message_class: Type[Message],
    ):
        """
        Insert outgoing message from instance, using DRF serializer and message_class
        """
        data = serializer_class(instance).data
        self.append(message_class(**data))

    def append_from_queryset(
        self,
        queryset: QuerySet,
        serializer_class,  #: Type[ModelSerializer],
        message_class: Type[Message],
    ):
        """
        Insert outgoing messages from queryset, using DRF serializer and message class
        """
        for instance in queryset:
            self.append_from(instance, serializer_class, message_class)
