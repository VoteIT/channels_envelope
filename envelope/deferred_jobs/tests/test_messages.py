from unittest.mock import patch

from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django_rq import get_queue
from fakeredis import FakeStrictRedis
from pydantic import BaseModel
from rq import SimpleWorker

from envelope import WS_INCOMING
from envelope.deferred_jobs.message import ContextAction
from envelope.deferred_jobs.message import DeferredJob
from envelope.messages.errors import NotFoundError
from envelope.messages.errors import UnauthorizedError
from envelope.models import Connection
from envelope.utils import get_message_registry

User = get_user_model()


class DummyJob(DeferredJob):
    name = "dummy_job"

    def run_job(self):
        Connection.objects.create(user=self.user, channel_name="abc")


class BadJob(DeferredJob):
    name = "bad_job"

    def run_job(self):
        return 1 / 0


class NeverFoundJob(DeferredJob):
    name = "bad_at_looking"

    def run_job(self):
        raise NotFoundError.from_message(self, model="something", value="1")


class DummyContextAction(ContextAction):
    name = "dummy_context_action"
    permission = None
    model = Connection
    atomic = False

    def run_job(self):
        self.context.awol = True
        self.context.save()


class DeferredJobTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="runner")

    def test_enqueue_via_queue(self):
        msg = DummyJob(mm={"user_pk": self.user.pk})
        connection = FakeStrictRedis()
        queue = get_queue(connection=connection)
        queue.enqueue(msg.run_job)
        worker = SimpleWorker([queue], connection=connection)
        self.assertTrue(worker.work(burst=True))
        self.assertTrue(Connection.objects.filter(channel_name="abc").exists())

    def test_enqueue_via_msg(self):
        msg = DummyJob(mm={"user_pk": self.user.pk, "env": WS_INCOMING})
        connection = FakeStrictRedis()
        queue = get_queue(connection=connection)
        msg.enqueue(
            queue=queue,
        )
        worker = SimpleWorker([queue], connection=connection)
        self.assertTrue(worker.work(burst=True))
        self.assertTrue(Connection.objects.filter(channel_name="abc").exists())

    def test_job_name(self):
        msg = DummyJob(mm={"user_pk": self.user.pk, "env": WS_INCOMING})
        connection = FakeStrictRedis()
        queue = get_queue(connection=connection)
        job = msg.enqueue(
            queue=queue,
        )
        self.assertEqual(
            "envelope.deferred_jobs.tests.test_messages.DummyJob.init_job",
            job.func_name,
        )

    def test_error_handling(self):
        msg = BadJob(
            mm={"user_pk": self.user.pk, "env": WS_INCOMING, "consumer_name": "abc"}
        )
        connection = FakeStrictRedis()
        queue = get_queue(connection=connection)
        msg.enqueue(queue)
        worker = SimpleWorker([queue], connection=connection)
        channel_layer = get_channel_layer()
        with patch.object(channel_layer, "send") as mock_send:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(worker.work(burst=True))
        self.assertTrue(mock_send.called)
        self.assertEqual(
            {
                "t": "error.job",
                "p": {"msg": "division by zero"},
                "i": None,
                "s": "f",
                "type": "ws.error.send",
            },
            mock_send.call_args[0][1],
        )

    def test_job_raises_catchable_error(self):
        msg = NeverFoundJob(
            mm={"user_pk": self.user.pk, "env": WS_INCOMING, "consumer_name": "abc"},
        )
        connection = FakeStrictRedis()
        queue = get_queue(connection=connection)
        msg.enqueue(queue)
        worker = SimpleWorker([queue], connection=connection)
        channel_layer = get_channel_layer()
        with patch.object(channel_layer, "send") as mock_send:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(worker.work(burst=True))
        self.assertTrue(mock_send.called)
        self.assertEqual(
            {
                "t": "error.job",
                "p": {"key": "pk", "model": "something", "value": "1"},
                "i": None,
                "s": "f",
                "t": "error.not_found",
                "type": "ws.error.send",
            },
            mock_send.call_args[0][1],
        )


class DummyContextActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="runner")
        cls.conn = Connection.objects.create(user=cls.user, channel_name="abc")
        cls.msg_reg = get_message_registry(WS_INCOMING)
        cls.msg_reg[DummyContextAction.name] = DummyContextAction

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.msg_reg.pop(DummyContextAction.name)

    def _mk_msg(self, **kwargs):
        msg = DummyContextAction(**kwargs)
        return msg

    def test_enqueue_via_queue(self):
        msg = self._mk_msg(pk=self.conn.pk, mm={"user_pk": self.user.pk})
        connection = FakeStrictRedis()
        queue = get_queue(connection=connection)
        queue.enqueue(msg.run_job)
        worker = SimpleWorker([queue], connection=connection)
        self.assertTrue(worker.work(burst=True))
        self.assertTrue(
            Connection.objects.filter(channel_name="abc", awol=True).exists()
        )

    def test_enqueue_via_msg(self):
        msg = self._mk_msg(
            pk=self.conn.pk, mm={"user_pk": self.user.pk, "env": WS_INCOMING}
        )
        connection = FakeStrictRedis()
        queue = get_queue(connection=connection)
        msg.enqueue(
            queue=queue,
        )
        worker = SimpleWorker([queue], connection=connection)
        self.assertTrue(worker.work(burst=True))
        self.assertTrue(
            Connection.objects.filter(channel_name="abc", awol=True).exists()
        )

    def test_context(self):
        msg = self._mk_msg(
            pk=self.conn.pk, mm={"user_pk": self.user.pk, "env": WS_INCOMING}
        )
        self.assertEqual(self.conn, msg.context)
        msg = self._mk_msg(pk=-1, mm={"user_pk": self.user.pk, "env": WS_INCOMING})
        with self.assertRaises(NotFoundError) as cm:
            msg.context
        self.assertEqual(
            {"key": "pk", "model": "envelope.connection", "value": "-1"},
            cm.exception.data.dict(),
        )

    def test_perm(self):
        msg = self._mk_msg(
            pk=self.conn.pk, mm={"user_pk": self.user.pk, "env": WS_INCOMING}
        )
        self.assertTrue(msg.allowed())
        msg.permission = "hard to come by"
        self.assertFalse(msg.allowed())

    def test_perm_raises(self):
        msg = self._mk_msg(
            pk=self.conn.pk, mm={"user_pk": self.user.pk, "env": WS_INCOMING}
        )
        self.assertIsNone(msg.assert_perm())
        msg.permission = "hard to come by"
        with self.assertRaises(UnauthorizedError) as cm:
            msg.assert_perm()
        self.assertEqual(
            {
                "key": "pk",
                "model": "envelope.connection",
                "value": str(self.conn.pk),
                "permission": "hard to come by",
            },
            cm.exception.data.dict(),
        )
