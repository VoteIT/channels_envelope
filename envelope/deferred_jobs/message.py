from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import activate
from django_rq import get_queue
from pydantic import BaseModel
from rq import Queue

from envelope import DEFAULT_QUEUE_NAME
from envelope import Error
from envelope.core.message import ErrorMessage
from envelope.core.message import Message
from envelope.utils import get_error_type
from envelope.utils import update_connection_status
from envelope.utils import websocket_send_error

if TYPE_CHECKING:
    from envelope.consumers.websocket import WebsocketConsumer
    from django.db.models import Model
    from rq.job import Job

_marker = object()


class DeferredJob(Message, ABC):
    """
    Command/query can be deferred to a job queue
    """

    # Related to RQ - these values override queue default and sets a message default
    ttl: int | None = None  # Queue timeout in seconds
    result_ttl: int | None = None  # Keep result,in seconds
    job_timeout: int | None = None  # Job exec timeout in seconds
    failure_ttl: int | None = None  # Keep result, in seconds
    queue: str = DEFAULT_QUEUE_NAME  # Queue name
    # Envelope/Django things
    atomic: bool = True
    on_worker: bool = False
    should_run: bool = True  # Mark as false to abort run

    async def pre_queue(self, *, consumer: WebsocketConsumer, **kwargs):
        """
        Do something before entering the queue. Only applies to when the consumer receives the message.
        It's a good idea to avoid using this if it's not needed.
        """

    @staticmethod
    def handle_failure(job, connection, exc_type, exc_value, traceback):
        """
        Failure callbacks are functions that accept job, connection, type, value and traceback arguments.
        type, value and traceback values returned by sys.exc_info(),
        which is the exception raised when executing your job.

        See RQs docs
        """
        mm = job.kwargs.get("mm", {})
        if mm:
            if consumer_name := mm.get("consumer_name", None):
                # FIXME: exc value might not be safe here
                err = get_error_type(Error.JOB)(mm=mm, msg=str(exc_value))
                websocket_send_error(err, channel_name=consumer_name)
                return err  # For testing, has no effect

    @classmethod
    def init_job(
        cls,
        data: dict,
        mm: dict,
        t: str,
        *,
        enqueued_at: datetime = None,
        update_conn: bool = True,
        **kwargs,
    ):
        message = cls(mm=mm, data=data)
        message.on_worker = True
        if message.mm.language:
            # Otherwise skip lang?
            activate(message.mm.language)
        result = None
        try:
            if message.atomic:
                with transaction.atomic(durable=True):
                    result = message.run_job()
            else:
                result = message.run_job()
        except ErrorMessage as err:  # Catchable, nice errors
            if err.mm.id is None:
                err.mm.id = message.mm.id
            if err.mm.consumer_name is None:
                err.mm.consumer_name = message.mm.consumer_name
            if err.mm.consumer_name:
                websocket_send_error(err)
        else:
            # Everything went fine
            if update_conn and message.mm.user_pk and message.mm.consumer_name:
                update_connection_status(
                    user_pk=message.mm.user_pk,
                    channel_name=message.mm.consumer_name,
                    last_action=enqueued_at,
                )
        return result

    def enqueue(self, queue: Queue | None = None, **kwargs):
        if queue is None:
            queue = get_queue(name=self.queue)
        assert isinstance(queue, Queue)
        data = {}
        if self.data:
            data = self.data.dict()
        kwargs.setdefault("on_failure", self.handle_failure)
        for attr_name in ("job_timeout", "ttl", "result_ttl", "failure_ttl"):
            if attr_name in kwargs:
                continue
            attr_v = getattr(self, attr_name, _marker)
            if attr_v != _marker:
                kwargs[attr_name] = attr_v
        if self.mm.env is None:
            raise ValueError(
                "To call enqueue on DeferredJob messages, env must be present in message meta."
            )
        qualname = ".".join(
            [self.__class__.__module__, self.__class__.__name__, "init_job"]
        )
        return queue.enqueue(
            qualname,
            t=self.name,
            mm=self.mm.dict(),
            data=data,
            enqueued_at=now(),
            **kwargs,
        )

    async def post_queue(self, *, job: Job, consumer: WebsocketConsumer, **kwargs):
        """
        Do something after entering the queue. Only called if the message was actually added to the queue.
        """

    @abstractmethod
    def run_job(self):
        """
        Run this within the worker to do the actual job.
        Note: Anything returned here will be stored by RQ, depending on the result_ttl setting
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
