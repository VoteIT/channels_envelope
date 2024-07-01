# Changelog

## 1.0.4 (unreleased)

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