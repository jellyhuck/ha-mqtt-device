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

    # run() connects, subscribes, and processes messages until stop() is called.
    run_task = asyncio.create_task(provider.run())
    try:
        await run_task
    finally:
        await provider.stop()

asyncio.run(main())
```

### Planned: devices and entities

Device discovery payloads and entity management (sensors, switches, etc.) are
the next layer on top of the MQTT provider.

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
