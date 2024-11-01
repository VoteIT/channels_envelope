from __future__ import annotations

import doctest
from json import dumps
from json import loads
from pkgutil import walk_packages
from typing import TYPE_CHECKING
from unittest.mock import PropertyMock
from unittest.mock import patch

from async_signals import Signal as AsyncSignal
from channels.auth import AuthMiddlewareStack
from channels.testing import WebsocketCommunicator
from django.dispatch import Signal
from django_rq import get_queue
from pydantic import BaseModel
from rq import Queue
from rq import SimpleWorker

from envelope import ERRORS
from envelope import INTERNAL
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope import WS_SEND_TRANSPORT
from envelope.core import Message
from envelope.core.envelope import Envelope
from envelope.core.message import AsyncRunnable
from envelope.core.transport import DictTransport
from envelope.decorators import add_message
from envelope.messages.testing import ClientInfo
from envelope.messages.testing import SendClientInfo
from envelope.schemas import OutgoingEnvelopeSchema
from envelope.utils import add_envelopes
from envelope.utils import get_envelope
from envelope.utils import get_sender_util

if TYPE_CHECKING:
    from envelope.channels.models import PubSubChannel
    from fakeredis import FakeRedis


TESTING_NS = "testing"
testing_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}

testing_envelope = Envelope(
    schema=OutgoingEnvelopeSchema,
    name=TESTING_NS,
    transport=DictTransport(WS_SEND_TRANSPORT),
    allow_batch=True,
)

add_envelopes(testing_envelope)


@add_message(TESTING_NS)
class WebsocketHello(AsyncRunnable):
    name = "testing.hello"

    async def run(self, **kwargs): ...


def mk_simple_worker(queue="default") -> SimpleWorker:
    if isinstance(queue, str):
        queue = get_queue(name=queue)

    return SimpleWorker(queues=[queue], connection=queue.connection)


def work_with_conn(queue: str = "default", *, connection: FakeRedis):
    queue = Queue(name=queue, connection=connection)
    worker = SimpleWorker([queue], connection=connection)
    result = worker.work(burst=True)
    assert result, "Worker did noting"


def load_doctests(tests, package, ignore_names: set[str] = frozenset()) -> None:
    """
    Load doctests from a specific package/module. Must be called from a test_ file with the following function:

    def load_tests(loader, tests, pattern):
        load_doctests(tests, <module>)
        return tests

    Where module is envelope for instance.
    """
    opts = (
        doctest.NORMALIZE_WHITESPACE
        | doctest.ELLIPSIS
        | doctest.FAIL_FAST
        | doctest.IGNORE_EXCEPTION_DETAIL
    )
    for importer, name, ispkg in walk_packages(
        package.__path__, package.__name__ + "."
    ):
        tests.addTests(doctest.DocTestSuite(name, optionflags=opts))


class TempSignal:
    def __init__(self, signal: Signal | AsyncSignal, method: callable, sender=None):
        self.signal = signal
        self.method = method
        self.sender = sender

    def __enter__(self):
        self.signal.connect(self.method, sender=self.sender)

    def __exit__(self, *args):
        self.signal.disconnect(self.method, sender=self.sender)


def mk_consumer(consumer_name="abc", user=None, **kwargs):
    from envelope.consumers.websocket import WebsocketConsumer

    consumer = WebsocketConsumer(**kwargs)
    consumer.channel_name = consumer_name
    if user:
        consumer.user = user
        consumer.user_pk = user.pk
    return consumer


class EnvelopeWebsocketCommunicator(WebsocketCommunicator):

    async def send_msg(self, msg: Message):
        envelope = get_envelope(WS_INCOMING)
        assert (
            msg.name in envelope.registry
        ), f"{msg.name} doesn't exist in message registry registry {envelope.name}"
        payload = envelope.pack(msg)
        text_data = payload.json()
        await self.send_to(text_data=text_data)

    async def send_internal(self, msg: Message):
        envelope = get_envelope(INTERNAL)
        assert (
            msg.name in envelope.registry
        ), f"{msg.name} doesn't exist in message registry registry {envelope.name}"
        payload = envelope.pack(msg)
        data = payload.dict()
        await self.send_input({"type": "internal.msg", **data})

    async def receive_msg(self) -> Message:
        """
        Note: This will strip some message metadata!
        """
        response = await self.receive_from(0.2)
        # We're guessing here since this is normally frontend domain :)
        data = loads(response)
        if data["t"].startswith("error"):
            envelope = get_envelope(ERRORS)
        else:
            envelope = get_envelope(WS_OUTGOING)
        data = envelope.parse(response)
        return envelope.unpack(data)

    async def get_consumer_name(self):
        msg = SendClientInfo()
        await self.send_msg(msg)
        response = await self.receive_msg()
        assert isinstance(response, ClientInfo), f"Got {response} instead of ClientInfo"
        return response.data.consumer_name


async def mk_communicator(client=None, drain=True, headers=()):
    from envelope.consumers.websocket import WebsocketConsumer

    headers = list(headers)
    if client:
        headers.extend(
            [
                (b"origin", b"..."),
                (b"cookie", client.cookies.output(header="", sep="; ").encode()),
            ]
        )
    communicator = EnvelopeWebsocketCommunicator(
        AuthMiddlewareStack(WebsocketConsumer.as_asgi()),
        "/testws/",
        headers=headers,
    )
    connected, subprotocol = await communicator.connect()
    assert connected, "Not connected"
    if drain:
        while communicator.output_queue.qsize():
            await communicator.output_queue.get()
    return communicator


class BaseMessageCatcher:
    messages: list

    def __init__(
        self,
        *args: type[Message] | str,
    ):

        filter = set()
        for f in args:
            if isinstance(f, str):
                filter.add(f)
            elif issubclass(f, Message):
                filter.add(f.name)
            else:
                raise TypeError("Filter args must be string or Message type")
        self.filter = filter or None
        self.messages = []

    def __iter__(self) -> iter[Message]:
        return iter(self.messages)

    def __bool__(self) -> bool:
        return bool(self.messages)

    def __contains__(self, item: Message | str) -> bool:
        if isinstance(item, str):
            return any(x for x in self if x.name == item)
        elif isinstance(item, Message):
            return item in self.messages
        return False


class ChannelMessageCatcher(BaseMessageCatcher):
    """
    Helper for sync_publish for instance

    >>> from envelope.messages.ping import Ping
    >>> from envelope.app.user_channel.channel import UserChannel
    >>> msg = Ping()
    >>> with ChannelMessageCatcher(UserChannel) as messages:
    ...     ch = UserChannel(1)
    ...     ch.sync_publish(msg, on_commit=False)
    >>> len(messages)
    1
    >>> with ChannelMessageCatcher(UserChannel, 'only_this_type') as messages:
    ...     ch = UserChannel(1)
    ...     ch.sync_publish(msg, on_commit=False)
    >>> len(messages)
    0
    """

    def __init__(
        self,
        channel: type[PubSubChannel],
        *args: type[Message] | str,
    ):
        super().__init__(*args)
        self.channel = channel
        self.mock = None

    def __enter__(self) -> list[Message]:
        self._patch = patch.object(self.channel, "sync_publish", return_value=None)
        self.mock = self._patch.start()
        return self.messages

    def __exit__(self, *args):
        self._patch.stop()
        for call in self.mock.mock_calls:
            msg = call.args[0]
            assert isinstance(msg, Message)
            if self.filter is None or msg.name in self.filter:
                self.messages.append(msg)


class MessageCatcher(BaseMessageCatcher):
    """
    Helper for messages for non-channel messages sent directly to a consumer.

    >>> from envelope.messages.ping import Ping

    >>> from envelope.utils import websocket_send
    >>> msg = Ping()
    >>> with MessageCatcher(Ping) as messages:
    ...     websocket_send(msg, on_commit=False, channel_name='abc')
    >>> len(messages)
    1
    >>> with MessageCatcher('only_this_type') as messages:
    ...     websocket_send(msg, on_commit=False, channel_name='abc')
    >>> len(messages)
    0
    >>> from django.db import transaction

    >>> with MessageCatcher(Ping) as messages:
    ...     with transaction.atomic():
    ...         websocket_send(msg, on_commit=True, channel_name='abc')
    >>> len(messages)
    1
    """

    def __init__(
        self,
        *args: type[Message] | str,
    ):
        super().__init__(*args)
        self.mock_message = None
        self.mock_call = None

    def __enter__(self) -> list[Message]:
        self._patch_message = patch.object(
            get_sender_util(), "message", new_callable=PropertyMock
        )
        self._patch_call = patch.object(
            get_sender_util(), "__call__", return_value=None
        )
        self.mock_message = self._patch_message.start()
        self.mock_call = self._patch_call.start()
        return self.messages

    def __exit__(self, *args):
        self._patch_message.stop()
        self._patch_call.stop()
        for call in self.mock_message.mock_calls:
            if call.args:
                msg = call.args[0]
                assert isinstance(msg, Message)
                if self.filter is None or msg.name in self.filter:
                    self.messages.append(msg)


def serialization_check(instance: BaseModel) -> str:
    data = instance.dict()
    return dumps(data)
