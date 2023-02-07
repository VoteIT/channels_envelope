from __future__ import annotations
import logging
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from envelope.consumer.websocket import WebsocketConsumer
    from envelope.core import Message


class EventLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        super().process(msg, kwargs)
        message: Message = kwargs.pop("message", None)
        if message:
            kwargs["extra"]["i"] = message.mm.id
            kwargs["extra"]["t"] = message.name
            kwargs["extra"]["reg"] = message.mm.registry
            kwargs["extra"]["user"] = message.mm.user_pk
            # May be overwritten if consumer is passed
            kwargs["extra"]["consumer_name"] = message.mm.consumer_name
            if message.mm.state:
                kwargs["extra"]["s"] = message.mm.state
        consumer: WebsocketConsumer = kwargs.pop("consumer", None)
        if consumer:
            if consumer.user:
                kwargs["extra"]["user"] = consumer.user.pk
            kwargs["extra"]["consumer_name"] = consumer.channel_name
        if consumer is None and message is None:  # pragma: no cover
            raise ValueError("Must specify consumer or message")
        return msg, kwargs


def getEventLogger(name=None) -> EventLoggerAdapter:
    return EventLoggerAdapter(logging.getLogger(name), {"user": None})
