from channels.auth import AuthMiddlewareStack
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.test import override_settings

from envelope import INTERNAL
from envelope.app.user_channel.channel import UserChannel
from envelope.async_signals import consumer_connected
from envelope.async_signals import incoming_internal_message
from envelope.async_signals import incoming_websocket_message
from envelope.async_signals import outgoing_websocket_error
from envelope.async_signals import outgoing_websocket_message
from envelope.channels.messages import Leave
from envelope.channels.messages import ListSubscriptions
from envelope.channels.testing import ForceSubscribe
from envelope.envelopes import incoming
from envelope.envelopes import outgoing
from envelope.messages.errors import MessageTypeError
from envelope.messages.errors import ValidationErrorMsg
from envelope.messages.ping import Ping
from envelope.messages.ping import Pong
from envelope.messages.testing import SendClientInfo
from envelope.tests.helpers import TempSignal
from envelope.tests.helpers import mk_consumer
from envelope.tests.helpers import testing_channel_layers_setting
from envelope.utils import get_sender_util

User = get_user_model()


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting, ENVELOPE_CONNECTIONS_QUEUE=None
)
class WebsocketConsumerTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create(username="hello")
        self.client.force_login(self.user)

    @property
    def _cut(self):
        from envelope.consumer.websocket import WebsocketConsumer

        return WebsocketConsumer

    def _mk_one(self, **kwargs):
        kwargs.setdefault("user", self.user)
        return mk_consumer(**kwargs)

    async def _mk_connection(self):
        headers = [
            (b"origin", b"..."),
            (b"cookie", self.client.cookies.output(header="", sep="; ").encode()),
        ]
        communicator = WebsocketCommunicator(
            AuthMiddlewareStack(self._cut.as_asgi()),
            "/testws/",
            headers=headers,
        )
        connected, subprotocol = await communicator.connect()
        assert connected
        return communicator

    async def get_consumer_name(self, communicator):
        msg = SendClientInfo()
        payload = incoming.pack(msg)
        text_data = payload.json()
        await communicator.send_to(text_data=text_data)
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        message = outgoing.unpack(payload)
        return message.data.consumer_name

    async def test_connect(self):
        self.signal_was_fired = False

        async def signal_check(*, sender, consumer, **kwargs):
            self.assertTrue(issubclass(sender, self._cut))
            self.assertIsInstance(consumer, self._cut)
            self.signal_was_fired = True

        with TempSignal(consumer_connected, signal_check):
            # await communicator.send_to(text_data=text_data)
            communicator = await self._mk_connection()

        self.assertTrue(self.signal_was_fired)
        await communicator.disconnect()

    async def test_ping_receive(self):
        self.signal_was_fired = False

        # Test sending text
        msg = Ping(mm={"id": "a"})
        data = incoming.pack(msg)
        text_data = data.json()
        communicator = await self._mk_connection()

        async def msg_check(*, sender, message, **kwargs):
            self.assertIsInstance(message, Ping)
            self.signal_was_fired = True

        with TempSignal(incoming_websocket_message, msg_check):
            await communicator.send_to(text_data=text_data)
            response = await communicator.receive_from()

        self.assertEqual('{"t": "s.pong", "p": null, "i": "a", "s": "s"}', response)
        self.assertTrue(self.signal_was_fired)
        await communicator.disconnect()

    async def test_pong_send(self):
        self.signal_was_fired = False
        # Test that pong was sent
        msg = Ping(mm={"id": "a"})
        data = incoming.pack(msg)
        text_data = data.json()
        communicator = await self._mk_connection()

        async def msg_check(*, sender, message, **kwargs):
            self.assertIsInstance(message, Pong)
            self.signal_was_fired = True

        with TempSignal(outgoing_websocket_message, msg_check):
            await communicator.send_to(text_data=text_data)
            response = await communicator.receive_from()
        self.assertEqual('{"t": "s.pong", "p": null, "i": "a", "s": "s"}', response)

        self.assertTrue(self.signal_was_fired)
        await communicator.disconnect()

    async def test_incoming_missing_message_error(self):
        self.signal_was_fired = False
        text_data = "{}"
        communicator = await self._mk_connection()

        async def msg_check(*, sender, message, **kwargs):
            self.assertIsInstance(message, ValidationErrorMsg)
            self.signal_was_fired = True

        with TempSignal(outgoing_websocket_error, msg_check):
            await communicator.send_to(text_data=text_data)
            response = await communicator.receive_from()

        self.assertEqual(
            '{"t": "error.validation", "p": {"msg": null, "errors": [{"loc": ["t"], "msg": "field required", "type": "value_error.missing"}]}, "i": null, "s": "f"}',
            response,
        )
        self.assertTrue(self.signal_was_fired)
        await communicator.disconnect()

    async def test_empty_message(self):
        self.signal_was_fired = False
        text_data = " "
        communicator = await self._mk_connection()

        async def msg_check(*, sender, message, **kwargs):
            self.assertIsInstance(message, ValidationErrorMsg)
            self.signal_was_fired = True

        with TempSignal(outgoing_websocket_error, msg_check):
            await communicator.send_to(text_data=text_data)
            response = await communicator.receive_from()

        self.assertEqual(
            '{"t": "error.validation", "p": {"msg": null, "errors": [{"loc": ["__root__"], "msg": "Expecting value: line 1 column 2 (char 1)", "type": "value_error.jsondecode", "ctx": {"msg": "Expecting value", "doc": " ", "pos": 1, "lineno": 1, "colno": 2}}]}, "i": null, "s": "f"}',
            response,
        )
        self.assertTrue(self.signal_was_fired)
        await communicator.disconnect()

    async def test_message_type_missing(self):
        self.signal_was_fired = False
        text_data = '{"t": "jeff"}'
        communicator = await self._mk_connection()

        async def msg_check(*, sender, message, **kwargs):
            self.assertIsInstance(message, MessageTypeError)
            self.signal_was_fired = True

        with TempSignal(outgoing_websocket_error, msg_check):
            await communicator.send_to(text_data=text_data)
            response = await communicator.receive_from()

        self.assertEqual(
            '{"t": "error.msg_type", "p": {"msg": null, "type_name": "jeff", "envelope": "ws_incoming"}, "i": null, "s": "f"}',
            response,
        )
        self.assertTrue(self.signal_was_fired)
        await communicator.disconnect()

    async def test_internal_msg(self):
        self.signal_was_fired = False
        communicator = await self._mk_connection()
        consumer_name = await self.get_consumer_name(communicator)
        msg = SendClientInfo(mm={"consumer_name": consumer_name})
        sender = get_sender_util()(msg, channel_name=consumer_name, envelope=INTERNAL)

        async def msg_check(*, sender, message, **kwargs):
            self.assertIsInstance(message, SendClientInfo)
            self.signal_was_fired = True

        with TempSignal(incoming_internal_message, msg_check):
            await sender.async_send()
            response = await communicator.receive_from()

        self.assertEqual(
            '{"t": "s.client_info", "p": {"consumer_name": "%s"}, "i": null, "s": null}'
            % consumer_name,
            response,
        )
        self.assertTrue(self.signal_was_fired)
        await communicator.disconnect()

    async def test_subscriptions_lifecycle(self):
        self.signal_was_fired = False
        communicator = await self._mk_connection()
        # Subscribe
        msg = ForceSubscribe(pk=self.user.pk, channel_type=UserChannel.name)
        payload = incoming.pack(msg)
        await communicator.send_to(text_data=payload.json())
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        self.assertEqual(
            {
                "t": "channel.subscribed",
                "p": {
                    "pk": self.user.pk,
                    "channel_type": "user",
                    "channel_name": f"user_{self.user.pk}",
                    "app_state": None,
                },
                "s": "s",
            },
            payload.dict(exclude_none=True),
        )
        # List
        msg = ListSubscriptions()
        payload = incoming.pack(msg)
        await communicator.send_to(text_data=payload.json())
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        self.assertEqual(
            {
                "t": "channel.subscriptions",
                "p": {"subscriptions": [{"pk": self.user.pk, "channel_type": "user"}]},
                "s": "s",
            },
            payload.dict(exclude_none=True),
        )
        # Leave
        msg = Leave(pk=self.user.pk, channel_type=UserChannel.name)
        payload = incoming.pack(msg)
        await communicator.send_to(text_data=payload.json())
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        self.assertEqual(
            {
                "t": "channel.left",
                "p": {
                    "pk": self.user.pk,
                    "channel_type": "user",
                },
                "s": "s",
            },
            payload.dict(exclude_none=True),
        )
        # List again
        msg = ListSubscriptions()
        payload = incoming.pack(msg)
        await communicator.send_to(text_data=payload.json())
        response = await communicator.receive_from()
        payload = outgoing.parse(response)
        self.assertEqual(
            {
                "t": "channel.subscriptions",
                "p": {"subscriptions": []},
                "s": "s",
            },
            payload.dict(exclude_none=True),
        )
