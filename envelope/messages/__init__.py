from django.conf import settings

# API
from .base import ErrorMessage
from .base import Message
from .base import AsyncRunnable
from .base import MessageMeta
from .base import MessageStates


def register_messages():
    from . import ping

    if settings.DEBUG:
        from . import testing
