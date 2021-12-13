from django.conf import settings

WS_INCOMING = "ws_incoming"
WS_OUTGOING = "ws_outgoing"
WS_ERRORS = "ws_errors"
# The name of the consumer function that will receive outgoing websocket messages queued from a script
# or somewhere outside of the consumer
WS_TRANSPORT_NAME = "websocket.send"

CONNECTIONS_QUEUE = getattr(settings, "ENVELOPE_CONNECTIONS_QUEUE", "default")
