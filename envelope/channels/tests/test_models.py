from __future__ import annotations

import json
from unittest.mock import patch

from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.test import TestCase
from django.test import override_settings

from envelope.app.user_channel.channel import UserChannel
from envelope.channels.errors import SubscribeError
from envelope.channels.messages import Leave
from envelope.channels.messages import Left
from envelope.channels.messages import ListSubscriptions
from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed
from envelope.channels.models import ContextChannel
from envelope.channels.schemas import ChannelSchema
from envelope.messages.errors import NotFoundError
from envelope.signals import channel_subscribed
from envelope.tests.helpers import TempSignal
from envelope.tests.helpers import WebsocketHello
from envelope.tests.helpers import mk_consumer
from envelope.tests.helpers import testing_channel_layers_setting


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
