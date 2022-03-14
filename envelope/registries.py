from __future__ import annotations


from envelope import ERRORS
from envelope import INTERNAL
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.core.registry import ChannelRegistry
from envelope.core.registry import ContextChannelRegistry
from envelope.core.registry import HandlerRegistry
from envelope.core.registry import MessageRegistry
from envelope.core.registry import EnvelopeRegistry


envelope_registry = EnvelopeRegistry()

ws_incoming_messages = MessageRegistry(WS_INCOMING)
ws_outgoing_messages = MessageRegistry(WS_OUTGOING)
internal_messages = MessageRegistry(INTERNAL)
default_error_messages = MessageRegistry(ERRORS)

pubsub_channel_registry = ChannelRegistry()

context_channel_registry = ContextChannelRegistry()

ws_incoming_handlers = HandlerRegistry(WS_INCOMING)
ws_outgoing_handlers = HandlerRegistry(WS_OUTGOING)
internal_handlers = HandlerRegistry(INTERNAL)
default_error_handlers = HandlerRegistry(ERRORS)
