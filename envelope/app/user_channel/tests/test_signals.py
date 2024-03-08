from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.test import TransactionTestCase

from envelope.app.user_channel.channel import UserChannel
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

    async def test_disconnect_leaves(self):
        communicator = await mk_communicator(self.client, drain=False)
        layer = get_channel_layer()
        self.assertIn(f"user_{self.jane.pk}", layer.groups)
        await communicator.disconnect()
        self.assertNotIn(f"user_{self.jane.pk}", layer.groups)
