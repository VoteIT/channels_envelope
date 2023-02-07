from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.test import TestCase
from django.test import override_settings

from envelope.app.user_channel.channel import UserChannel
from envelope.channels.errors import SubscribeError
from envelope.channels.messages import Leave
from envelope.channels.messages import Left
from envelope.channels.messages import ListSubscriptions
from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed
from envelope.channels.schemas import ChannelSchema
from envelope.signals import channel_subscribed
from envelope.tests.helpers import TempSignal
from envelope.tests.helpers import WebsocketHello
from envelope.tests.helpers import mk_consumer
from envelope.tests.helpers import testing_channel_layers_setting
from envelope.utils import channel_layer

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class SubscribeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_one: AbstractUser = User.objects.create(username="one")
        cls.user_two: AbstractUser = User.objects.create(username="two")

    @property
    def _cut(self):
        return Subscribe

    def _mk_msg(
        self,
        pk,
        *,
        user=None,
        consumer_name="abc",
        channel_type=UserChannel.name,
        **kwargs,
    ):
        return self._cut(
            mm={"user_pk": user and user.pk or None, "consumer_name": consumer_name},
            pk=pk,
            channel_type=channel_type,
        )

    def test_get_app_state(self):
        ch = UserChannel.from_instance(self.user_one)

        def signal_handler(context, app_state, **kwargs):
            app_state.append(WebsocketHello())

        msg = self._mk_msg(1)
        with TempSignal(channel_subscribed, signal_handler):
            app_state = msg.get_app_state(ch)

        self.assertEqual(1, len(app_state))
        self.assertEqual({"t": WebsocketHello.name, "p": None}, app_state[0])

    async def test_pre_queue(self):
        msg = self._mk_msg(1)
        consumer = mk_consumer()
        with patch.object(consumer, "send") as mocked_send:
            result = await msg.pre_queue(consumer)
        self.assertIsInstance(result, Subscribed)
        self.assertTrue(mocked_send.called)
        self.assertIn("text_data", mocked_send.mock_calls[0].kwargs)
        text_data = mocked_send.mock_calls[0].kwargs["text_data"]
        self.assertIn("channel.subscribed", text_data)

    def test_run_job(self):
        msg = self._mk_msg(self.user_one.pk, user=self.user_one)
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        self.assertEqual(self._cut.SUCCESS, response.mm.state)

    def test_run_job_wrong_user(self):
        msg = self._mk_msg(self.user_one.pk, user=self.user_two)
        with self.assertRaises(SubscribeError):
            msg.run_job()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class SubscribedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_one: AbstractUser = User.objects.create(username="one")

    @property
    def _cut(self):
        return Subscribed

    def _mk_msg(
        self,
        channel,
        *,
        user=None,
        consumer_name="abc",
        **kwargs,
    ):
        return self._cut(
            mm={"user_pk": user and user.pk or None, "consumer_name": consumer_name},
            pk=channel.pk,
            channel_name=channel.channel_name,
            channel_type=channel.name,
        )

    async def test_adds_to_subscription(self):
        ch = UserChannel.from_instance(self.user_one)
        msg = self._mk_msg(ch, user=self.user_one)
        consumer = mk_consumer()
        await msg.run(consumer=consumer)
        subs = ChannelSchema(pk=1, channel_type="user")
        self.assertEqual({subs}, consumer.subscriptions)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class LeaveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_one: AbstractUser = User.objects.create(username="one")

    @property
    def _cut(self):
        return Leave

    def _mk_msg(
        self,
        pk,
        *,
        user=None,
        consumer_name="abc",
        channel_type=UserChannel.name,
        **kwargs,
    ):
        return self._cut(
            mm={"user_pk": user and user.pk or None, "consumer_name": consumer_name},
            pk=pk,
            channel_type=channel_type,
        )

    async def test_run(self):
        msg = self._mk_msg(1)
        consumer = mk_consumer()
        with patch.object(consumer, "send") as mocked_send:
            result = await msg.run(consumer=consumer)
        self.assertIsInstance(result, Left)
        self.assertTrue(mocked_send.called)
        self.assertIn("text_data", mocked_send.mock_calls[0].kwargs)
        text_data = mocked_send.mock_calls[0].kwargs["text_data"]
        self.assertIn("channel.left", text_data)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class ListSubscriptionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_one: AbstractUser = User.objects.create(username="one")

    @property
    def _cut(self):
        return ListSubscriptions

    def _mk_msg(
        self,
        pk,
        *,
        user=None,
        consumer_name="abc",
        channel_type=UserChannel.name,
        **kwargs,
    ):
        return self._cut(
            mm={"user_pk": user and user.pk or None, "consumer_name": consumer_name},
            pk=pk,
            channel_type=channel_type,
        )

    async def test_run_no_subscriptions(self):
        msg = self._mk_msg(1)
        consumer = mk_consumer()
        with patch.object(consumer, "send") as mocked_send:
            await msg.run(consumer=consumer)

        self.assertTrue(mocked_send.called)
        self.assertIn("text_data", mocked_send.mock_calls[0].kwargs)
        text_data = mocked_send.mock_calls[0].kwargs["text_data"]
        self.assertIn("channel.subscriptions", text_data)

    async def test_run(self):
        msg = self._mk_msg(1)
        consumer = mk_consumer()
        channel_data = ChannelSchema(pk=self.user_one.pk, channel_type=UserChannel.name)
        consumer.subscriptions.add(channel_data)
        with patch.object(consumer, "send") as mocked_send:
            await msg.run(consumer=consumer)
        self.assertTrue(mocked_send.called)
        self.assertIn("text_data", mocked_send.mock_calls[0].kwargs)
        text_data = mocked_send.mock_calls[0].kwargs["text_data"]
        self.assertIn("channel.subscriptions", text_data)
        data = json.loads(text_data)
        self.assertEqual(
            {
                "t": "channel.subscriptions",
                "p": {
                    "subscriptions": [{"pk": self.user_one.pk, "channel_type": "user"}]
                },
                "i": None,
                "s": "s",
            },
            data,
        )


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class RecheckChannelSubscriptionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_one: AbstractUser = User.objects.create(username="one")

    @property
    def _cut(self):
        from envelope.channels.messages import RecheckChannelSubscriptions

        return RecheckChannelSubscriptions

    def _mk_msg(
        self,
        *,
        user=None,
        consumer_name="abc",
        subscriptions: set[ChannelSchema] = frozenset(),
        **kwargs,
    ):
        return self._cut(
            mm={"user_pk": user and user.pk or None, "consumer_name": consumer_name},
            subscriptions=subscriptions,
        )

    async def test_pre_queue(self):
        consumer = mk_consumer()
        sub1 = ChannelSchema(pk=self.user_one.pk, channel_type=UserChannel.name)
        sub2 = ChannelSchema(pk=-1, channel_type=UserChannel.name)
        consumer.subscriptions.add(sub1)
        msg = self._mk_msg(subscriptions={sub2})
        await msg.pre_queue(consumer)
        self.assertEqual({sub1, sub2}, msg.data.subscriptions)

    def test_should_run(self):
        msg = self._mk_msg()
        self.assertFalse(msg.should_run)
        sub1 = ChannelSchema(pk=self.user_one.pk, channel_type=UserChannel.name)
        msg.data.subscriptions.add(sub1)
        self.assertTrue(msg.should_run)

    def test_run_job(self):
        sub_acceptable = ChannelSchema(
            pk=self.user_one.pk, channel_type=UserChannel.name
        )
        sub_bad = ChannelSchema(pk=-1, channel_type=UserChannel.name)
        msg = self._mk_msg(user=self.user_one, subscriptions={sub_acceptable, sub_bad})
        msg.data.consumer_name = "abc"  # Set by pre_queue normally
        with patch.object(channel_layer, "send") as mocked_send:
            with self.captureOnCommitCallbacks(execute=True):
                response = msg.run_job()
        self.assertEqual([sub_bad], response)
        self.assertTrue(mocked_send.called)
        payload = mocked_send.mock_calls[0].args[1]
        self.assertEqual(
            {
                "t": "channel.left",
                "p": {"pk": -1, "channel_type": "user"},
                "i": None,
                "s": "s",
                "type": "websocket.send",
            },
            payload,
        )
