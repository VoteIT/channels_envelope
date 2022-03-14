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

from django.contrib.auth import get_user_model
from django.utils.functional import cached_property
from django.utils.timezone import now
from django_rq import get_queue
from pydantic import BaseModel
from rq import Queue

from envelope import Error
from envelope import MessageStates
from envelope.core.schemas import MessageMeta
from envelope.core.schemas import NoPayload
from envelope.models import Connection
from envelope.queues import DEFAULT_QUEUE_NAME
from envelope.utils import get_envelope_registry
from envelope.utils import get_error_type

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from envelope.core.envelope import Envelope


S = TypeVar("S")  # schema
M = TypeVar("M")  # model


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
        *,
        mm: Union[dict, MessageMeta] = None,
        data: Optional[dict] = None,
        _orm: Optional[Any] = None,
        _registry: Optional[str] = None,
        **kwargs,
    ):
        if mm is None:
            mm = {}
        if isinstance(mm, MessageMeta):
            self.mm = mm
        else:
            assert isinstance(self.name, str), "Name attribute is not set as a string"
            self.mm = MessageMeta(**mm)
        if _registry is not None:
            assert (
                _registry in self.registries()
            ), "Specified registry not valid for this message type"
            self.mm.registry = _registry
        if self.mm.registry is None and len(self.registries()) == 1:
            for rname in self.registries():
                # If there's only one registry, it's quite unproblematic to attach it here
                self.mm.registry = rname
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

    @cached_property
    def envelope(self) -> Type[Envelope]:
        assert self.mm.registry, f"Message {self} has no registry name"
        reg = get_envelope_registry()
        if self.mm.registry not in reg:
            raise KeyError(f"No registry called {self.mm.registry}")
        return reg[self.mm.registry]


class ErrorMessage(Message, Generic[S], Exception, ABC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.validate()  # Any validation error on errors should be handled straight away
        self.initial_data = None  # We don't care...


class AsyncRunnable(Message, ABC):
    """
    This message is meant to be processed within the consumer.
    It mustn't be blocking or run database queries.
    Anything locking up the consumer will cause it to stop processing messages for that user.
    """

    @abstractmethod
    async def run(self, consumer=None, **kwargs):
        pass


class DeferredJob(Message, ABC):
    """
    Command/query can be deferred to a job queue
    """

    # Related to RQ
    ttl = 20
    job_timeout = 20
    queue: str = DEFAULT_QUEUE_NAME  # Queue name

    atomic: bool = True
    on_worker: bool = False
    # Markers for type checking
    mm: MessageMeta
    data: BaseModel  # But really the schema
    should_run: bool = True  # Mark as false to abort run

    def __init__(self, queue: Union[str, Queue] = None, **kwargs):
        if queue is not None:
            if isinstance(queue, str):
                self.queue = queue
            elif isinstance(queue, Queue):
                # note, for testing injection!
                self.rq_queue = queue
            else:
                raise TypeError(f"{queue} is not a str or an instance of rq.Queue")
        super().__init__(**kwargs)

    @cached_property
    def rq_queue(self) -> Queue:
        return get_queue(self.queue)

    async def pre_queue(self, **kwargs):
        """
        Do something before entering the queue. Only applies to when the consumer receives the message.
        It's a good idea to avoid using this if it's not needed.
        """

    @property
    def job(self):
        from envelope.jobs import default_incoming_websocket

        return default_incoming_websocket

    def enqueue(self, **kwargs):
        from envelope.jobs import handle_failure

        data = {}
        if self.data:
            data = self.data.dict()
        kwargs.setdefault("on_failure", handle_failure)
        return self.rq_queue.enqueue(
            self.job,
            t=self.name,
            mm=self.mm.dict(),
            data=data,
            enqueued_at=now(),
            job_timeout=self.job_timeout,
            ttl=self.ttl,
            **kwargs,
        )

    @abstractmethod
    def run_job(self):
        """
        Run this within the worker to do the actual job
        """
        pass


class ContextAction(DeferredJob, Generic[S, M], ABC):
    """
    An action performed on a specific context.
    It has a permission and a model. The schema itself must contain an attribute that will be
    used for lookup of the context to perform the action on. (context_schema_attr)
    You can specify which keyword to use when searching by setting context_query_kw.

    Note that it only works as a placeholder for an action, the code itself should be constructed by
    combining it with DeferredJob and must also inherit BaseIncomingMessage or BaseOutgoingMessage
    """

    context_schema_attr = "pk"  # Fetch context from this identifier
    context_query_kw = "pk"  # And use this search keyword

    @property
    @abstractmethod
    def permission(self) -> Optional[str]:
        """
        Text permission, None means allow any.
        """

    @property
    @abstractmethod
    def model(self) -> Type[M]:
        """
        Model class this operates on.
        Must (normally) be something connected to the database
        """

    def allowed(self) -> bool:
        if self.user is None:
            return False
        if self.context is None:
            return False
        if self.permission is None:
            return True
        return self.user.has_perm(self.permission, self.context)

    @cached_property
    def context(self) -> M:
        try:
            value = getattr(self.data, self.context_schema_attr)
        except AttributeError:
            raise AttributeError(
                f"{self.context_schema_attr} is not a valid schema attribute for lookup. Message: {self}"
            )
        try:
            return self.model.objects.get(**{self.context_query_kw: value})
        except self.model.DoesNotExist:
            raise get_error_type(Error.NOT_FOUND).from_message(
                self, model=self.model, key=self.context_query_kw, value=value
            )

    def assert_perm(self):
        if not self.allowed():
            raise get_error_type(Error.UNAUTHORIZED).from_message(
                self,
                model=self.model,
                key=self.context_query_kw,
                value=getattr(self.data, self.context_schema_attr),
                permission=self.permission,
            )
