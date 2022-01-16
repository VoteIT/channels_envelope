from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Generic
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type
from typing import TypeVar

from django.utils.functional import cached_property
from django.utils.timezone import now
from envelope import Error
from envelope.messages import Message
from envelope.messages import MessageMeta
from envelope.utils import get_error_type
from pydantic import BaseModel

if TYPE_CHECKING:
    pass


S = TypeVar("S")  # schema
M = TypeVar("M")  # model


class AsyncRunnable(Message, ABC):
    """
    This message is meant to be processed within the consumer.
    It mustn't be blocking or run database queries.
    Anything locking up the consumer will cause it to stop processing messages for that user.
    """

    @abstractmethod
    async def run(self, consumer):
        pass


class DeferredJob(Message, ABC):
    """
    Command/query can be deferred to a job queue
    """

    # job_timeout = 7
    # autocommit = True
    # is_async = True
    atomic: bool = True
    on_worker: bool = False
    # Markers for type checking
    mm: MessageMeta
    data: BaseModel  # But really the schema
    should_run: bool = True  # Mark as false to abort run

    async def pre_queue(self, consumer):
        """
        Do something before entering the queue. Only applies to when the consumer receives the message.
        It's a good idea to avoid using this if it's not needed.
        """

    @property
    def job(self):
        from envelope.jobs import default_incoming_websocket

        return default_incoming_websocket

    def enqueue(self):
        return self.job.delay(
            t=self.name, mm=self.mm.dict(), data=self.data.dict(), enqueued_at=now()
        )

    @abstractmethod
    def run_job(self):
        """Run this within the worker to do the actual job"""
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
