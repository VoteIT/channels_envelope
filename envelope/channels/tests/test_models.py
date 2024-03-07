from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from envelope.channels.models import ContextChannel
from envelope.messages.errors import NotFoundError
from envelope.testing import testing_channel_layers_setting


User = get_user_model()


class _UnrestrictedUserChannel(ContextChannel):
    name = ""
    model = User
    permission = None


class _ProtectedUserChannel(ContextChannel):
    name = ""
    model = User
    permission = "whatever"


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class ContextChannelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="user")

    def test_permission(self):
        ch = _ProtectedUserChannel.from_instance(self.user)
        self.assertFalse(ch.allow_subscribe(self.user))
        self.user.is_superuser = True
        self.user.save()
        self.assertTrue(ch.allow_subscribe(self.user))
        self.assertFalse(ch.allow_subscribe(None))
        ch.context = None
        self.assertFalse(ch.allow_subscribe(self.user))

    def test_no_permission(self):
        ch = _UnrestrictedUserChannel.from_instance(self.user)
        self.assertTrue(ch.allow_subscribe(self.user))

    def test_context(self):
        ch = _ProtectedUserChannel(pk=self.user.pk)
        self.assertEqual(self.user, ch.context)
        ch = _ProtectedUserChannel(pk=-1)
        with self.assertRaises(NotFoundError) as cm:
            ch.context
        self.assertEqual(
            {"model": "auth.user", "key": "pk", "value": "-1"},
            cm.exception.data.dict(),
        )
