from __future__ import annotations

from async_signals import Signal


__all__ = (
    "consumer_connected",
    "consumer_closed",
    "incoming_internal_message",
    "incoming_websocket_message",
    "outgoing_websocket_error",
    "outgoing_websocket_message",
)


consumer_connected = Signal(debug=True)
consumer_closed = Signal(debug=True)
incoming_websocket_message = Signal(debug=True)
outgoing_websocket_message = Signal(debug=True)
outgoing_websocket_error = Signal(debug=True)
incoming_internal_message = Signal(debug=True)
