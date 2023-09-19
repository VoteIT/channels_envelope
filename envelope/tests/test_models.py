from unittest.mock import patch
from django.test import TestCase
from django.test import override_settings

from envelope.messages.common import ProgressNum
from envelope.utils import channel_layer
from envelope.utils import websocket_send


class TransactionSenderIntegrationTests(TestCase):
    @override_settings(ENVELOPE_BATCH_MESSAGE="envelope.messages.common.Batch2")
    @patch.object(channel_layer, "send")
    def test_batch2_messages(self, mock_send):
        # 3 messages to trigger batch
        with self.captureOnCommitCallbacks(execute=True):
            for i in range(1, 4):
                websocket_send(ProgressNum(curr=i, total=3), channel_name="abc")
        self.failUnless(mock_send.called)
        data = mock_send.call_args[0][1]
        self.assertEqual("s.batch2", data["t"])
        self.assertEqual(
            {
                "common": None,
                "keys": ["curr", "total", "msg"],
                "t": "progress.num",
                "values": [[1, 3, None], [2, 3, None], [3, 3, None]],
            },
            data["p"],
        )
        # and channel fetched from initial message
        self.assertEqual("abc", mock_send.call_args[0][0])

    @patch.object(channel_layer, "send")
    def test_batch_message_with_status(self, mock_send):
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
