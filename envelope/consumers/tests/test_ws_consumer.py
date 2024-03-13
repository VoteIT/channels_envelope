from json import loads

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.test import override_settings

from envelope import ERRORS
from envelope import INTERNAL
from envelope.app.user_channel.channel import UserChannel
from envelope.async_signals import consumer_connected
from envelope.async_signals import incoming_internal_message
from envelope.async_signals import incoming_websocket_message
from envelope.async_signals import outgoing_websocket_error
from envelope.async_signals import outgoing_websocket_message
from envelope.channels.messages import Leave
from envelope.channels.messages import ListSubscriptions
from envelope.channels.messages import Subscribe
from envelope.envelopes import incoming
from envelope.envelopes import outgoing
from envelope.messages.errors import MessageTypeError
from envelope.messages.errors import ValidationErrorMsg
from envelope.messages.ping import Ping
from envelope.messages.ping import Pong
from envelope.messages.testing import SendClientInfo
from envelope.testing import TempSignal
from envelope.testing import mk_communicator
from envelope.testing import mk_consumer
from envelope.testing import testing_channel_layers_setting
from envelope.utils import SenderUtil
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
        from envelope.consumers.websocket import WebsocketConsumer

        return WebsocketConsumer

    def _mk_one(self, **kwargs):
        kwargs.setdefault("user", self.user)
        return mk_consumer(**kwargs)

    async def test_connect(self):
        self.signal_was_fired = False

        async def signal_check(*, sender, consumer, **kwargs):
            self.assertTrue(issubclass(sender, self._cut))
            self.assertIsInstance(consumer, self._cut)
            self.signal_was_fired = True

        with TempSignal(consumer_connected, signal_check):
            communicator = await mk_communicator(self.client)

        self.assertTrue(self.signal_was_fired)
        await communicator.disconnect()

    async def test_ping_receive(self):
        self.signal_was_fired = False

        # Test sending text
        msg = Ping(mm={"id": "a"})
        data = incoming.pack(msg)
        text_data = data.json()
        communicator = await mk_communicator(self.client)

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
        communicator = await mk_communicator(self.client)

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
        communicator = await mk_communicator(self.client)

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
        communicator = await mk_communicator(self.client)

        async def msg_check(*, sender, message, **kwargs):
            self.assertIsInstance(message, ValidationErrorMsg)
            self.signal_was_fired = True

        with TempSignal(outgoing_websocket_error, msg_check):
            await communicator.send_to(text_data=text_data)
            response = await communicator.receive_from()

        data = loads(response)
        self.assertEqual(
            {
                "t": "error.validation",
                "p": {
                    "msg": None,
                    "errors": [
                        {
                            "loc": ["__root__"],
                            "msg": "Expecting value: line 1 column 2 (char 1)",
                            "type": "value_error.jsondecode",
                            "ctx": {
                                "msg": "Expecting value",
                                "doc": " ",
                                "pos": 1,
                                "lineno": 1,
                                "colno": 2,
                            },
                        }
                    ],
                },
                "i": None,
                "s": "f",
            },
            data,
        )
        self.assertTrue(self.signal_was_fired)
        await communicator.disconnect()

    async def test_message_type_missing(self):
        self.signal_was_fired = False
        text_data = '{"t": "jeff"}'
        communicator = await mk_communicator(self.client)

        async def msg_check(*, sender, message, **kwargs):
            self.assertIsInstance(message, MessageTypeError)
            self.signal_was_fired = True

        with TempSignal(outgoing_websocket_error, msg_check):
            await communicator.send_to(text_data=text_data)
            response = await communicator.receive_from()
        data = loads(response)
        self.assertEqual(
            {
                "t": "error.msg_type",
                "p": {"msg": None, "type_name": "jeff", "envelope": "ws_incoming"},
                "i": None,
                "s": "f",
            },
            data,
        )
        self.assertTrue(self.signal_was_fired)
        await communicator.disconnect()

    async def test_internal_msg(self):
        self.signal_was_fired = False
        communicator = await mk_communicator(self.client)
        consumer_name = await communicator.get_consumer_name()
        msg = SendClientInfo(mm={"consumer_name": consumer_name})
        sender = get_sender_util()(msg, channel_name=consumer_name, envelope=INTERNAL)

        async def msg_check(*, sender, message, **kwargs):
            self.assertIsInstance(message, SendClientInfo)
            self.signal_was_fired = True

        with TempSignal(incoming_internal_message, msg_check):
            await sender.async_send()
            response = await communicator.receive_from()

        data = loads(response)
        self.assertEqual(
            {
                "t": "s.client_info",
                "p": {"consumer_name": consumer_name, "lang": "en"},
                "i": None,
                "s": None,
            },
            data,
        )
        self.assertTrue(self.signal_was_fired)
        await communicator.disconnect()

    async def test_message_validation_error(self):
        communicator = await mk_communicator(self.client)
        payload = {"t": Subscribe.name, "p": {"pk": 1, "channel_type": "404"}}
        await communicator.send_json_to(payload)
        response = await communicator.receive_msg()
        self.assertIsInstance(response, ValidationErrorMsg)
        self.assertEqual(
            {
                "errors": [
                    {
                        "loc": ["channel_type"],
                        "msg": "'404' is not a valid channel",
                        "type": "value_error",
                    }
                ]
            },
            response.data.dict(exclude={"msg"}),
        )

    async def test_subscriptions_lifecycle(self):
        self.signal_was_fired = False
        communicator = await mk_communicator(self.client, drain=False)
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

    async def test_send_error(self):
        # self.signal_was_fired = False
        communicator = await mk_communicator(self.client)
        consumer_name = await communicator.get_consumer_name()
        # The error will be received as a dict

        msg = MessageTypeError(
            envelope="something", type_name="i dont exist", msg="Oh man"
        )
        util = SenderUtil(msg, ERRORS, channel_name=consumer_name)
        await util.async_send()
        response = await communicator.receive_from()
        data = loads(response)
        self.assertEqual(
            {
                "i": None,
                "p": {
                    "envelope": "something",
                    "msg": "Oh man",
                    "type_name": "i dont exist",
                },
                "s": "f",
                "t": "error.msg_type",
            },
            data,
        )
        await communicator.disconnect()

    async def test_unauthenticated(self):
        await sync_to_async(self.client.logout)()
        with self.assertRaises(AssertionError) as cm:
            await mk_communicator(self.client)
        self.assertEqual("Not connected", str(cm.exception))

    @override_settings(ENVELOPE_ALLOW_UNAUTHENTICATED=True)
    async def test_unauthenticated_allowed(self):
        await sync_to_async(self.client.logout)()
        communicator = await mk_communicator(self.client)
        msg = Ping(mm={"id": "boo"})
        data = incoming.pack(msg)
        text_data = data.json()
        await communicator.send_to(text_data=text_data)
        response = await communicator.receive_from()
        data = loads(response)
        self.assertEqual({"t": "s.pong", "p": None, "i": "boo", "s": "s"}, data)

    @override_settings(
        LANGUAGES=[
            ("sv", "Svenska"),
            ("en", "English"),
        ]
    )
    async def test_language_and_threading(self):
        communicator_en = await mk_communicator(
            self.client, headers=[(b"accept-language", b"en")]
        )
        communicator_sv = await mk_communicator(
            self.client, headers=[(b"accept-language", b"sv")]
        )
        # 2 times to make sure settings aren't changed!
        checks = [(communicator_en, "en"), (communicator_sv, "sv")]
        checks.extend(checks)
        for communicator, lang in checks:
            msg = SendClientInfo()
            payload = incoming.pack(msg)
            text_data = payload.json()
            await communicator.send_to(text_data=text_data)
            response = await communicator.receive_from()
            payload = outgoing.parse(response)
            message = outgoing.unpack(payload)
            self.assertEqual(lang, message.data.lang)
