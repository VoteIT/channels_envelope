from abc import ABC
from abc import abstractmethod
from collections import UserDict
from typing import Dict
from typing import Optional
from typing import Type

from envelope import WS_ERRORS
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.handlers.base import AsyncHandler
from envelope.messages.base import Message

global_message_registry = {}
global_handler_registry = {}


class Registry(UserDict, ABC):
    name: str
    global_registry: dict  # Also for testing injection
    type: Optional[Type] = None

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

    def add(self, klass):
        self[klass.name] = klass

    def __setitem__(self, name, klass):
        assert getattr(klass, "name", None), "%s must have a 'name' attribute" % klass
        assert name == klass.name
        if self.type:
            assert issubclass(klass, self.type)
        klass.registries().add(self.name)
        super().__setitem__(name, klass)


class MessageRegistry(Registry):
    global_registry = global_message_registry
    data: Dict[str, Type[Message]]
    type = Message


class HandlerRegistry(Registry):
    global_registry = global_handler_registry
    data: Dict[str, Type[AsyncHandler]]
    type = AsyncHandler

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
ws_error_messages = MessageRegistry(WS_ERRORS)

ws_incoming_handlers = HandlerRegistry(WS_INCOMING)
ws_outgoing_handlers = HandlerRegistry(WS_OUTGOING)
ws_error_handlers = HandlerRegistry(WS_ERRORS)
