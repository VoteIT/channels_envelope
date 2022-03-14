from datetime import datetime
from logging import getLogger
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import activate
from envelope import WS_INCOMING

from envelope import Error
from envelope.handlers.deferred_job import DeferredJob
from envelope.core.message import ErrorMessage
from envelope.models import Connection
from envelope.signals import client_close
from envelope.signals import client_connect
from envelope.utils import get_envelope_registry
from envelope.utils import get_error_type
from envelope.utils import update_connection_status
from envelope.utils import websocket_send_error

User = get_user_model()

logger = getLogger(__name__)


# FIXME: We'll need our own worker class to have decent throughput
# https://python-rq-docs-cn.readthedocs.io/en/latest/workers.html#performance-notes


def _set_lang(lang=None):
    """
    Language is set via the request normally, so it has to be set manually outside of the regular request scope.
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
            websocket_send_error(err, consumer_name)
            return err  # For testing, has no effect


def signal_websocket_connect(
    user_pk: int = None,
    consumer_name: str = "",
    language: Optional[str] = None,
    online_at: datetime = None,
):
    """
    This job handles the sync code for a user connecting to a consumer.
    """
    assert online_at
    user = User.objects.get(
        pk=user_pk
    )  # User should always exist when this job is dispatched
    _set_lang(language)
    logger.debug("%s connected consumer %s", user_pk, consumer_name)
    conn = update_connection_status(
        user=user,
        channel_name=consumer_name,
        online=True,
        online_at=online_at,
        last_action=online_at,  # Yes same
    )
    client_connect.send(
        sender=None,
        user=user,
        consumer_name=consumer_name,
        connection=conn,
    )


def signal_websocket_close(
    user_pk: int = None,
    consumer_name: str = "",
    close_code: int = None,
    language: Optional[str] = None,
    offline_at: datetime = None,
):
    assert offline_at
    user = User.objects.get(
        pk=user_pk
    )  # User should always exist when this job is dispatched
    _set_lang(language)
    conn = update_connection_status(
        user, channel_name=consumer_name, online=False, offline_at=offline_at
    )
    logger.debug(
        "%s disconnected consumer %s. close_code: %s",
        user_pk,
        consumer_name,
        close_code,
    )
    client_close.send(
        sender=None,
        user=user,
        user_pk=user_pk,
        consumer_name=consumer_name,
        close_code=close_code,
        connection=conn,
    )


def mark_connection_action(
    consumer_name: str = "",
    action_at: datetime = None,
):
    conn: Connection = Connection.objects.get(channel_name=consumer_name)
    conn.last_action = action_at
    conn.save()


def default_incoming_websocket(
    t: str,
    data: dict,
    mm: dict,
    enqueued_at: datetime = None,
    envelope=WS_INCOMING,  # For testing injection
):
    reg = get_envelope_registry()
    envelope_type = reg[envelope]
    env = envelope_type(t=t, p=data)
    msg = env.unpack(mm=mm)
    run_job(msg, enqueued_at=enqueued_at)


def run_job(msg: DeferredJob, enqueued_at: datetime = None):
    msg.on_worker = True
    if msg.connection:
        # We could've used enqueued_at from RQ if it had supported TZ :(
        if enqueued_at is None:
            enqueued_at = now()
        if msg.connection.last_action < enqueued_at:
            msg.connection.last_action = enqueued_at
            msg.connection.save()
    msg.validate()  # We already know this is valid since it has passed the consumers handle func
    if msg.mm.language:
        # Otherwise skip lang?
        activate(msg.mm.language)
    try:
        if msg.atomic:
            with transaction.atomic(durable=True):
                msg.run_job()
        else:
            msg.run_job()
    except ErrorMessage as err:  # Catchable, nice errors
        if err.mm.id is None:
            err.mm.id = msg.mm.id
        if err.mm.consumer_name is None:
            err.mm.consumer_name = msg.mm.consumer_name
        if err.mm.consumer_name:
            websocket_send_error(err, err.mm.consumer_name)
