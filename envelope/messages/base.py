from __future__ import annotations

from abc import ABC
from abc import abstractmethod
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

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


__all__ = []


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


S = TypeVar("S")


class MessageStates:
    """
    Message state constants
    """

    ACKNOWLEDGED = "a"
    QUEUED = "q"
    RUNNING = "r"
    SUCCESS = "s"
    FAILED = "f"
    MESSAGE_STATES = {ACKNOWLEDGED, QUEUED, RUNNING, SUCCESS, FAILED}


class Message(MessageStates, Generic[S], ABC):
    mm: MessageMeta
    data: S
    schema: Type[S] = NoPayload
    initial_data: dict

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
        # _registry = None
        # if _registry is None:
        #     assert (
        #         _registry in cls.registries()
        #     ), "Specified registry not valid for this message type"
        #     mm.registry = _registry
        return cls(mm=mm, **kwargs)

    @property
    def data(self):
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


class AsyncRunnable(Message, ABC):
    """
    This message is meant to be processed within the consumer.
    It mustn't be blocking or run database queries.
    Anything locking up the consumer will cause it to stop processing messages for that user.
    """

    @abstractmethod
    async def run(self, consumer):
        pass


class ErrorMessage(Message, Generic[S], Exception, ABC):
    ...


# class DeferredJob(Message, ABC):
#     """
#     Command/query can be deferred to a job queue.
#     Must be used together with BaseIncomingMessage or BaseOutgoingMessage"""
#
#     # queue_name = DEFAULT_QUEUE
#     # job_timeout = 7
#     # autocommit = True
#     # is_async = True
#     job_func = "voteit.messaging.jobs.handle_job_message"
#     job_atomic: bool = True
#     on_worker: bool = False
#     # Markers for type checking
#     mm: MessageMeta
#     data: BaseModel  # But really the schema
#     should_run: bool = True  # Mark as false to abort run
#
#     async def pre_queue(self, consumer):
#         """
#         Do something before entering the queue. Only applies to when the consumer receives the message.
#         It's a good idea to avoid using this if it's not needed.
#         """
#
#     def queue(self):
#         # FIXME: Queues and django_rq are kind of a mess right now
#         from voteit.messaging.jobs import run_job
#
#         if not self.should_run:
#             return
#         print("HELLO FROM ENQUEUE")
#         # kwargs = dict(
#         #     msg_data=self.data.dict(),  # FIXME: Json encode instead?
#         #     mm_data=self.mm.dict(),
#         #     incoming=isinstance(self, BaseIncomingMessage),
#         #     atomic=self.job_atomic,
#         # )
#         # if queue:
#         #     return queue.enqueue(run_job, **kwargs)
#         # # Job-decorated queue
#         # return run_job.delay(**kwargs)
#
#         # kwargs = dict(
#         #     atomic=self.job_atomic,
#         #      msg_data=self.data.dict(),
#         #      mm_data=self.mm.dict(),
#         # )
#         # queue = get_queue(name=self.queue, is_async=self.is_async, serializer=JSONSerializer)
#         # queue.enqueue("voteit.messaging.jobs.run_job", timeout=self.job_timeout, kwargs=kwargs)
#
#         # queue = get_queue(
#         #     self.queue,
#         #     autocommit=self.autocommit,
#         #     #default_timeout=self.job_timeout,
#         #     is_async=self.is_async,
#         #     serializer=JSONSerializer,
#         # )
#         # queue.enqueue(
#         #     "voteit.messaging.jobs.run_job",
#         #     job_timeout=self.job_timeout,
#         #
#         #     atomic=self.job_atomic,
#         #     msg_data=self.data.dict(),
#         #     mm_data=self.mm.dict(),
#         # )
#
#     @classmethod
#     def from_job(
#         cls, msg_data, mm_data, incoming=True
#     ) -> Union[DeferredJob, MessageABC]:
#         if incoming:
#             registry = get_incoming_registry()
#         else:
#             registry = get_outgoing_registry()
#         mm = MessageMeta(**mm_data)
#         # Key error here would be a programming error, not a validation error
#         msg_cls = registry[mm.type]
#         instance = msg_cls(mm, msg_data)
#         instance.on_worker = True
#         return instance
#
#     @abstractmethod
#     def run_job(self):
#         """Run this within the worker to do the actual job"""
#         pass
