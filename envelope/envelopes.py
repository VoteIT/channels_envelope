from __future__ import annotations

from envelope import ERRORS
from envelope import INTERNAL
from envelope import INTERNAL_TRANSPORT
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope import WS_SEND_ERROR_TRANSPORT
from envelope import WS_SEND_TRANSPORT
from envelope.core.envelope import Envelope
from envelope.core.schemas import EnvelopeSchema
from envelope.core.schemas import ErrorSchema
from envelope.core.schemas import OutgoingEnvelopeSchema
from envelope.decorators import add_envelope


@add_envelope
class IncomingWebsocketEnvelope(Envelope):
    name = WS_INCOMING
    schema = EnvelopeSchema
    data: EnvelopeSchema


@add_envelope
class OutgoingWebsocketEnvelope(Envelope):
    name = WS_OUTGOING
    schema = OutgoingEnvelopeSchema
    data: OutgoingEnvelopeSchema
    transport = WS_SEND_TRANSPORT


@add_envelope
class InternalEnvelope(Envelope):
    name = INTERNAL
    schema = EnvelopeSchema
    data: EnvelopeSchema
    transport = INTERNAL_TRANSPORT


@add_envelope
class ErrorEnvelope(OutgoingWebsocketEnvelope):
    name = ERRORS
    schema = ErrorSchema
    data: ErrorSchema
    transport = WS_SEND_ERROR_TRANSPORT
