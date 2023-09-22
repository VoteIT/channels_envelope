from django.apps import AppConfig
from django.conf import settings


class EvenlopeChannelsConfig(AppConfig):
    name = "envelope.channels"
    label = "envelope_channels"

    def ready(self):
        from . import errors
        from . import messages

        if settings.DEBUG:
            from . import testing
