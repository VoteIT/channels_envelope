from __future__ import annotations
from typing import TYPE_CHECKING

from async_signals import Signal
from django.apps import apps

if TYPE_CHECKING:
    from envelope.core.message import Message


def add_message(*namespaces):
    """
    Decorator to add messages to a specific message registry.

    >>> from envelope.core.message import Message
    >>> from envelope.utils import get_message_registry

    >>> @add_message('testing')
    ... class HelloWorld(Message):
    ...     name='hello_world'
    ...

    >>> testing_messages = get_message_registry('testing')
    >>> 'hello_world' in testing_messages
    True
    """

    def _inner(cls):
        from envelope.utils import get_global_message_registry

        global_reg = get_global_message_registry()

        for name in namespaces:
            # Check names later instead
            reg = global_reg.setdefault(name, {})
            reg[cls.name] = cls
        return cls

    return _inner


def receiver_all_message_subclasses(
    signals: Signal | list[Signal] | set[Signal], sender=None, **kwargs
):
    """
    Similar to Django's receiver decorator, but fetches messages that subclassed sender.
    """
    from envelope.core.message import Message

    assert isinstance(sender, type), "This decorator requires sender to be specified"
    assert issubclass(sender, Message), "This only works for messages"
    if not isinstance(signals, (list, tuple, set)):
        signals = (signals,)

    def _decorator(func):
        app_config = apps.get_app_config("envelope")
        for signal in signals:
            app_config.add_deferred_message_signal(signal, func, sender, kwargs)
        return func

    return _decorator
