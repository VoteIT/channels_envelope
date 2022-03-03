from django.contrib.auth import get_user_model

from envelope import DEFAULT_CHANNELS
from envelope.core.channels import ContextChannel
from envelope.decorators import add_channel


@add_channel(DEFAULT_CHANNELS)
class UserChannel(ContextChannel):
    model = get_user_model()
    permission = None
    name = "user"

    def allow_subscribe(self, user):
        return user.pk and user.pk == self.pk
