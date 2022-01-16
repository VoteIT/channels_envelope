from envelope import DEFAULT_CHANNELS
from envelope.channels import PubSubChannel
from envelope.decorators import add_channel


@add_channel(DEFAULT_CHANNELS)
class OnlineChannel(PubSubChannel):
    """
    Users that are (probably!) online. Depending on channel layer, we don't really know.
    """

    name = "online"
    channel_name = "online_users"