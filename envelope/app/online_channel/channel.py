from envelope.core.channels import PubSubChannel
from envelope.decorators import add_pubsub_channel


@add_pubsub_channel
class OnlineChannel(PubSubChannel):
    """
    Users that are (probably!) online. Depending on channel layer, we don't really know.
    """

    name = "online"
    channel_name = "online_users"
