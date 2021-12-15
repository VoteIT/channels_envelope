# API
from .base import Message
from .base import ErrorMessage
from .base import MessageMeta

from .actions import AsyncRunnable


def register_messages():
    from . import ping
    from django.conf import settings

    if settings.DEBUG:
        from . import testing
