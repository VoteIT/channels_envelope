from __future__ import annotations

from time import sleep
from typing import Optional
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.dispatch import receiver
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel
from pydantic import validator

from envelope import WS_INCOMING
from envelope import WS_OUTGOING
from envelope.core.message import DeferredJob
from envelope.core.message import Message
from envelope.decorators import add_message
from envelope.messages.common import ProgressNum
from envelope.signals import client_connect
from envelope.utils import websocket_send

if TYPE_CHECKING:
    from envelope.consumers.websocket import EnvelopeWebsocketConsumer

if not settings.DEBUG:
    raise ImproperlyConfigured(
        "%s should never be imported unless DEBUG mode is on." % __name__
    )


@receiver(client_connect)
def say_hello_at_connect(user, consumer_name, **kw):
    print("Active language in automatic greeting: ", translation.get_language())
    greeting = _("Hello %(username)s!") % {"username": user.username}
    msg = Pleasantry(greeting=greeting)
    websocket_send(msg, consumer_name, on_commit=False)


class PleasantrySchema(BaseModel):
    greeting: str


@add_message(WS_OUTGOING)
class Pleasantry(Message[PleasantrySchema]):
    name = "testing.hello"
    schema = PleasantrySchema


class CountSchema(BaseModel):
    num: int = 10
    fail: Optional[int]

    @validator("num")
    def check_num(cls, v):
        if v > 10:
            raise ValueError(f"{v} is higher than 10")
        if v < 1:
            raise ValueError(f"{v} must be at least 1")
        return v


@add_message(WS_INCOMING)
class Count(DeferredJob):
    name = "testing.count"
    schema = CountSchema

    async def pre_queue(self, consumer: EnvelopeWebsocketConsumer):
        msg = ProgressNum.from_message(
            self,
            curr=0,
            total=self.data.num,
            msg=f"We're about to count to {self.data.num}.",
        )
        await consumer.send_ws_message(msg, state=self.QUEUED)

    def run_job(self):
        num = self.data.num
        fail = self.data.fail
        text = f"Let's count to {num}!"
        if self.data.fail:
            text += f" ...But fail at {fail}"
        msg = ProgressNum.from_message(self, curr=0, total=num, msg=text)
        websocket_send(msg, self.mm.consumer_name, state=self.RUNNING, on_commit=False)
        sleep(1)
        for i in range(1, num):
            if fail and fail == i:
                msg = ProgressNum.from_message(
                    self, curr=i, total=num, msg=f"Deliberate fail at {fail}"
                )
                websocket_send(
                    msg, self.mm.consumer_name, state=self.RUNNING, on_commit=False
                )
                return
            else:
                msg = ProgressNum.from_message(self, curr=i, total=num)
                websocket_send(
                    msg, self.mm.consumer_name, state=self.RUNNING, on_commit=False
                )
            sleep(1)
        msg = ProgressNum.from_message(self, curr=num, total=num, msg="All done!")
        websocket_send(msg, self.mm.consumer_name, state=self.SUCCESS, on_commit=False)
