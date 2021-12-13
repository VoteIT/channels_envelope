from typing import TypedDict


class InternalTransport(TypedDict):
    error: bool
    text_data: str
    type: str
