from typing import Optional
from typing import Union

from envelope.core.message import Message
from pydantic import BaseModel
from envelope import WS_OUTGOING
from envelope.decorators import add_message


class ProgressSchema(BaseModel):
    curr: int
    total: int
    msg: Optional[str]


@add_message(WS_OUTGOING)
class ProgressNum(Message):
    name = "progress.num"
    schema = ProgressSchema
    data: ProgressSchema


@add_message(WS_OUTGOING)
class Status(Message):
    name = "s.stat"


class BatchSchema(BaseModel):
    t: str
    payloads: list[Union[dict, None]]


@add_message(WS_OUTGOING)
class Batch(Message):
    name = "s.batch"
    schema = BatchSchema
    data: BatchSchema

    @classmethod
    def start(self, msg: Message):
        if msg.data is None:
            payloads = [None]
        else:
            payloads = [msg.data]
        return Batch.from_message(msg, data={"t": msg.name, "payloads": payloads})

    def append(self, msg: Message):
        if self.data.t != msg.name:
            raise TypeError(
                f"All batch messages must be of the same type. Expected: {self.data.t} Was: {msg.name}"
            )
        if msg.data is None:
            self.data.payloads.append(None)
        else:
            self.data.payloads.append(msg.data)
