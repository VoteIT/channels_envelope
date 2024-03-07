from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.test import TransactionTestCase

from envelope.app.online_channel.channel import OnlineChannel
from envelope.envelopes import outgoing
from envelope.messages.common import Status
from envelope.testing import get_consumer_name
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
        communicator = await mk_communicator(self.client)
        layer = get_channel_layer()
        self.assertIn(OnlineChannel.channel_name, layer.groups)
        consumer_name = await get_consumer_name(communicator)
        ch = OnlineChannel(consumer_channel=consumer_name)
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
        communicator = await mk_communicator(self.client)
        layer = get_channel_layer()
        self.assertIn(OnlineChannel.channel_name, layer.groups)
        await communicator.disconnect()
        self.assertNotIn(OnlineChannel.channel_name, layer.groups)
