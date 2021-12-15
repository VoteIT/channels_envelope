from django.utils.timezone import now
from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.decorators import add_handler
from envelope.handlers.base import AsyncHandler
from envelope.messages.base import DeferredJob


@add_handler(WS_INCOMING, WS_OUTGOING)
class DeferredJobHandler(AsyncHandler):
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
