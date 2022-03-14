from __future__ import annotations

from datetime import timedelta
from json import dumps
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now
from django_rq import get_queue
from fakeredis import FakeRedis
from pydantic import BaseModel
from rq import Queue
from rq import SimpleWorker

from envelope.testing import mk_communicator

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

User = get_user_model()

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ConsumerUnitTests(TestCase):
    communicator = None

    @classmethod
    def setUpTestData(cls):
        cls.user: AbstractUser = User.objects.create(username="sockety")
        from envelope.messages import register_messages
        from envelope.handlers import register_handlers

        register_messages()
        register_handlers()

    def setUp(self):
        self.redis_conn = FakeRedis()
        self.queue = Queue(connection=self.redis_conn)

    @property
    def _cut(self):
        from envelope.consumers.websocket import WebsocketConsumer

        return WebsocketConsumer

    def _mk_one(self):
        consumer = self._cut(enable_connection_signals=False)
        consumer.last_job = now()
        consumer.channel_name = "abc"
        return consumer

    def test_update_connection(self):
        consumer = self._mk_one()
        with patch.object(consumer.timestamp_queue, "enqueue") as patched_enqueue:
            self.assertFalse(patched_enqueue.called)
            self.assertIsNone(consumer.update_connection())
            self.assertFalse(patched_enqueue.called)
            consumer.last_job = now() - timedelta(minutes=4)
            self.assertIsNotNone(consumer.update_connection())
            self.assertTrue(patched_enqueue.called)

    async def test_receive_bad_format(self):
        consumer = self._mk_one()
        with patch.object(consumer, "send_ws_error") as patched:
            await consumer.receive(text_data="Buhu")
            self.assertTrue(patched.called)

    async def test_receive_bad_data(self):
        consumer = self._mk_one()
        consumer.base_send = AsyncMock()
        with patch.object(consumer, "send_ws_error") as patched:
            data = dumps({"t": "testing.count", "p": {"num": "abc"}})
            await consumer.receive(text_data=data)
            self.assertTrue(patched.called)

    async def test_send(self):
        from envelope.envelopes import OutgoingWebsocketEnvelope

        consumer = self._mk_one()
        consumer.base_send = AsyncMock()
        data = {"t": "testing.hello", "p": {"greeting": "Hello"}}
        await consumer.send(text_data=dumps(data))
        envelope = OutgoingWebsocketEnvelope(**data)
        await consumer.send(envelope=envelope)
        with self.assertRaises(ValueError):
            await consumer.send(envelope=envelope, text_data=dumps(data))
            await consumer.send()

    def test_mark_subscribed_left(self):
        from envelope.messages.channels import ChannelSchema

        subs = ChannelSchema(pk=1, channel_type="user")
        consumer = self._mk_one()
        consumer.mark_subscribed(subs)
        self.assertIn(subs, consumer.subscriptions)
        consumer.mark_left(subs)
        self.assertNotIn(subs, consumer.subscriptions)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ConsumerCommunicatorTests(TestCase):
    communicator = None

    @classmethod
    def setUpTestData(cls):
        cls.user: AbstractUser = User.objects.create(username="sockety")

    def setUp(self):
        self.redis_conn = FakeRedis()
        # name?
        self.queue = Queue(connection=self.redis_conn)

    def tearDown(self):
        super().tearDown()

        if self.communicator is not None:
            async_to_sync(self.communicator.disconnect)()
        # In case we left anything bad behind...
        queue = get_queue()
        queue.empty()

    @property
    def _cut(self):
        from envelope.consumers.websocket import WebsocketConsumer

        return WebsocketConsumer

    def _mk_worker(self):
        return SimpleWorker(
            queues=[self.queue],
            connection=self.redis_conn,
        )

    def _mk_deferred_job(self):
        from envelope.core.message import DeferredJob

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

        return Incoming(queue=self.queue, mm={"user_pk": self.user.pk}, username="jane")

    def test_connection_signal(self):
        from envelope.signals import client_connect

        @receiver(client_connect)
        def my_listener(user, **kw):
            user.username = "hello_world"
            user.save()

        async_to_sync(mk_communicator)(self.user, queue=self.queue)

        self.assertEqual("sockety", self.user.username)
        worker = self._mk_worker()
        completed = worker.work(burst=True)
        self.assertTrue(completed)
        self.user.refresh_from_db()
        self.assertEqual("hello_world", self.user.username)

    def test_close_signal(self):
        from envelope.signals import client_close

        @receiver(client_close)
        def my_listener(user, close_code, **kw):
            user.username = "closed_%s" % close_code
            user.save()

        async def run_communicator():
            self.communicator = await mk_communicator(self.user, queue=self.queue)
            await self.communicator.disconnect(code=1001)

        async_to_sync(run_communicator)()

        self.assertEqual("sockety", self.user.username)
        worker = self._mk_worker()
        completed = worker.work(burst=True)
        self.assertTrue(completed)
        self.user.refresh_from_db()
        self.assertEqual("closed_1001", self.user.username)

    async def test_connection_anon_user(self):
        with self.assertRaises(AssertionError):
            await mk_communicator(queue=self.queue)
