# ha-mqtt-device

A thin Python library for creating and maintaining [Home Assistant](https://www.home-assistant.io/) devices that are discoverable via [MQTT device discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery). Individual entities associated with a device can be added, updated, and removed through the same API.

## Features

- **Device discovery**: publish the discovery payload Home Assistant needs to automatically pick up your device over MQTT.
- **Entity management**: add and maintain multiple entities (sensors, switches, binary sensors, etc.) that belong to a device.
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

Individual entities (sensors, switches, etc.) will be added to the same
discovery topic as `cmps` entries in a later layer.

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
