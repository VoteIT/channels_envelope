from envelope import ERRORS
from envelope import INTERNAL
from envelope import INTERNAL_TRANSPORT
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope import WS_SEND_ERROR_TRANSPORT
from envelope import WS_SEND_TRANSPORT
from envelope import async_signals
from envelope.core.envelope import DictTransport
from envelope.core.envelope import Envelope
from envelope.core.envelope import TextTransport
from envelope.schemas import EnvelopeSchema
from envelope.schemas import ErrorEnvelopeSchema
from envelope.schemas import IncomingEnvelopeSchema
from envelope.schemas import OutgoingEnvelopeSchema
from envelope.utils import add_envelopes

__all__ = ("register_envelopes",)  # Should be done via settings instead
incoming = Envelope(
    schema=IncomingEnvelopeSchema,
    registry_name=WS_INCOMING,
    message_signal=async_signals.incoming_websocket_message,
)
outgoing = Envelope(
    schema=OutgoingEnvelopeSchema,
    registry_name=WS_OUTGOING,
    transport=TextTransport(WS_SEND_TRANSPORT),
    message_signal=async_signals.outgoing_websocket_message,
    allow_batch=True,
)
internal = Envelope(
    schema=EnvelopeSchema,
    registry_name=INTERNAL,
    transport=DictTransport(INTERNAL_TRANSPORT),
    message_signal=async_signals.incoming_internal_message,
)
errors = Envelope(
    schema=ErrorEnvelopeSchema,
    registry_name=ERRORS,
    transport=DictTransport(WS_SEND_ERROR_TRANSPORT),
    message_signal=async_signals.outgoing_websocket_error,
)


def register_envelopes():
    add_envelopes(incoming, outgoing, internal, errors)
