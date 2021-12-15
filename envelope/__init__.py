from typing import TypedDict
from django.conf import settings


WS_INCOMING = "ws_incoming"
WS_OUTGOING = "ws_outgoing"
WS_ERRORS = "ws_errors"
# The name of the consumer function that will receive outgoing websocket messages queued from a script
# or somewhere outside of the consumer
WS_TRANSPORT_NAME = "websocket.send"

# Note: django_rq creates jobs on import, so there's no way to override this setting during runtime
CONNECTIONS_QUEUE = getattr(settings, "ENVELOPE_CONNECTIONS_QUEUE", "default")


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
