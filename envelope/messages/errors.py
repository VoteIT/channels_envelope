from collections import UserString
from typing import List
from typing import Optional

from django.db.models import Model
from pydantic import BaseModel
from pydantic import validator

from envelope import ERRORS
from envelope import Error
from envelope.core.message import ErrorMessage
from envelope.decorators import add_message


class ErrorSchema(BaseModel):
    msg: Optional[str]


@add_message(ERRORS)
class GenericError(ErrorMessage[ErrorSchema]):
    name = Error.GENERIC
    schema = ErrorSchema


class ValidationErrorSchema(ErrorSchema):
    errors: List[dict]


@add_message(ERRORS)
class ValidationErrorMsg(ErrorMessage[ValidationErrorSchema]):
    name = Error.VALIDATION
    schema = ValidationErrorSchema


class MessageTypeErrorSchema(ErrorSchema):
    type_name: str
    registry: str


@add_message(ERRORS)
class MessageTypeError(ErrorMessage[MessageTypeErrorSchema]):
    name = Error.MSG_TYPE
    schema = MessageTypeErrorSchema


@add_message(ERRORS)
class BadRequestError(GenericError):
    """
    Pretty much HTTP 400
    """

    name = Error.BAD_REQUEST


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


@add_message(ERRORS)
class NotFoundError(ErrorMessage[NotFoundSchema]):
    name = Error.NOT_FOUND
    schema = NotFoundSchema


class UnauthorizedSchema(NotFoundSchema):
    permission: Optional[str]

    @validator("permission", pre=True)
    def adjust_user_str(cls, v):
        """
        Make sure user strings work too

        >>> from collections import UserString
        >>> class MyString(UserString):
        ...     ...
        ...
        >>> mine = MyString("bla")
        >>> mine.__class__.__name__
        'MyString'

        >>> new_str = UnauthorizedSchema.adjust_user_str(mine)
        >>> new_str.__class__.__name__
        'str'
        """
        if isinstance(v, UserString):
            return str(v)
        return v


@add_message(ERRORS)
class UnauthorizedError(ErrorMessage[UnauthorizedSchema]):
    name = Error.UNAUTHORIZED
    schema = UnauthorizedSchema


class SubscribeSchema(BaseModel):
    channel_name: str


@add_message(ERRORS)
class SubscribeError(ErrorMessage[SubscribeSchema]):
    name = Error.SUBSCRIBE
    schema = SubscribeSchema


@add_message(ERRORS)
class JobError(GenericError):
    """
    A background task caused an exception/error. This is not meant for error checking, but merely to notify
    frontend that there's no use waiting for this.
    """

    name = Error.JOB
