from django.dispatch import Signal

# On confirmed websocket connect or disconnect - note that user and connection might be none!
# Args:
#   consumer_name   The specific channel name for the consumer
#   user            User object or None
#   user_pk         Primary key of user, should always exist
#   connection      Connection instance, see models
#   close_code      Websocket close code
client_connect = Signal(
    providing_args=["consumer_name", "user", "user_pk", "connection"]
)
client_close = Signal(
    providing_args=["consumer_name", "user", "user_pk", "connection", "close_code"]
)

# When a connection can't be verified or when it's closed normally, this is the place to hook cleanup and similar
# connection_terminated is normally sent before client_close, but since it could be sent by a script
# looking for dead connections, we don't know.
# connection        The Connection instance
# awol             "Absent Without Official Leave" - did you just disappear on us?
connection_terminated = Signal(providing_args=["connection", "awol"])

# When a user is subscribed to a channel, components can send state app messages to that channel,
# to make sure the user is caught up.
channel_subscribed = Signal(providing_args=["context", "user", "app_state"])
