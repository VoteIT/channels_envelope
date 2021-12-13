from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.decorators import add_handler
from envelope.handlers.base import AsyncHandler
from envelope.messages.base import AsyncRunnable


@add_handler(WS_INCOMING, WS_OUTGOING)
class AsyncRunnableHandler(AsyncHandler):
    name = "async_runnable"

    def check(self) -> bool:
        return isinstance(self.message, AsyncRunnable) and "consumer" in self.kwargs

    async def run(self):
        return await self.message.run(**self.kwargs)
