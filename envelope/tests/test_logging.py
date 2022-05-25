from json import loads

from django.contrib.auth.models import User
from django.test import TestCase
from pythonjsonlogger import jsonlogger

from envelope.consumers.websocket import WebsocketConsumer
from envelope.logging import getEventLogger
from envelope.testing import WebsocketHello

json_formatter = jsonlogger.JsonFormatter()


class LoggingTests(TestCase):
    def _mk_dict(self, record):
        # Also to test jsonlogger
        output = json_formatter.format(record)
        return loads(output)

    def test_message(self):
        logger = getEventLogger()
        msg = WebsocketHello(mm={"user_pk": 1, "consumer_name": "abc", "state": "s"})
        with self.assertLogs() as logs:
            logger.info("Booo", message=msg)
        self.assertEqual(1, len(logs.records))
        record = logs.records[0]
        self.assertEqual(1, record.user)
        self.assertEqual("abc", record.consumer_name)
        self.assertEqual("testing", record.msg_reg)
        self.assertEqual("s", record.s)
        self.assertEqual(
            {
                "consumer_name": "abc",
                "message": "Booo",
                "msg_reg": "testing",
                "s": "s",
                "t": "testing.hello",
                "i": None,
                "user": 1,
            },
            self._mk_dict(record),
        )

    def test_message_specified_state(self):
        logger = getEventLogger()
        msg = WebsocketHello(
            mm={"user_pk": 1, "consumer_name": "abc", "state": "s", "id": "a"}
        )
        with self.assertLogs() as logs:
            logger.info("Booo", message=msg, state="f")
        self.assertEqual(1, len(logs.records))
        record = logs.records[0]
        self.assertEqual("f", record.s)
        self.assertEqual(
            {
                "consumer_name": "abc",
                "message": "Booo",
                "msg_reg": "testing",
                "s": "f",
                "t": "testing.hello",
                "i": "a",
                "user": 1,
            },
            self._mk_dict(record),
        )

    def test_consumer(self):
        logger = getEventLogger()
        user = User.objects.create(username="jeff")
        consumer = WebsocketConsumer()
        consumer.user = user
        consumer.channel_name = "a_name"
        with self.assertLogs() as logs:
            logger.info("Booo", consumer=consumer)
        self.assertEqual(1, len(logs.records))
        record = logs.records[0]
        self.assertEqual(user.pk, record.user)
        self.assertEqual("a_name", record.consumer_name)
        self.assertEqual(
            {"consumer_name": "a_name", "message": "Booo", "user": 1},
            self._mk_dict(record),
        )

    def test_both(self):
        logger = getEventLogger()
        user = User.objects.create(username="jeff")
        consumer = WebsocketConsumer()
        consumer.user = user
        consumer.channel_name = "a_name"
        msg = WebsocketHello(
            mm={
                "user_pk": 1,
                "consumer_name": "abc",
                "state": "s",
                "id": "a",
            }
        )
        with self.assertLogs() as logs:
            logger.info("Booo", consumer=consumer, message=msg)
        self.assertEqual(1, len(logs.records))
        record = logs.records[0]
        # Msg wins over consumer on user
        # Consumer wins over message on consumer_name
        self.assertEqual(
            {
                "consumer_name": "a_name",
                "message": "Booo",
                "msg_reg": "testing",
                "s": "s",
                "t": "testing.hello",
                "i": "a",
                "user": 1,
            },
            self._mk_dict(record),
        )

    def test_none_specified(self):
        logger = getEventLogger()
        msg = WebsocketHello(mm={"user_pk": 1, "consumer_name": "abc", "state": "s"})
        with self.assertLogs():
            # I'm lazy and don't want to figure out how to configure loggers similarly :)
            logger.info("Booo", message=msg)
            with self.assertRaises(ValueError):
                logger.info("Booo")
