from django.contrib.auth import get_user_model
from django.utils.functional import classproperty

from envelope.channels.decorators import add_context_channel
from envelope.channels.models import ContextChannel


@add_context_channel
class UserChannel(ContextChannel):
    permission = None
    name = "user"

    def allow_subscribe(self, user):
        return user and user.pk and user.pk == self.pk

    @classproperty
    def model(cls):
        """
        In case the application that contains a custom user model imports this too,
        this at least help against odd import errors.
        """
        return get_user_model()
