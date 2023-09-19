from abc import ABC
from abc import abstractmethod

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


class BatchMessage(Message, ABC):
    allow_batch = False

    @classmethod
    @abstractmethod
    def start(cls, msg: Message):
        ...

    @abstractmethod
    def append(self, msg: Message):
        ...


@add_message(WS_OUTGOING)
class Batch(BatchMessage):
    name = "s.batch"
    schema = BatchSchema
    data: BatchSchema

    @classmethod
    def start(cls, msg: Message):
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
        # Transform to batch, keep mm, state etc
        return Batch(mm=msg.mm, data={"t": msg.name, "payloads": payloads})

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


class Batch2Schema(BaseModel):
    t: str
    common: dict | None
    keys: list = []  # Field(default_factory=list)
    values: list = []


@add_message(WS_OUTGOING)
class Batch2(BatchMessage):
    name = "s.batch2"
    schema = Batch2Schema
    data: Batch2Schema

    @classmethod
    def start(cls, msg: Message, common: dict | None = None):
        """
        >>> from envelope.tests.helpers import WebsocketHello
        >>> hello = WebsocketHello()
        >>> batch = Batch2.start(hello)
        >>> batch.data
        Batch2Schema(t='testing.hello', common=None, keys=[], values=[None])

        >>> progress = ProgressNum(curr=1, total=2)
        >>> batch = Batch2.start(progress)
        >>> batch.data
        Batch2Schema(t='progress.num', common=None, keys=['curr', 'total', 'msg'], values=[[1, 2, None]])

        """
        if msg.data:
            data = msg.data.dict()
            return Batch2(
                mm=msg.mm,
                data={
                    "t": msg.name,
                    "keys": list(data.keys()),
                    "values": [list(data.values())],
                    "common": common,
                },
            )
        return Batch2(
            mm=msg.mm, data={"t": msg.name, "values": [None], "common": common}
        )

    def append(self, msg: Message):
        """
        >>> from envelope.tests.helpers import WebsocketHello
        >>> hello = WebsocketHello()
        >>> batch = Batch2.start(hello)
        >>> batch.append(hello)
        >>> batch.data
        Batch2Schema(t='testing.hello', common=None, keys=[], values=[None, None])

        >>> progress = ProgressNum(curr=1, total=2)
        >>> batch = Batch2.start(progress)
        >>> batch.append(progress)
        >>> batch.data
        Batch2Schema(t='progress.num', common=None, keys=['curr', 'total', 'msg'], values=[[1, 2, None], [1, 2, None]])
        """
        if self.data.t != msg.name:
            raise TypeError(
                f"All batch messages must be of the same type. Expected: {self.data.t} Was: {msg.name}"
            )
        if msg.data is None:
            self.data.values.append(None)
        else:
            data = msg.data.dict()
            v = []
            for k in self.data.keys:
                v.append(data.pop(k))
            if data:
                raise ValueError(
                    f"batch2 messages appended can't have extra keys. Offending keys: {', '.join(data.keys())}"
                )
            self.data.values.append(v)
