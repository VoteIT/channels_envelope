from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Optional
from typing import TYPE_CHECKING

from envelope import Error
from envelope import MessageStates
from envelope.registry import HandlerRegistry
from envelope.registry import MessageRegistry
from envelope.registry import default_error_handlers
from envelope.registry import default_error_messages
from envelope.registry import ws_incoming_handlers
from envelope.registry import ws_incoming_messages
from envelope.registry import ws_outgoing_handlers
from envelope.registry import ws_outgoing_messages
from envelope.utils import get_error_type
from pydantic import BaseModel
from pydantic import Field
from typing import Type

from pydantic import validator

if TYPE_CHECKING:
    from channels.consumer import AsyncConsumer
    from envelope.messages import MessageMeta
    from envelope.messages.base import Message


class Envelope(ABC):
    message_registry: MessageRegistry
    handler_registry: HandlerRegistry
    data: BaseModel
    schema: Type[BaseModel]

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
        consumer: Optional[AsyncConsumer] = None,
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
            mm = dict(registry=self.message_registry.name, **consumer.get_msg_meta())
        if self.data.i:
            mm["id"] = self.data.i
        try:
            msg_class = self.message_registry[self.data.t]
        except KeyError:
            raise get_error_type(Error.MSG_TYPE)(
                mm=mm,
                registry=self.message_registry.name,
                type_name=self.data.t,
            )
        msg = msg_class(
            mm=mm,
            data=self.data.p,
        )
        if consumer and getattr(consumer, "user", None):
            msg.user = consumer.user
        return msg

    @classmethod
    def pack(cls, message: Message) -> Envelope:
        kwargs = dict(t=message.name, **message.mm.envelope_data())
        if message.data is not None:
            kwargs["p"] = message.data
        return cls(**kwargs)

    @property
    @abstractmethod
    def schema(self) -> Type[BaseModel]:
        ...

    @property
    @abstractmethod
    def message_registry(self) -> MessageRegistry:
        ...

    @property
    @abstractmethod
    def handler_registry(self) -> HandlerRegistry:
        ...

    @classmethod
    def is_compatible(cls, message, exception=False):
        result = cls.message_registry.name in message.registries()
        if not result and exception:
            raise KeyError(f"{message} is not in registry {cls.message_registry.name}")
        return result

    async def apply_handlers(self, message, **kwargs):
        await self.handler_registry.apply(message, **kwargs)


class EnvelopeSchema(BaseModel):
    """
    t - message type, same as name on message class.
        This describes the payload and how to handle the message.
    p - payload
    i - optional message id
    """

    t: str
    p: Optional[dict]
    i: Optional[str] = Field(
        max_length=20,
    )


class OutgoingEnvelopeSchema(EnvelopeSchema):
    """
    s - status/state
    """

    s: Optional[str] = Field(max_length=6)

    @validator("s")
    def validate_state(cls, v):
        if v and v not in MessageStates.MESSAGE_STATES:
            raise ValueError("%s is not a valid message state" % v)
        return v


class ErrorSchema(OutgoingEnvelopeSchema):
    s: str = Field(MessageStates.FAILED, const=True)


class IncomingWebsocketEnvelope(Envelope):
    schema = EnvelopeSchema
    data: EnvelopeSchema
    message_registry = ws_incoming_messages
    handler_registry = ws_incoming_handlers


class OutgoingWebsocketEnvelope(Envelope):
    schema = OutgoingEnvelopeSchema
    data: OutgoingEnvelopeSchema
    message_registry = ws_outgoing_messages
    handler_registry = ws_outgoing_handlers


class ErrorEnvelope(OutgoingWebsocketEnvelope):
    schema = ErrorSchema
    data: ErrorSchema
    message_registry = default_error_messages
    handler_registry = default_error_handlers
