# API


def register_messages():
    from . import ping
    from django.conf import settings

    if settings.DEBUG:
        from . import testing
