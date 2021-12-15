# Envelope

Note: This is still experimental. Don't use it!

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
  and then maybe actual objects.
- **No surprises**
  If a payload doesn't conform to an actual message
  that's supposed to be communicated through that channel, 
  it will be dropped.

## Prerequesites

Read up on Django Channels and what it does - especially consumers.
In this example we'll be using a mock consumer. We'll focus
on what happens after the Channels consumer has received a message.

We'll also prep replies to be sent to a websocket connection or another
channels consumer.

## Core concepts

### Envelope

Keeps track of what kind of messages to accept and how to handle them.
Performs serialization/deserialisation and basic validation of message
payload.

Envelopes have short keys where only 't' is required.

#### Envelope schema - keys

* `t`  Type of message. Must exist within a message registry as key.
* `i`  Message trace id. Any error or response caused by 
  this message will be returned with the same trace id. It's a good idea 
  to pass this along to whatever action this message will cause. (A process queue for instance)
* `p`  Payload. Can be blank, normally a dict but it's up to the envelopes
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
a `Pydantic` schema for it's payload.

Deserialized messages also have metadata that keeps track of their origin
and possible trace id.

### Message registry

Not much more than a dict where the key is a string corresponding to message
type, and the value is a message class.

Registries have names that correspond to their communication channel.
They're always one direction, but messages can be added to 
different registries.

Use names that explain the direction, for instance 'websocket_incoming'.

### Handler

Checks incoming messages for specific patterns and perform actions on them.
A simle example would be to install a print-handler and simply run
print() on the message payload.

The default handlers AsyncRunnableHandler and DeferredJobHandler
checks for a specific message subclass.

### Handler registry

Also a dict-like registry. It may loop through handlers and check them
against a specific message.

As with messages, handler registries must also be named and unless
you want to trigger things manually it's a good idea to use the same
name as the communication channel. (See example below)

## Code example - building a message ping/pong ("Hello")

First off we'll create a message regitries, and handler registries
where we'll store message classes and message handlers.

Note that registries are meant to be used for messages traveling in one
direction. So you'll want several registries for each transport and direction.

For this demonstration simply incoming and outgoing.

``` python

>>> from envelope.registry import MessageRegistry, HandlerRegistry

>>> incoming_messages = MessageRegistry('incoming')
>>> incoming_handlers = HandlerRegistry('incoming')

>>> outgoing_messages = MessageRegistry('outgoing')
>>> outgoing_handlers = HandlerRegistry('outgoing')

```

These are needed to construct an envelope.

Envelopes pack and unpack messages depending on their direction. They
may also perform extra validation on messages if debug
mode is on.

Envelopes also need a schema, we'll use the default one here.

``` python

>>> from envelope.envelope import Envelope
>>> from envelope.envelope import EnvelopeSchema
>>> from envelope.envelope import OutgoingEnvelopeSchema

>>> class IncomingEnvelope(Envelope):
...     schema = EnvelopeSchema
...     message_registry = incoming_messages
...     handler_registry = incoming_handlers
...

>>> class OutgoingEnvelope(Envelope):
...     schema = OutgoingEnvelopeSchema  # Contains state (s) too!
...     message_registry = outgoing_messages
...     handler_registry = outgoing_handlers
...

```

Construct a message by inheriting from the Message class or
any of its subclasses.

It requires a name - this will be a unique 
identifier for this message type. 

This message also has a schema with required items.

To be usable, the message must also be added to one or more message
registries. This is done via the `add_message` decorator.

We'll also add the run-method to the message and use the AsyncRunnable
message class. It's simply a message that has an async function 
that should be run by the consumer.

``` python

>>> from envelope.messages import Message
>>> from envelope.messages import AsyncRunnable
>>> from envelope.decorators import add_message
>>> from envelope.utils import websocket_send
>>> from pydantic import BaseModel

>>> class HelloSchema(BaseModel):
...     name: str
...

>>> @add_message('incoming')
... class HelloMessage(AsyncRunnable):
...     name='hello'
...     schema = HelloSchema
...     data: HelloSchema
...
...     async def run(self, consumer):
...         msg = HelloResponseMessage.from_message(self, msg=f"Hello you too {self.data.name}!")
...         msg.validate()
...         await consumer.send_ws_message(msg, state=self.SUCCESS)
...

>>> 'hello' in incoming_messages
True

>>> class HelloResponseSchema(BaseModel):
...     msg: str
...

>>> @add_message('outgoing')
... class HelloResponseMessage(Message):
...     name = 'hello_response'  # <- Only needs to be unique per registry
...     schema = HelloResponseSchema
...     data: HelloResponseSchema
...

>>> 'hello_response' in outgoing_messages
True

```

So we have a response and a reply.

Envelopes idea is to inject functionality rather than build custom
message csonumers. This is done via handlers. 
Each message direction can have its own handlers, and the
handler decides if it should do something with the message.

We need to add the `AsyncRunnableHandler` to our registries
to make it work.

``` python

>>> from envelope.handlers.async_runnable import AsyncRunnableHandler

>>> incoming_handlers.add(AsyncRunnableHandler)
>>> AsyncRunnableHandler.name in incoming_handlers
True

```

To run this example we'll mock our consumer that already executes
handlers,

Note the `i` key here, it will be added to the outgoing message
so we know it's a result of that specific operation. This is optional,
but very usable for error handling and similar. Think of it as a way to try
to reinvent the request/response pattern.

``` python

>>> import json
>>> data={'t': 'hello', 'i': 'msg-1', 'p': {'name': 'Jane'}}
>>> payload = json.dumps(data)

# Payload will be the package a websocket comsumer receives

>>> from envelope.consumers.websocket import EnvelopeWebsocketConsumer
>>> consumer = EnvelopeWebsocketConsumer(enable_connection_signals=False)
>>> consumer.channel_name = 'abc'  # This will be set by channels during normal operation

# We'll replace the outgoing and incoming default message registries
# with the ones we built during this demonstration.

>>> consumer.incoming_envelope = IncomingEnvelope
>>> consumer.outgoing_envelope = OutgoingEnvelope

# We use mock to check if the consumer sends something
# This will of course block real outgoing messages.

>>> from unittest import mock
>>> consumer.send = mock.AsyncMock()

# We need async_to_sync to test receiving a message
# since we're in syncworld right now.

>>> from asgiref.sync import async_to_sync
>>> async_to_sync(consumer.receive)(text_data=payload)

If all went well we'll have caught an outgoing text payload
that we can use the outgoing envelope to catch

>>> consumer.send.called
True

>>> outgoing_env=consumer.send.mock_calls[0].kwargs.get('envelope')
>>> outgoing_env.data.t
'hello_response'

# And the trace id is part of the outbound message too
>>> outgoing_env.data.i
'msg-1'

>>> outgoing_env.data.s == 's'  # Success
True

```

Same example once again, but this time we'll cause a few errors.
Error messages inherit the exception class and have their own registry.
Errors always have the state 'f' - as in failed.

Frontend developers can turn messages with id into promises and have
them resolve on success or fail.

Here's what happens if you specify a message type that doesn't exist:

``` python

>>> data={'t': 'i dont exist', 'i': 'msg-2'}
>>> payload_bad_type = json.dumps(data)
>>> async_to_sync(consumer.receive)(text_data=payload_bad_type)
>>> outgoing_env=consumer.send.mock_calls[1].kwargs.get('envelope')
>>> outgoing_env.data.t
'error.msg_type'
>>> outgoing_env.data.i
'msg-2'

# The payload here is basically 'what was this checked against?'
>>> outgoing_env.data.p
{'msg': None, 'type_name': 'i dont exist', 'registry': 'incoming'}
>>> outgoing_env.data.s == 'f'
True

```

Or if you cause a validation error in Pydantic:

``` python

>>> data={'t': 'hello', 'i': 'msg-3'}  # Lacks 'name' in payload!
>>> payload_bad_name = json.dumps(data)
>>> async_to_sync(consumer.receive)(text_data=payload_bad_name)
>>> outgoing_env=consumer.send.mock_calls[2].kwargs.get('envelope')
>>> outgoing_env.data.t
'error.validation'
>>> outgoing_env.data.i
'msg-3'

# Errors here are exactly the ValidationError from pydantic.
>>> outgoing_env.data.p
{'msg': None, 'errors': [{'loc': ('name',), 'msg': 'field required', 'type': 'value_error.missing'}]}
>>> outgoing_env.data.s == 'f'
True

```

## Messages that perform actions

Since websockets and channels are part of the async domain and Django's tied to sync code,
we'll need to bridge these to somehow.

We mainly handle this by deferring actions to a queue. (We already built connections for RQ)

Actions would basically be what you would do through a REST API, and many
times it might be better to do those actions via REST.

Anything performing a background task should inherit the class `DeferredJob`.
It needs a few more items. Here's a basic example to fetch a users name.

Since we're inside the worker when any actions are processed we don't have access to the
consumer and its method. To send messages outside of the consumer we'll use
`websocket_send`. And for that to work we need to add the messages to the default websocket
channels.

Note: We're going to run these messages like unittests rather than through workers since
this is just documentation :)

``` python

>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> jane_doe = User.objects.create(username='jane', first_name='Jane', last_name='Doe')
>>> isinstance(jane_doe, User)
True

>>> from envelope.messages.actions import DeferredJob
>>> from envelope.utils import websocket_send
>>> from envelope import WS_INCOMING, WS_OUTGOING

>>> class FetchUserSchema(BaseModel):
...     username: str
...


>>> @add_message(WS_INCOMING)
... class FetchUser(DeferredJob[FetchUserSchema]):
...     name = 'user.fetch'
...     schema = FetchUserSchema
...
...     def run_job(self):
...         # This is what's running inside the worker
...         user = User.objects.get(username=self.data.username)
...         # To use _orm we need orm mode enabled for the schema the response uses. See below
...         response = UserData.from_message(self, _orm=user)
...         websocket_send(response, self.mm.consumer_name, state=self.SUCCESS)
...         return response  # To make unittesting easier!


>>> class UserSchema(BaseModel):
...     username: str
...     first_name: str
...     last_name: str
...     pk: int
...
...     class Config:
...         orm_mode=True


>>> @add_message(WS_OUTGOING)
... class UserData(Message[UserSchema]):
...     name = "user.data"
...     schema = UserSchema
...

# And let's try it out - we'll fake message meta (mm)

>>> msg = FetchUser(mm={'consumer_name': 'abc'}, username='jane')

Normally workers validate the messages before they call run_job, so we'll do that too.

>>> msg.validate()
>>> response = msg.run_job()
>>> response.name
'user.data'
>>> data = response.data.dict()
>>> 'pk' in data
True
>>> data.pop('pk') == jane_doe.pk
True
>>> data
{'username': 'jane', 'first_name': 'Jane', 'last_name': 'Doe'}


```

This common operation can be shortened a bit if we think about the specific user as a context
this action's performed on. That way we can also add permissions and similar.
(We recommend using Django `rules` for instance)

We'll use `ContextAction` together with a schema, 
and a model to create an update action for our user.

`ContextAction` is a subclass of `DeferredJob` so it will normally be run inside a worker aswell.

We won't much about with permissions for this demonstration, 
so let's just add a superuser to test against.

``` python


>>> from typing import Optional
>>> from envelope.messages.actions import ContextAction

>>> class UpdateUserSchema(BaseModel):
...     pk: int
...     first_name: Optional[str]
...     last_name: Optional[str]
...


>>> @add_message(WS_INCOMING)
... class UpdateUser(ContextAction[UpdateUserSchema, User]):
...     name = 'user.update'
...     schema = UpdateUserSchema
...     model = User
...     context_pk_attr = 'pk'
...     permission = 'user.change_user'
...
...     def run_job(self):
...         self.assert_perm()
...         user: User = self.context  # Fetched based on schema
...         to_modify = self.data.dict(exclude={'pk'}, exclude_none=True)
...         if to_modify:
...             for (k, v) in to_modify.items():
...                 setattr(user, k, v)
...             user.save()
...         response = UserData.from_message(self, _orm=user)
...         websocket_send(response, self.mm.consumer_name, state=self.SUCCESS)
...         return response

A difference here is that we need to specify user to make this work.
This will be attached to message meta by the consumer, so we'll add it manually fo this test.

>>> jane_doe.is_superuser = True
>>> jane_doe.save()
>>> msg = UpdateUser(mm={'consumer_name': 'abc', 'user_pk': jane_doe.pk}, pk=jane_doe.pk, first_name='Jennifer')
>>> msg.validate()
>>> response = msg.run_job()
>>> response.name
'user.data'
>>> data = response.data.dict(exclude={'pk'})
>>> data
{'username': 'jane', 'first_name': 'Jennifer', 'last_name': 'Doe'}

Since Jane/Jennifer turned superuser, this worked out. Lets turn that off and catch the error.
The method that checks permissions is called `allowed`, it will simply return a bool.
If we run assert_perm instead we'll get an exception with some details.

>>> jane_doe.is_superuser = False
>>> jane_doe.save()
>>> from envelope.messages.errors import UnauthorizedError

Messages cache user objects, we'll simply refresh it

>>> msg.user.refresh_from_db()
>>> error=None
>>> try:
...     msg.assert_perm()
... except UnauthorizedError as err:
...     error=err
...

>>> isinstance(error, UnauthorizedError)
True
>>> error.name
'error.unauthorized'

While errors are exceptions, they're also messages that can be sent and accessed.
They can even cause side-effects like signal logut.

>>> data = error.data.dict()
>>> data['key']
'pk'


>>> int(data['value']) == jane_doe.pk
True
>>> data['permission']
'user.change_user'

This is djangos natural key, that the model will be converted to
>>> data['model'] == f"{User._meta.app_label}.{User._meta.model_name.lower()}"
True

```
