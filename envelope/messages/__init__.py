# API
from envelope.utils import add_messages


def register_messages():
    from . import errors
    from . import common, ping
    from django.conf import settings

    if settings.DEBUG:
        from . import testing
