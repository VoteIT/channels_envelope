from envelope import DEFAULT_CHANNELS


def add_message(*namespaces):
    """
    Decorator to add messages to a specific message registry.

    >>> from envelope.testing import testing_messages
    >>> from envelope.messages import Message

    >>> @add_message('testing')
    ... class HelloWorld(Message):
    ...     name='hello_world'
    ...

    >>> 'hello_world' in testing_messages
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
    """
    Decorator to add message handlers to a specific registry.

    >>> from envelope.testing import testing_handlers
    >>> from envelope.handlers import AsyncHandler

    >>> @add_handler('testing')
    ... class HelloWorld(AsyncHandler):
    ...     name='hello_world'
    ...
    ...     def check(self): return True
    ...
    ...     async def run(self): ...
    ...

    >>> 'hello_world' in testing_handlers
    True
    """

    def _inner(cls):
        from envelope.registry import global_handler_registry

        for name in namespaces:
            assert name in global_handler_registry, (
                "No handler registry named %s" % name
            )
            reg = global_handler_registry[name]
            reg.add(cls)
        return cls

    return _inner


def add_channel(*namespaces):
    """
    Decorator to add pub/sbunchannel to a specific registry

    >>> from envelope.testing import testing_channels
    >>> from envelope.channels import PubSubChannel
    >>> from envelope.utils import get_channel_registry

    >>> @add_channel('testing')
    ... class HelloWorld(PubSubChannel):
    ...     name='hello_world'
    ...     channel_name='testing_demo'
    ...

    >>> 'hello_world' in testing_channels
    True

    """
    # FIXME: Allow arg-less default

    def _inner(cls):
        from envelope.registry import global_channel_registry

        for name in namespaces:
            assert name in global_channel_registry, (
                "No channel registry named %s" % name
            )
            reg = global_channel_registry[name]
            reg.add(cls)
        return cls

    return _inner
