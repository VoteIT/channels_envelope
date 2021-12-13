# # from __future__ import annotations
# # from abc import ABC
# # from abc import abstractmethod
# # from typing import Generic
# # from typing import Optional
# # from typing import TypeVar
# # from typing import Union
# #
# # from django.contrib.auth import get_user_model
# # from django.contrib.auth.models import AbstractUser
# # from django.db import models
# # from django.utils.functional import cached_property
# # from envelope import MessageStates
# # from pydantic import BaseModel
# # from typing import Type
#
#
# # class MessageMeta(BaseModel):
# #     """
# #     Information about the nature of the message itself.
# #     It's never sent to the user but used
# #
# #     id
# #         A made-up id for this message. The frontend decides the id.
# #
# #     user_pk
# #         The user this message originated from.
# #
# #     consumer_name:
# #         The consumers name (id) this message passed. Any reply to the author (for instance an error message)
# #         should be directed here.
# #
# #     category:
# #         Which kind of message is this. Category corresponds to registry.
# #     """
# #
# #     id: Optional[str]
# #     user_pk: Optional[int]
# #     consumer_name: Optional[str]
# #     language: Optional[str] = None
# #     state: Optional[str]
# #
# #
# # class NO_PAYLOAD(BaseModel):
# #     pass
# #
# #
# # class Message(MessageStates, ABC):
# #     mm: MessageMeta
# #     data: BaseModel
# #     schema: Type[BaseModel] = NO_PAYLOAD
# #     initial_data: dict
# #
# #     @property
# #     @abstractmethod
# #     def name(self) -> str:
# #         """
# #         The ID/name of the message type. This corresponds to 't' on incoming messages.
# #         """
# #
# #     def __init__(
# #         self,
# #         mm: Union[dict, MessageMeta] = None,
# #         data: Optional[dict] = None,
# #         **kwargs,
# #     ):
# #         if mm is None:
# #             mm = {}
# #         if isinstance(mm, MessageMeta):
# #             self.mm = mm
# #         else:
# #             assert isinstance(self.name, str), "Name attribute is not set as a string"
# #             mm["type_name"] = self.name
# #             self.mm = MessageMeta(**mm)
# #         if data is None:
# #             data = {}
# #         data.update(kwargs)
# #         self.initial_data = data
# #         self._data = None
# #         self._validated = False
# #         if self.schema is NO_PAYLOAD:
# #             self.validate()
# #
# #     @property
# #     def data(self):
# #         try:
# #             return self._data
# #         except AttributeError:
# #             raise ValueError("data accessed before validation")
# #
# #     @property
# #     def is_validated(self):
# #         return self._validated
# #
# #     def validate(self):
# #         if not self.is_validated:
# #             if self.schema is NO_PAYLOAD:
# #                 self._data = None
# #             else:
# #                 self._data = self.schema(**self.initial_data)
# #             self._validated = True
#
# # @classmethod
# # @abstractmethod
# # def from_message(cls, message: Message, type_name=None, **kwargs) -> Message:
# #     pass
#
# # @property
# # def is_on_commit_disabled(self):
# #     return getattr(settings, "DISABLE_MESSAGE_ON_COMMIT", False)
#
# # @cached_property
# # def user(self) -> Optional[AbstractUser]:
# #     """
# #     Retrieve user from MessageMeta.user_pk, if it exists
# #     """
# #     if self.mm.user_pk:
# #         User: AbstractUser = get_user_model()
# #         return User.objects.filter(pk=self.mm.user_pk).first()
# #     return None
#
# # @cached_property
# # def channel_layer(self):
# #     return get_channel_layer(self.channel_layer_name)
# #
# # def send_internal(self, channel_name: str, group: bool = False, on_commit=True):
# #     """Queue an internal message, meant for the consumer and not to be transmitted over websocket.
# #     These are usually actions that need to be taken by the consumers, like healthchecks.
# #     """
# #
# #     def _hook():
# #         async_to_sync(self.async_send_internal)(channel_name, group=group)
# #
# #     if on_commit and not self.is_on_commit_disabled:
# #         transaction.on_commit(_hook)
# #     else:
# #         _hook()
# #
# # async def async_send_internal(
# #     self, channel_name: str, group: bool = False, on_commit=None
# # ):
# #     assert on_commit is None, "This argument doesn't work on async calls!"
# #     envelope = InternalEnvelope(
# #         p=self.data.json(),
# #         i=self.mm.message_id,
# #         t=self.mm.type,
# #         l=self.mm.language,
# #         incoming=isinstance(self, BaseIncomingMessage),
# #     )
# #     if group:
# #         await self.channel_layer.group_send(channel_name, envelope.dict())
# #     else:
# #         await self.channel_layer.send(channel_name, envelope.dict())
# #
# # def send_outgoing(
# #     self,
# #     channel_name: str,
# #     state: Optional[str] = None,
# #     success: Optional[bool] = None,
# #     group: bool = False,
# #     on_commit: bool = True,
# # ):
# #     """Queue a message that the consumer is meant to deliver over websocket to the client.
# #     The message may also contain actions that'll be taken before the message is transmitted.
# #     """
# #
# #     def _hook():
# #         async_to_sync(self.async_send_outgoing)(
# #             channel_name, state=state, success=success, group=group
# #         )
# #
# #     if on_commit and not self.is_on_commit_disabled:
# #         transaction.on_commit(_hook)
# #     else:
# #         _hook()
# #
# # async def async_send_outgoing(
# #     self,
# #     channel_name: str,
# #     state: Optional[str] = None,
# #     success: Optional[bool] = None,
# #     group: bool = False,
# #     on_commit=None,
# # ):
# #     """Async call to queue an outgoing message. Use this directly when possible.
# #     Note that it doesn't support transactions so it will be queued directly.
# #     """
# #     assert on_commit is None, "This argument doesn't work on async calls!"
# #     if success is not None:
# #         if state is not None:
# #             raise ValueError("Can't specify both state and success")
# #         if success:
# #             state = self.SUCCESS
# #         else:
# #             state = self.FAILED
# #     envelope = OutgoingEnvelope(
# #         p=self.data.json(),
# #         i=self.mm.message_id,
# #         t=self.mm.type,
# #         s=state,
# #         l=self.mm.language,
# #     )
# #     if group:
# #         await self.channel_layer.group_send(channel_name, envelope.dict())
# #     else:
# #         await self.channel_layer.send(channel_name, envelope.dict())
#
# # @classmethod
# # def from_consumer(
# #     cls,
# #     consumer,
# #     envelope: Union[IncomingEnvelope, InternalEnvelope, OutgoingEnvelope],
# # ):
# #     """Instantiate a message with details from the consumer and an envelope."""
# #     mm = MessageMeta(
# #         consumer_name=consumer.channel_name,
# #         user_pk=consumer.user.pk,
# #         message_id=envelope.i,
# #         type=envelope.t,
# #         internal=getattr(envelope, "type", None) == INTERNAL_MESSAGE,
# #         language=envelope.l,
# #     )
# #     msg_cls = cls.get_registry()[mm.type]  # Already validated
# #     inst = msg_cls(mm, envelope.p)
# #     inst.user = consumer.user  # This will be the same anyway
# #     return inst
#
# # @classmethod
# # def create(
# #     cls,
# #     type_name=None,
# #     message_id=None,
# #     consumer_name=None,
# #     user_pk=None,
# #     language=None,
# #     **kwargs,
# # ):
# #     if type_name is None:
# #         assert (
# #             cls.name is not None
# #         ), "You need to specify type name, this is an abstract class"
# #         type_name = cls.name
# #     mm = MessageMeta(
# #         type=type_name,
# #         message_id=message_id,
# #         consumer_name=consumer_name,
# #         user_pk=user_pk,
# #         language=language,
# #     )
# #     return cls.get_registry()[type_name](mm, kwargs)
# from typing import TypeVar
#
# M = TypeVar(
#     "M"
# )  # Inherit ContextAction using ContextAction[Model] for correct type annotation of context.
#
#
# class ContextAction(ABC, Generic[M]):
#     """
#     An action performed on a specific context.
#     It has a permission and a model. The schema itself must contain an attribute that will be
#     used for lookup of the context to perform the action on. (context_pk_attr)
#
#     Note that it only works as a placeholder for an action, the code itself should be constructed by
#     combining it with DeferredJob and must also inherit BaseIncomingMessage or BaseOutgoingMessage
#     """
#
#     @property
#     @abstractmethod
#     def context_pk_attr(self) -> str:
#         """Fetch context from this attribute in the schema"""
#
#     @property
#     @abstractmethod
#     def schema(self) -> Type[BaseModel]:
#         """This really must have a valid schema"""
#
#     @property
#     @abstractmethod
#     def permission(self) -> Optional[str]:
#         """Text permission, None means allow any."""
#
#     @property
#     @abstractmethod
#     def model(self) -> Type[models.Model]:
#         """Model class this operates on."""
#
#     def allowed(self) -> bool:
#         if self.user is None:
#             return False
#         if self.context is None:
#             return False
#         if self.permission is None:
#             return True
#         return self.user.has_perm(self.permission, self.context)
#
#     @cached_property
#     def context(self) -> M:
#         try:
#             pk = getattr(self.data, self.context_pk_attr)
#         except AttributeError:
#             raise AttributeError(
#                 f"{self.context_pk_attr} is not a valid schema attribute for pk lookup. Message: {self}"
#             )
#         try:
#             return self.model.objects.get(pk=pk)
#         except self.model.DoesNotExist:
#             raise BaseError.create(
#                 type_name="error.not_found",
#                 consumer_name=self.mm.consumer_name,
#                 permission=self.permission,
#                 msg=_(
#                     "No %(context)s with pk %(pk)s"
#                     % {"context": self.model, "pk": self.data.pk}
#                 ),
#             )
#
#     def assert_perm(self, msg=None):
#         if not self.allowed():
#             raise BaseError.from_message(
#                 self,
#                 type_name="error.unauthorized",  # Constant?
#                 permission=self.permission,
#                 msg=msg,  # None is default
#             )
