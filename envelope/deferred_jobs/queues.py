from django.conf import settings
from django_rq import get_queue
from rq import Queue

from envelope import DEFAULT_QUEUE_NAME


def get_queue_or_default(attr: str, default=DEFAULT_QUEUE_NAME, **kwargs) -> Queue:
    try:
        name = getattr(settings, attr)
    except AttributeError:
        name = default
    if name is not None:
        return get_queue(name, **kwargs)
