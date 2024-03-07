# Envelope

**Note**: This is still experimental.

The readme is also work in progress...

## Introduction

While channels handles routing of messages within the async domain,
it's very open in terms of what gets transported.

Envelope is basically a system to structure and handle what different
messages mean and what they do.

Some core principles:

- **Readability above speed**
  Messages are serialized and deserialized as real objects that
  contain metadata about their origins and have methods on them.
  If you need to process 1M messages / sec you
  shouldn't use channels anyway.
- **Keep the async and sync world as separate as possible**
  If something needs to work with the database, defer it to a queue.
  Mixing these makes testing very hard and causes a lot of
  unexpected errors.
- **Pluggable**
  Allow other applications to build on this and inject functionality.
- **Predictability and type checking**
  We use Pydantic and Pythons type annotations. All valid message
  types must be registered as valid within each specific communication
  channel to be valid.
- **Message validation in different steps**
  First the basic message structure, then the payload itself
  and any expensive validations (like db queries) outside the async consumer.
- **No surprises**
  If a payload doesn't conform to an actual message
  that's supposed to be communicated through that channel, 
  it will be dropped.

## Prerequisites

* Basic Django knowledge.
* Read up on Django Channels and what it does - especially consumers.

## Dependencies - and why

* `RQ` with `django_rq` handles queues and deferred actions.
* `async-signals` for exactly what the package says. Since Django 5 this works in Djangos default signals,
we may refactor later.
* `pydantic` for all schemas, but with a bit of refactoring it would be possible to use any serializer.  

## Core concepts

### Envelope

Keeps track of what kind of messages to accept and how to handle them.
Performs serialization/deserialization and basic validation of message
payload. The registered envelopes always have a single direction via a single transport type,
for instance incoming websocket message, or outgoing websocket message.

Envelopes have short keys where only `t` is required.

#### Envelope schema - keys

* `t`  Type of message. Must exist within a message registry as key.
* `i`  Message trace id. Any error or response caused by 
  this message will be returned with the same trace id. It's a good idea 
  to pass this along to whatever action this message will cause. (A process queue for instance)
* `p`  Payload. Can be blank, normally a dict, but it's up to the envelopes
  schema to define this.
* `s`  State - an outbound message that's caused by another message 
  usually has state to indicate the result of the action. By using state
  and `i` together it's possible to build request/response functionality.

#### Default message states

* `a`  Acknowledged - message received and passed at least basic validation.
* `q`  Queued - Waiting within a process queue.
* `r`  Running - process worker started working on this task. 
  (It may be a good idea to send periodic updates with this marker if it's a long-running task)
* `s`  Success. Any kind of thumbs up reply, 
  doesn't have to be more dramatic than a ping/pong reply.
* `f`  Failed (Through exception or something else)

### Message

A class that knows what to do with a specific message. It may have
other actions it will perform when it's received, and it may define
a `Pydantic` schema for its payload.

Deserialized messages also have metadata that keeps track of their origin
and possible trace id.

### Message registry

Not much more than a dict where the key is a string corresponding to message
type, and the value is a message class.

Registries have names that correspond to their communication channel.
They're always one direction, but messages can be added to 
different registries.

Use names that explain the direction, for instance 'websocket_incoming'.

### Connection signals

The async signals `consumer_connected` and `consumer_closed` fires as soon as a connection
is accepted or closed. They in turn will que a job with the sync signals 
`connection_created` and `connection_closed`. That way the sync code won't block the connection.

```doctest

>>> from envelope.async_signals import consumer_connected, consumer_closed
>>> from envelope.signals import connection_created, connection_closed

```

### Message signals

Any recipient of a message will generate an event that other parts of the application can react to.
That way functionality can be added to messages. For instance any message that inherits
`envelope.core.message.AsyncRunnable` will call the method `run`.

Each message direction has its own async signal.


```doctest

>>> from envelope.async_signals import incoming_websocket_message
>>> from envelope.async_signals import outgoing_websocket_message
>>> from envelope.async_signals import outgoing_websocket_error

```

## Settings

Most of the required settings will be handled by django_rq and channels. But there are some aspects
of envelope that can be tweaked.

Remember that message registries will contain some mesasges by default - if you don't want that,
make sure to clear them.

ENVELOPE_CONNECTIONS_QUEUE - default: None

: Name of the `RQ` queue to use for jobs that will create Connection objects.
`None` disables functionality.

ENVELOPE_TIMESTAMP_QUEUE - default: None

: Name of the `RQ` queue to use for timestamp updates for Connection objects.
`None` disables functionality.

ENVELOPE_CONNECTION_UPDATE_INTERVAL - in seconds, default: 180

: How often should a timestamp job be queued? `None` disables functionality.

ENVELOPE_BATCH_MESSAGE - default: `envelope.messages.common.BatchMessage`

: Which class to use for batch messages.

ENVELOPE_SENDER_UTIL - default: `envelope.utils.SenderUtil`

: Which class to use for sender util.


ENVELOPE_ALLOW_UNAUTHENTICATED - default: False

: Experimental

## Usage examples

### Sending messages when content is changed

In this example, we'll signal the users own channel when the user object is changed.
A user that has several tabs connected to the same server will see the change in all tabs instantly.

Make sure envelope.app.user_channel is in INSTALLED_APPS for this example to work.

```doctest python

>>> from pydantic import BaseModel
>>> from django.contrib.auth import get_user_model
>>> from django.dispatch import receiver
>>> from django.db.models.signals import post_save
>>> from envelope.core.message import Message
>>> from envelope.app.user_channel.channel import UserChannel
>>> from envelope import WS_OUTGOING
>>> from envelope.decorators import add_message
    
>>> User = get_user_model()
    
>>> class UserSchema(BaseModel):
...     username: str
...     first_name: str = ""
...     last_name: str = ""
...     email: str = ""
    
    
>>> @add_message(WS_OUTGOING)
... class UserDetails(Message):
...     name = "user.details"
...     schema = UserSchema
    
    
>>> @receiver(post_save, sender=User)
... def send_user_details_on_change(instance: User, **kwargs):
...     data = {k: getattr(instance, k) for k in UserSchema.schema()['properties']}
...     msg = UserDetails(**data)
...     channel = UserChannel.from_instance(instance)
...     channel.sync_publish(msg)
    
# We'll mock the channels layer to catch the message
# By default, sync messages will only be sent when the transaction commits
# to avoid sending messages for things that may not happen.

>>> from json import loads
>>> from unittest.mock import patch
>>> from channels.layers import get_channel_layer
>>> layer = get_channel_layer()

# Test here is Djangos instance of TestCase
>>> with patch.object(layer, 'group_send') as mock_send:
...     with test.captureOnCommitCallbacks(execute=True):
...         new_user = User.objects.create(username="jane", first_name="Jane", last_name="Doe")
...         first = mock_send.called  # No message yet since db hasn't committed!
...     second = mock_send.called


>>> first
False

>>> second
True

>>> mock_send.mock_calls[0].args[0] == f"user_{new_user.pk}"
True

>>> data = loads(mock_send.mock_calls[0].args[1]['text_data'])
>>> data['p']
{'username': 'jane', 'first_name': 'Jane', 'last_name': 'Doe', 'email': ''}

```
