from __future__ import annotations
from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from envelope.core.envelope import Envelope
    from envelope.core.message import Message

__all__ = (
    "Transport",
    "TextTransport",
    "DictTransport",
)


class Transport(ABC):
    def __init__(self, type_name: str):
        self.type_name = type_name

    @abstractmethod
    def __call__(self, envelope: Envelope, message: Message): ...


class TextTransport(Transport):
    def __call__(self, envelope: Envelope, message: Message) -> dict:
        packed = envelope.pack(message)
        return {
            "text_data": packed.json(),
            "type": self.type_name,
            "i": packed.i,
            "t": packed.t,
            "s": getattr(packed, "s", None),
        }


class DictTransport(Transport):
    def __call__(self, envelope: Envelope, message: Message) -> dict:
        packed = envelope.pack(message)
        data = packed.dict()
        data["type"] = self.type_name
        return data
