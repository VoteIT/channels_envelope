from __future__ import annotations
from typing import TYPE_CHECKING

# Registry names
WS_INCOMING = "ws_incoming"
WS_OUTGOING = "ws_outgoing"
INTERNAL = "internal"
DEFAULT_ERRORS = "default_errors"
DEFAULT_CHANNELS = "default"

# The name of the consumer function that will receive outgoing websocket messages queued from a script
# or somewhere outside of the consumer
WS_SEND_TRANSPORT = "websocket.send"
WS_SEND_ERROR_TRANSPORT = "ws.error.send"
INTERNAL_TRANSPORT = "internal.msg"

# Note: django_rq creates jobs on import, so there's no way to override this setting during runtime

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


# Common errors
class Error:
    GENERIC = "error.generic"
    VALIDATION = "error.validation"
    MSG_TYPE = "error.msg_type"
    NOT_FOUND = "error.not_found"
    UNAUTHORIZED = "error.unauthorized"
    SUBSCRIBE = "error.subscribe"
