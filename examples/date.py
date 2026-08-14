"""Example: a device with a single date."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

import typer

from ha_mqtt_device import AioMqttProvider, Date, Device, DeviceInfo, Event

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/date.py --host=... --port=... --username=... --password=...


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
    target_date = Date(unique_id="target_date", name="Target date")
    device = Device(provider, info, entities=[target_date])

    date_command_received = asyncio.Event()

    async def on_date_command(event: Event) -> None:
        """Handle a command published to the date's command topic."""
        logger.info("Date received command %r (state=%s)", event.message, event.state)
        if isinstance(event.state, str):
            await target_date.set_state(event.state)
            logger.info("Date value updated: %s", event.state)
        else:
            logger.warning("Ignoring unknown date command %r", event.message)
        date_command_received.set()

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await target_date.set_state(date(2024, 1, 1))
            logger.info("Date state updated: 2024-01-01")

            await target_date.on_event(on_date_command)

            command_topic = info.resolve_topic(target_date.command_topic)
            logger.info("Publishing 2024-02-14 command to %s", command_topic)
            await provider.publish(command_topic, "2024-02-14")

            try:
                await asyncio.wait_for(date_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the date command to be acknowledged"
                )

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
