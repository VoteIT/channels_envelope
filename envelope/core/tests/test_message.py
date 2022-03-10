from django.contrib.auth import get_user_model
from django.test import TestCase
from pydantic import BaseModel

from envelope.messages.errors import NotFoundError
from envelope.messages.errors import UnauthorizedError

User = get_user_model()


class MessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):

        cls.user = User.objects.create(username="jane")

    def test_registry(self):
        pass

    def test_orm(self):
        pass
