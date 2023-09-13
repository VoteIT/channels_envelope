from __future__ import annotations
from logging import getLogger
from typing import TYPE_CHECKING

from async_signals import Signal
from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured




if TYPE_CHECKING:
    from envelope.core.message import Message

logger = getLogger(__name__)


class ChannelsEnvelopeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "envelope"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.deferred_message_signals = set()

    def ready(self):
        from envelope.envelopes import register_envelopes

        register_envelopes()

        from envelope.core.errors import register_errors

        register_errors()

        self.check_consumer_settings()
        self.check_registries_names()
        self.register_deferred_signals()

    @staticmethod
    def check_consumer_settings():
        ...
        # Consumer
        # if not isinstance(getattr(settings, "ENVELOPE_CONSUMER", None), dict):
        #     raise ImproperlyConfigured(
        #         "ENVELOPE_CONSUMER must exist in settings and be a dict"
        #     )
        # consumer_settings = settings.ENVELOPE_CONSUMER
        #
        # for (k, v) in [
        #     ("connect_signal_job", "envelope.jobs.signal_websocket_connect"),
        #     ("close_signal_job", "envelope.jobs.signal_websocket_connect"),
        # ]:
        #     consumer_settings.setdefault(k, v)
        #     if isinstance(consumer_settings[k], str):
        #         consumer_settings[k] = import_string(consumer_settings[k])
        # for (k, v) in [
        #     ("connections_queue", "default"),
        #     ("timestamp_queue", "default"),
        # ]:
        #     consumer_settings.setdefault(k, v)
        #     queue = get_queue(consumer_settings[k])
        #     if not isinstance(queue, Queue):
        #         raise ImproperlyConfigured(
        #             f"ENVELOPE_CONSUMER queue {consumer_settings[k]} is not a valid RQ Queue"
        #         )

    @staticmethod
    def check_registries_names():
        """
        >>> ChannelsEnvelopeConfig.check_registries_names()

        >>> from envelope.registries import envelope_registry
        >>> envelope_registry['_testing'] = {}
        >>> ChannelsEnvelopeConfig.check_registries_names()
        Traceback (most recent call last):
        ...
        django.core.exceptions.ImproperlyConfigured:

        Cleanup
        >>> _ = envelope_registry.pop('_testing')
        """
        from envelope.registries import message_registry
        from envelope.registries import envelope_registry

        missing = set(envelope_registry) - set(message_registry)
        if missing:
            raise ImproperlyConfigured(
                f"Message registries {','.join(missing)} have no corresponding envelope registry. Messages won't work."
            )

    def add_deferred_message_signal(
        self, signal: Signal, func: callable, superclass: type[Message], kwargs: dict
    ):
        self.deferred_message_signals.add(
            # FIX tuple
            (signal, func, superclass, tuple([(k, v) for k, v in kwargs]))
        )

    def register_deferred_signals(self):
        from envelope.utils import get_global_message_registry

        for registry in get_global_message_registry().values():
            for msg_klass in registry.values():
                for (signal, func, superclass, kwargs) in self.deferred_message_signals:
                    if issubclass(msg_klass, superclass):
                        signal.connect(func, sender=msg_klass, **dict(kwargs))
        self.deferred_message_signals.clear()
