from typing import Optional

from pydantic import BaseModel
from pydantic import Field
from pydantic import validator

from envelope import MessageStates


class EnvelopeSchema(BaseModel):
    """
    t - message type, same as name on message class.
        This describes the payload and how to handle the message.
    p - payload
    i - optional message id
    """

    t: str
    p: Optional[dict]
    i: Optional[str] = Field(
        max_length=20,
    )


class OutgoingEnvelopeSchema(EnvelopeSchema):
    """
    s - status/state
    """

    s: Optional[str] = Field(max_length=6)

    @validator("s")
    def validate_state(cls, v):
        if v and v not in MessageStates.MESSAGE_STATES:
            raise ValueError("%s is not a valid message state" % v)
        return v


class ErrorSchema(OutgoingEnvelopeSchema):
    s: str = Field(MessageStates.FAILED, const=True)


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

    id: Optional[str]
    user_pk: Optional[int]
    consumer_name: Optional[str]
    language: Optional[str] = None
    state: Optional[str]
    registry: Optional[str]

    def envelope_data(self) -> dict:
        data = dict(i=self.id, l=self.language)
        if self.state:
            data["s"] = self.state
        return data


class NoPayload(BaseModel):
    pass
