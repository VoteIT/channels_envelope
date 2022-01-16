from django.contrib.auth import get_user_model
from django.test import TestCase
from pydantic import BaseModel

from envelope.messages.errors import NotFoundError
from envelope.messages.errors import UnauthorizedError

User = get_user_model()


class ContextActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from envelope.messages.actions import ContextAction

        cls.user = User.objects.create(username="jane")

        class UserActionSchema(BaseModel):
            username: str

        class UserAction(ContextAction):
            name = "user_action"
            schema = UserActionSchema
            context_schema_attr = "username"
            context_query_kw = "username"
            permission = None  # But still needs a real user
            model = User

            def run_job(self):
                self.validate()
                self.assert_perm()
                return self.context

        cls.action = UserAction

    def test_no_user(self):
        action = self.action(username="jeff")
        self.assertRaises(UnauthorizedError, action.run_job)

    def test_context_lookup_not_found(self):
        action = self.action(mm={"user_pk": self.user.pk}, username="john_doe")
        try:
            action.run_job()
        except NotFoundError as exc:
            exception = exc
        else:
            self.fail()
        self.assertEqual(exception.data.model, "auth.user")
        self.assertEqual(exception.data.key, "username")
        self.assertEqual(exception.data.value, "john_doe")

    def test_context_lookup(self):
        action = self.action(mm={"user_pk": self.user.pk}, username="jane")
        action.validate()
        self.assertEqual(action.context, self.user)

    def test_with_permission(self):
        action = self.action(mm={"user_pk": self.user.pk}, username="jane")
        action.permission = "__nopes__"
        action.validate()
        try:
            action.assert_perm()
        except UnauthorizedError as exc:
            exception = exc
        else:
            self.fail()
        self.assertEqual(exception.data.model, "auth.user")
        self.assertEqual(exception.data.key, "username")
        self.assertEqual(exception.data.value, "jane")
        self.assertEqual(exception.data.permission, "__nopes__")
