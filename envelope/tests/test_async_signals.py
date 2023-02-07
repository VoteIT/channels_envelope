from unittest.mock import patch

from django.test import TestCase

from envelope.async_signals import incoming_websocket_message
from envelope.channels.messages import Subscriptions
from envelope.tests.helpers import mk_consumer


class RunAsyncRunnableTest(TestCase):
    async def test_run(self):
        from envelope.channels.messages import ListSubscriptions

        consumer = mk_consumer()
        msg = ListSubscriptions()
        with patch.object(consumer, "send_ws_message") as mocked_send:
            await incoming_websocket_message.send(
                ListSubscriptions, message=msg, consumer=consumer
            )
        self.assertTrue(mocked_send.called)
        msg = mocked_send.mock_calls[0].args[0]
        self.assertIsInstance(msg, Subscriptions)
