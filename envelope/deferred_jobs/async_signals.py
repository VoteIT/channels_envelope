from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from async_signals import receiver
from django.utils.timezone import now

from envelope.async_signals import consumer_connected
from envelope.async_signals import consumer_disconnected
from envelope.async_signals import incoming_internal_message
from envelope.async_signals import incoming_websocket_message
from envelope.async_signals import outgoing_websocket_error
from envelope.async_signals import outgoing_websocket_message
from envelope.decorators import receiver_all_message_subclasses
from envelope.deferred_jobs.jobs import create_connection_status_on_websocket_connect
from envelope.deferred_jobs.jobs import mark_connection_action
from envelope.deferred_jobs.jobs import update_connection_status_on_websocket_close
from envelope.deferred_jobs.message import DeferredJob
from envelope.deferred_jobs.queues import get_queue_or_default

if TYPE_CHECKING:
    from envelope.consumer.websocket import WebsocketConsumer

logger = getLogger(__name__)


@receiver(consumer_connected)
async def dispatch_connection_job(consumer: WebsocketConsumer, **kwargs):
    queue = get_queue_or_default("ENVELOPE_CONNECTIONS_QUEUE")
    if queue is not None:
        consumer.last_job = now()
        queue.enqueue(
            create_connection_status_on_websocket_connect,
            user_pk=consumer.user_pk,
            consumer_name=consumer.channel_name,
            language=consumer.language,
            online_at=now(),
        )
        logger.debug(
            "'consumer_connected' signal 'dispatch_connection_job' to queue '%s' for consumer '%s'",
            queue.name,
            consumer.channel_name,
        )


@receiver(consumer_disconnected)
async def dispatch_disconnection_job(
    consumer: WebsocketConsumer, close_code=None, **kwargs
):
    if consumer.user_pk:
        if queue := get_queue_or_default("ENVELOPE_CONNECTIONS_QUEUE"):
            consumer.last_job = now()  # We probably don't need to care about this :)
            queue.enqueue(
                update_connection_status_on_websocket_close,
                user_pk=consumer.user_pk,
                consumer_name=consumer.channel_name,
                close_code=close_code,
                language=consumer.language,
                offline_at=now(),
            )
            logger.debug(
                "'consumer_disconnected' signal 'dispatch_disconnection_job' to queue '%s' for consumer '%s'",
                queue.name,
                consumer.channel_name,
            )


@receiver(incoming_websocket_message)
def maybe_update_connection(*, consumer: WebsocketConsumer, **kwargs):
    if consumer.connection_update_interval is not None and consumer.user_pk:
        if queue := get_queue_or_default("ENVELOPE_TIMESTAMP_QUEUE"):
            # We should check if we need to update
            if (
                consumer.last_job is None
                or now() - consumer.last_job > consumer.connection_update_interval
            ):
                consumer.event_logger.debug("Queued conn update", consumer=consumer)
                # FIXME: configurable probably
                return queue.enqueue(
                    mark_connection_action,
                    user_pk=consumer.user_pk,
                    action_at=now(),
                    consumer_name=consumer.channel_name,
                )


@receiver_all_message_subclasses(
    {
        incoming_internal_message,
        outgoing_websocket_error,
        incoming_websocket_message,
        outgoing_websocket_message,
    },
    sender=DeferredJob,
)
async def queue_deferred_job(
    *, consumer: WebsocketConsumer, message: DeferredJob, **kwargs
):
    await message.pre_queue(consumer=consumer, **kwargs)
    if message.should_run:
        message.enqueue()
        # FIXME: Probably shouldn't mark this here. Rethink design?
        consumer.last_job = now()
