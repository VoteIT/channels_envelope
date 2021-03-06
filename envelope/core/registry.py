from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from collections import UserDict
from typing import Dict
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type


if TYPE_CHECKING:
    from envelope.core.message import Message
    from envelope.core.envelope import Envelope
    from envelope.core.channels import ContextChannel
    from envelope.core.channels import PubSubChannel
    from envelope.handlers.base import AsyncHandler

global_message_registry = {}
global_handler_registry = {}


class Registry(UserDict, ABC):
    @abstractmethod
    def get_type(self) -> Optional[Type]:
        ...

    def add(self, klass):
        """
        Convenience method since key should always be from name
        """
        self[klass.name] = klass

    def __setitem__(self, name, klass):
        assert getattr(klass, "name", None), "%s must have a 'name' attribute" % klass
        assert name == klass.name
        type = self.get_type()
        if type:
            assert issubclass(klass, type)
        abs_methods = getattr(klass, "__abstractmethods__", None)
        if abs_methods:
            missing = "', '".join(abs_methods)
            raise TypeError(
                f"{klass} doesn't implement the required abstract methods: '{missing}'"
            )
        super().__setitem__(name, klass)


class MultiRegistry(Registry, ABC):
    def __init__(self, name):
        super().__init__()
        if name in self.global_registry:
            raise KeyError(f"{name} already exists within this registry")
        self.global_registry[name] = self
        self.name = name

    @property
    @abstractmethod
    def global_registry(self):
        """
        Return a dict where every instance of this registry type will be stored
        """

    def __setitem__(self, name, klass):
        super().__setitem__(name, klass)
        klass.registries().add(self.name)


class MessageRegistry(MultiRegistry):
    global_registry = global_message_registry
    data: Dict[str, Type[Message]]

    def get_type(self):
        from envelope.core.message import Message

        return Message


class HandlerRegistry(MultiRegistry):
    global_registry = global_handler_registry
    data: Dict[str, Type[AsyncHandler]]

    def get_type(self):
        from envelope.handlers import AsyncHandler

        return AsyncHandler

    async def apply(self, message, **kwargs) -> dict:
        result = {}
        for (name, klass) in self.items():
            handler: AsyncHandler = klass(message, **kwargs)
            if handler:
                result[name] = await handler.run()
            else:
                result[name] = False
        return result


class EnvelopeRegistry(Registry):
    """
    Contains envelopes the system should be aware of.
    Any message registry needs a corresponding envelope.
    """

    data: Dict[str, Type[Envelope]]

    def get_type(self):
        from envelope.core.envelope import Envelope

        return Envelope


class ChannelRegistry(Registry):
    """
    Stores channel types the system should be aware of.
    It's up to the developer to decide if a channel should be registered or not.
    """

    data: Dict[str, Type[PubSubChannel]]

    def get_type(self):
        from envelope.core.channels import PubSubChannel

        return PubSubChannel


class ContextChannelRegistry(Registry):
    """
    Stores channel types the system should be aware of.
    It's up to the developer to decide if a channel should be registered or not.

    This is separate from the pub/sub channels since they can't have permissions.
    Subscribe/leave commands are only executed against channels within this registry.
    """

    data: Dict[str, Type[ContextChannel]]

    def get_type(self):
        from envelope.core.channels import ContextChannel

        return ContextChannel


def validate_registries():
    """
    Make sure all registries here have a corresponding envelope and matching handlers.

    >>> from envelope.apps import ChannelsEnvelopeConfig
    >>> ChannelsEnvelopeConfig.populate_registries()
    >>> validate_registries()
    """
    from envelope.registries import envelope_registry

    for k in global_message_registry:
        assert (
            k in envelope_registry
        ), f"Message registry {k} has no envelope registered to handle it"
        assert (
            k in global_handler_registry
        ), f"Message registry {k} has no handler registry with the same name"
