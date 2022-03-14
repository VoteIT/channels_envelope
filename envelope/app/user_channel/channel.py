from django.contrib.auth import get_user_model

from envelope.core.channels import ContextChannel
from envelope.decorators import add_context_channel


@add_context_channel
class UserChannel(ContextChannel):
    model = get_user_model()
    permission = None
    name = "user"

    def allow_subscribe(self, user):
        return user.pk and user.pk == self.pk
