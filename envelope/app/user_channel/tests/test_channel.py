from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class ChannelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.jane = User.objects.create(username="jane")
        cls.tarzan = User.objects.create(username="tarzan")

    @property
    def _cut(self):
        from envelope.app.user_channel.channel import UserChannel

        return UserChannel

    def test_allow_subscribe(self):
        janes_channel = self._cut.from_instance(self.jane)
        self.assertTrue(janes_channel.allow_subscribe(self.jane))
        self.assertFalse(janes_channel.allow_subscribe(self.tarzan))

    def test_context(self):
        janes = self._cut(self.jane.pk)
        self.assertEqual(self.jane, janes.context)
