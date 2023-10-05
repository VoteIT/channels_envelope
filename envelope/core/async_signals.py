from __future__ import annotations
from typing import TYPE_CHECKING

from envelope.async_signals import incoming_internal_message
from envelope.async_signals import incoming_websocket_message
from envelope.async_signals import outgoing_websocket_error
from envelope.async_signals import outgoing_websocket_message
from envelope.core.message import AsyncRunnable
from envelope.decorators import receiver_all_message_subclasses

if TYPE_CHECKING:
    from envelope.consumer.websocket import WebsocketConsumer


@receiver_all_message_subclasses(
    {
        incoming_internal_message,
        outgoing_websocket_error,
        incoming_websocket_message,
        outgoing_websocket_message,
    },
    sender=AsyncRunnable,
)
async def run_async_runnable(
    *, consumer: WebsocketConsumer, message: AsyncRunnable, **kwargs
):
    await message.run(consumer=consumer, **kwargs)
