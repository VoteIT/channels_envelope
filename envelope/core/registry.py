from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from collections import UserDict
from typing import Dict
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type

from envelope.core.channels import PubSubChannel

if TYPE_CHECKING:
    from envelope.handlers.base import AsyncHandler
    from envelope.core.message import Message

global_message_registry = {}
global_handler_registry = {}
global_channel_registry = {}


class Registry(UserDict, ABC):
    name: str
    global_registry: dict  # Also for testing injection

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
        klass.registries().add(self.name)
        super().__setitem__(name, klass)


class MessageRegistry(Registry):
    global_registry = global_message_registry
    data: Dict[str, Type[Message]]

    def get_type(self):
        from envelope.core.message import Message

        return Message


class HandlerRegistry(Registry):
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


class ChannelRegistry(Registry):
    """
    This stores channel types the system should be aware of.
    It's up to the developer to decide if a channel should be registered or not.
    """

    global_registry = global_channel_registry
    data: Dict[str, Type[PubSubChannel]]

    def get_type(self):
        from envelope.core.channels import PubSubChannel

        return PubSubChannel
