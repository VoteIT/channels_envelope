from datetime import datetime
from unittest import mock
from unittest.mock import patch

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings
from fakeredis import FakeStrictRedis
from rq import Queue
from rq import SimpleWorker

from envelope import WS_INCOMING
from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed
from envelope.logging import getEventLogger
from envelope.messages.ping import Ping
from envelope.models import Connection

User = get_user_model()


class _MockConsumer:
    user_pk: int = None
    channel_name: str = "abc"
    language: str = "en"
    connection_update_interval: int | None = None
    last_job: datetime | None = None
    event_logger = getEventLogger(__name__ + ".event")
    user: User | AnonymousUser = AnonymousUser()

    def __init__(self):
        self.ws_out = []

    async def send_ws_message(self, msg):
        self.ws_out.append(msg)


@override_settings(
    ENVELOPE_CONNECTIONS_QUEUE="default",
    ENVELOPE_TIMESTAMP_QUEUE="default",
)
class DeferredJobsAsyncSignalsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="user")

    def setUp(self):
        self.fake_redis_conn = FakeStrictRedis()
        self.mock_consumer = _MockConsumer()

    def fake_redis_queue(self, *, name, **kwargs):
        kwargs["connection"] = self.fake_redis_conn

        return Queue(**kwargs)

    async def test_dispatch_connection(self):
        self.mock_consumer.user_pk = self.user.pk

        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=self.fake_redis_conn,
        ):
            from envelope.deferred_jobs.async_signals import dispatch_connection_job

            await dispatch_connection_job(consumer=self.mock_consumer)

        queue = self.fake_redis_queue(name="default")
        worker = SimpleWorker([queue], connection=self.fake_redis_conn)
        result = await sync_to_async(worker.work)(burst=True)
        self.assertTrue(result)
        self.assertEqual(1, await sync_to_async(Connection.objects.all().count)())

    async def test_dispatch_connection_job_no_user(self):
        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=self.fake_redis_conn,
        ):
            with patch.object(Queue, "enqueue") as mock_enqueue:
                from envelope.deferred_jobs.async_signals import dispatch_connection_job

                await dispatch_connection_job(consumer=self.mock_consumer)
                self.assertFalse(mock_enqueue.called)

    async def test_dispatch_disconnection_job(self):
        self.mock_consumer.user_pk = self.user.pk

        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=self.fake_redis_conn,
        ):
            from envelope.deferred_jobs.async_signals import dispatch_disconnection_job

            await dispatch_disconnection_job(consumer=self.mock_consumer)

        queue = self.fake_redis_queue(name="default")
        worker = SimpleWorker([queue], connection=self.fake_redis_conn)
        result = await sync_to_async(worker.work)(burst=True)
        self.assertTrue(result)
        connection = await sync_to_async(Connection.objects.all().last)()
        self.assertFalse(connection.online)

    async def test_dispatch_disconnection_job_no_user(self):
        with patch(
            "django_rq.get_queue",
            wraps=self.fake_redis_queue,
        ):
            with patch.object(Queue, "enqueue") as mock_enqueue:
                from envelope.deferred_jobs.async_signals import (
                    dispatch_disconnection_job,
                )

                await dispatch_disconnection_job(consumer=self.mock_consumer)
                self.assertFalse(mock_enqueue.called)

    async def test_maybe_update_connection(self):
        self.mock_consumer.user_pk = self.user.pk
        self.mock_consumer.connection_update_interval = 10

        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=self.fake_redis_conn,
        ):
            from envelope.deferred_jobs.async_signals import maybe_update_connection

            await maybe_update_connection(consumer=self.mock_consumer)

        queue = self.fake_redis_queue(name="default")
        worker = SimpleWorker([queue], connection=self.fake_redis_conn)
        result = await sync_to_async(worker.work)(burst=True)
        self.assertTrue(result)
        connection = await sync_to_async(Connection.objects.all().last)()
        self.assertTrue(connection.online)
        self.assertIsInstance(connection.last_action, datetime)

    async def test_queue_deferred_job(self):

        self.mock_consumer.user_pk = self.user.pk

        msg = Subscribe(
            mm={"user_pk": self.user.pk, "env": WS_INCOMING},
            channel_type="user",
            pk=self.user.pk,
        )
        msg.post_queue = mock.AsyncMock()
        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=self.fake_redis_conn,
        ):
            from envelope.deferred_jobs.async_signals import queue_deferred_job

            await queue_deferred_job(consumer=self.mock_consumer, message=msg)

        queue = self.fake_redis_queue(name="default")
        worker = SimpleWorker([queue], connection=self.fake_redis_conn)
        result = await sync_to_async(worker.work)(burst=True)
        self.assertTrue(result)
        self.assertTrue(self.mock_consumer.ws_out)
        response = self.mock_consumer.ws_out[0]
        self.assertIsInstance(response, Subscribed)
        self.assertEqual(
            {
                "app_state": None,
                "channel_name": f"user_{self.user.pk}",
                "channel_type": "user",
                "pk": self.user.pk,
            },
            response.data.dict(),
        )
        self.assertTrue(msg.post_queue.called)
        self.assertIn("job", msg.post_queue.mock_calls[0].kwargs)
        self.assertIn("consumer", msg.post_queue.mock_calls[0].kwargs)

    async def test_queue_deferred_job_wrong_msg_type(self):
        self.mock_consumer.user_pk = self.user.pk

        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=self.fake_redis_conn,
        ):
            from envelope.deferred_jobs.async_signals import queue_deferred_job

            await queue_deferred_job(consumer=self.mock_consumer, message=Ping())

        queue = self.fake_redis_queue(name="default")
        worker = SimpleWorker([queue], connection=self.fake_redis_conn)
        result = await sync_to_async(worker.work)(burst=True)
        self.assertFalse(result)
        self.assertIsNone(self.mock_consumer.last_job)
