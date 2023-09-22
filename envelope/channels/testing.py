from __future__ import annotations

from typing import TYPE_CHECKING

from envelope import WS_INCOMING
from envelope.channels.messages import ChannelCommand
from envelope.channels.messages import Subscribed
from envelope.core.message import AsyncRunnable
from envelope.decorators import add_message

if TYPE_CHECKING:
    from envelope.consumer.websocket import WebsocketConsumer

# FIXME: Debug isn't registered properly? :/
# if not settings.DEBUG:
#    raise ImproperlyConfigured(
#        "%s should never be imported unless DEBUG mode is on." % __name__
#    )


@add_message(WS_INCOMING)
class ForceSubscribe(ChannelCommand, AsyncRunnable):
    name = "force_subscribe"

    async def run(self, *, consumer: WebsocketConsumer, **kwargs) -> Subscribed:
        channel = self.get_channel(
            self.data.channel_type, self.data.pk, self.mm.consumer_name
        )
        msg = Subscribed.from_message(
            self,
            state=self.SUCCESS,
            channel_name=channel.channel_name,
            **self.data.dict(),
        )
        await consumer.send_ws_message(msg)
        return msg  # For testing
