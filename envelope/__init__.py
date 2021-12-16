from __future__ import annotations
from typing import TypedDict, TYPE_CHECKING
from django.conf import settings

WS_INCOMING = "ws_incoming"
WS_OUTGOING = "ws_outgoing"
DEFAULT_ERRORS = "default_errors"
# The name of the consumer function that will receive outgoing websocket messages queued from a script
# or somewhere outside of the consumer
WS_TRANSPORT_NAME = "websocket.send"

# Note: django_rq creates jobs on import, so there's no way to override this setting during runtime
CONNECTIONS_QUEUE = getattr(settings, "ENVELOPE_CONNECTIONS_QUEUE", "default")

if TYPE_CHECKING:
    from envelope.messages import ErrorMessage


class MessageStates:
    """
    Message state constants
    """

    ACKNOWLEDGED = "a"
    QUEUED = "q"
    RUNNING = "r"
    SUCCESS = "s"
    FAILED = "f"
    MESSAGE_STATES = {ACKNOWLEDGED, QUEUED, RUNNING, SUCCESS, FAILED}


class InternalTransport(TypedDict):
    error: bool
    text_data: str
    type: str


# Common errors
class Error:
    GENERIC = "error.generic"
    VALIDATION = "error.validation"
    MSG_TYPE = "error.msg_type"
    NOT_FOUND = "error.not_found"
    UNAUTHORIZED = "error.unauthorized"
