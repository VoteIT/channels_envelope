from pydantic import BaseModel

from envelope import WS_OUTGOING
from envelope.core.message import Message
from envelope.decorators import add_message


class ProgressSchema(BaseModel):
    curr: int
    total: int
    msg: str | None


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
    payloads: list[dict | BaseModel | None]


@add_message(WS_OUTGOING)
class Batch(Message):
    name = "s.batch"
    schema = BatchSchema
    data: BatchSchema
    allow_batch = False

    @classmethod
    def start(self, msg: Message):
        """
        >>> from envelope.tests.helpers import WebsocketHello
        >>> hello = WebsocketHello()
        >>> batch = Batch.start(hello)
        >>> batch.data
        BatchSchema(t='testing.hello', payloads=[None])

        >>> progress = ProgressNum(curr=1, total=2)
        >>> batch = Batch.start(progress)
        >>> batch.data
        BatchSchema(t='progress.num', payloads=[{'curr': 1, 'total': 2, 'msg': None}])
        """
        if msg.data is None:
            payloads = [None]
        else:
            payloads = [msg.data]
        return Batch.from_message(msg, data={"t": msg.name, "payloads": payloads})

    def append(self, msg: Message):
        """
        >>> from envelope.tests.helpers import WebsocketHello
        >>> hello = WebsocketHello()
        >>> batch = Batch.start(hello)
        >>> batch.append(hello)
        >>> batch.data
        BatchSchema(t='testing.hello', payloads=[None, None])

        >>> progress = ProgressNum(curr=1, total=2)
        >>> batch = Batch.start(progress)
        >>> batch.append(progress)
        >>> batch.data
        BatchSchema(t='progress.num', \
        payloads=[{'curr': 1, 'total': 2, 'msg': None}, ProgressSchema(curr=1, total=2, msg=None)])

        Note the mixed payloads-content - but that doesn't matter later on

        >>> batch.data.dict()
        {'t': 'progress.num', \
        'payloads': [{'curr': 1, 'total': 2, 'msg': None}, {'curr': 1, 'total': 2, 'msg': None}]}

        """
        if self.data.t != msg.name:
            raise TypeError(
                f"All batch messages must be of the same type. Expected: {self.data.t} Was: {msg.name}"
            )
        if msg.data is None:
            self.data.payloads.append(None)
        else:
            self.data.payloads.append(msg.data)
