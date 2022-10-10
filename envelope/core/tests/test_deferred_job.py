from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from fakeredis import FakeRedis
from pydantic import BaseModel
from rq import Queue
from rq import Retry
from rq import SimpleWorker

from envelope.core.message import DeferredJob
from envelope.testing import TestingEnvelope
from envelope.utils import websocket_send_error

User = get_user_model()

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


class MyJobData(BaseModel):
    fail: bool = False


class MyJob(DeferredJob):
    name = "my_job"
    ttl = 200
    job_timeout = 300
    data: MyJobData
    schema = MyJobData

    def run_job(self):
        if self.data.fail:
            raise ValueError("Oh no!")
        return "Yay"


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class DeferredJobTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from envelope.testing import testing_messages

        testing_messages.add(MyJob)

    @classmethod
    def tearDownClass(cls):
        from envelope.testing import testing_messages

        testing_messages.pop(MyJob.name)
        super().tearDownClass()

    def setUp(self):
        self.fakeredis = FakeRedis()
        self.queue = Queue(connection=self.fakeredis)
        self.worker = SimpleWorker(
            queues=[self.queue],
            connection=self.fakeredis,
        )

    def mk_job(self, fail=False, **kwargs):
        return MyJob(
            queue=self.queue,
            fail=fail,
            mm={"consumer_name": "abc", "id": "123"},
            **kwargs
        )

    def test_settings_respected(self):
        job = self.mk_job()
        job.validate()
        job.enqueue()
        self.assertEqual(1, len(self.queue.job_ids))
        job = self.queue.jobs[0]
        self.assertEqual(200, job.ttl)
        self.assertEqual(300, job.timeout)

    def test_job_nothing_special(self):
        job = self.mk_job()
        job.validate()
        self.assertEqual(0, len(self.queue.job_ids))
        job.enqueue(envelope=TestingEnvelope.name)
        completed = self.worker.work(burst=True)
        self.assertTrue(completed)

    @patch("envelope.jobs.websocket_send_error")
    def test_handle_failure(self, patched):
        # A note on the patch: it's in the WRONG module, but it's where websocket_send_error gets executed
        # So if we patch utils it won't work! It's one of the mock gotchas, beware.
        job = self.mk_job(fail=True)
        job.validate()
        self.assertEqual(0, len(self.queue.job_ids))
        job.enqueue(envelope=TestingEnvelope.name)
        self.assertEqual(1, len(self.queue.job_ids))
        completed = self.worker.work(burst=True)
        self.assertTrue(completed)
        self.assertTrue(patched.called)
