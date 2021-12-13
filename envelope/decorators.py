from envelope.handlers.base import AsyncHandler
from envelope.messages.base import Message


def add_message(*namespaces):
    """
    Decorator to add messages to a specific message registry.

    >>> from envelope.testing import testing_registry
    >>> from envelope.messages import Message

    >>> @add_message('testing')
    ... class HelloWorld(Message):
    ...     name='hello_world'
    ...

    >>> 'hello_world' in testing_registry
    True
    """

    def _inner(cls):
        from envelope.registry import global_message_registry

        for name in namespaces:
            assert name in global_message_registry, (
                "No message registry named %s" % name
            )
            reg = global_message_registry[name]
            reg.add(cls)
        return cls

    return _inner


def add_handler(*namespaces):
    def _inner(cls):
        assert issubclass(cls, AsyncHandler)
        from envelope.registry import global_handler_registry

        for name in namespaces:
            assert name in global_handler_registry, (
                "No handler registry named %s" % name
            )
            reg = global_handler_registry[name]
            reg.add(cls)
        return cls

    return _inner
