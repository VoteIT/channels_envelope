from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from async_signals import receiver
from django.conf import settings
from django.utils.timezone import now
from django_rq import get_queue

from envelope.async_signals import consumer_connected
from envelope.async_signals import consumer_closed
from envelope.async_signals import incoming_internal_message
from envelope.async_signals import incoming_websocket_message
from envelope.async_signals import outgoing_websocket_error
from envelope.async_signals import outgoing_websocket_message
from envelope.deferred_jobs.jobs import create_connection_status_on_websocket_connect
from envelope.deferred_jobs.jobs import mark_connection_action
from envelope.deferred_jobs.jobs import update_connection_status_on_websocket_close
from envelope.deferred_jobs.message import DeferredJob

if TYPE_CHECKING:
    from envelope.consumers.websocket import WebsocketConsumer

logger = getLogger(__name__)


@receiver(consumer_connected)
async def dispatch_connection_job(consumer: WebsocketConsumer, **kwargs):
    if consumer.user_pk:
        if queue_name := getattr(settings, "ENVELOPE_CONNECTIONS_QUEUE", None):
            queue = get_queue(name=queue_name)
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


@receiver(consumer_closed)
async def dispatch_disconnection_job(
    consumer: WebsocketConsumer, close_code: None | int = None, **kwargs
):
    if consumer.user_pk:
        if queue_name := getattr(settings, "ENVELOPE_CONNECTIONS_QUEUE", None):
            queue = get_queue(name=queue_name)
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
                "'consumer_closed' signal 'dispatch_disconnection_job' to queue '%s' for consumer '%s'",
                queue.name,
                consumer.channel_name,
            )


@receiver(incoming_websocket_message)
async def maybe_update_connection(*, consumer: WebsocketConsumer, **kwargs):
    if consumer.connection_update_interval is not None and consumer.user_pk:
        if queue_name := getattr(settings, "ENVELOPE_TIMESTAMP_QUEUE", None):
            queue = get_queue(name=queue_name)
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


@receiver(
    (
        incoming_internal_message,
        outgoing_websocket_error,
        incoming_websocket_message,
        outgoing_websocket_message,
    ),
)
async def queue_deferred_job(
    *, consumer: WebsocketConsumer, message: DeferredJob, **kwargs
):
    if isinstance(message, DeferredJob):
        await message.pre_queue(consumer=consumer, **kwargs)
        if message.should_run:
            job = message.enqueue()
            consumer.last_job = now()
            await message.post_queue(job=job, consumer=consumer, **kwargs)
