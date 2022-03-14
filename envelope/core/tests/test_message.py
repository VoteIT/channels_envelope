from django.contrib.auth import get_user_model
from django.test import TestCase
from pydantic import BaseModel
from pydantic import ConfigError
from pydantic import ValidationError

from envelope.core.message import Message
from envelope.core.schemas import MessageMeta
from envelope.messages.testing import Pleasantry

User = get_user_model()


class OrmSchema(BaseModel):
    greeting: str

    class Config:
        orm_mode = True


class OrmMsg(Message):
    schema = OrmSchema
    name = "testing.orm"


class EmptyTestingMessage(Message):
    name = "testing.message_empty"


class TestingMessageSchema(BaseModel):
    num: int


class TestingMessage(Message):
    name = "testing.message"
    schema = TestingMessageSchema


class MockData:
    greeting = "Hello"


class MessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="tester")
        cls.user.connections.create(channel_name="abc")

    def test_orm_with_non_orm_msg(self):
        obj = MockData()
        with self.assertRaises(ConfigError):
            msg = Pleasantry(_orm=obj)

    def test_orm(self):
        obj = MockData()
        msg = OrmMsg(_orm=obj)
        self.assertEqual("Hello", msg.data.greeting)

    def test_orm_bad_data(self):
        obj = object()
        with self.assertRaises(ValidationError) as exc:
            msg = OrmMsg(_orm=obj)
        self.assertEqual(
            [
                {
                    "loc": ("greeting",),
                    "msg": "field required",
                    "type": "value_error.missing",
                }
            ],
            exc.exception.errors(),
        )

    def test_mm_dict(self):
        msg = TestingMessage(mm={"user_pk": 1, "registry": "testing", "id": 123})
        self.assertIsInstance(msg.mm, MessageMeta)
        self.assertEqual("testing", msg.mm.registry)
        self.assertEqual("123", msg.mm.id)

    def test_mm(self):
        mm = MessageMeta(user_pk=1, registry="testing", id=123)
        msg = TestingMessage(mm=mm)
        self.assertIs(mm, msg.mm)
        self.assertEqual("testing", msg.mm.registry)
        self.assertEqual("123", msg.mm.id)

    def test_no_data_required(self):
        msg = EmptyTestingMessage()
        self.assertIsNone(msg.data)
        self.assertTrue(msg.is_validated)

    def test_data_access_before_validation_performs_lazy_validation(self):
        msg = TestingMessage(num=1)
        self.assertFalse(msg.is_validated)
        msg.data
        self.assertTrue(msg.is_validated)

    def test_data_validation(self):
        msg = TestingMessage()
        with self.assertRaises(ValidationError):
            msg.validate()

    def test_data_correct(self):
        msg = TestingMessage(num=1)
        msg.validate()
        self.assertTrue(msg.is_validated)

    def test_user(self):
        msg = EmptyTestingMessage(mm={"user_pk": self.user.pk})
        self.assertEqual(msg.user, self.user)

    def test_user_not_found(self):
        msg = EmptyTestingMessage(mm={"user_pk": -1})
        self.assertIsNone(msg.user)
        msg = EmptyTestingMessage()
        self.assertIsNone(msg.user)

    def test_connection_no_consumer_name(self):
        msg = EmptyTestingMessage()
        self.assertIsNone(msg.connection)

    def test_connection_exists(self):
        from envelope.models import Connection

        msg = EmptyTestingMessage(mm={"consumer_name": "abc"})
        self.assertIsInstance(msg.connection, Connection)
