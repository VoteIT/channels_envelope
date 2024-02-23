from __future__ import annotations

import doctest
from pkgutil import walk_packages
from typing import TYPE_CHECKING
from unittest.mock import patch

from channels.auth import AuthMiddlewareStack
from channels.testing import WebsocketCommunicator
from django.dispatch import Signal
from async_signals import Signal as AsyncSignal
from django_rq import get_queue
from rq import SimpleWorker

from envelope import WS_SEND_TRANSPORT
from envelope.core import Message
from envelope.core.transport import DictTransport
from envelope.core.envelope import Envelope
from envelope.core.message import AsyncRunnable
from envelope.decorators import add_message
from envelope.messages.testing import ClientInfo
from envelope.messages.testing import SendClientInfo
from envelope.schemas import OutgoingEnvelopeSchema
from envelope.utils import add_envelopes

if TYPE_CHECKING:
    from envelope.channels.models import PubSubChannel


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


#
#
# @add_message(TESTING_NS)
# class WebsocketWorld(Message):
#     name = "testing.world"


# async def mk_communicator(user=None, queue: Queue = None):
#     """
#     A logged-in user is required for this consumer.
#     But async/sync doesn't mix well so we'll patch the user
#     """
#     from envelope.consumers.websocket import WebsocketConsumer
#
#     init_kwargs = {}
#     if queue:
#         assert isinstance(queue, Queue)
#         init_kwargs["connection_queue"] = queue
#         init_kwargs["timestamp_queue"] = queue
#
#     websocket_urlpatterns = [
#         re_path(r"testws/$", WebsocketConsumer.as_asgi(**init_kwargs))
#     ]
#     application = ProtocolTypeRouter(
#         {"websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns))}
#     )
#     communicator = WebsocketCommunicator(application, "/testws/")
#     if user:
#         with patch.object(WebsocketConsumer, "get_user", return_value=user):
#             connected, subprotocol = await communicator.connect()
#             assert connected
#     else:
#         connected, subprotocol = await communicator.connect()
#         assert connected  # This won't happen
#     return communicator


def mk_simple_worker(queue="default") -> SimpleWorker:
    if isinstance(queue, str):
        queue = get_queue(queue)

    return SimpleWorker(queues=[queue], connection=queue.connection)


# class ResetRegistries:
#     def __enter__(self):
#         self.registries = {}
#         for name, item in registries.__dict__.items():
#             if isinstance(item, Registry):
#                 self.registries[name] = deepcopy(item)
#
#     def __exit__(self, exc_type, exc_value, traceback):
#         """
#         Execute all on_commit hooks and cleanup.
#         """
#         for (k, v) in self.registries.items():
#             registries.__dict__[k] = v
#         breakpoint()
# current_run_on_commit = self.connection.run_on_commit
# self.connection.run_on_commit = []
# while current_run_on_commit:
#     sids, func = current_run_on_commit.pop(0)
#     func()


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
        # if not any(
        #     name.startswith(
        #         f"{package.__name__}.{x}." or name == f"{package.__name__}.{x}"
        #     )
        #     for x in ignore_names
        # ):
        #     print(name)
        tests.addTests(doctest.DocTestSuite(name, optionflags=opts))
        # continue


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


async def mk_communicator(client=None, drain=True):
    from envelope.consumers.websocket import WebsocketConsumer

    headers = []
    if client:
        headers.extend(
            [
                (b"origin", b"..."),
                (b"cookie", client.cookies.output(header="", sep="; ").encode()),
            ]
        )
    communicator = WebsocketCommunicator(
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


async def get_consumer_name(communicator):
    from envelope.envelopes import incoming, outgoing

    msg = SendClientInfo()
    payload = incoming.pack(msg)
    text_data = payload.json()
    await communicator.send_to(text_data=text_data)
    response = await communicator.receive_from()
    payload = outgoing.parse(response)
    message = outgoing.unpack(payload)
    assert isinstance(message, ClientInfo)
    return message.data.consumer_name


class ChannelMessageCatcher:
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
    """

    def __init__(
        self,
        channel: type[PubSubChannel],
        method: str = "sync_publish",
        *args: type[Message] | str,
    ):
        self.channel = channel
        self.mock = None
        assert hasattr(channel, method)
        self.method = method
        filter = set()
        for f in args:
            if isinstance(f, str):
                filter.add(f)
            elif isinstance(f, Message):
                filter.add(f.name)
            else:
                raise TypeError("Filter args must be string or Message type")
        self.filter = filter or None
        self.messages = []

    def __enter__(self) -> list[Message]:
        self._patch = patch.object(self.channel, self.method, return_value=None)
        self.mock = self._patch.start()
        return self.messages

    def __exit__(self, *args):
        self._patch.stop()
        for call in self.mock.mock_calls:
            msg = call.args[0]
            assert isinstance(msg, Message)
            if self.filter is None or msg.name in self.filter:
                self.messages.append(msg)

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
