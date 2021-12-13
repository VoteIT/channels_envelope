from asgiref.sync import async_to_sync
from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.conf.urls import url
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class SyncWebsocketConsumerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="sockety", password="secret")

    @property
    def _cut(self):
        from envelope.consumers import SyncWebsocketConsumer

        return SyncWebsocketConsumer

    def test_s(self):
        pass


#       self.client.login(username="sockety", password="secret")
#        self.client.cookies.get("sessionid").value

# application = URLRouter(
#     [
#         url(r"^testws/$", self._cut.as_asgi()),
#     ]
# )
# communicator = WebsocketCommunicator(application, "/testws/")

# # Test on connection welcome message
# message = await communicator.receive_from()
# assert message == "test"
# # Close
# async_to_sync(communicator.disconnect)()
