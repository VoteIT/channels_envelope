from __future__ import annotations
from collections import UserDict
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from envelope.core.message import Message
    from envelope.core.envelope import Envelope
    from envelope.channels.models import ContextChannel
    from envelope.channels.models import PubSubChannel

__all__ = (
    "MessageRegistry",
    "EnvelopeRegistry",
    "PubSubChannelRegistry",
    "ContextChannelRegistry",
    "message_registry",
    "envelope_registry",
    "pubsub_channel_registry",
    "context_channel_registry",
)


class MessageRegistry(UserDict):
    data: dict[str, dict[str, type[Message]]]


class EnvelopeRegistry(UserDict):
    data: dict[str, Envelope]


class PubSubChannelRegistry(UserDict):
    data: dict[str, type[PubSubChannel]]


class ContextChannelRegistry(UserDict):
    data: dict[str, type[ContextChannel]]


message_registry = MessageRegistry()
envelope_registry = EnvelopeRegistry()
pubsub_channel_registry = PubSubChannelRegistry()
context_channel_registry = ContextChannelRegistry()
