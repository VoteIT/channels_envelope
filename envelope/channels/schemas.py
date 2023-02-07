from pydantic import BaseModel
from pydantic import validator

from envelope.schemas import OutgoingEnvelopeSchema
from envelope.utils import get_context_channel_registry


class ChannelSchema(BaseModel):
    pk: int
    channel_type: str

    class Config:
        frozen = True

    @validator("channel_type", allow_reuse=True)
    def real_channel_type(cls, v):
        cr = get_context_channel_registry()
        v = v.lower()
        if v not in cr:  # pragma: no cover
            raise ValueError(f"'{v}' is not a valid channel")
        return v


class ChannelSubscription(ChannelSchema):
    """
    Track subscriptions to protected channels.
    """

    channel_name: str
    app_state: list[OutgoingEnvelopeSchema] | None
