# from django.contrib.auth import get_user_model
# from django.test import TestCase
# from pydantic import BaseModel
#
# User = get_user_model()
#
#
# class ContextActionTests(TestCase):
#     def setUpTestData(cls):
#         from envelope.messages.actions import ContextAction
#         cls.user = User.objects.create(username="hello")
#
#         class UserActionSchema(BaseModel):
#             pk:int
#
#         class UserAction(ContextAction[UserActionSchema, User]):
#
#
#     def get_class(self):
