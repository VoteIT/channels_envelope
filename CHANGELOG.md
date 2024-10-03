# Changelog

## 1.0.4 (unreleased)

* Added setting `ENVELOPE_USER_CHANNEL_SEND_SUBSCRIBE` to send a subscribe message to consumer rather than just adding
  the client to the users channel.
* `user_logged_out` signal causes a close message to be sent on the user channel, so consumers will be disconnected. 
* Loading RQ-job via message class for deferred jobs, to make the code easier to follow + overrides simpler.

## 1.0.3 (2024-03-13)

* Fixed problem with consumer not catching validation errors
deeper down in message processing.

## 1.0.2 (2024-03-08)

* Internal messages needed a custom job which wasn't intuitive or easy to debug.
  Passing along env as envelope_name instead.

## 1.0.1 (2024-03-07)

* RecheckSubscriptionsSchema subscriptions changed from set to list to 
  fix common serialization problems.
* PubSub and context channels accepts arguments `envelope_name` and `layer_name` in case
  they need to be overridden. (#2)

## 1.0.0 (2024-03-07)

* Initial release