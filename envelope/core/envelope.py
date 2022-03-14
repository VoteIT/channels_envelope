from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type

from pydantic import BaseModel

from envelope import Error
from envelope.core.registry import HandlerRegistry
from envelope.core.registry import MessageRegistry
from envelope.utils import get_error_type
from envelope.utils import get_handler_registry
from envelope.utils import get_message_registry

if TYPE_CHECKING:
    from envelope.core.consumer import BaseWebsocketConsumer
    from envelope.messages import MessageMeta
    from envelope.core.message import Message


class Envelope(ABC):
    data: BaseModel
    schema: Type[BaseModel]

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Name of this envelope type. Should be the same as message registry it needs to handle.
        """

    def __init__(self, _data=None, **kwargs):
        if _data is not None:
            self.data = _data
        else:
            self.data = self.schema(**kwargs)

    @classmethod
    def parse(cls, text: str):
        data = cls.schema.parse_raw(text)
        return cls(_data=data)

    def unpack(
        self,
        mm: Optional[MessageMeta, dict] = None,
        consumer: Optional[BaseWebsocketConsumer] = None,
        **kwargs,
    ) -> Message:
        """
        Unpack envelope and deserialize the message.
        """
        if mm is None and consumer is None:
            mm = {"user_pk": None}
        if bool(mm) == bool(consumer):
            raise ValueError("Can't specify both mm and consumer")
        if consumer:
            mm = consumer.get_msg_meta()
            if self.data.i:
                mm["id"] = self.data.i
        try:
            msg_class = self.message_registry[self.data.t]
        except KeyError:
            raise get_error_type(Error.MSG_TYPE)(
                mm=mm,
                registry=self.name,
                type_name=self.data.t,
            )
        msg = msg_class(
            mm=mm,
            data=self.data.p,
            _registry=self.name,
        )
        if consumer and getattr(consumer, "user", None):
            msg.user = consumer.user
        return msg

    @classmethod
    def pack(cls, message: Message) -> Envelope:
        message.validate()  # In case it wasn't done before
        kwargs = dict(t=message.name, **message.mm.envelope_data())
        if message.data is not None:
            kwargs["p"] = message.data
        return cls(**kwargs)

    def as_text_transport(self, channels_type: str) -> dict:
        return {"text_data": self.data.json(), "type": channels_type}

    def as_dict_transport(self, channels_type: str):
        data = self.data.dict()
        data["type"] = channels_type
        return data

    @property
    @abstractmethod
    def schema(self) -> Type[BaseModel]:
        ...

    @property
    def message_registry(self) -> MessageRegistry:
        return get_message_registry(self.name)

    @property
    def handler_registry(self) -> HandlerRegistry:
        return get_handler_registry(self.name)

    async def apply_handlers(self, message, **kwargs):
        await self.handler_registry.apply(message, **kwargs)
