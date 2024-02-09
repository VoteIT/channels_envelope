from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.transaction import TransactionManagementError
from django.db.transaction import get_connection
from django.test import SimpleTestCase
from django.test import TestCase
from django.test import override_settings

from envelope.messages.errors import BadRequestError
from envelope.messages.ping import Pong
from envelope.tests.helpers import testing_channel_layers_setting
from envelope.utils import get_or_create_txn_sender

User = get_user_model()


class UpdateConnectionStatusTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="connecter")

    @property
    def _fut(self):
        from envelope.utils import update_connection_status

        return update_connection_status

    def test_update_connection_status(self):
        conn = self._fut(self.user.pk, "abc")
        self.assertIsInstance(conn.online_at, datetime)
        self.assertEqual(self.user, conn.user)


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
    ENVELOPE_CONNECTIONS_QUEUE=None,
)
class WebsocketSendTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="sender")

    @property
    def _fut(self):
        from envelope.utils import websocket_send

        return websocket_send

    def test_send(self):
        msg = Pong(mm={"consumer_name": "abc"})
        self._fut(msg)

    def test_send_w_channel(self):
        msg = Pong(mm={"consumer_name": "abc"})
        self._fut(msg, channel_name="def")
        txn_sender = get_or_create_txn_sender()
        sender = txn_sender.data[0]
        self.assertEqual(False, sender.group)
        self.assertEqual("def", sender.channel_name)

    def test_send_group_without_channel(self):
        msg = Pong(mm={"consumer_name": "abc"})
        with self.assertRaises(ValueError):
            self._fut(msg, group=True)

    def test_send_group_with_channel(self):
        msg = Pong(mm={"consumer_name": "abc"})
        self._fut(msg, channel_name="def", group=True)
        txn_sender = get_or_create_txn_sender()
        sender = txn_sender.data[0]
        self.assertEqual(True, sender.group)
        self.assertEqual("def", sender.channel_name)

    def test_send_no_channel(self):
        msg = Pong(mm={"consumer_name": None})
        with self.assertRaises(ValueError):
            self._fut(msg)


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
    ENVELOPE_CONNECTIONS_QUEUE=None,
)
class InternalSendTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="sender")

    @property
    def _fut(self):
        from envelope.utils import internal_send

        return internal_send

    def test_send(self):
        msg = Pong(mm={"consumer_name": "abc"})
        self._fut(msg)

    def test_send_w_channel(self):
        msg = Pong(mm={"consumer_name": "abc"})
        self._fut(msg, channel_name="def")
        conn = get_connection()
        sender = conn.run_on_commit[0][1]
        self.assertEqual(False, sender.group)
        self.assertEqual("def", sender.channel_name)

    def test_send_group_without_channel(self):
        msg = Pong(mm={"consumer_name": "abc"})
        with self.assertRaises(ValueError):
            self._fut(msg, group=True)

    def test_send_group_with_channel(self):
        msg = Pong(mm={"consumer_name": "abc"})
        self._fut(msg, channel_name="def", group=True)
        conn = get_connection()
        sender = conn.run_on_commit[0][1]
        self.assertEqual(True, sender.group)
        self.assertEqual("def", sender.channel_name)

    def test_send_no_channel(self):
        msg = Pong(mm={"consumer_name": None})
        with self.assertRaises(ValueError):
            self._fut(msg)


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
    ENVELOPE_CONNECTIONS_QUEUE=None,
)
class WebsocketSendErrorTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="sender")

    @property
    def _fut(self):
        from envelope.utils import websocket_send_error

        return websocket_send_error

    def test_send(self):
        msg = BadRequestError(mm={"consumer_name": "abc"})
        self._fut(msg)

    def test_send_w_channel(self):
        msg = BadRequestError(mm={"consumer_name": "abc"})
        self._fut(msg, channel_name="def")

        with patch("envelope.utils.SenderUtil.async_send", autospec=True) as mocked:
            self._fut(msg, channel_name="def")
        self.assertTrue(mocked.called)
        sender = mocked.call_args[0][0]
        self.assertEqual(False, sender.group)
        self.assertEqual("def", sender.channel_name)

    def test_send_group_without_channel(self):
        msg = BadRequestError(mm={"consumer_name": "abc"})
        with self.assertRaises(ValueError):
            self._fut(msg, group=True)

    def test_send_group_with_channel(self):
        msg = BadRequestError(mm={"consumer_name": "abc"})
        with patch("envelope.utils.SenderUtil.async_send", autospec=True) as mocked:
            self._fut(msg, channel_name="def", group=True)
        sender = mocked.call_args[0][0]
        self.assertEqual(True, sender.group)
        self.assertEqual("def", sender.channel_name)

    def test_send_no_channel(self):
        msg = BadRequestError(mm={"consumer_name": None})
        with self.assertRaises(ValueError):
            self._fut(msg)


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
    ENVELOPE_CONNECTIONS_QUEUE=None,
)
class UtilTestsWithoutTransactionsTests(SimpleTestCase):

    def test_websocket_send(self):
        from envelope.utils import websocket_send

        msg = Pong(mm={"consumer_name": "hello"})

        with patch("envelope.utils.SenderUtil.async_send", autospec=True) as mocked:
            websocket_send(msg, on_commit=True)  # Will be immediate regardless
        self.assertTrue(mocked.called)

    def test_websocket_send_right_away(self):
        from envelope.utils import websocket_send

        msg = Pong(mm={"consumer_name": "hello"})

        with patch("envelope.utils.SenderUtil.async_send", autospec=True) as mocked:
            websocket_send(msg, on_commit=False)
        self.assertTrue(mocked.called)

    def test_internal_send(self):
        from envelope.utils import internal_send

        msg = Pong(mm={"consumer_name": "hello"})

        with patch("envelope.utils.SenderUtil.async_send", autospec=True) as mocked:
            internal_send(msg, on_commit=True)  # Will be immediate regardless
        self.assertTrue(mocked.called)

    def test_internal_send_right_away(self):
        from envelope.utils import internal_send

        msg = Pong(mm={"consumer_name": "hello"})

        with patch("envelope.utils.SenderUtil.async_send", autospec=True) as mocked:
            internal_send(msg, on_commit=False)
        self.assertTrue(mocked.called)

    def test_get_or_create_txn_sender(self):
        with self.assertRaises(TransactionManagementError):
            get_or_create_txn_sender(raise_exception=True)
