from __future__ import annotations

from typing import TYPE_CHECKING

from envelope.core.envelope import Envelope
from envelope.core.schemas import EnvelopeSchema
from envelope.core.schemas import ErrorSchema
from envelope.core.schemas import OutgoingEnvelopeSchema
from envelope.registries import default_error_handlers
from envelope.registries import default_error_messages
from envelope.registries import internal_messages
from envelope.registries import ws_incoming_handlers
from envelope.registries import ws_incoming_messages
from envelope.registries import ws_outgoing_handlers
from envelope.registries import ws_outgoing_messages

if TYPE_CHECKING:
    pass


class IncomingWebsocketEnvelope(Envelope):
    schema = EnvelopeSchema
    data: EnvelopeSchema
    message_registry = ws_incoming_messages
    handler_registry = ws_incoming_handlers


class OutgoingWebsocketEnvelope(Envelope):
    schema = OutgoingEnvelopeSchema
    data: OutgoingEnvelopeSchema
    message_registry = ws_outgoing_messages
    handler_registry = ws_outgoing_handlers


class InternalEnvelope(Envelope):
    schema = EnvelopeSchema
    data: EnvelopeSchema
    message_registry = internal_messages
    handler_registry = ws_outgoing_handlers


class ErrorEnvelope(OutgoingWebsocketEnvelope):
    schema = ErrorSchema
    data: ErrorSchema
    message_registry = default_error_messages
    handler_registry = default_error_handlers
