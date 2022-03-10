from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.decorators import add_handler
from envelope.handlers.base import AsyncHandler
from envelope.core.message import AsyncRunnable


@add_handler(WS_INCOMING, WS_OUTGOING)
class AsyncRunnableHandler(AsyncHandler):
    """
    Async runnable are meant to be run inside the consumer. They must not access the database
    or do anything that might block the message flow.

    >>> class Example(AsyncRunnable):
    ...     name = 'testing.example'
    ...     executed = False
    ...
    ...     async def run(self, **kwargs):
    ...         self.executed = True
    ...

    >>> msg = Example()
    >>> handler = AsyncRunnableHandler(msg)
    >>> handler.check()
    False

    The async handler must have access to the consumer, we can simply mock that here
    >>> handler = AsyncRunnableHandler(msg, consumer=None)
    >>> handler.check()
    True

    >>> from asgiref.sync import async_to_sync
    >>> async_to_sync(handler.run)()
    >>> msg.executed
    True

    """
    name = "async_runnable"

    def check(self) -> bool:
        return isinstance(self.message, AsyncRunnable) and "consumer" in self.kwargs

    async def run(self):
        return await self.message.run(**self.kwargs)
