from typing import Optional

from envelope import WS_ERRORS
from envelope.decorators import add_message
from envelope.messages.base import ErrorMessage
from pydantic import BaseModel
from typing import List


class ErrorSchema(BaseModel):
    msg: Optional[str]


@add_message(WS_ERRORS)
class GenericError(ErrorMessage[ErrorSchema]):
    name = "error.generic"
    schema = ErrorSchema


class ValidationErrorSchema(ErrorSchema):
    errors: List[dict]


@add_message(WS_ERRORS)
class ValidationErrorMsg(ErrorMessage[ValidationErrorSchema]):
    name = "error.validation"
    schema = ValidationErrorSchema


class MessageTypeErrorSchema(ErrorSchema):
    type_name: str
    registry: str


@add_message(WS_ERRORS)
class MessageTypeError(ErrorMessage[MessageTypeErrorSchema]):
    name = "error.msg_type"
    schema = MessageTypeErrorSchema

    # @property
    # def default_msg(self):
    #     return f"No message type {self.data.type_name} within registry {self.data.registry}"
