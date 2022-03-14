from copy import deepcopy
from unittest.mock import patch

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.db.transaction import get_connection
from django.urls import re_path
from django_rq import get_queue
from envelope.core.registry import Registry
from rq import Queue
from rq import SimpleWorker

from envelope.core.envelope import Envelope
from envelope.core.message import AsyncRunnable
from envelope.core.message import Message
from envelope.core.registry import ChannelRegistry
from envelope.core.registry import HandlerRegistry
from envelope.core.registry import MessageRegistry
from envelope.core.schemas import EnvelopeSchema
from envelope.decorators import add_envelope
from envelope.decorators import add_message
from envelope import registries

testing_messages = MessageRegistry("testing")
testing_handlers = HandlerRegistry("testing")
testing_channels = ChannelRegistry()
TESTING_NS = "testing"


@add_envelope
class TestingEnvelope(Envelope):
    name = TESTING_NS
    schema = EnvelopeSchema


@add_message(TESTING_NS)
class WebsocketHello(AsyncRunnable):
    name = "testing.hello"

    async def run(self, **kwargs):
        pass


@add_message(TESTING_NS)
class WebsocketWorld(Message):
    name = "testing.world"


async def mk_communicator(user=None, queue: Queue = None):
    """
    A logged-in user is required for this consumer.
    But async/sync doesn't mix well so we'll patch the user
    """
    from envelope.consumers.websocket import WebsocketConsumer

    init_kwargs = {}
    if queue:
        assert isinstance(queue, Queue)
        init_kwargs["connection_queue"] = queue
        init_kwargs["timestamp_queue"] = queue

    websocket_urlpatterns = [
        re_path(r"testws/$", WebsocketConsumer.as_asgi(**init_kwargs))
    ]
    application = ProtocolTypeRouter(
        {"websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns))}
    )
    communicator = WebsocketCommunicator(application, "/testws/")
    if user:
        with patch.object(WebsocketConsumer, "get_user", return_value=user):
            connected, subprotocol = await communicator.connect()
            assert connected
    else:
        connected, subprotocol = await communicator.connect()
        assert connected  # This won't happen
    return communicator


def mk_simple_worker(queue="default") -> SimpleWorker:
    if isinstance(queue, str):
        queue = get_queue(queue)

    return SimpleWorker(queues=[queue], connection=queue.connection)


class FakeCommit:
    """
    A very destructive context manager that will wreak havoc if you use it outside unittests!
    So don't!

    So why does it exist?
    Most unittests start with mock data that's part of the tests own transaction.
    So if we want to test on_commit hooks, it becomes very problematic since that initial test data may
    have caused commit hooks - and theres no way we can start a new atomic transaction
    within a regular unittest. (It does work with TransactionTestCase but that's painfully slow)
    """

    def __enter__(self):
        """
        Remove staged all on_commit methods on enter - yes this will destroy them for the
        atomic block that's active!
        """
        self.connection = get_connection()
        self.connection.run_on_commit = []

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Execute all on_commit hooks and cleanup.
        """
        current_run_on_commit = self.connection.run_on_commit
        self.connection.run_on_commit = []
        while current_run_on_commit:
            sids, func = current_run_on_commit.pop(0)
            func()


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
