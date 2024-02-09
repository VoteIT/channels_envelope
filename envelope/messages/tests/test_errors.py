from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase


User = get_user_model()


class ErrorTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="tester")

    def test_not_found(self):
        from envelope.messages.errors import NotFoundError

        user_nat_key = f"{User._meta.app_label}.{User._meta.model_name.lower()}"
        one = NotFoundError(model=self.user, value="1")
        self.assertEqual(user_nat_key, one.data.model)

        two = NotFoundError(model=user_nat_key, value="1")
        self.assertEqual(user_nat_key, two.data.model)

        three = NotFoundError(model=User, value="1")
        self.assertEqual(user_nat_key, three.data.model)
