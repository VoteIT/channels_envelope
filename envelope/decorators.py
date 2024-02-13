from __future__ import annotations
from typing import TYPE_CHECKING

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
