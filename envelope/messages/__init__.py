# API


def register_messages():
    from . import channels, common, errors, ping
    from django.conf import settings

    if settings.DEBUG:
        from . import testing
