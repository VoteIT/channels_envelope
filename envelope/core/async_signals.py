from __future__ import annotations
from typing import TYPE_CHECKING

from async_signals import receiver

from envelope.async_signals import incoming_internal_message
from envelope.async_signals import incoming_websocket_message
from envelope.async_signals import outgoing_websocket_error
from envelope.async_signals import outgoing_websocket_message
from envelope.core.message import AsyncRunnable


if TYPE_CHECKING:
    from envelope.consumers.websocket import WebsocketConsumer


@receiver(
    (
        incoming_internal_message,
        outgoing_websocket_error,
        incoming_websocket_message,
        outgoing_websocket_message,
    ),
)
async def run_async_runnable(
    *, consumer: WebsocketConsumer, message: AsyncRunnable, **kwargs
):
    if isinstance(message, AsyncRunnable):
        await message.run(consumer=consumer, **kwargs)
