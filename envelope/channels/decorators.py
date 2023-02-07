from __future__ import annotations

from envelope.channels.models import ContextChannel
from envelope.channels.models import PubSubChannel


def add_pubsub_channel(klass: PubSubChannel):
    """
    Decorator to add pub/sub channel
    >>> from envelope.channels.decorators import add_pubsub_channel
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

    pubsub_channel_registry[klass.name] = klass
    return klass


def add_context_channel(klass: ContextChannel):
    """
    Decorator to context channel

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

    context_channel_registry[klass.name] = klass
    return klass
