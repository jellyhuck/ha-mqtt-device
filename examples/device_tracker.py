"""Example: a device with a single device tracker."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, DeviceTracker

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/device_tracker.py --host=... --port=... --username=... --password=...


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
    tracker = DeviceTracker(
        unique_id="phone",
        name="Phone",
        source_type="gps",
        latitude=32.87336,
        longitude=-117.22743,
        gps_accuracy=50,
        battery_level=82,
        icon="mdi:cellphone",
    )
    device = Device(provider, info, entities=[tracker])

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await tracker.set_state(True)
            logger.info("Published tracker state: home")
            await tracker.set_location(32.87336, -117.22743)
            logger.info("Published GPS position report")
            await tracker.set_state(False)
            logger.info("Published tracker state: not_home")

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
