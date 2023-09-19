from pydantic import BaseModel

from envelope import ERRORS
from envelope import Error
from envelope.messages.errors import GenericError
from envelope.core.message import ErrorMessage
from envelope.decorators import add_message


class SubscribeErrorSchema(BaseModel):
    channel_name: str


@add_message(ERRORS)
class SubscribeError(ErrorMessage):
    name = Error.SUBSCRIBE
    schema = SubscribeErrorSchema
    data: SubscribeErrorSchema


@add_message(ERRORS)
class JobError(GenericError):
    """
    A background task caused an exception/error. This is not meant for error checking, but merely to notify
    frontend that there's no use waiting for this.
    """

    name = Error.JOB
