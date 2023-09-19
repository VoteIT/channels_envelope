from __future__ import annotations
from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING
from typing import TypeVar

from async_signals import Signal
from pydantic import BaseModel

from envelope import ERRORS
from envelope import Error
from envelope.schemas import EnvelopeSchema
from envelope.utils import get_error_type
from envelope.utils import get_message_registry

if TYPE_CHECKING:
    from envelope.consumer.websocket import WebsocketConsumer
    from envelope.core.message import Message
    from envelope.registries import MessageRegistry
    from envelope.schemas import MessageMeta


S = TypeVar("S")  # schema
M = TypeVar("M")  # model


class Transport(ABC):
    def __init__(self, type_name: str):
        self.type_name = type_name

    @abstractmethod
    def __call__(self, envelope: Envelope, message: Message):
        ...


# class TextTransport(Transport):
#     def __call__(self, envelope: Envelope, message: Message) -> dict:
#         packed = envelope.pack(message)
#         return {
#             "text_data": packed.json(),
#             "type": self.type_name,
#             "i": packed.i,
#             "t": packed.t,
#             "s": getattr(packed, "s", None),
#         }


class DictTransport(Transport):
    def __call__(self, envelope: Envelope, message: Message) -> dict:
        packed = envelope.pack(message)
        data = packed.dict()
        data["type"] = self.type_name
        return data


class Envelope:
    name: str
    schema: type[EnvelopeSchema]
    registry_name: str
    registry: MessageRegistry
    allow_batch: bool = False
    transport: Transport | None
    message_signal: Signal | None

    def __init__(
        self,
        *,
        schema: type[EnvelopeSchema],
        registry_name: str,
        transport: Transport | None = None,
        allow_batch: bool = False,
        message_signal: Signal | None = None,
    ):
        if not issubclass(schema, BaseModel):  # pragma: no coverage
            raise TypeError("Must be a subclass of pydantic.BaseModel")
        self.schema = schema
        self.registry_name = registry_name
        self.allow_batch = allow_batch
        self.transport = transport
        self.message_signal = message_signal

    @property
    def registry(self):
        return get_message_registry(self.registry_name)

    def parse(self, text_data: str) -> BaseModel:
        """
        >>> env = Envelope(schema=EnvelopeSchema, registry_name='testing')
        >>> txt = '{"t": "msg.name"}'
        >>> env.parse(txt)
        EnvelopeSchema(t='msg.name', p=None, i=None)
        """
        return self.schema.parse_raw(text_data)

    def unpack(
        self,
        data: EnvelopeSchema,
        *,
        mm: MessageMeta | dict | None = None,
        consumer: WebsocketConsumer | None = None,
        **kwargs,
    ):
        """
        >>> from envelope.schemas import OutgoingEnvelopeSchema
        >>> env = Envelope(schema=OutgoingEnvelopeSchema, registry_name='testing')
        >>> 'testing.hello' in env.registry
        True
        >>> msg_class = env.registry['testing.hello']
        >>> data = OutgoingEnvelopeSchema(t='testing.hello')
        >>> msg = env.unpack(data)
        >>> isinstance(msg, msg_class)
        True
        >>> msg.mm
        MessageMeta(id=None, user_pk=None, consumer_name=None, language=None, state=None, registry='testing')

        And with consumer
        >>> from envelope.tests.helpers import mk_consumer
        >>> consumer = mk_consumer(consumer_name='abc')
        >>> msg = env.unpack(data, consumer=consumer)
        >>> msg.mm
        MessageMeta(id=None, user_pk=None, consumer_name='abc', language=None, state=None, registry='testing')

        And user
        >>> class MockUser:
        ...     pk = 1
        ...
        >>> user = MockUser()
        >>> consumer = mk_consumer(consumer_name='abc', user=user)
        >>> msg = env.unpack(data, consumer=consumer)
        >>> msg.mm
        MessageMeta(id=None, user_pk=1, consumer_name='abc', language=None, state=None, registry='testing')

        And id + state
        >>> data.i = 5
        >>> data.s = 's'
        >>> msg = env.unpack(data, consumer=consumer)
        >>> msg.mm
        MessageMeta(id='5', user_pk=1, consumer_name='abc', language=None, state='s', registry='testing')

        Specifying both consumer and mm isn't allowed
        >>> env.unpack(data, consumer=consumer, mm={'user_pk': 1})
        Traceback (most recent call last):
        ...
        ValueError: Can't specify both mm and consumer

        And a message type that doesn't exist
        >>> data = OutgoingEnvelopeSchema(t='404')
        >>> env.unpack(data, consumer=consumer)
        Traceback (most recent call last):
        ...
        envelope.core.errors.MessageTypeError: MessageTypeErrorSchema(msg=None, type_name='404', registry='testing')
        """
        if mm is None and consumer is None:
            mm = {"user_pk": None}
        if bool(mm) == bool(consumer):
            raise ValueError("Can't specify both mm and consumer")
        if consumer:
            mm = consumer.get_msg_meta(**data.dict(exclude={"t"}, exclude_none=True))
        try:
            msg_class = self.registry[data.t]
        except KeyError as exc:
            error = get_error_type(Error.MSG_TYPE)(
                mm=mm,
                type_name=data.t,
                registry=self.registry_name,
            )
            error.mm.registry = ERRORS
            raise error from exc
        msg = msg_class(
            mm=mm,
            data=data.p,
        )
        if consumer and getattr(consumer, "user", None):
            msg.user = consumer.user
        msg.mm.registry = self.registry_name
        return msg

    def pack(self, message: Message) -> EnvelopeSchema:
        """
        Pack (or insert) message into an envelope 👅

        >>> from envelope.schemas import OutgoingEnvelopeSchema
        >>> env = Envelope(schema=OutgoingEnvelopeSchema, registry_name='testing')
        >>> 'testing.hello' in env.registry
        True
        >>> msg_class = env.registry['testing.hello']
        >>> hello_msg = msg_class( \
                mm={'registry': 'boo', 'consumer_name': 'abc', 'user_pk': 1, 'state': 'q', 'id': 5})
        >>> env.pack(hello_msg)
        OutgoingEnvelopeSchema(t='testing.hello', p=None, i='5', s='q')
        """
        kwargs = message.mm.dict(
            exclude={"registry", "consumer_name"}, exclude_none=True
        )
        if message.data is not None:
            kwargs["p"] = message.data.dict()
        return self.schema(t=message.name, **kwargs)
