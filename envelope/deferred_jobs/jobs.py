from __future__ import annotations
from datetime import datetime
from logging import getLogger
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import activate

from envelope import Error
from envelope import WS_INCOMING
from envelope.core.message import ErrorMessage
from envelope.signals import connection_closed
from envelope.signals import connection_created
from envelope.utils import get_envelope
from envelope.utils import get_error_type
from envelope.utils import update_connection_status
from envelope.utils import websocket_send_error

if TYPE_CHECKING:
    from envelope.deferred_jobs.message import DeferredJob

User = get_user_model()

logger = getLogger(__name__)


# FIXME: We'll need our own worker class to have decent throughput
# https://python-rq-docs-cn.readthedocs.io/en/latest/workers.html#performance-notes


def _set_lang(lang=None):
    """
    Language is set via the request normally, so it has to be set manually outside the regular request scope.
    """
    if lang is None:
        lang = settings.LANGUAGE_CODE
    activate(lang)


def handle_failure(job, connection, exc_type, exc_value, traceback):
    """
    Failure callbacks are functions that accept job, connection, type, value and traceback arguments.
    type, value and traceback values returned by sys.exc_info(),
    which is the exception raised when executing your job.

    See RQs docs
    """
    mm = job.kwargs.get("mm", {})
    if mm:
        message_id = mm.get("id", None)
        consumer_name = mm.get("consumer_name", None)
        if message_id and consumer_name:
            # FIXME: exc value might not be safe here
            err = get_error_type(Error.JOB)(mm=mm, msg=str(exc_value))
            websocket_send_error(err, channel_name=consumer_name)
            return err  # For testing, has no effect


def create_connection_status_on_websocket_connect(
    user_pk: int = None,
    consumer_name: str = "",
    language: str | None = None,
    online_at: datetime = None,
):
    """
    This job handles the sync code for a user connecting to a consumer.
    """
    assert online_at
    #    _set_lang(language)
    logger.debug("%s connected consumer %s", user_pk, consumer_name)
    connection = update_connection_status(
        user_pk=user_pk,
        channel_name=consumer_name,
        online=True,
        online_at=online_at,
        last_action=online_at,  # Yes same
    )
    connection_created.send(
        sender=connection.__class__,
        instance=connection,
        language=language,
    )


def update_connection_status_on_websocket_close(
    user_pk: int = None,
    consumer_name: str = "",
    close_code: int = None,
    language: str | None = None,
    offline_at: datetime = None,
):
    assert offline_at
    # _set_lang(language)
    connection = update_connection_status(
        user_pk, channel_name=consumer_name, online=False, offline_at=offline_at
    )
    logger.debug(
        "%s disconnected consumer %s. close_code: %s",
        user_pk,
        consumer_name,
        close_code,
    )
    connection_closed.send(
        sender=connection.__class__,
        instance=connection,
        close_code=close_code,
        language=language,
    )


def mark_connection_action(
    *,
    user_pk: int,
    consumer_name: str,
    action_at: datetime,
):
    update_connection_status(user_pk, channel_name=consumer_name, last_action=action_at)


def default_incoming_websocket(
    data: dict, mm: dict, t: str, *, enqueued_at: datetime = None, **kwargs
):
    envelope = get_envelope(WS_INCOMING)
    # We won't handle key error here. Message name should've been checked when it was received.
    message = envelope.registry[t](mm=mm, data=data)
    run_job(message, enqueued_at=enqueued_at)


def run_job(message: DeferredJob, *, enqueued_at: datetime = None, update_conn=True):
    message.on_worker = True
    if message.mm.language:
        # Otherwise skip lang?
        activate(message.mm.language)
    try:
        if message.atomic:
            with transaction.atomic(durable=True):
                message.run_job()
        else:
            message.run_job()
    except ErrorMessage as err:  # Catchable, nice errors
        if err.mm.id is None:
            err.mm.id = message.mm.id
        if err.mm.consumer_name is None:
            err.mm.consumer_name = message.mm.consumer_name
        if err.mm.consumer_name:
            websocket_send_error(err)
    else:
        # Everything went fine
        if update_conn and message.mm.user_pk and message.mm.consumer_name:
            update_connection_status(
                user_pk=message.mm.user_pk,
                channel_name=message.mm.consumer_name,
                last_action=enqueued_at,
            )
