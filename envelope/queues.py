from typing import Optional
from typing import Union

from django.conf import settings
from django_rq import get_queue
from rq import Queue

DEFAULT_QUEUE_NAME = "default"


def get_connection_queue(queue: Optional[Union[str, Queue]] = None) -> Queue:
    """
    Return connection queue used for adding jobs that relate to connect/disconnect
    """
    if queue is None:
        try:
            queue = settings.ENVELOPE_CONNECTIONS_QUEUE
        except AttributeError:
            queue = DEFAULT_QUEUE_NAME
    if isinstance(queue, str):
        return get_queue(queue)
    elif isinstance(queue, Queue):
        return queue
    else:
        raise TypeError(f"{queue} is not a str or instance of rq.Queue")


def get_timestamp_queue(queue: Optional[Union[str, Queue]] = None) -> Queue:
    """
    Return timestamp queue used for adding jobs that relate to connect/disconnect
    """
    if queue is None:
        try:
            queue = settings.ENVELOPE_TIMESTAMP_QUEUE
        except AttributeError:
            queue = DEFAULT_QUEUE_NAME
    if isinstance(queue, str):
        return get_queue(queue)
    elif isinstance(queue, Queue):
        return queue
    else:
        raise TypeError(f"{queue} is not a str or instance of rq.Queue")
