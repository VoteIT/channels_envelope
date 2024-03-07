from __future__ import annotations
from typing import TYPE_CHECKING

from async_signals import Signal
from channels import DEFAULT_CHANNEL_LAYER
from pydantic import BaseModel

from envelope import Error
from envelope.logging import getEventLogger
from envelope.schemas import EnvelopeSchema
from envelope.schemas import MessageMeta
from envelope.utils import get_error_type
from envelope.utils import get_message_registry

if TYPE_CHECKING:
    from envelope.logging import EventLoggerAdapter
    from envelope.consumers.websocket import WebsocketConsumer
    from envelope.core.message import Message
    from envelope.registries import MessageRegistry
    from envelope.core.transport import Transport

__all__ = ("Envelope",)

_default = object()


class Envelope:
    name: str
    schema: type[EnvelopeSchema]
    registry: MessageRegistry
    allow_batch: bool = False
    transport: Transport | None
    message_signal: Signal | None
    logger: EventLoggerAdapter
    layer_name: str

    def __init__(
        self,
        *,
        schema: type[EnvelopeSchema],
        name: str,
        logger_name=_default,
        transport: Transport | None = None,
        allow_batch: bool = False,
        message_signal: Signal | None = None,
        layer_name: str = DEFAULT_CHANNEL_LAYER,
    ):
        if not issubclass(schema, BaseModel):  # pragma: no coverage
            raise TypeError("Must be a subclass of pydantic.BaseModel")
        self.schema = schema
        self.name = name
        self.allow_batch = allow_batch
        self.transport = transport
        self.message_signal = message_signal
        if logger_name == _default:
            logger_name = "envelope." + name + ".event"
        self.logger = getEventLogger(logger_name)
        self.layer_name = layer_name

    @property
    def registry(self):
        return get_message_registry(self.name)

    def parse(self, text_data: str) -> EnvelopeSchema:
        """
        >>> env = Envelope(schema=EnvelopeSchema, name='testing')
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
        >>> env = Envelope(schema=OutgoingEnvelopeSchema, name='testing')
        >>> 'testing.hello' in env.registry
        True
        >>> msg_class = env.registry['testing.hello']
        >>> data = OutgoingEnvelopeSchema(t='testing.hello')
        >>> msg = env.unpack(data)
        >>> isinstance(msg, msg_class)
        True
        >>> msg.mm
        MessageMeta(id=None, user_pk=None, consumer_name=None, language=None, state=None, env='testing')

        And with consumer
        >>> from envelope.testing import mk_consumer
        >>> consumer = mk_consumer(consumer_name='abc')
        >>> msg = env.unpack(data, consumer=consumer)
        >>> msg.mm
        MessageMeta(id=None, user_pk=None, consumer_name='abc', language=None, state=None, env='testing')

        And user
        >>> class MockUser:
        ...     pk = 1
        ...
        >>> user = MockUser()
        >>> consumer = mk_consumer(consumer_name='abc', user=user)
        >>> msg = env.unpack(data, consumer=consumer)
        >>> msg.mm
        MessageMeta(id=None, user_pk=1, consumer_name='abc', language=None, state=None, env='testing')

        And id + state
        >>> data.i = 5
        >>> data.s = 's'
        >>> msg = env.unpack(data, consumer=consumer)
        >>> msg.mm
        MessageMeta(id='5', user_pk=1, consumer_name='abc', language=None, state='s', env='testing')

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
        envelope.core.errors.MessageTypeError: MessageTypeErrorSchema(msg=None, type_name='404')
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
                envelope=self.name,
            )
            raise error from exc
        # Attach origin of unpacked, needed by workers for instance
        if isinstance(mm, dict):
            mm["env"] = self.name
        elif isinstance(mm, MessageMeta):
            mm.env = self.name
        msg = msg_class(
            mm=mm,
            data=data.p,
        )
        if consumer and getattr(consumer, "user", None):
            msg.user = consumer.user
        return msg

    def pack(self, message: Message) -> EnvelopeSchema:
        """
        Pack (or insert) message into an envelope 👅

        >>> from envelope.schemas import OutgoingEnvelopeSchema
        >>> env = Envelope(schema=OutgoingEnvelopeSchema, name='testing')
        >>> 'testing.hello' in env.registry
        True
        >>> msg_class = env.registry['testing.hello']
        >>> hello_msg = msg_class( \
                mm={'consumer_name': 'abc', 'user_pk': 1, 'state': 'q', 'id': 5})
        >>> env.pack(hello_msg)
        OutgoingEnvelopeSchema(t='testing.hello', p=None, i='5', s='q')
        """
        kwargs = message.mm.dict(exclude={"consumer_name"}, exclude_none=True)
        if message.data is not None:
            kwargs["p"] = message.data.dict()
        return self.schema(t=message.name, **kwargs)
