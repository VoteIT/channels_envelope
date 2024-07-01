from __future__ import annotations

from datetime import datetime
from logging import getLogger

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import activate

from envelope.signals import connection_closed
from envelope.signals import connection_created
from envelope.utils import update_connection_status

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


def create_connection_status_on_websocket_connect(
    *,
    user_pk: int,
    consumer_name: str = "",
    language: str | None = None,
    online_at: datetime = None,
):
    """
    This job handles the sync code for a user connecting to a consumer.
    """
    assert online_at
    _set_lang(language)
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
    _set_lang(language)
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
