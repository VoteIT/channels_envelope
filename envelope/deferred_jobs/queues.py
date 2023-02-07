from django.conf import settings
from django_rq import get_queue
from rq import Queue

from envelope import DEFAULT_QUEUE_NAME


def get_queue_or_default(attr: str, default=DEFAULT_QUEUE_NAME, **kwargs) -> Queue:
    try:
        name = getattr(settings, attr)
    except AttributeError:
        name = DEFAULT_QUEUE_NAME
    if name is not None:
        return get_queue(name, **kwargs)


CONNECTIONS_QUEUE = get_queue_or_default("ENVELOPE_CONNECTIONS_QUEUE")
TIMESTAMP_QUEUE = get_queue_or_default("ENVELOPE_TIMESTAMP_QUEUE")
