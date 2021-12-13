from django.apps import AppConfig


class ChannelsEnvelopeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "envelope"

    def ready(self):
        from envelope import signals
        from envelope.messages import register_messages

        register_messages()
        from envelope.handlers import register_handlers

        register_handlers()
