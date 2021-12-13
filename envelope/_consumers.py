# from abc import ABC
# from datetime import datetime
# from logging import getLogger
# from typing import Optional
# from typing import Union
#
# from asgiref.sync import async_to_sync
# from asgiref.sync import sync_to_async
# from channels.auth import get_user
# from channels.exceptions import DenyConnection
# from channels.generic.websocket import AsyncWebsocketConsumer
# from channels.generic.websocket import WebsocketConsumer
# from django.conf import settings
# from django.contrib.auth import get_user_model
# from django.contrib.auth.models import AbstractUser
# from django.utils.translation import activate
# from django.utils.translation import check_for_language
# from django.utils.translation import get_supported_language_variant
# from django.utils.translation.trans_real import get_languages
# from django.utils.translation.trans_real import language_code_re
# from django.utils.translation.trans_real import parse_accept_lang_header
# from envelope import WS_OUTGOING
# from envelope.envelope import Envelope
# from envelope.envelope import IncomingWebsocketEnvelope
# from envelope.envelope import OutgoingWebsocketEnvelope
# from envelope.messages.base import AsyncRunnable
#
# # from envelope.messages.base import DeferredJob
# from envelope.messages.base import Message
# from envelope.messages.base import Runnable
# from envelope.signals import client_close
# from envelope.signals import client_connect
# from envelope.utils import update_connection_status
#
# logger = getLogger(__name__)
#
#
# class AbstractWebsocketConsumer(ABC):
#     # The users pk associated with the connection. No anon connections are allowed at this time.
#     # This will remain even if the user logs out. (The consumer will die shortly after logout)
#     user_pk: Optional[int] = None
#     # The specific connections own channel. Use this to send messages to one
#     # specific connection or as id when subscribing to other channels.
#     channel_name: str
#     # Keep track of communication
#     last_sent: datetime
#     last_recv: datetime
#     last_error: Optional[datetime] = None
#     # Language
#     user_lang: Optional[str] = None
#     # Scope is set by the consumer - see channels docs
#     scope: dict
#
#     @property
#     def user(self) -> Optional[AbstractUser]:
#         user = self.scope["user"]
#         if user.is_authenticated:
#             return user
#
#     def get_msg_meta(self) -> dict:
#         """
#         Return values meant to be attached to the message meta information,
#         """
#         return dict(
#             consumer_name=self.channel_name,
#             language=self.user_lang,
#             user_pk=self.user and self.user.pk or None,
#         )
#
#     # def connect(self):
#     #     self.user_lang = self.get_language()
#     #     activate(self.user_lang)  # FIXME: Safe here?
#     #
#     #     self.user = await self.refresh_user()
#     #     if self.user is None:
#     #         logger.debug("Invalid token, closing connection")
#     #         raise DenyConnection()
#     #     # Save for later use in case of invalidation of the user object
#     #     self.user_pk = self.user.pk
#     #     # And mark action
#     #     self.last_sent = self.last_recv = now()
#     #     logger.debug("Connection for user: %s", self.user)
#     #     await self.accept()
#     #     logger.debug(
#     #         "Connection accepted for user %s (%s) with lang %s",
#     #         self.user,
#     #         self.user.pk,
#     #         self.user_lang,
#     #     )
#     #     if self.enable_connection_signals:
#     #         self.dispatch_connect()
#
#     # async def refresh_user(self) -> Optional[AbstractUser]:
#     #     user = await get_user(self.scope)
#     #     if user.pk is not None:
#     #         self.user = user
#     #         return user
#
#     def get_language(self) -> str:
#         """
#         Get language according to this order:
#
#         1) From cookie
#         2) From Accept-Language HTTP header
#         3) Default language from settings
#         """
#         # Note: This whole method should mimic the behaviour of Django's get_language_from_request
#         # for consistency. So yeah this code looks like this in Django.
#         lang_code = self.scope.get("cookies", {}).get(settings.LANGUAGE_COOKIE_NAME)
#
#         if (
#             lang_code is not None
#             and lang_code in get_languages()
#             and check_for_language(lang_code)
#         ):
#             return lang_code
#
#         try:
#             return get_supported_language_variant(lang_code)
#         except LookupError:
#             pass
#
#         accept = []
#         for (k, v) in self.scope.get("headers", {}):
#             if k == b"accept-language":
#                 accept.append(v.decode())
#             elif k == "accept-language":
#                 # Mostly for testing or in case this changes
#                 accept.append(v)
#         if accept:
#             accept_str = ",".join(accept)
#             for accept_lang, unused in parse_accept_lang_header(accept_str):
#                 if accept_lang == "*":
#                     break
#                 if not language_code_re.search(accept_lang):
#                     continue
#                 try:
#                     return get_supported_language_variant(accept_lang)
#                 except LookupError:
#                     continue
#         try:
#             return get_supported_language_variant(settings.LANGUAGE_CODE)
#         except LookupError:
#             return settings.LANGUAGE_CODE
#
#
# class SyncWebsocketConsumer(AbstractWebsocketConsumer, WebsocketConsumer):
#     sync = True
#
#     def connect(self):
#         logger.debug("%s connected consumer %s", self.user, self.channel_name)
#         if not self.user:
#             # return self.close()
#             raise DenyConnection()
#         self.user_pk = self.user.pk
#         super().connect()
#         print("SCOPE IS:", self.scope)
#         print("USER IS:", self.user)
#         conn = update_connection_status(
#             user=self.user, channel_name=self.channel_name, online=True
#         )
#         client_connect.send(
#             sender=None,
#             user=self.user,
#             user_pk=self.user.pk,
#             consumer_name=self.channel_name,
#             connection=conn,
#         )
#
#     def disconnect(self, code):
#         # https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent
#         user = self.user
#         if not user and self.user_pk:
#             User = get_user_model()
#             user = User.objects.filter(pk=self.user_pk).first()
#         if user:
#             conn = update_connection_status(
#                 self.user, channel_name=self.channel_name, online=False
#             )
#             client_close.send(
#                 sender=None,
#                 user=user,
#                 user_pk=self.user_pk,
#                 consumer_name=self.channel_name,
#                 close_code=code,
#                 connection=conn,
#             )
#         logger.debug(
#             "%s disconnected consumer %s. close_code: %s",
#             self.user_pk,
#             self.channel_name,
#             code,
#         )
#         super().disconnect(code)
#
#     def receive(self, text_data=None, bytes_data=None):
#         if text_data is not None:
#             env = IncomingWebsocketEnvelope.parse(text_data)
#             message = env.unpack(consumer=self)
#         else:
#             raise ValueError("No clue")
#         self.handle_message(message)
#
#     def handle_message(self, message):
#         activate(self.user_lang)  # FIXME: Every time...?
#         try:
#             message.validate()
#         except Exception:
#             # FIXME:
#             raise
#         # FIXME: Mabe move to separate handlers later on
#         if isinstance(message, Runnable):
#             message.run(self)
#
#         # if isinstance(message, AsyncRunnable):
#         # inspect.iscoroutinefunction
#         # message.run(self)
#         # if isinstance(message, DeferredJob):
#         #     async_to_sync(message.pre_queue)(self)
#         #     message.queue()
#         # queue = self.get_queue(message)
#         # message.enqueue(queue=queue)
#
#     def send(self, payload: Union[Envelope, Message], state=None):
#         if isinstance(payload, OutgoingWebsocketEnvelope):
#             envelope = payload
#         elif isinstance(payload, Message):
#             if WS_OUTGOING not in payload.registries():
#                 raise TypeError("%s not in %s registry" % (payload.name, WS_OUTGOING))
#             envelope = OutgoingWebsocketEnvelope.pack(payload)
#         else:
#             raise TypeError("Can only send Envelope or Message objects")
#         if state:
#             envelope.data.s = state
#         text_data = envelope.data.json()
#         super().send(text_data)
