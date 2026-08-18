"""Example: a device with a single event entity."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, EventEntity

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/event.py --host=... --port=... --username=... --password=...


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
    doorbell = EventEntity(
        unique_id="doorbell",
        name="Doorbell",
        device_class="doorbell",
        event_types=["doorbell_pressed", "doorbell_long_press"],
    )
    device = Device(provider, info, entities=[doorbell])

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await doorbell.set_event("doorbell_pressed")
            logger.info("Fired event: doorbell_pressed")
            await doorbell.set_event("doorbell_long_press")
            logger.info("Fired event: doorbell_long_press")

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
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Interrupted")


if __name__ == "__main__":
    typer.run(run_cli)
