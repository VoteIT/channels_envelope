from unittest.mock import patch

from channels.layers import get_channel_layer
from django.test import TestCase
from django.test import override_settings

from envelope.messages.common import ProgressNum
from envelope.utils import websocket_send


class TransactionSenderIntegrationTests(TestCase):
    @override_settings(ENVELOPE_BATCH_MESSAGE="envelope.messages.common.Batch2")
    def test_batch2_messages(self):
        channel_layer = get_channel_layer()
        with patch.object(channel_layer, "send") as mock_send:
            # 3 messages to trigger batch
            with self.captureOnCommitCallbacks(execute=True):
                for i in range(1, 4):
                    websocket_send(ProgressNum(curr=i, total=3), channel_name="abc")
            self.failUnless(mock_send.called)
            data = mock_send.call_args[0][1]
            self.assertEqual("s.batch2", data["t"])
            self.assertEqual("websocket.send", data["type"])
            self.assertEqual(
                '{"t": "s.batch2", "p": {"t": "progress.num", "common": null, "keys": ["curr", "total", "msg"], "values": [[1, 3, null], [2, 3, null], [3, 3, null]]}, "i": null, "s": null}',
                data["text_data"],
            )
            # and channel fetched from initial message
            self.assertEqual("abc", mock_send.call_args[0][0])

    def test_batch_message_with_status(self):
        channel_layer = get_channel_layer()
        with patch.object(channel_layer, "send") as mock_send:
            # 3 messages to trigger batch
            with self.captureOnCommitCallbacks(execute=True):
                for i in range(1, 4):
                    websocket_send(
                        ProgressNum(curr=i, total=3), channel_name="abc", state="s"
                    )
            self.failUnless(mock_send.called)
            data = mock_send.call_args[0][1]
            self.assertEqual("s.batch", data["t"])
            self.assertEqual("s", data["s"])
            # and channel fetched from initial message
            self.assertEqual("abc", mock_send.call_args[0][0])
