from typing import Optional

from django.db.models import Model
from envelope import DEFAULT_ERRORS
from envelope import Error
from envelope.decorators import add_message
from envelope.messages import ErrorMessage
from pydantic import BaseModel
from typing import List

from pydantic import validator


class ErrorSchema(BaseModel):
    msg: Optional[str]


@add_message(DEFAULT_ERRORS)
class GenericError(ErrorMessage[ErrorSchema]):
    name = Error.GENERIC
    schema = ErrorSchema


class ValidationErrorSchema(ErrorSchema):
    errors: List[dict]


@add_message(DEFAULT_ERRORS)
class ValidationErrorMsg(ErrorMessage[ValidationErrorSchema]):
    name = Error.VALIDATION
    schema = ValidationErrorSchema


class MessageTypeErrorSchema(ErrorSchema):
    type_name: str
    registry: str


@add_message(DEFAULT_ERRORS)
class MessageTypeError(ErrorMessage[MessageTypeErrorSchema]):
    name = Error.MSG_TYPE
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


@add_message(DEFAULT_ERRORS)
class NotFoundError(ErrorMessage[NotFoundSchema]):
    name = Error.NOT_FOUND
    schema = NotFoundSchema


class UnauthorizedSchema(NotFoundSchema):
    permission: str


@add_message(DEFAULT_ERRORS)
class UnauthorizedError(ErrorMessage[UnauthorizedSchema]):
    name = Error.UNAUTHORIZED
    schema = UnauthorizedSchema
