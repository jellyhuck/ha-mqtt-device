"""Example: a device with a single sensor."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Sensor

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/sensor.py --host=... --port=... --username=... --password=...


async def main(
    host: str,
    port: int,
    username: str | None,
    password: str | None,
) -> None:
    provider = AioMqttProvider(
        hostname=host,
        port=port,
        username=username,
        password=password,
        logger=logger,
    )

    info = DeviceInfo(device_id="example_device_01", name="Example device")
    temperature = Sensor(
        unique_id="temperature",
        name="Temperature",
        device_class="temperature",
        unit_of_measurement="°C",
        state_class="measurement",
        suggested_display_precision=1,
    )
    device = Device(provider, info, entities=[temperature])

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await temperature.set_state(21.5)
            logger.info("Published temperature: 21.5 °C")

            await temperature.set_state(21.7)
            logger.info("Published temperature: 21.7 °C")

        logger.info("Removing the device from Home Assistant")
        await device.remove()

    logger.info("Provider stopped")


def run_cli(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Run the example with MQTT settings supplied by Typer."""
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main(host=host, port=port, username=username, password=password))
    except KeyboardInterrupt, asyncio.CancelledError:
        logger.info("Interrupted")


if __name__ == "__main__":
    typer.run(run_cli)
