from pydantic import BaseModel
from pydantic import Field

from envelope import MessageStates


class MessageMeta(BaseModel):
    """
    Information about the nature of the message itself.
    It's never sent to the user but used

    id
        A made-up id for this message. The frontend decides the id.

    user_pk
        The user this message originated from.

    consumer_name:
        The consumers name (id) this message passed. Any reply to the author (for instance an error message)
        should be directed here.

    registry:
        Which registry this was created from.
    """

    id: str | None = Field(alias="i")
    user_pk: int | None
    consumer_name: str | None
    language: str | None = Field(alias="l")
    state: str | None = Field(alias="s")
    registry: str | None

    class Config:
        extra = "forbid"
        allow_population_by_field_name = True


class NoPayload(BaseModel):
    pass


class EnvelopeSchema(BaseModel):
    """
    t - message type, same as name on message class.
        This describes the payload and how to handle the message.
    p - payload
    i - optional message id
    """

    t: str
    p: dict | None
    i: str | None = Field(max_length=20, alias="id")

    class Config:
        allow_population_by_field_name = True


class IncomingEnvelopeSchema(EnvelopeSchema):
    """
    l - language
    """

    l: str | None = Field(default=None, max_length=20, alias="language")


class OutgoingEnvelopeSchema(EnvelopeSchema):
    """
    s - state
    """

    s: str | None = Field(max_length=6, alias="state")

    # @validator("s")
    # def validate_state(cls, v):
    #     if v and v not in MessageStates.MESSAGE_STATES:
    #         raise ValueError("%s is not a valid message state" % v)
    #     return v


class ErrorEnvelopeSchema(OutgoingEnvelopeSchema):
    s: str = Field(MessageStates.FAILED, const=True)
