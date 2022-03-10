from django.utils.timezone import now

from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.decorators import add_handler
from envelope.handlers.base import AsyncHandler
from envelope.core.message import DeferredJob


@add_handler(WS_INCOMING, WS_OUTGOING)
class DeferredJobHandler(AsyncHandler):
    """
    Handles stuff that should be passed to a queue.
    These checks are usually done by the consumer.

    >>> class Example(DeferredJob):
    ...     name = 'this_job'
    ...
    ...     def run_job(self):
    ...         pass
    ...

    >>> msg = Example()
    >>> handler = DeferredJobHandler(msg)

    The handler can be cast as bool depending on if it should run or not.
    >>> bool(handler)
    True

    >>> handler.check()
    True

    >>> from asgiref.sync import async_to_sync
    >>> job = async_to_sync(handler.run)()
    >>> job is not None
    True

    >>> from django_rq import get_queue
    >>> queue = get_queue()

    Check that it exists and remove
    >>> queue.remove(job.id)
    1
    """

    name = "deferred_job"

    def check(self) -> bool:
        return isinstance(self.message, DeferredJob)

    async def run(self):
        await self.message.pre_queue(**self.kwargs)
        if self.message.should_run:
            consumer = self.kwargs.get("consumer", None)
            if consumer and hasattr(consumer, "last_job"):
                consumer.last_job = now()
            return self.message.enqueue()
