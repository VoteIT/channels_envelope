"""
Note - these are the sync signals - there are async signals too!
"""
from django.dispatch import Signal


# When a user is subscribed to a channel, components can send state app messages to that channel,
# to make sure the user is caught up.
# Args:
#   context     The instance (object) this channel is for
#   user        object or None
#   app_state   Additional data passed along as a result of the subscribe command
channel_subscribed = Signal()


# Args:
#   instance        Connection instance
#   sender          Connection class
# Specifically for close:
#   close_code      Websocket close code
client_connect = Signal()
client_close = Signal()
