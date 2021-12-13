from logging import getLogger
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import activate
from envelope import CONNECTIONS_QUEUE
from envelope.signals import client_close
from envelope.signals import client_connect
from envelope.utils import update_connection_status
from django_rq import job

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


@job(CONNECTIONS_QUEUE)
def signal_websocket_connect(
    user_pk: int = None,
    consumer_name: str = "",
    language: Optional[str] = None,
):
    """
    This job handles the sync code for a user connecting to a consumer.
    """
    user = User.objects.get(
        pk=user_pk
    )  # User should always exist when this job is dispatched
    _set_lang(language)
    logger.debug("%s connected consumer %s", user_pk, consumer_name)
    conn = update_connection_status(user=user, channel_name=consumer_name, online=True)
    client_connect.send(
        sender=None,
        user=user,
        consumer_name=consumer_name,
        connection=conn,
    )


@job(CONNECTIONS_QUEUE)
def signal_websocket_close(
    user_pk: int = None,
    consumer_name: str = "",
    close_code: int = None,
    language: Optional[str] = None,
):
    user = User.objects.get(
        pk=user_pk
    )  # User should always exist when this job is dispatched
    _set_lang(language)
    conn = update_connection_status(user, channel_name=consumer_name, online=False)
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
