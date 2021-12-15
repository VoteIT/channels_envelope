from typing import Optional

from envelope.messages import Message
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
