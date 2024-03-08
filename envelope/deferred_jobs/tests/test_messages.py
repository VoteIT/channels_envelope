from django.contrib.auth import get_user_model
from django.test import TestCase
from django_rq import get_queue
from fakeredis import FakeStrictRedis
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
        cls.msg_reg = get_message_registry(WS_INCOMING)
        cls.msg_reg[DummyJob.name] = DummyJob

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.msg_reg.pop(DummyJob.name)

    def _mk_msg(self, **kwargs):
        msg = DummyJob(**kwargs)
        return msg

    def test_enqueue_via_queue(self):
        msg = self._mk_msg(mm={"user_pk": self.user.pk})
        connection = FakeStrictRedis()
        queue = get_queue(connection=connection)
        queue.enqueue(msg.run_job)
        worker = SimpleWorker([queue], connection=connection)
        self.assertTrue(worker.work(burst=True))
        self.assertTrue(Connection.objects.filter(channel_name="abc").exists())

    def test_enqueue_via_msg(self):
        msg = self._mk_msg(mm={"user_pk": self.user.pk, "env": WS_INCOMING})
        connection = FakeStrictRedis()
        queue = get_queue(connection=connection)
        msg.enqueue(
            queue=queue,
        )
        worker = SimpleWorker([queue], connection=connection)
        self.assertTrue(worker.work(burst=True))
        self.assertTrue(Connection.objects.filter(channel_name="abc").exists())


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
                "value": "1",
                "permission": "hard to come by",
            },
            cm.exception.data.dict(),
        )
