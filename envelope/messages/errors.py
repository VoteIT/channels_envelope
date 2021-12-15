from typing import Optional

from django.db.models import Model
from envelope import WS_ERRORS
from envelope.decorators import add_message
from envelope.messages import ErrorMessage
from pydantic import BaseModel
from typing import List

from pydantic import validator


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


class NotFoundSchema(BaseModel):
    model: str
    key: str = "pk"
    value: str

    @validator("model", pre=True)
    def fetch_natural_key(cls, v):
        if isinstance(v, str):
            return v
        elif isinstance(v, Model):
            v = v.__class__
        if issubclass(v, Model):
            return f"{v._meta.app_label}.{v._meta.model_name.lower()}"
        raise ValueError(
            "Needs to be a string or instance/class based on djangos Model"
        )


@add_message(WS_ERRORS)
class NotFoundError(ErrorMessage[NotFoundSchema]):
    name = "error.not_found"
    schema = NotFoundSchema


class UnauthorizedSchema(NotFoundSchema):
    permission: str


@add_message(WS_ERRORS)
class UnauthorizedError(ErrorMessage[UnauthorizedSchema]):
    name = "error.unauthorized"
    schema = UnauthorizedSchema
