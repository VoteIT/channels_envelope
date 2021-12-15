# API
from .base import Message
from .base import ErrorMessage
from .base import AsyncRunnable
from .base import MessageMeta


def register_messages():
    from . import ping
    from django.conf import settings

    if settings.DEBUG:
        from . import testing
