# Examples

The [`examples/`](examples/) directory contains one copy-pasteable MQTT example
for the provider, device discovery, and every supported entity. Each script
accepts `--host`, `--port`, `--username`, and `--password`; for example:

```text
uv run examples/text.py --host=localhost --port=1883
```

The snippets below are intentionally small API illustrations, not complete
programs. They assume the calls run in an async function and that the entity is
bound to a `Device` as shown in the setup examples. The legacy Home Assistant
MQTT Device Trigger is intentionally excluded; use `EventEntity` and its event
callback model instead.

## MQTT provider

[`MqttProvider`](src/ha_mqtt_device/provider.py) supplies asynchronous
`publish()` and `subscribe()` operations. The bundled
[`AioMqttProvider`](src/ha_mqtt_device/aio_provider.py) uses `aiomqtt` and is
installed with the `mqtt` extra:

```python
import asyncio

from ha_mqtt_device import AioMqttProvider

provider = AioMqttProvider(hostname="localhost", port=1883)
await provider.publish("home/device/state", "ON")
await provider.publish("home/device/state", "ON", retain=True)

async with provider:
    await asyncio.Event().wait()  # provider.run() keeps MQTT callbacks active
```

## Reusable values

[`Value`](src/ha_mqtt_device/values/value.py) and its typed subclasses store a
value independently of an entity and publish changes through an
[`MqttProvider`](src/ha_mqtt_device/provider.py). Each value starts unset;
publication uses the topic and retention policy from its
[`PublishTopic`](src/ha_mqtt_device/publish_topic.py). See the runnable
[`examples/values.py`](examples/values.py).

```python
from datetime import date
from enum import StrEnum

from ha_mqtt_device import DateValue, StrEnumValue, StrValue
from ha_mqtt_device.publish_topic import PublishTopic

class Status(StrEnum):
    READY = "ready"

status = StrValue(PublishTopic("home/device/status", retain=True))
target_date = DateValue(PublishTopic("home/device/date", retain=True))
device_status = StrEnumValue[Status](
    PublishTopic("home/device/status_enum", retain=True)
)

assert status.value is None
await status.set_value("ready", provider)
await status.set_value("ready", provider)  # unchanged, so not published
await status.set_value("ready", provider, force_publish=True)
await target_date.set_value(date(2024, 2, 14), provider)
await device_status.set_value(Status.READY, provider)
```

## Device discovery

Construct a [`DeviceInfo`](src/ha_mqtt_device/device_info.py) and attach
entities to [`Device`](src/ha_mqtt_device/device.py). Entering the device
publishes discovery and availability; `remove()` clears the discovery payload.
See the runnable [`examples/device_only.py`](examples/device_only.py) for a
device without entities.

```python
from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Sensor

provider = AioMqttProvider(hostname="localhost", port=1883)
info = DeviceInfo(device_id="my_device", name="My device")
temperature = Sensor(unique_id="temperature", name="Temperature")
device = Device(provider, info, entities=[temperature])

async with provider:
    async with device:
        await temperature.set_state(21.5)  # ~/temperature/state
    await device.remove()
```

## Entities

All entity classes are exported from `ha_mqtt_device`. Runtime entity topics
use the `~/` prefix resolved by the device; discovery configs contain the
fully resolved topic names, and entity-level availability is inherited from
the device.

### Alarm control panel

HA Integration: [MQTT Alarm Control Panel](https://www.home-assistant.io/integrations/alarm_control_panel.mqtt/).

[`AlarmControlPanel`](src/ha_mqtt_device/alarm_control_panel.py) receives arm,
disarm, and trigger commands and can publish alarm states. See
[`examples/alarm_control_panel.py`](examples/alarm_control_panel.py).

```python
from ha_mqtt_device import AlarmControlPanel

alarm = AlarmControlPanel(
    unique_id="alarm",
    name="Alarm",
    code_arm_required=True,
)
await alarm.on_event(on_alarm_command)
await alarm.set_state("armed_home")
```

### Binary sensor

HA Integration: [MQTT Binary Sensor](https://www.home-assistant.io/integrations/binary_sensor.mqtt/).

[`BinarySensor`](src/ha_mqtt_device/binary_sensor.py) publishes boolean state
values and has no command topic. See
[`examples/binary_sensor.py`](examples/binary_sensor.py).

```python
from ha_mqtt_device import BinarySensor

led = BinarySensor(unique_id="is_led_on", name="LED state", device_class="light")
await led.set_state(True)   # publishes "ON"
await led.set_state(False)  # publishes "OFF"
```

### Button

HA Integration: [MQTT Button](https://www.home-assistant.io/integrations/button.mqtt/).

[`Button`](src/ha_mqtt_device/button.py) is command-only. Register `on_event()`
to handle Home Assistant presses; `event.state` is `"press"` for the default
payload. See [`examples/button.py`](examples/button.py).

```python
from ha_mqtt_device import Button

restart = Button(unique_id="restart", name="Restart", device_class="restart")
await restart.on_event(on_press)
```

### Camera

HA Integration: [MQTT Camera](https://www.home-assistant.io/integrations/camera.mqtt/).

[`Camera`](src/ha_mqtt_device/camera.py) publishes image frames to Home
Assistant. The example explicitly selects Base64 image encoding; omit
`encoding` when publishing raw image bytes. See
[`examples/camera.py`](examples/camera.py).

```python
import base64

from ha_mqtt_device import Camera

camera = Camera(
    unique_id="front_door", name="Front door camera", encoding="b64"
)
await camera.set_image(base64.b64encode(jpeg_bytes))
```

### Cover

HA Integration: [MQTT Cover](https://www.home-assistant.io/integrations/cover.mqtt/).

[`Cover`](src/ha_mqtt_device/cover.py) publishes state and position and
receives open, close, stop, and position commands through `on_event()`. See
[`examples/cover.py`](examples/cover.py).

```python
from ha_mqtt_device import Cover

blinds = Cover(unique_id="blinds", name="Blinds", device_class="blind")
await blinds.on_event(on_cover_event)
await blinds.set_state("closed")
await blinds.set_position(0)
```

### Climate (HVAC)

HA Integration: [MQTT Climate (HVAC)](https://www.home-assistant.io/integrations/climate.mqtt/).

[`Climate`](src/ha_mqtt_device/climate.py) exposes current temperature, target
temperature, HVAC mode, and current action, validating finite temperatures and
configured modes. See
[`examples/climate.py`](examples/climate.py).

```python
from ha_mqtt_device import Climate

thermostat = Climate(
    unique_id="thermostat",
    name="Thermostat",
    modes=["off", "heat", "cool"],
    temperature_unit="C",
)
await thermostat.on_event(on_climate_event)
await thermostat.set_current_temperature(21.0)
await thermostat.set_target_temperature(21.5)
await thermostat.set_mode("heat")
await thermostat.set_action("heating")
```

### Date

HA Integration: [MQTT Date](https://www.home-assistant.io/integrations/date.mqtt/).

[`Date`](src/ha_mqtt_device/date.py) validates and publishes `YYYY-MM-DD`
values and delivers valid commands through `on_event()`. See
[`examples/date.py`](examples/date.py).

```python
from ha_mqtt_device import Date

target_date = Date(unique_id="target_date", name="Target date")
await target_date.on_event(on_command)
await target_date.set_state("2024-02-14")
```

### Date Time

HA Integration: [MQTT Date/Time](https://www.home-assistant.io/integrations/datetime.mqtt/).

[`DateTime`](src/ha_mqtt_device/date_time.py) handles strict
`YYYY-MM-DD HH:MM:SS` values. See
[`examples/date_time.py`](examples/date_time.py).

```python
from datetime import datetime

from ha_mqtt_device import DateTime

alarm_time = DateTime(unique_id="alarm_time", name="Alarm time")
await alarm_time.set_state(datetime(2024, 2, 14, 7, 30))
await alarm_time.on_event(on_command)
```

### Device tracker

HA Integration: [MQTT Device Tracker](https://www.home-assistant.io/integrations/device_tracker.mqtt/).

[`DeviceTracker`](src/ha_mqtt_device/device_tracker.py) reports presence and
can publish a JSON location payload. See
[`examples/device_tracker.py`](examples/device_tracker.py).

```python
from ha_mqtt_device import DeviceTracker

phone = DeviceTracker(
    unique_id="phone",
    name="Phone",
    source_type="gps",
    battery_level=82,
)
await phone.set_state(True)
await phone.set_location(32.87336, -117.22743, battery_level=82)
```

### Event

HA Integration: [MQTT Event](https://www.home-assistant.io/integrations/event.mqtt/).

[`EventEntity`](src/ha_mqtt_device/event_entity.py) publishes transient event
types that Home Assistant automations can trigger. The legacy Device Trigger
is not supported. See [`examples/event.py`](examples/event.py).

```python
from ha_mqtt_device import EventEntity

doorbell = EventEntity(
    unique_id="doorbell",
    name="Doorbell",
    event_types=["doorbell_pressed", "doorbell_long_press"],
)
await doorbell.set_event("doorbell_pressed")
```

### Fan

HA Integration: [MQTT Fan](https://www.home-assistant.io/integrations/fan.mqtt/).

[`Fan`](src/ha_mqtt_device/fan.py) supports on/off state plus optional
percentage, preset, oscillation, and direction controls. Percentage values are
validated in the documented 0–100 range. See
[`examples/fan.py`](examples/fan.py).

```python
from ha_mqtt_device import Fan

fan = Fan(
    unique_id="ceiling_fan",
    name="Ceiling fan",
    preset_mode_enabled=True,
    oscillation_enabled=True,
)
await fan.on_event(on_fan_event)
await fan.set_state(True)
await fan.set_percentage(60)
```

### Humidifier

HA Integration: [MQTT Humidifier](https://www.home-assistant.io/integrations/humidifier.mqtt/).

[`Humidifier`](src/ha_mqtt_device/humidifier.py) publishes power and target
humidity and receives both command types through `on_event()`. Target humidity
is validated against the configured minimum and maximum. See
[`examples/humidifier.py`](examples/humidifier.py).

```python
from ha_mqtt_device import Humidifier

humidifier = Humidifier(
    unique_id="bedroom_humidifier",
    name="Bedroom humidifier",
    min_humidity=30,
    max_humidity=80,
)
await humidifier.on_event(on_humidifier_event)
await humidifier.set_state(True)
await humidifier.set_target_humidity(50)
```

### Image

HA Integration: [MQTT Image](https://www.home-assistant.io/integrations/image.mqtt/).

[`Image`](src/ha_mqtt_device/image.py) publishes image data without a command
topic. The example explicitly selects Base64 image encoding; omit `encoding`
when publishing raw image bytes. See [`examples/image.py`](examples/image.py).

```python
import base64

from ha_mqtt_device import Image

snapshot = Image(unique_id="camera", name="Camera", encoding="b64")
await snapshot.set_image(base64.b64encode(jpeg_bytes))
```

### Infrared

HA Integration: [MQTT Infrared](https://www.home-assistant.io/integrations/infrared.mqtt/).

[`InfraredEmitter`](src/ha_mqtt_device/infrared.py) receives signals from Home
Assistant, while [`InfraredReceiver`](src/ha_mqtt_device/infrared.py) publishes
received signals. Signals require non-empty integer timings and valid optional
modulation/repeat fields. See [`examples/infrared.py`](examples/infrared.py).

```python
from ha_mqtt_device import InfraredEmitter, InfraredReceiver

emitter = InfraredEmitter(unique_id="tv_power", name="TV power")
receiver = InfraredReceiver(unique_id="living_room_ir", name="Living room IR")
await emitter.on_event(on_ir_command)
await receiver.set_state({"timings": [9000, -4500, 562, -1687], "modulation": 38000})
```

### Lawn mower

HA Integration: [MQTT Lawn Mower](https://www.home-assistant.io/integrations/lawn_mower.mqtt/).

[`LawnMower`](src/ha_mqtt_device/lawn_mower.py) publishes activity states and
receives plain start, pause, and dock command payloads by default. Legacy JSON
commands remain accepted for compatibility. See
[`examples/lawn_mower.py`](examples/lawn_mower.py).

```python
from ha_mqtt_device import LawnMower

mower = LawnMower(unique_id="mower", name="Lawn mower")
await mower.on_event(on_mower_command)
await mower.set_state("mowing")
```

### Light

HA Integration: [MQTT Light](https://www.home-assistant.io/integrations/light.mqtt/).

[`Light`](src/ha_mqtt_device/light.py) supports grouped power, brightness,
color, effect, and white-control topics when enabled, validating finite numeric
values and configured effects. See
[`examples/light.py`](examples/light.py).

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
await light.on_event(on_light_event)
await light.set_state(True)
await light.set_brightness(75)
await light.set_rgb((255, 80, 20))
```

### Lock

HA Integration: [MQTT Lock](https://www.home-assistant.io/integrations/lock.mqtt/).

[`Lock`](src/ha_mqtt_device/lock.py) publishes lock state and receives lock,
unlock, and optional open commands. See
[`examples/lock.py`](examples/lock.py).

```python
from ha_mqtt_device import Lock

lock = Lock(unique_id="front_door_lock", name="Front door")
await lock.on_event(on_lock_command)
await lock.set_state("locked")
```

### Notify

HA Integration: [MQTT Notify](https://www.home-assistant.io/integrations/notify.mqtt/).

[`Notify`](src/ha_mqtt_device/notify.py) is an action-only notification
service. It has no state topic; incoming text or JSON payloads are delivered
through `on_event()`. See [`examples/notify.py`](examples/notify.py).

```python
from ha_mqtt_device import Notify

notifier = Notify(unique_id="notifications", name="Notifications")
await notifier.on_event(on_notification)
```

### Number

HA Integration: [MQTT Number](https://www.home-assistant.io/integrations/number.mqtt/).

[`Number`](src/ha_mqtt_device/number.py) publishes numeric state and receives
finite numeric commands within its configured range. See [`examples/number.py`](examples/number.py).

```python
from ha_mqtt_device import Number

dimmer = Number(
    unique_id="dimmer",
    name="Dimmer",
    min_value=0,
    max_value=100,
    step=1,
    unit_of_measurement="%",
)
await dimmer.on_event(on_number_command)
await dimmer.set_state(75)
```

### Scene

HA Integration: [MQTT Scene](https://www.home-assistant.io/integrations/scene.mqtt/).

[`Scene`](src/ha_mqtt_device/scene.py) is command-only; `activate()` publishes
the configured scene-on payload. See [`examples/scene.py`](examples/scene.py).

```python
from ha_mqtt_device import Scene

scene = Scene(unique_id="party", name="Party")
await scene.on_event(on_scene_command)
await scene.activate()
```

### Select

HA Integration: [MQTT Select](https://www.home-assistant.io/integrations/select.mqtt/).

[`SelectEntity`](src/ha_mqtt_device/select_entity.py) validates configured
options, publishes its state, and delivers selections through `on_event()`.
See [`examples/select_entity.py`](examples/select_entity.py).

```python
from ha_mqtt_device import SelectEntity

mode = SelectEntity(unique_id="mode", name="Mode", options=["Automatic", "Manual"])
await mode.on_event(on_selection)
await mode.set_state("Automatic")
```

### Sensor

HA Integration: [MQTT Sensor](https://www.home-assistant.io/integrations/sensor.mqtt/).

[`Sensor`](src/ha_mqtt_device/sensor.py) publishes string or numeric readings
without a command topic. See [`examples/sensor.py`](examples/sensor.py).

```python
from ha_mqtt_device import Sensor

temperature = Sensor(
    unique_id="temperature",
    name="Temperature",
    device_class="temperature",
    unit_of_measurement="°C",
    state_class="measurement",
)
await temperature.set_state(21.5)
```

### Siren

HA Integration: [MQTT Siren](https://www.home-assistant.io/integrations/siren.mqtt/).

[`Siren`](src/ha_mqtt_device/siren.py) publishes JSON state and optional tone,
duration, and volume parameters. See [`examples/siren.py`](examples/siren.py).

```python
from ha_mqtt_device import Siren

siren = Siren(
    unique_id="alarm_siren",
    name="Alarm siren",
    available_tones=["bell", "siren"],
)
await siren.on_event(on_siren_command)
await siren.set_state(True, tone="bell", duration=10, volume_level=0.5)
```

### Switch

HA Integration: [MQTT Switch](https://www.home-assistant.io/integrations/switch.mqtt/).

[`Switch`](src/ha_mqtt_device/switch.py) publishes on/off state and delivers
Home Assistant commands through `on_event()`. See
[`examples/switch.py`](examples/switch.py).

```python
from ha_mqtt_device import Switch

relay = Switch(unique_id="relay_1", name="Relay")
await relay.on_event(on_switch_command)
await relay.set_state(True)
```

### Update

HA Integration: [MQTT Update](https://www.home-assistant.io/integrations/update.mqtt/).

[`Update`](src/ha_mqtt_device/update.py) publishes JSON update state, requiring
an installed version, and can publish an install command and an optional
latest-version topic. See
[`examples/update.py`](examples/update.py).

```python
from ha_mqtt_device import Update

update = Update(
    unique_id="firmware",
    name="Firmware",
    title="Example firmware",
    latest_version_enabled=True,
)
await update.on_event(on_install)
await update.set_state("1.21.0", latest_version="1.22.0")
await update.install()
```

### Tag scanner

HA Integration: [MQTT Tag Scanner](https://www.home-assistant.io/integrations/tag.mqtt/).

[`TagScanner`](src/ha_mqtt_device/tag_scanner.py) is included in the device
discovery component map. `scan()` publishes a tag ID and `on_event()` receives
scans. See [`examples/tag_scanner.py`](examples/tag_scanner.py).

```python
from ha_mqtt_device import TagScanner

scanner = TagScanner(
    unique_id="reader",
    topic="~/tag_scanned",
    value_template="{{ value_json.uid }}",
)
await scanner.on_event(on_scan)
await scanner.scan("E9F35959")
```

### Text

HA Integration: [MQTT Text](https://www.home-assistant.io/integrations/text.mqtt/).

[`Text`](src/ha_mqtt_device/text.py) validates text length and an optional
pattern while publishing state and receiving commands. See
[`examples/text.py`](examples/text.py).

```python
from ha_mqtt_device import Text

message = Text(
    unique_id="message",
    name="Message",
    max_length=100,
    pattern=r"[A-Za-z0-9 ]*",
)
await message.on_event(on_text_command)
await message.set_state("Ready")
```

### Time

HA Integration: [MQTT Time](https://www.home-assistant.io/integrations/time.mqtt/).

[`Time`](src/ha_mqtt_device/time.py) normalizes `datetime.time` values and
strict time strings. See [`examples/mqtt_time.py`](examples/mqtt_time.py).

```python
from datetime import time

from ha_mqtt_device import Time

alarm = Time(unique_id="alarm", name="Alarm time")
await alarm.on_event(on_time_command)
await alarm.set_state(time(7, 30))  # publishes 07:30:00
```

### Vacuum

HA Integration: [MQTT Vacuum](https://www.home-assistant.io/integrations/vacuum.mqtt/).

[`Vacuum`](src/ha_mqtt_device/vacuum.py) publishes JSON state and exposes
feature-specific command methods. See [`examples/vacuum.py`](examples/vacuum.py).

```python
from ha_mqtt_device import Vacuum

vacuum = Vacuum(
    unique_id="cleaner",
    name="Cleaner",
    supported_features=["start", "stop", "return_home", "status"],
)
await vacuum.on_event(on_vacuum_command)
await vacuum.set_state("docked")
await vacuum.start()
```

### Valve

HA Integration: [MQTT Valve](https://www.home-assistant.io/integrations/valve.mqtt/).

[`Valve`](src/ha_mqtt_device/valve.py) publishes valve states and open, close,
and optional stop commands. See [`examples/valve.py`](examples/valve.py).

```python
from ha_mqtt_device import Valve

valve = Valve(unique_id="water_valve", name="Water valve", payload_stop="STOP")
await valve.on_event(on_valve_command)
await valve.set_state("closed")
await valve.open()
```

### Water heater

HA Integration: [MQTT Water Heater](https://www.home-assistant.io/integrations/water_heater.mqtt/).

[`WaterHeater`](src/ha_mqtt_device/water_heater.py) publishes current and target
temperatures and mode, with optional power control. See
[`examples/water_heater.py`](examples/water_heater.py).

```python
from ha_mqtt_device import WaterHeater

heater = WaterHeater(
    unique_id="boiler",
    name="Boiler",
    modes=["off", "eco", "electric"],
    temperature_unit="C",
    power_enabled=True,
)
await heater.on_event(on_heater_command)
await heater.set_current_temperature(52.5)
await heater.set_target_temperature(55)
await heater.set_mode("eco")
```

## See also

- [README.md](README.md) — overview, installation, and development workflow.
- [`examples/`](examples/) — standalone scripts for every supported entity and
  the device discovery example.
