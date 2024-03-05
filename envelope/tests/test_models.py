from django.test import TestCase

from envelope.messages.common import Batch
from envelope.testing import WebsocketHello
from envelope.utils import SenderUtil


class TransactionSenderTests(TestCase):
    @property
    def _cut(self):
        from envelope.models import TransactionSender

        return TransactionSender

    def test_groupby(self):
        txn_sender = self._cut()

        for i in range(3):
            util = SenderUtil(WebsocketHello(), channel_name="abc", state="s")
            txn_sender.add(util)

        different_ch_name = SenderUtil(WebsocketHello(), channel_name="123", state="s")
        txn_sender.add(different_ch_name)
        other_with_state = SenderUtil(WebsocketHello(), channel_name="abc", state="q")
        txn_sender.add(other_with_state)
        reformatted = dict((k, list(v)) for k, v in txn_sender.groupby())
        self.assertEqual(3, len(reformatted))
        self.assertIn("testing.hello123s00testing", reformatted)
        self.assertIn("testing.helloabcq00testing", reformatted)
        self.assertEqual(3, len(reformatted["testing.helloabcs00testing"]))

    def test_batch_mixed(self):
        txn_sender = self._cut()

        for i in range(3):
            util = SenderUtil(WebsocketHello(), channel_name="abc", state="s")
            txn_sender.add(util)
            util = SenderUtil(WebsocketHello(), channel_name="cde", state="s")
            txn_sender.add(util)

        txn_sender.batch_messages()
        self.assertEqual(["s.batch", "s.batch"], [x.msg.name for x in txn_sender.data])

    def test_batch(self):
        txn_sender = self._cut()

        for i in range(3):
            util = SenderUtil(WebsocketHello(), channel_name="abc", state="s")
            txn_sender.add(util)

        different_ch_name = SenderUtil(WebsocketHello(), channel_name="123", state="s")
        txn_sender.add(different_ch_name)
        other_with_state = SenderUtil(WebsocketHello(), channel_name="abc", state="q")
        txn_sender.add(other_with_state)
        self.assertEqual(5, len(txn_sender))
        txn_sender.batch_messages()
        self.assertEqual(3, len(txn_sender))
        batched_util = None
        for x in txn_sender:
            if x.msg.name == "s.batch":
                batched_util = x
                break
        self.assertIsInstance(batched_util.msg, Batch)
        self.assertEqual("testing.hello", batched_util.msg.data.t)
        self.assertEqual([None, None, None], batched_util.msg.data.payloads)
