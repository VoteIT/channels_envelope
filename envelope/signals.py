from django.dispatch import Signal

# On confirmed websocket connect or disconnect - note that user and connection might be none!
# Args:
#   consumer_name   The specific channel name for the consumer
#   user            object or None
#   user_pk         Primary key of user, should always exist
#   connection      Instance, see models
# Specifically for close:
#   close_code      Websocket close code
client_connect = Signal()
client_close = Signal()

# When a connection can't be verified or when it's closed normally, this is the place to hook cleanup and similar
# connection_terminated is normally sent before client_close, but since it could be sent by a script
# looking for dead connections, we don't know.
# connection        The Connection instance
# awol             "Absent Without Official Leave" - did you just disappear on us?
connection_terminated = Signal()

# When a user is subscribed to a channel, components can send state app messages to that channel,
# to make sure the user is caught up.
# Args:
#   context     The instance (object) this channel is for
#   user        object or None
#   app_state   Additional data passed along as a result of the subscribe command
channel_subscribed = Signal(providing_args=["context", "user", "app_state"])
