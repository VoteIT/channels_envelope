from __future__ import annotations
from abc import ABC
from abc import abstractmethod
from collections import UserDict
from typing import Dict
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type

from envelope import DEFAULT_ERRORS
from envelope import WS_INCOMING
from envelope import WS_OUTGOING

if TYPE_CHECKING:
    from envelope.handlers.base import AsyncHandler
    from envelope.messages.base import Message

global_message_registry = {}
global_handler_registry = {}


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
        self[klass.name] = klass

    def __setitem__(self, name, klass):
        assert getattr(klass, "name", None), "%s must have a 'name' attribute" % klass
        assert name == klass.name
        type = self.get_type()
        if type:
            assert issubclass(klass, type)
        klass.registries().add(self.name)
        super().__setitem__(name, klass)


class MessageRegistry(Registry):
    global_registry = global_message_registry
    data: Dict[str, Type[Message]]

    def get_type(self) -> Optional[Type]:
        from envelope.messages.base import Message

        return Message


class HandlerRegistry(Registry):
    global_registry = global_handler_registry
    data: Dict[str, Type[AsyncHandler]]

    def get_type(self) -> Optional[Type]:
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


ws_incoming_messages = MessageRegistry(WS_INCOMING)
ws_outgoing_messages = MessageRegistry(WS_OUTGOING)
default_error_messages = MessageRegistry(DEFAULT_ERRORS)

ws_incoming_handlers = HandlerRegistry(WS_INCOMING)
ws_outgoing_handlers = HandlerRegistry(WS_OUTGOING)
default_error_handlers = HandlerRegistry(DEFAULT_ERRORS)
