# Future work

This list contains potential improvements and compatibility work for future
versions of `ha-mqtt-device`. Changes should preserve existing callers where
possible and include discovery, topic, payload, and lifecycle tests as
appropriate.

## Recently resolved

- **TODO-19 — Asynchronous provider test contract:** The short-lived publish
  test now expects the `hostname` keyword that `AioMqttProvider` forwards to
  `aiomqtt.Client`; the provider contract and existing callers remain unchanged.

- **TODO-01 — Shared discovery identity and component structure:** Regular
  components now advertise their platform and state topic separately, and
  `Device.configure()` publishes the flattened component-ID `cmps` map with
  deterministic global unique-ID validation. Regression coverage includes
  cross-platform coexistence and duplicate IDs.

- **TODO-03 — Camera and Image encoding behavior:** Camera and Image now
  default to raw image payloads by omitting `img_e`; explicit image encoding
  uses the documented `img_e` key. Image content types use `cont_type`, while
  unsupported Camera content types and generic text encoding are not emitted.

- **TODO-02 — Platform-specific discovery keys:** Camera, Cover, Event, Fan,
  Humidifier, Image, Infrared, Lawn Mower, Light, Number, and Switch now emit
  the documented discovery keys, topics, defaults, and omissions. Exact
  recording-provider regressions cover each correction.

## Discovery configuration

- **TODO-04 — Improve shared availability support**
  Add a common model for entity availability and ensure availability options
  are represented consistently across supported platforms.

- **TODO-05 — Review unsupported discovery options**
  Reconcile options such as optimistic mode, forced updates, reset payloads,
  templates, and camera content type with the documented MQTT schema.

## Entity capabilities

- **TODO-06 — Expand Cover and Device Tracker support**
  Add a documented approach for cover tilt and templates, and for Device
  Tracker location, battery, and JSON attributes.

- **TODO-07 — Improve Lawn Mower configuration**
  Decide whether separate command topics and custom state payloads should be
  supported as explicit API options.

- **TODO-08 — Complete Light white-channel support**
  Clarify and implement the documented white-channel command behavior without
  advertising unsupported state fields.

- **TODO-09 — Complete Fan direction and preset-reset support**
  Add documented direction and preset-reset configuration while preserving
  compatibility with existing defaults and callers.

- **TODO-10 — Add Text command validation**
  Decide how values outside configured minimum, maximum, or pattern constraints
  should be handled and apply that policy consistently.

- **TODO-11 — Review Event message handling**
  Decide whether raw bytes, configurable encodings, event templates, and reset
  behavior should be supported without breaking the current text-based API.

## Provider and lifecycle behavior

- **TODO-12 — Support reliable retained removal**
  Extend the provider contract as needed so device and entity removal can clear
  retained discovery messages reliably.

- **TODO-13 — Fix Device Tracker location publication**
  Publish location and attributes through a documented MQTT state/attributes
  arrangement while preserving presence-state behavior.

- **TODO-14 — Make multi-topic subscriptions idempotent**
  Prevent duplicate subscriptions when one of several related subscriptions
  fails and event registration is retried.

- **TODO-15 — Define reset and empty-payload behavior**
  Establish consistent publication and event semantics for reset and empty
  payloads across entities and providers.

## Documentation and verification

- **TODO-16 — Add exact discovery regression coverage**
  Test component maps, key names, topic fields, defaults, omissions, and
  standalone discovery for every supported platform.

- **TODO-17 — Add lifecycle and failure-path tests**
  Cover retained removal, availability, location attributes, subscription
  retries, encoding, and reset behavior with recording providers.

- **TODO-18 — Resolve Switch discovery compatibility**
  Verify Switch command and state key names against a version-matched Home
  Assistant reference before changing or documenting them.

- **TODO-20 — Keep examples synchronized with the public API**
  Add runnable examples for newly supported capabilities and avoid documenting
  fields that are not implemented and tested.
