from __future__ import annotations


# Registry names
WS_INCOMING = "ws_incoming"
WS_OUTGOING = "ws_outgoing"
INTERNAL = "internal"
ERRORS = "errors"

# The name of the consumer function that will receive outgoing websocket messages queued from a script
# or somewhere outside the consumer
WS_SEND_TRANSPORT = "websocket.send"
WS_SEND_ERROR_TRANSPORT = "ws.error.send"
INTERNAL_TRANSPORT = "internal.msg"


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
    BAD_REQUEST = "error.bad_request"
    MSG_TYPE = "error.msg_type"
    NOT_FOUND = "error.not_found"
    UNAUTHORIZED = "error.unauthorized"
    SUBSCRIBE = "error.subscribe"
    JOB = "error.job"
