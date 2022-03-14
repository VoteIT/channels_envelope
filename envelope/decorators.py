def add_message(*namespaces):
    """
    Decorator to add messages to a specific message registry.

    >>> from envelope.testing import testing_messages
    >>> from envelope.core.message import Message

    >>> @add_message('testing')
    ... class HelloWorld(Message):
    ...     name='hello_world'
    ...

    >>> 'hello_world' in testing_messages
    True
    """

    def _inner(cls):
        from envelope.core.registry import global_message_registry

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
        from envelope.core.registry import global_handler_registry

        for name in namespaces:
            assert name in global_handler_registry, (
                "No handler registry named %s" % name
            )
            reg = global_handler_registry[name]
            reg.add(cls)
        return cls

    return _inner


def add_pubsub_channel(klass):
    """
    Decorator to add pub/sub channel

    >>> from envelope.core.channels import PubSubChannel
    >>> from envelope.registries import pubsub_channel_registry


    >>> @add_pubsub_channel
    ... class HelloWorld(PubSubChannel):
    ...     name='hello_world'
    ...     channel_name='testing_demo'
    ...

    >>> 'hello_world' in pubsub_channel_registry
    True

    Cleanup
    >>> del pubsub_channel_registry['hello_world']
    """
    from envelope.registries import pubsub_channel_registry

    pubsub_channel_registry.add(klass)
    return klass


def add_context_channel(klass):
    """
    Decorator to context channel

    >>> from envelope.core.channels import ContextChannel
    >>> from envelope.registries import context_channel_registry
    >>> from django.contrib.auth import get_user_model


    >>> @add_context_channel
    ... class HelloWorld(ContextChannel):
    ...     name='hello_world'
    ...     model=get_user_model()
    ...     permission = None
    ...

    >>> 'hello_world' in context_channel_registry
    True

    Cleanup
    >>> del context_channel_registry['hello_world']
    """
    from envelope.registries import context_channel_registry

    context_channel_registry.add(klass)
    return klass


def add_envelope(klass):
    """
    Decorator to add handlers to several namespaces.

    >>> from envelope.core.envelope import Envelope
    >>> from envelope.registries import envelope_registry

    >>> @add_envelope
    ... class HelloEnvelope(Envelope):
    ...     name = 'testing'
    ...     schema = object()
    ...

    >>> 'testing' in envelope_registry
    True

    Cleanup
    >>> del envelope_registry['testing']
    """
    from envelope.registries import envelope_registry

    envelope_registry.add(klass)
    return klass
