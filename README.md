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
Performs serialization/deserialization and basic validation of message
payload. The registered envelopes always have a single direction via a single transport type,
for instance incoming websocket message, or outgoing websocket message.

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

### Connection events

The async signals `consumer_connected` and `consumer_disconnected` fires as soon as a connection
is accepted or closed. They in turn will que a job with the sync signals 
`connection_created` and `connection_closed`. That way the sync code won't block the connection.

### Message events

Any recipient of a message will generate an event that other parts of the application can react to.
That way functionality can be added to messages. For instance any message that inherits
`envelope.core.message.AsyncRunnable` will call the method `run`. 
