from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Any
from typing import Generic
from typing import Optional
from typing import Set
from typing import TYPE_CHECKING
from typing import Type
from typing import TypeVar
from typing import Union

from pydantic import BaseModel
from django.contrib.auth import get_user_model
from django.utils.functional import cached_property

from envelope import MessageStates
from envelope.models import Connection

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


# __all__ = []


class MessageMeta(BaseModel):
    """
    Information about the nature of the message itself.
    It's never sent to the user but used

    id
        A made-up id for this message. The frontend decides the id.

    user_pk
        The user this message originated from.

    consumer_name:
        The consumers name (id) this message passed. Any reply to the author (for instance an error message)
        should be directed here.

    registry:
        Which registry this was created from.
    """

    id: Optional[str]
    user_pk: Optional[int]
    consumer_name: Optional[str]
    language: Optional[str] = None
    state: Optional[str]
    registry: Optional[str]

    def envelope_data(self) -> dict:
        data = dict(i=self.id, l=self.language)
        if self.state:
            data["s"] = self.state
        return data


class NoPayload(BaseModel):
    pass


S = TypeVar("S")  # schema


class Message(MessageStates, Generic[S], ABC):
    mm: MessageMeta
    schema: Type[S] = NoPayload
    initial_data: Optional[dict]

    def __init_subclass__(cls, **kwargs):
        cls.__registries = set()
        super().__init_subclass__(**kwargs)

    @classmethod
    def registries(cls) -> Set:
        return cls.__registries

    @property
    @abstractmethod
    def name(self) -> str:
        """
        The ID/name of the message type. This corresponds to 't' on incoming messages.
        """

    def __init__(
        self,
        mm: Union[dict, MessageMeta] = None,
        data: Optional[dict] = None,
        _registry: Optional[str] = None,
        _orm: Optional[Any] = None,
        **kwargs,
    ):
        if mm is None:
            mm = {}
        if isinstance(mm, MessageMeta):
            self.mm = mm
        else:
            assert isinstance(self.name, str), "Name attribute is not set as a string"
            mm["type_name"] = self.name
            self.mm = MessageMeta(**mm)
        if _registry is not None:
            assert (
                _registry in self.registries()
            ), "Specified registry not valid for this message type"
            self.mm.registry = _registry
        if _orm is not None:
            assert data is None, "Can only specify data or _orm"
            assert not kwargs, "kwargs and _orm isn't supported together"
            self.initial_data = _orm
            self._data = self.schema.from_orm(_orm)
            self._validated = True
        else:
            if data is None:
                data = {}
            data.update(kwargs)
            self.initial_data = data
            self._data = None
            self._validated = False
        if self.schema is NoPayload:
            self.validate()

    @classmethod
    def from_message(cls, message: Message, **kwargs) -> Message:
        mm = MessageMeta(**message.mm.dict(exclude={"registry"}))
        return cls(mm=mm, **kwargs)

    @property
    def data(self) -> S:
        if self.is_validated:
            return self._data
        raise ValueError("data accessed before validation")

    @property
    def is_validated(self) -> bool:
        return self._validated

    def validate(self):
        if not self.is_validated:
            if self.schema is NoPayload:
                self._data = None
            else:
                self._data = self.schema(**self.initial_data)
            self._validated = True

    @cached_property
    def user(self) -> Optional[AbstractUser]:
        """
        Retrieve user from MessageMeta.user_pk, if it exists
        """
        if self.mm.user_pk:
            User: AbstractUser = get_user_model()
            return User.objects.filter(pk=self.mm.user_pk).first()
        return None

    @cached_property
    def connection(self) -> Optional[Connection]:
        """
        Fetch Connection based on consumer name. Consumer names shouldn't be reused.
        """
        if self.mm.consumer_name:
            return Connection.objects.filter(channel_name=self.mm.consumer_name).first()


class ErrorMessage(Message, Generic[S], Exception, ABC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.validate()  # Any validation error on errors should be handled straight away
        self.initial_data = None  # We don't care...
