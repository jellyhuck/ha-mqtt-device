# ha-mqtt-device

A thin Python library for creating and maintaining [Home Assistant](https://www.home-assistant.io/) devices that are discoverable via [MQTT device discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery). Individual entities associated with a device can be added, updated, and removed through the same API.

## Features

- **Device discovery**: publish the discovery payload Home Assistant needs to automatically pick up your device over MQTT.
- **Entity management**: add and maintain multiple entities (sensors, switches, binary sensors, cameras, etc.) that belong to a device.
- **Event subscriptions**: entities can subscribe to MQTT topics and deliver updates — for example switch commands from Home Assistant — to your async callbacks as `Event` objects.
- **Thin and focused**: no heavy framework — just the abstractions needed to model a device and its entities.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) for development and dependency management
- [`aiomqtt`](https://aiomqtt.deroet.com/) for the MQTT provider (`pip install "ha-mqtt-device[mqtt]"`)

## Usage

### MQTT provider

The library communicates over MQTT through an [`MqttProvider`](src/ha_mqtt_device/provider.py).
The default implementation, [`AioMqttProvider`](src/ha_mqtt_device/aio_provider.py), is
backed by `aiomqtt` and installed with the `mqtt` extra:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider

async def on_command(message) -> None:
    print(f"{message.topic}: {message.payload!r}")

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883, username="user", password="pass")

    # Messages are delivered to the callback as Message(topic, payload) objects.
    await provider.subscribe("home/device/set", on_command)

    # Publish works standalone or while run() is active.
    await provider.publish("home/device/state", '{"state": "ON"}')

    # run() starts the message loop in a background task and returns
    # immediately; stop() shuts it down and drains in-flight callbacks.
    # "async with" ties the two together for the block's lifetime.
    async with provider:
        await asyncio.Event().wait()  # keep the loop alive until interrupted

asyncio.run(main())
```

### Device discovery

Create a [`DeviceInfo`](src/ha_mqtt_device/device_info.py) with just a device id
and a name — everything else has a sane default — then build a
[`Device`](src/ha_mqtt_device/device.py) on top of the provider:

```python
import asyncio
import json

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(
        device_id="my_device_id",
        name="My device",
        manufacturer="Acme",
        model="Widget",
        sw_version="1.0.0",
    )

    device = Device(provider, info)

    # Device is an async context manager: entering the block publishes the
    # discovery config and announces the device as "online"; leaving the block
    # announces it as "offline" — even when the body raises.
    async with device:
        # ... run the provider and update the device ...

    # Leaving the block announced "offline". To make Home Assistant forget the
    # device, publish an empty discovery config with remove().
    await device.remove()

asyncio.run(main())
```

The discovery payload is published to `homeassistant/device/<device_id>/config`
with the `dev`, `o`, `~`, and `avty` keys. The `~` prefix is registered as
`homeassistant/device/<device_id>` — the same prefix as the discovery topic —
and individual topics use `~` shorthand, so the availability topic defaults to
`~/status`, which resolves to `homeassistant/device/<device_id>/status` when
the device publishes its state. `DeviceInfo` also serializes to and from JSON
via `to_json()` / `from_json()`.

### Entities

Entities (sensors, binary sensors, numbers, switches, buttons, event entities,
images, cameras, etc.) are attached
to a device by passing them to the `Device` constructor. Each entity needs a
globally unique `unique_id`; entity topics follow the convention
`~/<unique_id>/<topic>`, so a binary sensor with `unique_id="is_led_on"`
publishes its state to `homeassistant/device/<device_id>/is_led_on/state`. The
device's `configure()` publishes the entities as `cmps` entries in the
discovery payload, and they inherit the device-level availability — no
per-entity availability config is needed.

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, BinarySensor, Device, DeviceInfo

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    led = BinarySensor(
        unique_id="is_led_on",
        name="LED state",
        device_class="light",
    )
    device = Device(provider, info, entities=[led])

    async with device:
        await led.set_state(True)   # publishes "ON" to ~/is_led_on/state
        await asyncio.sleep(1)
        await led.set_state(False)  # publishes "OFF"

    await device.remove()

asyncio.run(main())
```

Sensors are read-only like binary sensors, but report a text or numeric value
instead of a boolean. `set_state()` accepts `str`, `int`, or `float` and
publishes the stringified value to `~/<unique_id>/state`. Optional fields
describe the reading: `unit_of_measurement` (`unit_of_meas`), `state_class`
(`stat_cla`), `device_class` (`dev_cla`), `expire_after` (`exp_aft`),
`force_update` (`frc_upd`), and `suggested_display_precision` (`sug_dsp_prc`):

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Sensor

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    temperature = Sensor(
        unique_id="temperature",
        name="Temperature",
        device_class="temperature",
        unit_of_measurement="°C",
        state_class="measurement",
    )
    device = Device(provider, info, entities=[temperature])

    async with device:
        await temperature.set_state(21.5)  # publishes "21.5" to ~/temperature/state
        await asyncio.sleep(1)
        await temperature.set_state(21.7)

    await device.remove()

asyncio.run(main())
```

Switches add a command topic on top of the state topic. The device publishes
its state with `set_state()`, and Home Assistant commands are delivered as
[`Event`](src/ha_mqtt_device/event.py) objects to the async callback registered
with `on_event()` — the callback is invoked for every command received on
`~/<unique_id>/command`, and `set_state()` does not trigger it:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Switch

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    relay = Switch(unique_id="relay_1", name="Relay")
    device = Device(provider, info, entities=[relay])

    async def on_command(event: Event) -> None:
        # event.state is "on" or "off" (None for unknown payloads).
        print(f"{event.topic_type}: {event.message!r} -> {event.state}")
        await relay.set_state(event.state == "on")

    async with device:
        # Subscribes to ~/relay_1/command; commands from Home Assistant
        # are delivered to on_command.
        await relay.on_event(on_command)
        await relay.set_state(True)  # publishes "ON" to ~/relay_1/state
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

Numbers combine a numeric state topic with a command topic, like a switch for
values. The device publishes the current value with `set_state()`, and Home
Assistant commands are delivered as [`Event`](src/ha_mqtt_device/event.py)
objects to the async callback registered with `on_event()` — `event.state` is
the raw payload when it parses as a number (for example `"75"`) and `None`
otherwise. Bounds, step, and mode are advertised in the discovery config
(`min`, `max`, `step`, `mode`) and omitted when they match the defaults:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Number

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    dimmer = Number(
        unique_id="dimmer",
        name="Dimmer",
        min_value=0,
        max_value=100,
        step=1,
        mode="box",
        unit_of_measurement="%",
    )
    device = Device(provider, info, entities=[dimmer])

    async def on_command(event: Event) -> None:
        # event.state is the payload when it parses as a number
        # (e.g. "75"), None for unknown payloads.
        print(f"{event.topic_type}: {event.message!r} -> {event.state}")
        if event.state is not None:
            await dimmer.set_state(float(event.state))

    async with device:
        # Subscribes to ~/dimmer/command; values from Home Assistant
        # are delivered to on_command.
        await dimmer.on_event(on_command)
        await dimmer.set_state(75.0)  # publishes "75.0" to ~/dimmer/state
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

Covers are bidirectional like switches and numbers, with two incoming and two
outgoing topics. The device publishes the cover's state — one of `"open"`,
`"opening"`, `"closed"`, `"closing"`, or `"stopped"` — with `set_state()` to
`~/<unique_id>/state`, and its position (0–100) with `set_position()` to
`~/<unique_id>/position`. Home Assistant commands are delivered as
[`Event`](src/ha_mqtt_device/event.py) objects to the async callback
registered with `on_event()`:
- on the command topic `~/<unique_id>/command`, `event.event_type` is
  `"command"` and `event.state` is `"open"`, `"close"`, or `"stop"` (`None`
  for unknown payloads);
- on the set-position topic `~/<unique_id>/set_position`, `event.event_type`
  is `"set_position"` and `event.state` is the payload when it parses as a
  number (`None` otherwise).

The discovery config advertises the four topics as `sta_t`, `cmd_t`, `pos_t`,
and `set_pos_t` — note that the cover's state topic key is `sta_t`, not the
base `p` — and omits `pl_open`/`pl_cls`/`pl_stop`, the lowercase state
payloads, and `pos_open`/`pos_clsd` (100/0) when they match the defaults:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Cover, Device, DeviceInfo, Event

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    blinds = Cover(unique_id="blinds", name="Blinds", device_class="blind")
    device = Device(provider, info, entities=[blinds])

    async def on_cover_event(event: Event) -> None:
        if event.event_type == "command":
            # event.state is "open", "close", or "stop" (None for unknown).
            print(f"{event.topic_type}: {event.message!r} -> {event.state}")
            if event.state == "open":
                await blinds.set_state("open")
                await blinds.set_position(100)
        elif event.state is not None:
            # A position command; event.state is the payload (e.g. "50").
            await blinds.set_position(int(event.state))

    async with device:
        # Subscribes to ~/blinds/command and ~/blinds/set_position; commands
        # from Home Assistant are delivered to on_cover_event.
        await blinds.on_event(on_cover_event)
        await blinds.set_state("closed")  # publishes "closed" to ~/blinds/state
        await blinds.set_position(0)      # publishes "0" to ~/blinds/position
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

Buttons work in the opposite direction: Home Assistant shows the button and,
when pressed, publishes `payload_press` (default `"PRESS"`) to
`~/<unique_id>/command`. The device never publishes anything for a button —
there is no state topic. Registering a callback with `on_event()` delivers
each press as an [`Event`](src/ha_mqtt_device/event.py):

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Button, Device, DeviceInfo, Event

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    restart = Button(unique_id="restart", name="Restart", device_class="restart")
    device = Device(provider, info, entities=[restart])

    async def on_press(event: Event) -> None:
        # event.state is "press" (None for unknown payloads).
        print(f"{event.topic_type}: {event.message!r} -> {event.state}")
        # ... trigger the action the button represents ...

    async with device:
        # Subscribes to ~/restart/command; presses from Home Assistant
        # are delivered to on_press.
        await restart.on_event(on_press)
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

Event entities publish transient events to Home Assistant — for example a
doorbell that fires `doorbell_pressed`. Unlike switches and buttons there is
no command topic: events flow from the device to Home Assistant only, so the
entity has no `on_event()` callback. The `event_types` list is required —
Home Assistant only fires events whose type is declared — and `set_event()`
publishes a type to `~/<unique_id>/state`, which Home Assistant turns into an
HA event that automations can trigger on:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, EventEntity

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    doorbell = EventEntity(
        unique_id="doorbell",
        name="Doorbell",
        device_class="doorbell",
        event_types=["doorbell_pressed", "doorbell_long_press"],
    )
    device = Device(provider, info, entities=[doorbell])

    async with device:
        # Fires an HA event "doorbell_pressed" on ~/doorbell/state.
        await doorbell.set_event("doorbell_pressed")
        await asyncio.sleep(1)
        await doorbell.set_event("doorbell_long_press")

    await device.remove()

asyncio.run(main())
```

Images publish image data — for example a camera snapshot — from the device to
Home Assistant. Like sensors they are read-only: there is no command topic and
no `on_event()` callback. `set_image()` publishes the payload verbatim to
`~/<unique_id>/image`; with the default `encoding` (`"b64"`) Home Assistant
base64-decodes it, so pass base64-encoded bytes (or set `encoding` to a
non-`"b64"` value and publish raw image bytes). `content_type` (`cont_t`) and
`encoding` (`enc`) are omitted from the discovery config when they match the
defaults:

```python
import asyncio
import base64

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Image

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    camera = Image(unique_id="camera", name="Camera")
    device = Device(provider, info, entities=[camera])

    async with device:
        # Publishes base64-encoded bytes to ~/camera/image.
        await camera.set_image(base64.b64encode(b"...jpeg data..."))
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

Cameras publish live image frames — for example a video stream's latest frame
— from the device to Home Assistant. They are read-only like images (Home
Assistant subscribes to the image topic and displays every frame), so there is
no command topic and no `on_event()` callback. `set_image()` publishes the
payload verbatim to `~/<unique_id>/image`; with the default `encoding`
(`"b64"`) Home Assistant base64-decodes it, so pass base64-encoded bytes (or
set `encoding` to a non-`"b64"` value and publish raw image bytes).
`content_type` (`cont_t`) and `encoding` (`enc`) are omitted from the
discovery config when they match the defaults; the single image topic is
advertised as `t` (the Home Assistant camera discovery key):

```python
import asyncio
import base64

from ha_mqtt_device import AioMqttProvider, Camera, Device, DeviceInfo

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    camera = Camera(unique_id="front_door", name="Front door camera")
    device = Device(provider, info, entities=[camera])

    async with device:
        # Publishes base64-encoded bytes to ~/front_door/image.
        await camera.set_image(base64.b64encode(b"...jpeg data..."))
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

## Development

This project is managed with `uv`. Common commands:

| Task          | Command                        |
| ------------- | ------------------------------ |
| Run tests     | `uv run pytest`                |
| Format code   | `uv format`                    |
| Lint          | `uv run ruff check`            |
| Type checking | `uv run mypy .`                |
| Build         | `uv build`                     |

### Project layout

```
src/ha_mqtt_device/   # library source
tests/                # test suite
pyproject.toml        # project metadata and tool configuration
```

## License

[MIT](LICENSE)
