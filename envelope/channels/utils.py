from envelope.channels.models import ContextChannel
from envelope.utils import get_context_channel_registry


def get_context_channel(name) -> type[ContextChannel]:
    return get_context_channel_registry()[name]
