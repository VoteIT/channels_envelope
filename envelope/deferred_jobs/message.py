from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING

from django.utils.functional import cached_property
from django.utils.timezone import now
from django_rq import get_queue
from pydantic import BaseModel
from rq import Queue

from envelope import DEFAULT_QUEUE_NAME
from envelope import Error
from envelope.core.message import Message
from envelope.utils import get_error_type

if TYPE_CHECKING:
    from django.db.models import Model


class DeferredJob(Message, ABC):
    """
    Command/query can be deferred to a job queue
    """

    # Related to RQ
    ttl: int | None = None  # Queue timeout in seconds if you want to override default
    job_timeout: int | None = (
        None  # Job exec timeout in seconds if you want to override default
    )
    queue: str = DEFAULT_QUEUE_NAME  # Queue name
    # connection: None | Redis = None
    atomic: bool = True
    on_worker: bool = False
    job: callable | str = "envelope.deferred_jobs.jobs.default_incoming_websocket"
    should_run: bool = True  # Mark as false to abort run

    async def pre_queue(self, **kwargs):
        """
        Do something before entering the queue. Only applies to when the consumer receives the message.
        It's a good idea to avoid using this if it's not needed.
        """

    @property
    def on_failure(self) -> callable | None:
        from envelope.deferred_jobs.jobs import handle_failure

        return handle_failure

    def enqueue(self, queue: Queue | None = None, **kwargs):
        if queue is None:
            queue = get_queue(name=self.queue)
        assert isinstance(queue, Queue)
        data = {}
        if self.data:
            data = self.data.dict()
        kwargs.setdefault("on_failure", self.on_failure)
        if self.job_timeout:
            kwargs["job_timeout"] = self.job_timeout
        if self.ttl:
            kwargs["ttl"] = self.ttl
        return queue.enqueue(
            self.job,
            t=self.name,
            mm=self.mm.dict(),
            data=data,
            enqueued_at=now(),
            **kwargs,
        )

    @abstractmethod
    def run_job(self):
        """
        Run this within the worker to do the actual job
        """
        pass


class ContextActionSchema(BaseModel):
    pk: int


class ContextAction(DeferredJob, ABC):
    """
    An action performed on a specific context.
    It has a permission and a model. The schema itself must contain an attribute that will be
    used for lookup of the context to perform the action on. (context_schema_attr)
    You can specify which keyword to use when searching by setting context_query_kw.

    Note that it only works as a placeholder for an action, the code itself should be constructed by
    combining it with DeferredJob and must also inherit BaseIncomingMessage or BaseOutgoingMessage
    """

    schema = ContextActionSchema  # Most basic required
    context_schema_attr = "pk"  # Fetch context from this identifier
    context_query_kw = "pk"  # And use this search keyword

    @property
    @abstractmethod
    def permission(self) -> str | None:
        """
        Text permission, None means allow any.
        """

    @property
    @abstractmethod
    def model(self) -> type[Model]:
        """
        Model class this operates on.
        Must (normally) be something connected to the database
        """

    def allowed(self) -> bool:
        if self.user is None:
            return False
        if self.user.is_anonymous:
            return False
        if self.context is None:
            return False
        if self.permission is None:
            return True
        return self.user.has_perm(self.permission, self.context)

    @cached_property
    def context(self):
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
