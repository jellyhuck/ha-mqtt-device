"""Example: a device with a single binary sensor."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, BinarySensor, Device, DeviceInfo

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/binary_sensor.py --host=... --port=... --username=... --password=...


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
    led = BinarySensor(unique_id="is_led_on", name="LED state", device_class="light")
    device = Device(provider, info, entities=[led])

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await led.set_state(True)
            logger.info("Published LED state: ON")
            await led.set_state(False)
            logger.info("Published LED state: OFF")

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
