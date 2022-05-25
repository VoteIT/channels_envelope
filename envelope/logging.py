from __future__ import annotations
import logging
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from envelope.core.consumer import BaseWebsocketConsumer
    from envelope.core.message import Message


class EventLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        super().process(msg, kwargs)
        message: Message = kwargs.pop("message", None)
        if message:
            kwargs["extra"]["i"] = message.mm.id
            kwargs["extra"]["t"] = message.name
            kwargs["extra"]["msg_reg"] = message.mm.registry
            kwargs["extra"]["user"] = message.mm.user_pk
            # May be overwritten if consumer is passed
            kwargs["extra"]["consumer_name"] = message.mm.consumer_name
            if message.mm.state:
                kwargs["extra"]["s"] = message.mm.state
        consumer: BaseWebsocketConsumer = kwargs.pop("consumer", None)
        if consumer:
            if consumer.user:
                kwargs["extra"]["user"] = consumer.user.pk
            kwargs["extra"]["consumer_name"] = consumer.channel_name
        if consumer is None and message is None:
            raise ValueError("Must specify consumer or message")
        state = kwargs.pop("state", None)
        if state:
            kwargs["extra"]["s"] = state
        handlers = kwargs.pop("handlers", None)
        if handlers is not None:
            kwargs["extra"]["handlers"] = handlers
        return msg, kwargs


def getEventLogger(name=None) -> EventLoggerAdapter:
    return EventLoggerAdapter(logging.getLogger(name), {"user": None})
