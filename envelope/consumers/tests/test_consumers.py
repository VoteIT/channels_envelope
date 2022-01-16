from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.test import TestCase
from django.test import override_settings
from django.urls import re_path
from django_rq import get_connection
from pydantic import BaseModel
from rq import SimpleWorker


if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

User = get_user_model()


_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ConsumerTests(TestCase):
    _connected = False

    @classmethod
    def setUpTestData(cls):
        cls.user: AbstractUser = User.objects.create(username="sockety")

    def tearDown(self):
        super().tearDown()
        if self._connected:
            async_to_sync(self.communicator.disconnect)()

    @property
    def _cut(self):
        from envelope.consumers.websocket import EnvelopeWebsocketConsumer

        return EnvelopeWebsocketConsumer

    async def _mk_communicator(self):
        websocket_urlpatterns = [re_path(r"testws/$", self._cut.as_asgi())]
        application = ProtocolTypeRouter(
            {"websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns))}
        )

        self.communicator = WebsocketCommunicator(application, "/testws/")
        connected, subprotocol = await self.communicator.connect()
        self._connected = True
        assert connected
        return self.communicator

    def _mk_worker(self):
        return SimpleWorker(
            queues=["default"],
            connection=get_connection(),
        )

    def _mk_deferred_job(self):
        from envelope.messages.actions import DeferredJob

        class Schema(BaseModel):
            username: str

        class Incoming(DeferredJob):
            name = "tester"
            schema = Schema
            data: Schema

            async def pre_queue(self, consumer):
                setattr(consumer, "hello", "world")

            def run_job(self):
                self.user.username = self.data.username
                self.user.save()

        return Incoming(mm={"user_pk": self.user.pk}, username="jane")

    @patch("envelope.consumers.websocket.EnvelopeWebsocketConsumer.get_user")
    def test_connection_signal(self, mocked):
        mocked.return_value = self.user

        from envelope.signals import client_connect

        @receiver(client_connect)
        def my_listener(user, **kw):
            user.username = "hello_world"
            user.save()

        communicator = async_to_sync(self._mk_communicator)()

        self.assertEqual("sockety", self.user.username)
        worker = self._mk_worker()
        completed = worker.work(burst=True)
        self.assertTrue(completed)
        self.user.refresh_from_db()
        self.assertEqual("hello_world", self.user.username)

    @patch("envelope.consumers.websocket.EnvelopeWebsocketConsumer.get_user")
    def test_close_signal(self, mocked):
        mocked.return_value = self.user

        from envelope.signals import client_close

        @receiver(client_close)
        def my_listener(user, close_code, **kw):
            user.username = "closed_%s" % close_code
            user.save()

        async def run_communicator():
            communicator = await self._mk_communicator()
            await communicator.disconnect(code=1001)

        async_to_sync(run_communicator)()

        self.assertEqual("sockety", self.user.username)
        worker = self._mk_worker()
        completed = worker.work(burst=True)
        self.assertTrue(completed)
        self.user.refresh_from_db()
        self.assertEqual("closed_1001", self.user.username)
