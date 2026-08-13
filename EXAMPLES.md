# Examples

This document walks through the library with runnable examples: the MQTT
provider, device discovery, and one section per entity type. Entities that
Home Assistant supports over MQTT but this library does not implement yet are
listed in place with a TODO note.

All examples assume an MQTT broker on `localhost:1883` and expect Python
3.14+ with `ha-mqtt-device[mqtt]` installed (see the
[README](README.md) for setup).

## MQTT provider

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

## Device discovery

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

## Entities

Entities (sensors, binary sensors, numbers, dates, datetimes, switches,
buttons, event entities, humidifiers, images, cameras, device trackers,
infrared emitters/receivers, etc.) are attached
to a device by passing them to the `Device` constructor. Each entity needs a
globally unique `unique_id`; entity topics follow the convention
`~/<unique_id>/<topic>`, so a binary sensor with `unique_id="is_led_on"`
publishes its state to `homeassistant/device/<device_id>/is_led_on/state`. The
device's `configure()` publishes the entities as `cmps` entries in the
discovery payload, and they inherit the device-level availability — no
per-entity availability config is needed.

### Alarm control panel

> TODO: not yet supported — there is no AlarmControlPanel entity in the
> library yet. Tracked as future work.

### Light

Lights use grouped topics: power is published to `~/lamp/state/power` and
commands arrive on `~/lamp/command/power`; optional brightness and color
features use the same `state`/`command` grouping. See the runnable
[`examples/light.py`](examples/light.py) example:

```python
from ha_mqtt_device import Light

light = Light(
    unique_id="lamp",
    name="Lamp",
    brightness_enabled=True,
    rgb_enabled=True,
    effect_enabled=True,
    effect_list=["rainbow", "pulse"],
)
await light.set_state(True)
await light.set_brightness(75)
await light.set_rgb((255, 80, 20))
```

### Binary sensor

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

### Button

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

### Camera

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

### Cover

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

### Climate (HVAC)

Climate entities model a thermostat/HVAC: the device publishes the current
temperature with `set_current_temperature()` to
`~/<unique_id>/current_temperature`, the target temperature with
`set_target_temperature()` to `~/<unique_id>/temperature`, the HVAC mode with
`set_mode()` to `~/<unique_id>/mode`, and the current action (for example
`"heating"` or `"cooling"`) with `set_action()` to `~/<unique_id>/action`.
Home Assistant commands are delivered as
[`Event`](src/ha_mqtt_device/event.py) objects to the async callback
registered with `on_event()`:
- on the temperature command topic `~/<unique_id>/temperature_command`,
  `event.event_type` is `"temperature"` and `event.state` is the payload when
  it parses as a number (for example `"21.5"`, `None` otherwise);
- on the mode command topic `~/<unique_id>/mode_command`, `event.event_type`
  is `"mode"` and `event.state` is the payload verbatim (the requested mode).

`set_mode()` rejects modes not in the optional `modes` list. The discovery
config advertises the six topics as `curr_temp_t`, `temp_stat_t`, `temp_cmd_t`,
`mode_stat_t`, `mode_cmd_t`, and `act_t` (there is no single state topic, so no
`p`), and omits `modes`, `temp_unit`, `min_temp`, `max_temp`, `temp_step`,
`prec`, `init`, `mode_opt`, and `temp_opt` when they are unset:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Climate, Device, DeviceInfo, Event

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    thermostat = Climate(
        unique_id="thermostat",
        name="Thermostat",
        modes=["off", "heat", "cool", "auto"],
        temperature_unit="C",
        min_temp=10,
        max_temp=30,
        temp_step=0.5,
    )
    device = Device(provider, info, entities=[thermostat])

    async def on_climate_event(event: Event) -> None:
        if event.event_type == "temperature" and event.state is not None:
            # event.state is the requested temperature (e.g. "21.5").
            await thermostat.set_target_temperature(float(event.state))
        elif event.event_type == "mode":
            # event.state is the requested mode (e.g. "heat").
            await thermostat.set_mode(event.state)

    async with device:
        # Subscribes to ~/thermostat/temperature_command and
        # ~/thermostat/mode_command; commands from Home Assistant are
        # delivered to on_climate_event.
        await thermostat.on_event(on_climate_event)
        await thermostat.set_current_temperature(21.0)  # ~/thermostat/current_temperature
        await thermostat.set_target_temperature(21.5)   # ~/thermostat/temperature
        await thermostat.set_mode("heat")               # ~/thermostat/mode
        await thermostat.set_action("heating")          # ~/thermostat/action
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

### Date

Dates are like numbers for calendar values: the device publishes the current
value with `set_state()` — a `datetime.date` or a `YYYY-MM-DD` string such as
`"2024-02-14"` — and Home Assistant commands are delivered as
[`Event`](src/ha_mqtt_device/event.py) objects to the async callback
registered with `on_event()` — `event.state` is the raw payload when it is a
valid `YYYY-MM-DD` date (for example `"2024-02-14"`) and `None` otherwise.
`set_state()` only accepts `datetime.date` objects and strict `YYYY-MM-DD`
strings; everything else raises a `ValueError`. The discovery config
advertises the command topic as `cmd_t` and omits `opt` and `frc_upd` when
they match the defaults:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Date, Device, DeviceInfo, Event

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    target = Date(unique_id="target_date", name="Target date")
    device = Device(provider, info, entities=[target])

    async def on_command(event: Event) -> None:
        # event.state is the payload when it is a valid YYYY-MM-DD date
        # (e.g. "2024-02-14"), None otherwise.
        print(f"{event.topic_type}: {event.message!r} -> {event.state}")
        if event.state is not None:
            await target.set_state(event.state)

    async with device:
        # Subscribes to ~/target_date/command; dates from Home Assistant
        # are delivered to on_command.
        await target.on_event(on_command)
        await target.set_state("2024-01-01")  # publishes "2024-01-01"
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

### Date Time

Datetimes are like dates but with a time of day: the device publishes the
current value with `set_state()` — a `datetime.datetime` or a
`YYYY-MM-DD HH:MM:SS` string such as `"2024-02-14 10:30:00"` — and Home
Assistant commands are delivered as
[`Event`](src/ha_mqtt_device/event.py) objects to the async callback
registered with `on_event()` — `event.state` is the raw payload when it is a
valid `YYYY-MM-DD HH:MM:SS` datetime (for example `"2024-02-14 10:30:00"`)
and `None` otherwise. `set_state()` only accepts `datetime.datetime` objects
and strict `YYYY-MM-DD HH:MM:SS` strings; a `datetime.date` raises a
`TypeError` and other strings raise a `ValueError`. A timezone-aware datetime
is published with its wall-clock components verbatim — no timezone conversion
is performed. The discovery config advertises the command topic as `cmd_t`
and omits `opt` and `frc_upd` when they match the defaults:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, DateTime, Device, DeviceInfo, Event

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    alarm = DateTime(unique_id="alarm_time", name="Alarm time")
    device = Device(provider, info, entities=[alarm])

    async def on_command(event: Event) -> None:
        # event.state is the payload when it is a valid YYYY-MM-DD HH:MM:SS
        # datetime (e.g. "2024-02-14 10:30:00"), None otherwise.
        print(f"{event.topic_type}: {event.message!r} -> {event.state}")
        if event.state is not None:
            await alarm.set_state(event.state)

    async with device:
        # Subscribes to ~/alarm_time/command; datetimes from Home Assistant
        # are delivered to on_command.
        await alarm.on_event(on_command)
        await alarm.set_state("2024-01-01 07:00:00")  # publishes "2024-01-01 07:00:00"
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

### Device tracker

Device trackers report a device's presence — and optionally its location —
from the device to Home Assistant. Like sensors they are read-only: there is
no command topic and no `on_event()` callback. `set_state()` publishes
`payload_home` (default `"home"`) or `payload_not_home` (default
`"not_home"`) to `~/<unique_id>/state`, and `set_location()` publishes a GPS
position report — a JSON payload with `latitude`, `longitude`, and optional
`gps_accuracy`, `battery_level`, and `source_type` — to the same topic.
Optional location fields are advertised in the discovery config (`lat`, `lon`,
`gps_acc`, `bat_lvl`, `source_type`) and used as fallbacks when the matching
`set_location()` argument is omitted (`source_type` is omitted from the config
when it matches the Home Assistant default `"gps"`); `pl_home`/`pl_not_home`
are omitted when they match the defaults:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, DeviceTracker

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    tracker = DeviceTracker(
        unique_id="phone",
        name="Phone",
        source_type="gps",
        gps_accuracy=50,
        battery_level=82,
    )
    device = Device(provider, info, entities=[tracker])

    async with device:
        # Publishes "home" to ~/phone/state.
        await tracker.set_state(True)
        # Publishes a JSON position report to ~/phone/state; gps_accuracy
        # and battery_level fall back to the configured values.
        await tracker.set_location(32.87336, -117.22743)
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

### Event

Event entities publish transient events to Home Assistant — for example a
doorbell that fires `doorbell_pressed`. Unlike switches and buttons there is
no command topic: events flow from the device to Home Assistant only, so the
entity has no `on_event()` callback. The `event_types` list is required —
Home Assistant only fires events whose type is declared — and `set_event()`
publishes a type to `~/<unique_id>/state`, which Home Assistant turns into an
HA event that automations can trigger on:

> **Device trigger:** the legacy "device trigger" MQTT entity is intentionally
> not provided — its functionality duplicates the `Event` entity, which is the
> newer and cleaner way to expose trigger events to Home Assistant.

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

### Fan

Fans are bidirectional like covers, with an on/off pair of topics and, when
the corresponding feature is enabled, percentage, preset-mode, oscillation,
and direction pairs. The device publishes the fan's state with `set_state()`
to `~/<unique_id>/state`; its speed with `set_percentage()` to
`~/<unique_id>/percentage_state`; its preset mode with `set_preset_mode()`
(`None` publishes `payload_reset_percentage`, to switch back to percentage
control) to `~/<unique_id>/preset_mode_state`; oscillation with
`set_oscillation()` to `~/<unique_id>/oscillation_state`; and direction with
`set_direction()` to `~/<unique_id>/direction_state`. Features are advertised
and subscribed only when the matching flag is set — `percentage_enabled` is on
by default, `preset_mode_enabled`, `oscillation_enabled`, and
`direction_enabled` are off; calling a disabled feature's setter raises a
`ValueError`. Home Assistant commands are delivered as
[`Event`](src/ha_mqtt_device/event.py) objects to the async callback
registered with `on_event()`:
- on the command topic `~/<unique_id>/command`, `event.event_type` is
  `"command"` and `event.state` is `"on"` or `"off"` (`None` for unknown
  payloads);
- on the percentage command topic `~/<unique_id>/percentage_command`,
  `event.event_type` is `"percentage"` and `event.state` is the payload when
  it parses as a number (`None` otherwise);
- on the preset-mode command topic `~/<unique_id>/preset_mode_command`,
  `event.event_type` is `"preset_mode"` and `event.state` is the payload when
  it is one of `preset_modes` or equals `payload_reset_percentage` (`None`
  otherwise);
- on the oscillation command topic `~/<unique_id>/oscillation_command`,
  `event.event_type` is `"oscillation"` and `event.state` is `"on"` or `"off"`
  (`None` for unknown payloads);
- on the direction command topic `~/<unique_id>/direction_command`,
  `event.event_type` is `"direction"` and `event.state` is `"forward"` or
  `"reverse"` (`None` for unknown payloads).

The discovery config advertises the on/off topics as `stat_t` and `cmd_t` —
note that the fan's state topic key is `stat_t`, not the base `p` — plus
`pct_stat_t`/`pct_cmd_t` for percentage, `prst_mode_stat_t`/`prst_mode_cmd_t`
for preset modes, `osc_stat_t`/`osc_cmd_t` for oscillation, and
`dir_stat_t`/`dir_cmd_t` for direction, each only when the feature is enabled.
It omits `pl_on`/`pl_off`, `pl_osc_on`/`pl_osc_off`, `pl_rst_pct`, `prst_modes`,
`spd_rng_min`/`spd_rng_max` (1/100), and `opt` when they match the defaults:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Fan

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    fan = Fan(
        unique_id="ceiling_fan",
        name="Ceiling fan",
        preset_mode_enabled=True,
        oscillation_enabled=True,
    )
    device = Device(provider, info, entities=[fan])

    async def on_fan_event(event: Event) -> None:
        if event.event_type == "command":
            # event.state is "on" or "off" (None for unknown payloads).
            print(f"{event.topic_type}: {event.message!r} -> {event.state}")
            await fan.set_state(event.state == "on")
        elif event.event_type == "percentage" and event.state is not None:
            # event.state is the requested speed (e.g. "60").
            await fan.set_percentage(int(event.state))
        elif event.event_type == "oscillation":
            await fan.set_oscillation(event.state == "on")

    async with device:
        # Subscribes to ~/ceiling_fan/command, ~/ceiling_fan/percentage_command,
        # and ~/ceiling_fan/oscillation_command; commands from Home Assistant
        # are delivered to on_fan_event.
        await fan.on_event(on_fan_event)
        await fan.set_state(True)       # publishes "ON" to ~/ceiling_fan/state
        await fan.set_percentage(60)    # publishes "60" to ~/ceiling_fan/percentage_state
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

### Humidifier

Humidifiers are bidirectional like switches, with an on/off pair of topics and
a target-humidity pair. The device publishes its on/off state with
`set_state()` to `~/<unique_id>/state` and its target humidity with
`set_target_humidity()` to `~/<unique_id>/target_humidity`. Home Assistant
commands are delivered as [`Event`](src/ha_mqtt_device/event.py) objects to
the async callback registered with `on_event()`:
- on the command topic `~/<unique_id>/command`, `event.event_type` is
  `"command"` and `event.state` is `"on"` or `"off"` (`None` for unknown
  payloads);
- on the target-humidity command topic
  `~/<unique_id>/target_humidity_command`, `event.event_type` is
  `"target_humidity"` and `event.state` is the payload when it parses as a
  number (for example `"50"`, `None` otherwise).

The discovery config advertises the four topics as `stat_t`, `cmd_t`,
`tgt_hum_stat_t`, and `tgt_hum_cmd_t` — note that the humidifier's state topic
key is `stat_t`, not the base `p` — and omits `pl_on`/`pl_off`, `min_hum`
(0)/`max_hum` (100), `opt`, and `dev_cla` when they match the defaults:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Humidifier

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    humidifier = Humidifier(
        unique_id="bedroom_humidifier",
        name="Bedroom humidifier",
        device_class="humidifier",
        min_humidity=30,
        max_humidity=80,
    )
    device = Device(provider, info, entities=[humidifier])

    async def on_humidifier_event(event: Event) -> None:
        if event.event_type == "command":
            # event.state is "on" or "off" (None for unknown payloads).
            print(f"{event.topic_type}: {event.message!r} -> {event.state}")
            await humidifier.set_state(event.state == "on")
        elif event.event_type == "target_humidity" and event.state is not None:
            # event.state is the requested target humidity (e.g. "50").
            await humidifier.set_target_humidity(float(event.state))

    async with device:
        # Subscribes to ~/bedroom_humidifier/command and
        # ~/bedroom_humidifier/target_humidity_command; commands from Home
        # Assistant are delivered to on_humidifier_event.
        await humidifier.on_event(on_humidifier_event)
        await humidifier.set_state(True)             # publishes "ON" to ~/bedroom_humidifier/state
        await humidifier.set_target_humidity(50)     # publishes "50" to ~/bedroom_humidifier/target_humidity
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

### Image

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

### Infrared

Infrared entities come in two flavors. An [`InfraredReceiver`](src/ha_mqtt_device/infrared.py)
reports received IR signals from the device to Home Assistant; it is read-only,
has no command topic, and publishes a JSON signal to
`~/<unique_id>/state` with `set_state()`. An
[`InfraredEmitter`](src/ha_mqtt_device/infrared.py) is triggered by Home
Assistant, which publishes an IR signal payload to `~/<unique_id>/command`;
registering a callback with `on_event()` delivers each signal as an
[`Event`](src/ha_mqtt_device/event.py) whose `state` is the parsed signal dict
(`timings`, optional `modulation`, optional `repeat_count`) or `None` for an
unparseable payload. The discovery config advertises the emitter's command topic
as `cmd_t` with `sch` set to `"emitter"`, and the receiver's state topic as `p`
with `sch` set to `"receiver"`:

```python
import asyncio
import json

from ha_mqtt_device import (
    AioMqttProvider,
    Device,
    DeviceInfo,
    Event,
    InfraredEmitter,
    InfraredReceiver,
)

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    emitter = InfraredEmitter(unique_id="tv_power", name="TV power")
    receiver = InfraredReceiver(unique_id="living_room_ir", name="Living room IR")
    device = Device(provider, info, entities=[emitter, receiver])

    async def on_ir_command(event: Event) -> None:
        # event.state is the parsed signal dict or None for an unknown payload.
        print(f"{event.topic_type}: {event.message!r} -> {event.state}")
        if event.state is not None:
            # ... send event.state to the IR hardware ...

    async with device:
        # Subscribes to ~/tv_power/command; signals from Home Assistant are
        # delivered to on_ir_command.
        await emitter.on_event(on_ir_command)

        # Publishes a received IR signal to ~/living_room_ir/state.
        await receiver.set_state(
            {"timings": [9000, -4500, 562, -1687], "modulation": 38000}
        )
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

### Lawn mower

Lawn mowers have one state topic and one command topic that carries all three
commands. The device publishes its activity — one of `"mowing"`, `"paused"`,
`"docked"`, or `"error"` — as a JSON payload `{"activity": "<activity>"}` with
`set_state()` to `~/<unique_id>/state`. Home Assistant commands arrive on the
shared command topic `~/<unique_id>/set` as JSON payloads
`{"activity": "start_mowing"}`, `{"activity": "pause"}`, or
`{"activity": "dock"}`, and are delivered as
[`Event`](src/ha_mqtt_device/event.py) objects to the async callback registered
with `on_event()`: `event.event_type` is `"command"`, `event.state` is
`"start_mowing"`, `"pause"`, or `"dock"` (`None` for unknown payloads), and
`event.topic_type` names which command topic the payload maps to
(`"start_mowing_command_topic"`, `"pause_command_topic"`, or
`"dock_command_topic"`). In the discovery config all three command topics
(`st_mow_cmd_t`, `pau_cmd_t`, `doc_cmd_t`) point to the same `~/set` topic, and
`act_stat_t` is the state topic; default payloads and states are omitted:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, LawnMower

async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883)
    info = DeviceInfo(device_id="my_device_id", name="My device")

    mower = LawnMower(unique_id="mower", name="Lawn Mower")
    device = Device(provider, info, entities=[mower])

    async def on_mower_command(event: Event) -> None:
        # event.state is "start_mowing", "pause", or "dock" (None for unknown).
        print(f"{event.topic_type}: {event.message!r} -> {event.state}")
        if event.state == "start_mowing":
            await mower.set_state("mowing")
        elif event.state == "pause":
            await mower.set_state("paused")
        elif event.state == "dock":
            await mower.set_state("docked")

    async with device:
        # Subscribes to ~/mower/set; commands from Home Assistant are
        # delivered to on_mower_command.
        await mower.on_event(on_mower_command)
        await mower.set_state("docked")  # publishes {"activity": "docked"}
        await asyncio.sleep(10)

    await device.remove()

asyncio.run(main())
```

### Light

> TODO: not yet supported — there is no Light entity in the library yet.
> Tracked as future work.

### Lock

> TODO: not yet supported — there is no Lock entity in the library yet.
> Tracked as future work.

### Notify

> TODO: not yet supported — there is no Notify entity in the library yet.
> Tracked as future work.

### Number

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

### Scene

> TODO: not yet supported — there is no Scene entity in the library yet.
> Tracked as future work.

### Select

> TODO: not yet supported — there is no Select entity in the library yet.
> Tracked as future work.

### Sensor

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

### Siren

> TODO: not yet supported — there is no Siren entity in the library yet.
> Tracked as future work.

### Switch

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

### Update

> TODO: not yet supported — there is no Update entity in the library yet.
> Tracked as future work.

### Tag scanner

> TODO: not yet supported — there is no TagScanner entity in the library yet.
> Tracked as future work.

### Text

> TODO: not yet supported — there is no Text entity in the library yet.
> Tracked as future work.

### Time

> TODO: not yet supported — there is no Time entity in the library yet.
> Tracked as future work.

### Vacuum

> TODO: not yet supported — there is no Vacuum entity in the library yet.
> Tracked as future work.

### Valve

> TODO: not yet supported — there is no Valve entity in the library yet.
> Tracked as future work.

### Water heater

> TODO: not yet supported — there is no WaterHeater entity in the library yet.
> Tracked as future work.

## See also

- [README.md](README.md) — overview, installation, and development workflow.
- [`examples/`](examples/) — standalone, runnable scripts for each supported entity.