from django.apps import AppConfig


class EvenlopeChannelsConfig(AppConfig):
    name = "envelope.channels"
    label = "envelope_channels"

    def ready(self):
        from . import errors
        from . import messages
