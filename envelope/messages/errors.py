from collections import UserString

from django.db.models import Model
from pydantic import BaseModel
from pydantic import validator

from envelope import ERRORS
from envelope import Error
from envelope.core.message import ErrorMessage
from envelope.decorators import add_message


class ErrorSchema(BaseModel):
    msg: str | None


class GenericError(ErrorMessage):
    name = Error.GENERIC
    schema = ErrorSchema
    data: ErrorSchema


class ValidationErrorSchema(ErrorSchema):
    errors: list[dict]


@add_message(ERRORS)
class ValidationErrorMsg(ErrorMessage):
    name = Error.VALIDATION
    schema = ValidationErrorSchema
    data: ValidationErrorSchema


class MessageTypeErrorSchema(ErrorSchema):
    type_name: str
    registry: str


@add_message(ERRORS)
class MessageTypeError(ErrorMessage):
    name = Error.MSG_TYPE
    schema = MessageTypeErrorSchema
    data: MessageTypeErrorSchema


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
        """
        >>> NotFoundSchema.fetch_natural_key('jeff')
        'jeff'
        >>> from envelope.models import Connection
        >>> NotFoundSchema.fetch_natural_key(Connection)
        'envelope.connection'
        >>> NotFoundSchema.fetch_natural_key(Connection())
        'envelope.connection'
        >>> NotFoundSchema.fetch_natural_key(object())
        Traceback (most recent call last):
        ...
        ValueError:
        """
        if isinstance(v, str):
            return v
        elif isinstance(v, Model):
            v = v.__class__
        if isinstance(v, type) and issubclass(v, Model):
            return f"{v._meta.app_label}.{v._meta.model_name.lower()}"
        raise ValueError(
            "Needs to be a string or instance/class based on djangos Model"
        )


@add_message(ERRORS)
class NotFoundError(ErrorMessage):
    name = Error.NOT_FOUND
    schema = NotFoundSchema
    data: NotFoundSchema


class UnauthorizedSchema(NotFoundSchema):
    permission: str | None

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
        >>> UnauthorizedSchema.adjust_user_str('regular')
        'regular'
        """
        if isinstance(v, UserString):
            return str(v)
        return v


@add_message(ERRORS)
class UnauthorizedError(ErrorMessage):
    name = Error.UNAUTHORIZED
    schema = UnauthorizedSchema
    data: UnauthorizedSchema
