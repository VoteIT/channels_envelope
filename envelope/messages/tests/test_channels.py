from __future__ import annotations

from asgiref.sync import async_to_sync
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.test import TestCase
from django_rq import get_queue

from envelope.messages.errors import SubscribeError
from envelope.testing import mk_communicator
from envelope.testing import mk_simple_worker

User = get_user_model()


class SubscribeTests(TestCase):
    communicator = None

    @classmethod
    def setUpTestData(cls):
        cls.user_one: AbstractUser = User.objects.create(username="one")
        cls.user_two: AbstractUser = User.objects.create(username="two")

    def setUp(self):
        self.queue = get_queue()
        self.queue.empty()

    def tearDown(self):
        super().tearDown()
        if self.communicator is not None:
            async_to_sync(self.communicator.disconnect)()

    def _mk_msg(self):
        from envelope.messages.channels import Subscribe

        return Subscribe(
            mm={"user_pk": self.user_one.pk}, channel_type="user", pk=self.user_one.pk
        )

    def _pack(self, msg):
        from envelope.envelope import IncomingWebsocketEnvelope

        return IncomingWebsocketEnvelope.pack(msg)


    async def test_subscribe(self):
        self.communicator = await mk_communicator(self.user_one)
        msg = self._mk_msg()
        msg.validate()
        envelope = self._pack(msg)
        envelope.data.i = "subs"
        await self.communicator.send_json_to(envelope.data.dict())
        response = await self.communicator.receive_json_from()
        self.assertEqual(
            {
                "t": "channel.subscribed",
                "p": {
                    "pk": self.user_one.pk,
                    "channel_type": "user",
                    "channel_name": f"user_{self.user_one.pk}",
                    "app_state": None,
                },
                "i": "subs",
                "s": "q",
            },
            response,
        )

    def test_subscribe_job(self):
        from envelope.messages.channels import Subscribed

        msg = self._mk_msg()
        msg.mm.consumer_name = "abc"
        msg.validate()
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        self.assertEqual(response.data.channel_name, f"user_{self.user_one.pk}")

    def test_subscribe_not_allowed(self):
        msg = self._mk_msg()
        msg.mm.user_pk = self.user_two.pk
        msg.validate()
        self.assertRaises(SubscribeError, msg.run_job)

    async def test_subscribe_not_allowed_via_communicator(self):
        msg = self._mk_msg()
        msg.validate()
        envelope = self._pack(msg)
        envelope.data.i = "subs"
        self.communicator = await mk_communicator(self.user_two, queue=self.queue)
        await self.communicator.send_json_to(envelope.data.dict())
        response = await self.communicator.receive_json_from()
        self.assertEqual("channel.subscribed", response['t'])
        self.assertEqual("q", response['s'])
        worker = mk_simple_worker()
        await sync_to_async(worker.work)(burst=True)
        response = await self.communicator.receive_json_from()
        self.assertEqual(
            {
                "t": "error.subscribe",
                "p": {
                    "channel_name": f"user_{self.user_one.pk}",
                },
                "i": "subs",
                "s": "f",
            },
            response,
        )


class LeaveTests(TestCase):
    communicator = None

    @classmethod
    def setUpTestData(cls):
        cls.user_one: AbstractUser = User.objects.create(username="one")
        cls.user_two: AbstractUser = User.objects.create(username="two")

    def tearDown(self):
        super().tearDown()
        if self.communicator is not None:
            async_to_sync(self.communicator.disconnect)()

    def _mk_msg(self):
        from envelope.messages.channels import Leave

        return Leave(
            mm={"user_pk": self.user_one.pk}, channel_type="user", pk=self.user_one.pk
        )

    def _pack(self, msg):
        from envelope.envelope import IncomingWebsocketEnvelope

        return IncomingWebsocketEnvelope.pack(msg)

    async def test_leave(self):
        self.communicator = await mk_communicator(self.user_one)
        msg = self._mk_msg()
        msg.validate()
        envelope = self._pack(msg)
        envelope.data.i = "subs"
        await self.communicator.send_json_to(envelope.data.dict())
        response = await self.communicator.receive_json_from()
        self.assertEqual(
            {
                "t": "channel.left",
                "p": {
                    "pk": self.user_one.pk,
                    "channel_type": "user",
                },
                "i": "subs",
                "s": "s",
            },
            response,
        )


class ListSubscriptionsTests(TestCase):
    communicator = None

    @classmethod
    def setUpTestData(cls):
        cls.user_one: AbstractUser = User.objects.create(username="one")
        cls.user_two: AbstractUser = User.objects.create(username="two")

    def tearDown(self):
        super().tearDown()
        if self.communicator is not None:
            async_to_sync(self.communicator.disconnect)()

    def _mk_msg(self):
        from envelope.messages.channels import ListSubscriptions

        return ListSubscriptions(mm={"user_pk": self.user_one.pk})

    async def test_list_subscriptions(self):
        from envelope.envelope import OutgoingWebsocketEnvelope
        from envelope.envelope import IncomingWebsocketEnvelope

        from envelope.messages.channels import Subscribed

        self.communicator = await mk_communicator(self.user_one)
        # Subscribe
        subs_msg = Subscribed(
            channel_type="user",
            pk=self.user_one.pk,
            channel_name=f"user_{self.user_one.pk}",
        )
        subs_msg.validate()
        subs_envelope = OutgoingWebsocketEnvelope.pack(subs_msg)
        subs_envelope.data.i = "subscribed"
        await self.communicator.send_input(
            {
                "type": "websocket.send",
                "text_data": subs_envelope.data.json(),
                "run_handlers": True,
            }
        )
        response = await self.communicator.receive_json_from()
        self.assertEqual("subscribed", response["i"])

        msg = self._mk_msg()
        msg.validate()
        envelope = IncomingWebsocketEnvelope.pack(msg)
        envelope.data.i = "query"
        await self.communicator.send_json_to(envelope.data.dict())
        response = await self.communicator.receive_json_from()
        self.assertEqual("s", response["s"])
        self.assertEqual("query", response["i"])
        self.assertEqual("channel.subscriptions", response["t"])
        self.assertEqual(
            {"subscriptions": [{"channel_type": "user", "pk": 1}]}, response["p"]
        )


class RecheckChannelSubscriptionsTests(TestCase):
    communicator = None

    @classmethod
    def setUpTestData(cls):
        cls.user_one: AbstractUser = User.objects.create(username="one")
        cls.user_two: AbstractUser = User.objects.create(username="two")

    def tearDown(self):
        super().tearDown()
        if self.communicator is not None:
            async_to_sync(self.communicator.disconnect)()

    def _mk_msg(self, **kwargs):
        from envelope.messages.channels import RecheckChannelSubscriptions

        return RecheckChannelSubscriptions(mm={"user_pk": self.user_one.pk}, **kwargs)

    async def test_recheck_channel_subscriptions_pre_queue(self):
        from envelope.consumers.websocket import WebsocketConsumer
        from envelope.messages.channels import ChannelSchema

        channel_subscription = ChannelSchema(pk=self.user_one.pk, channel_type="user")
        consumer = WebsocketConsumer()
        consumer.mark_subscribed(channel_subscription)
        consumer.channel_name = "abc"

        msg = self._mk_msg()
        msg.validate()
        await msg.pre_queue(consumer)
        self.assertIn(channel_subscription, msg.data.subscriptions)

    def test_recheck_run(self):
        from envelope.messages.channels import ChannelSchema

        good_subscription = ChannelSchema(pk=self.user_one.pk, channel_type="user")
        bad_subscription = ChannelSchema(pk=self.user_two.pk, channel_type="user")
        msg = self._mk_msg(
            subscriptions=[good_subscription, bad_subscription], consumer_name="abc"
        )
        msg.validate()
        results = msg.run_job()
        self.assertEqual([bad_subscription], results)
