from __future__ import annotations
from datetime import datetime
from itertools import groupby
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.db.transaction import TransactionManagementError
from django.db.transaction import get_connection
from django.utils.functional import cached_property
from django.utils.module_loading import import_string

from envelope import ERRORS
from envelope import INTERNAL
from envelope import WS_OUTGOING
from envelope.models import Connection

if TYPE_CHECKING:
    from envelope.core.message import ErrorMessage
    from envelope.core.message import Message
    from envelope.core.envelope import Envelope
    from envelope.registries import MessageRegistry
    from envelope.messages.common import BatchMessage

# FIXME: Selectable later on
channel_layer = get_channel_layer()


def get_global_message_registry() -> MessageRegistry:
    from envelope.registries import message_registry

    return message_registry


def get_message_registry(name: str):
    return get_global_message_registry()[name]


def get_context_channel_registry():
    from envelope.registries import context_channel_registry

    return context_channel_registry


def get_pubsub_channel_registry():
    from envelope.registries import pubsub_channel_registry

    return pubsub_channel_registry


def get_error_type(name) -> type[ErrorMessage]:
    return get_message_registry(ERRORS)[name]


def get_envelope(name) -> Envelope:
    from envelope.registries import envelope_registry

    return envelope_registry[name]


def get_envelope_from_message(message: Message) -> Envelope:
    if message.mm.registry is None:
        raise ValueError(f"{message} doesn't seem to have registry set")
    return get_envelope(message.mm.registry)


def get_batch_message() -> type[BatchMessage]:
    try:
        batch_message_name = getattr(settings, "ENVELOPE_BATCH_MESSAGE")
        return import_string(batch_message_name)
    except AttributeError:
        from envelope.messages.common import Batch

        return Batch


def get_sender_util() -> type[SenderUtil]:
    try:
        sender_util_name = getattr(settings, "ENVELOPE_SENDER_UTIL")
        return import_string(sender_util_name)
    except AttributeError:
        from envelope.utils import SenderUtil

        return SenderUtil


def add_envelopes(*envelopes: Envelope):
    """
    Decorator to add handlers to several namespaces.


    >>> from envelope.registries import envelope_registry
    >>> from envelope.registries import message_registry
    >>> from envelope.core.envelope import Envelope
    >>> from envelope.schemas import EnvelopeSchema

    >>> add_envelopes(Envelope(schema=EnvelopeSchema, registry_name='hello'))
    >>> 'hello' in envelope_registry
    True
    >>> 'hello' in message_registry
    True

    Cleanup
    >>> del envelope_registry['hello']
    >>> del message_registry['hello']
    """
    from envelope.registries import envelope_registry
    from envelope.registries import message_registry

    for envelope in envelopes:
        envelope_registry[envelope.registry_name] = envelope
        message_registry.setdefault(envelope.registry_name, {})


def add_messages(namespace: str, *messages: type[Message]):
    from envelope.registries import message_registry

    assert namespace in message_registry, "No message registry named %s" % namespace
    for message in messages:
        message_registry[namespace][message.name] = message


def update_connection_status(
    user_pk: int,
    channel_name: str,
    online: bool | None = True,
    awol: bool | None = None,
    online_at: datetime | None = None,
    offline_at: datetime | None = None,
    last_action: datetime | None = None,
) -> Connection:
    """
    This is sync-only code so don't call this in any async context!
    """
    new_values = {
        "online": online,
        "awol": awol,
        "online_at": online_at,
        "offline_at": offline_at,
        "last_action": last_action,
    }
    # None means we shouldn't touch it
    new_values = {k: v for k, v in new_values.items() if v is not None}
    conn, created = Connection.objects.update_or_create(
        user_id=user_pk,
        channel_name=channel_name,
        defaults=new_values,
    )
    return conn


class SenderUtil:
    """
    Takes care of sending data to channels.
    Made callable, so it can be added to the on_commit hook in django.
    """

    # FIXME: Allow channel layer specification?
    def __init__(
        self,
        message: Message,
        *,
        channel_name: str,
        group: bool = False,
        layer_name: str | None = None,
    ):

        self.message = message
        self.envelope = get_envelope_from_message(message)
        self.channel_name = channel_name
        self.group = group

    def __call__(self):
        async_to_sync(self.async_send)()

    @property
    def group_key(self):
        """
        Everything that makes message groupable
        """
        return f"{self.message.name}{self.channel_name}{self.message.mm.registry}{self.message.mm.state and self.message.mm.state or ''}{int(self.group)}"

    @property
    def batch(self) -> bool:
        return self.envelope.allow_batch and self.message.allow_batch

    async def async_send(self):
        if self.envelope.transport is None:
            raise ValueError(
                f"Don't know how to send message {self.message} since envelope {self.message} lacks transport"
            )
        payload = self.envelope.transport(self.envelope, self.message)
        if self.group:
            await channel_layer.group_send(self.channel_name, payload)
        else:
            await channel_layer.send(self.channel_name, payload)


def websocket_send(
    message: Message,
    *,
    channel_name: str = None,
    state: str | None = None,
    on_commit: bool = True,
    group: bool = False,
):
    """
    From sync world outside the websocket consumer - send a message to a group or a specific consumer.

    >>> from envelope.messages.ping import Pong
    >>> from unittest import mock
    >>> msg = Pong(mm={'consumer_name': 'abc'})

    This method can send straight away regardless of transactions
    >>> with mock.patch.object(channel_layer, 'send') as mock_send:
    ...     websocket_send(msg, channel_name='a-channel', on_commit=False)
    ...     mock_send.called
    True

    It can also be used with transactional support.
    >>> from django.db import transaction
    >>> with mock.patch.object(channel_layer, 'send') as mock_send:
    ...     with transaction.atomic():
    ...         websocket_send(msg, channel_name='a-channel')
    ...         pre_commit_called = mock_send.called
    ...     post_commit_called = mock_send.called
    ...
    >>> pre_commit_called
    False
    >>> post_commit_called
    True
    """
    if channel_name is None:
        if group:
            raise Exception(
                "Specify channel_name if you'd like to send the message to a group"
            )
        if message.mm.consumer_name is None:
            raise Exception(
                "Must specify either channel_name as argument to this function or on message"
            )
        channel_name = message.mm.consumer_name
    if state is not None:
        message.mm.state = state
    message.mm.registry = WS_OUTGOING
    sender = get_sender_util()(
        message,
        channel_name=channel_name,
        group=group,
    )
    if on_commit:
        txn_sender = get_or_create_txn_sender()
        if txn_sender is None:
            # logger.info("on_commit called outside of transaction, sending immediately")
            sender()
        else:
            txn_sender.add(sender)
    else:
        sender()


def internal_send(
    message: Message,
    *,
    channel_name: str = None,
    state: str | None = None,
    on_commit: bool = True,
    group: bool = False,
):
    """
    From sync world outside the consumer - send an internal message to a group or a specific consumer.

    >>> from envelope.messages.ping import Pong
    >>> from unittest import mock
    >>> msg = Pong(mm={'consumer_name': 'abc'})

    This method can send straight away regardless of transactions
    >>> with mock.patch.object(channel_layer, 'send') as mock_send:
    ...     internal_send(msg, channel_name='a-channel', on_commit=False)
    ...     mock_send.called
    True

    It can also be used with transactional support.
    >>> from django.db import transaction
    >>> with mock.patch.object(channel_layer, 'send') as mock_send:
    ...     with transaction.atomic():
    ...         internal_send(msg, channel_name='a-channel')
    ...         pre_commit_called = mock_send.called
    ...     post_commit_called = mock_send.called
    ...
    >>> pre_commit_called
    False
    >>> post_commit_called
    True
    """
    if channel_name is None:
        if group:
            raise Exception(
                "Specify channel_name if you'd like to send the message to a group"
            )
        if message.mm.consumer_name is None:
            raise Exception(
                "Must specify either channel_name as argument to this function or on message"
            )
        channel_name = message.mm.consumer_name
    if state is not None:
        message.mm.state = state
    message.mm.registry = INTERNAL
    sender = get_sender_util()(
        message,
        channel_name=channel_name,
        group=group,
    )
    if on_commit:
        transaction.on_commit(sender)
    else:
        sender()


def websocket_send_error(
    error: ErrorMessage,
    *,
    channel_name: str,
    group: bool = False,
):
    """
    Send an error to a group or a specific consumer. Errors can't be a part of transactions since
    there's a high probability that the transaction won't commit. (Depending on the error of course)
    """

    error.mm.registry = ERRORS
    sender = get_sender_util()(
        error,
        channel_name=channel_name,
        group=group,
    )
    sender()


def get_or_create_txn_sender(
    using: str | None = None, raise_exception=False
) -> TransactionSender | None:
    """
    >>> from django.db import transaction
    >>> txn_sender = get_or_create_txn_sender(raise_exception=True)
    Traceback (most recent call last):
    ...
    django.db.transaction.TransactionManagementError:

    >>> with transaction.atomic():
    ...     txn_sender = get_or_create_txn_sender()
    ...     isinstance(txn_sender, TransactionSender)
    True

    ...     get_or_create_txn_sender() is txn_sender
    True

    """
    conn = get_connection(using=using)
    if not conn.in_atomic_block:
        if raise_exception:
            raise TransactionManagementError("Not an atomic block")
        return
    for (_, _callable) in conn.run_on_commit:
        if isinstance(_callable, TransactionSender):
            return _callable
    txn_sender = TransactionSender()
    conn.on_commit(txn_sender)
    return txn_sender


class TransactionSender:
    def __init__(self):
        self.data = []

    def __call__(self):
        self.batch_messages()
        for x in self:
            x()

    @cached_property
    def batch_factory(self) -> type[BatchMessage]:
        return get_batch_message()

    @cached_property
    def sender_util(self) -> type[SenderUtil]:
        return get_sender_util()

    def groupby(self):
        return groupby(self.data, key=lambda x: x.group_key)

    def batch_messages(self):
        """
        Go through all messages and batch them if possible
        """

        data = []
        for k, g in self.groupby():
            items = list(g)
            if len(items) > 2 and items[0].batch:
                initial_util = items.pop(0)
                batch = self.batch_factory.start(initial_util.message)
                for util in items:
                    batch.append(util.message)
                items = [
                    self.sender_util(
                        batch,
                        channel_name=initial_util.channel_name,
                        group=initial_util.group,
                        # as_dict=initial_util.as_dict,
                        # run_handlers=initial_util.run_handlers,
                        # state=initial_util.state,
                    )
                ]
            data.extend(items)
        self.data = data

    def add(self, sender_util: SenderUtil):
        self.data.append(sender_util)

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)
