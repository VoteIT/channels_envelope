from django.dispatch import receiver
from django.utils import translation
from envelope import WS_OUTGOING
from envelope.decorators import add_message
from envelope.messages.base import Message
from envelope.signals import client_connect
from envelope.utils import websocket_send
from pydantic import BaseModel
from django.utils.translation import gettext_lazy as _


@receiver(client_connect)
def say_hello_at_connect(user, consumer_name, **kw):
    print("Active language in automatic greeting: ", translation.get_language())
    greeting = _("Hello %(username)s!") % {"username": user.username}
    msg = Pleasantry(greeting=greeting)
    websocket_send(msg, consumer_name, on_commit=False)


class PleasantrySchema(BaseModel):
    greeting: str


@add_message(WS_OUTGOING)
class Pleasantry(Message):
    name = "testing.hello"
    schema = PleasantrySchema
