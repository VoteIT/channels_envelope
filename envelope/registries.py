from __future__ import annotations

from envelope import DEFAULT_PUBSUB_CHANNELS
from envelope import DEFAULT_CONTEXT_CHANNELS
from envelope import DEFAULT_ERRORS
from envelope import INTERNAL
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.core.registry import ChannelRegistry
from envelope.core.registry import ContextChannelRegistry
from envelope.core.registry import HandlerRegistry
from envelope.core.registry import MessageRegistry

ws_incoming_messages = MessageRegistry(WS_INCOMING)
ws_outgoing_messages = MessageRegistry(WS_OUTGOING)
internal_messages = MessageRegistry(INTERNAL)
default_error_messages = MessageRegistry(DEFAULT_ERRORS)
default_pubsub_channel_registry = ChannelRegistry(DEFAULT_PUBSUB_CHANNELS)
default_context_channel_registry = ContextChannelRegistry(DEFAULT_CONTEXT_CHANNELS)

ws_incoming_handlers = HandlerRegistry(WS_INCOMING)
ws_outgoing_handlers = HandlerRegistry(WS_OUTGOING)
internal_handlers = HandlerRegistry(INTERNAL)
default_error_handlers = HandlerRegistry(DEFAULT_ERRORS)
