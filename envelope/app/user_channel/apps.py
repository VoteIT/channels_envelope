from django.apps import AppConfig


class UserChannelConfig(AppConfig):
    name = "envelope.app.user_channel"

    def ready(self):
        from . import channel  # noqa
        from . import async_signals  # noqa
        from . import signals  # noqa
