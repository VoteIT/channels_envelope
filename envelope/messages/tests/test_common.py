from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from envelope.apps import ChannelsEnvelopeConfig

from envelope.messages.common import Status
from envelope.messages.common import ProgressNum

# User = get_user_model()

ChannelsEnvelopeConfig.populate_registries()


class BatchTests(TestCase):
    @property
    def _cut(self):
        from envelope.messages.common import Batch

        return Batch

    def test_no_payload_message(self):
        msg = Status()
        batch = self._cut.start(msg)
        self.assertEqual(Status.name, batch.data.t)
        self.assertEqual([None], batch.data.payloads)
        batch.append(msg)
        self.assertEqual([None, None], batch.data.payloads)

    def test_with_payload(self):
        msg = ProgressNum(curr=1, total=2)
        batch = self._cut.start(msg)
        self.assertEqual([{"curr": 1, "total": 2, "msg": None}], batch.data.payloads)
        self.assertEqual(ProgressNum.name, batch.data.t)
        msg = ProgressNum(curr=2, total=2)

        batch.append(msg)
        self.assertEqual(
            [
                {"curr": 1, "total": 2, "msg": None},
                {"curr": 2, "total": 2, "msg": None},
            ],
            batch.data.payloads,
        )

    def test_wrong_second_type(self):
        msg = ProgressNum(curr=1, total=2)
        batch = self._cut.start(msg)
        with self.assertRaises(TypeError):
            batch.append(Status())
