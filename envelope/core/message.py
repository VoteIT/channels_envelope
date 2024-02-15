from __future__ import annotations
from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.utils.functional import cached_property
from pydantic import BaseModel

from envelope import MessageStates
from envelope.schemas import MessageMeta
from envelope.schemas import NoPayload

if TYPE_CHECKING:
    from envelope.consumers.websocket import WebsocketConsumer

__all__ = (
    "Message",
    "ErrorMessage",
    "AsyncRunnable",
)


class Message(MessageStates, ABC):
    mm: MessageMeta
    schema: type[BaseModel] = NoPayload
    data: BaseModel | None
    allow_batch: bool = True

    @property
    @abstractmethod
    def name(self) -> str:
        """
        The ID/name of the message type. This corresponds to 't' on incoming messages.
        """

    def __init__(
        self,
        *,
        mm: dict | MessageMeta = None,
        data: dict | None = None,
        **kwargs,
    ):
        if mm is None:
            mm = {}
        if isinstance(mm, MessageMeta):
            self.mm = mm
        else:
            self.mm = MessageMeta(**mm)
        if self.schema is NoPayload:
            self.data = None
        else:
            if data is None:
                data = {}
            data.update(kwargs)
            self.data = self.schema(**data)

    @classmethod
    def from_message(
        cls, message: Message, state: str | None = None, **kwargs
    ) -> Message:
        mm = MessageMeta(state=state, **message.mm.dict(exclude={"registry", "state"}))
        return cls(mm=mm, **kwargs)

    @cached_property
    def user(self) -> None | AbstractUser:
        """
        Retrieve user from MessageMeta.user_pk, if it exists
        """
        if self.mm.user_pk:
            User: AbstractUser = get_user_model()
            return User.objects.filter(pk=self.mm.user_pk).first()

    def __str__(self):
        return repr(self.data)


class ErrorMessage(Message, Exception, ABC):
    def __repr__(self):
        return f"{self.__class__.__name__}{self}"

    def __str__(self):
        return "\n" + "\n".join(
            f"{k}:\n    {v}" for k, v in self.data.dict(exclude_unset=True).items()
        )


class AsyncRunnable(Message, ABC):
    """
    This message is meant to be processed within the consumer.
    It mustn't be blocking or run database queries.
    Anything locking up the consumer will cause it to stop processing messages for that user.
    """

    @abstractmethod
    async def run(self, *, consumer: WebsocketConsumer, **kwargs):
        pass
