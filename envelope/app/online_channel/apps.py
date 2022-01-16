from django.apps import AppConfig


class OnlineChannelConfig(AppConfig):
    name = "envelope.app.online_channel"

    def ready(self):
        from . import channel
        from . import signals
