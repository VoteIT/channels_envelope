from unittest.mock import patch

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.contrib.auth import user_logged_out
from django.test import override_settings
from django.test import TransactionTestCase
from fakeredis import FakeStrictRedis
from rq import Queue
from rq import SimpleWorker

from envelope.app.user_channel.channel import UserChannel
from envelope.envelopes import internal
from envelope.envelopes import outgoing
from envelope.messages.common import Status
from envelope.testing import mk_communicator
from envelope.testing import testing_channel_layers_setting

User = get_user_model()


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
    ENVELOPE_CONNECTIONS_QUEUE=None,
)
class SubscribeSignalIntegrationTests(TransactionTestCase):
    def setUp(self):
        self.jane = User.objects.create(username="jane")
        self.client.force_login(self.jane)
        self.fake_redis = FakeStrictRedis()

    async def test_connection_subscribes(self):
        communicator = await mk_communicator(self.client, drain=False)
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        self.assertEqual(
            {
                "t": "channel.subscribed",
                "p": {
                    "pk": self.jane.pk,
                    "channel_type": "user",
                    "channel_name": f"user_{self.jane.pk}",
                    "app_state": None,
                },
            },
            payload.dict(exclude_none=True),
        )
        layer = get_channel_layer()
        self.assertIn(f"user_{self.jane.pk}", layer.groups)
        consumer_name = await communicator.get_consumer_name()
        ch = UserChannel(self.jane.pk, consumer_channel=consumer_name)
        msg = Status(state="s")
        await ch.publish(msg)
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        self.assertEqual(
            {"t": "s.stat"},
            payload.dict(exclude_none=True),
        )
        await communicator.disconnect()

    @override_settings(ENVELOPE_USER_CHANNEL_SEND_SUBSCRIBE=True)
    async def test_send_subscribe(self):
        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=FakeStrictRedis(),
        ):
            communicator = await mk_communicator(self.client, drain=False)
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        self.assertEqual(
            {
                "t": "channel.subscribed",
                "s": "q",
                "p": {
                    "pk": self.jane.pk,
                    "channel_type": "user",
                    "channel_name": f"user_{self.jane.pk}",
                    "app_state": None,
                },
            },
            payload.dict(exclude_none=True),
        )
        # Auto-added to layer too
        layer = get_channel_layer()
        self.assertIn(f"user_{self.jane.pk}", layer.groups)
        await communicator.disconnect()

    @override_settings(ENVELOPE_USER_CHANNEL_SEND_SUBSCRIBE=True)
    async def test_send_subscribe(self):
        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=self.fake_redis,
        ):
            communicator = await mk_communicator(self.client, drain=False)
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        self.assertEqual(
            {
                "t": "channel.subscribed",
                "s": "q",
                "p": {
                    "pk": self.jane.pk,
                    "channel_type": "user",
                    "channel_name": f"user_{self.jane.pk}",
                    "app_state": None,
                },
            },
            payload.dict(exclude_none=True),
        )
        # Auto-added to layer too
        layer = get_channel_layer()
        self.assertIn(f"user_{self.jane.pk}", layer.groups)
        await communicator.disconnect()

    @override_settings(ENVELOPE_USER_CHANNEL_SEND_SUBSCRIBE=True)
    async def test_send_subscribe(self):
        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=self.fake_redis,
        ):
            communicator = await mk_communicator(self.client, drain=False)
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        self.assertEqual(
            {
                "t": "channel.subscribed",
                "s": "q",
                "p": {
                    "pk": self.jane.pk,
                    "channel_type": "user",
                    "channel_name": f"user_{self.jane.pk}",
                    "app_state": None,
                },
            },
            payload.dict(exclude_none=True),
        )
        # Auto-added to layer too
        layer = get_channel_layer()
        self.assertIn(f"user_{self.jane.pk}", layer.groups)
        await communicator.disconnect()

    @override_settings(ENVELOPE_USER_CHANNEL_SEND_SUBSCRIBE=True)
    async def test_send_subscribe_with_worker(self):
        with patch(
            "django_rq.queues.get_redis_connection",
            return_value=self.fake_redis,
        ):
            communicator = await mk_communicator(self.client, drain=False)
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        self.assertEqual(
            {
                "t": "channel.subscribed",
                "s": "q",
                "p": {
                    "pk": self.jane.pk,
                    "channel_type": "user",
                    "channel_name": f"user_{self.jane.pk}",
                    "app_state": None,
                },
            },
            payload.dict(exclude_none=True),
        )
        fake_redis_queue = Queue(connection=self.fake_redis)
        worker = SimpleWorker([fake_redis_queue], connection=self.fake_redis)
        result = await sync_to_async(worker.work)(burst=True)
        self.assertTrue(result)
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        self.assertEqual(
            {
                "t": "channel.subscribed",
                "p": {
                    "pk": self.jane.pk,
                    "channel_type": "user",
                    "channel_name": f"user_{self.jane.pk}",
                    "app_state": None,
                },
                "s": "s",
            },
            payload.dict(exclude_none=True),
        )
        await communicator.disconnect()

    async def test_disconnect_leaves(self):
        communicator = await mk_communicator(self.client, drain=True)
        consumer_name = await communicator.get_consumer_name()
        layer = get_channel_layer()
        await UserChannel(self.jane.pk, consumer_channel=consumer_name).subscribe()
        self.assertIn(f"user_{self.jane.pk}", layer.groups)
        await communicator.disconnect()
        self.assertNotIn(f"user_{self.jane.pk}", layer.groups)

    async def test_logout_closes_connection(self):
        communicator = await mk_communicator(self.client, drain=True)
        await sync_to_async(user_logged_out.send)(sender=User, user=self.jane)
        response = await communicator.receive_from()
        payload = internal.parse(response)
        self.assertEqual(
            {"t": "s.closing", "p": {"code": 1000}},
            payload.dict(exclude_none=True),
        )
        response = await communicator.receive_output()
        self.assertEqual({"type": "websocket.close", "code": 1000}, response)
        await communicator.wait(0.1)
        self.assertTrue(communicator.future.cancelled())
