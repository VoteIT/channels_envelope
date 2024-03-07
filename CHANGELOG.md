# Changelog

## 1.0.2 (dev)

* Internal messages needed a custom job which wasn't intuitive or easy to debug.
  Passing along env as envelope_name instead.

## 1.0.1 (2024-03-07)

* RecheckSubscriptionsSchema subscriptions changed from set to list to 
  fix common serialization problems.
* PubSub and context channels accepts arguments `envelope_name` and `layer_name` in case
  they need to be overridden. (#2)

## 1.0.0 (2024-03-07)

* Initial release