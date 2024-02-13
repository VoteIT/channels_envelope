from __future__ import annotations
from logging import getLogger
from typing import TYPE_CHECKING

from async_signals import Signal
from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

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
        from envelope.messages import register_messages
        from envelope.core import async_signals
        from envelope import channels
        from envelope import deferred_jobs

        channels.include()
        deferred_jobs.include()
        register_envelopes()
        register_messages()
        self.check_settings_and_import()
        self.check_registries_names()
        self.check_rq_config()
        self.register_deferred_signals()

    @staticmethod
    def check_settings_and_import():
        from envelope.messages.common import BatchMessage
        from envelope.utils import get_sender_util
        from envelope.utils import SenderUtil

        # Batch message factory to use
        batch_message_name = getattr(settings, "ENVELOPE_BATCH_MESSAGE", None)
        if isinstance(batch_message_name, str):
            klass = import_string(batch_message_name)
            if not issubclass(klass, BatchMessage):
                raise ImproperlyConfigured(
                    f"{klass} is not a subclass of envelope.messages.common.BatchMessage - check ENVELOPE_BATCH_MESSAGE in settings."
                )

        # Sender util to use
        sender_util = get_sender_util()
        if not issubclass(sender_util, SenderUtil):
            raise ImproperlyConfigured(
                f"{sender_util} is not a subclass of envelope.utils.SenderUtil - check ENVELOPE_SENDER_UTIL in settings."
            )

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

    @staticmethod
    def check_rq_config():
        """
        >>> from django.test import override_settings
        >>> with override_settings(RQ_QUEUES={}):
        ...     ChannelsEnvelopeConfig.check_rq_config()
        Traceback (most recent call last):
        ...
        django.core.exceptions.ImproperlyConfigured:
        """
        from envelope.utils import get_global_message_registry
        from envelope.deferred_jobs.message import DeferredJob

        global_reg = get_global_message_registry()
        rq_queues = getattr(settings, "RQ_QUEUES", {})
        for reg_name, reg in global_reg.items():
            for msg in reg.values():
                if issubclass(msg, DeferredJob):
                    if msg.queue not in rq_queues:
                        raise ImproperlyConfigured(
                            f"Message {msg} set to queue {msg.queue} which doesn't exist in settings.RQ_QUEUES"
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
                for signal, func, superclass, kwargs in self.deferred_message_signals:
                    if issubclass(msg_klass, superclass):
                        signal.connect(func, sender=msg_klass, **dict(kwargs))
        self.deferred_message_signals.clear()
