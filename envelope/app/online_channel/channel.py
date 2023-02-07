from envelope.channels.decorators import add_pubsub_channel
from envelope.channels.models import PubSubChannel


@add_pubsub_channel
class OnlineChannel(PubSubChannel):
    """
    Users that are (probably!) online. Depending on channel layer, we don't really know.
    """

    name = "online"
    channel_name = "online_users"
