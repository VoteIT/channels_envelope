from logging import getLogger

from django.apps import AppConfig
from django.conf import settings

logger = getLogger(__name__)


class ChannelsEnvelopeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "envelope"

    def ready(self):
        if not isinstance(getattr(settings, "ENVELOPE_CONNECTIONS_QUEUE", None), str):
            logger.warning("ENVELOPE_CONNECTIONS_QUEUE missing from settings")
        if not isinstance(getattr(settings, "ENVELOPE_TIMESTAMP_QUEUE", None), str):
            logger.warning("ENVELOPE_TIMESTAMP_QUEUE missing from settings")
        from envelope import signals
        from envelope import registries
        from envelope.messages import register_messages

        register_messages()
        from envelope.handlers import register_handlers

        register_handlers()
