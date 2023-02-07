from envelope.channels.models import PubSubChannel
from envelope.channels.models import ContextChannel
from envelope.utils import get_context_channel_registry
from envelope.utils import get_pubsub_channel_registry


def get_pubsub_channel(name: str) -> type[PubSubChannel]:
    return get_pubsub_channel_registry()[name]


def get_context_channel(name) -> type[ContextChannel]:
    return get_context_channel_registry()[name]
