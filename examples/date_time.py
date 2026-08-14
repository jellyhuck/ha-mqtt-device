"""Example: a device with a single datetime."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import typer

from ha_mqtt_device import AioMqttProvider, DateTime, Device, DeviceInfo, Event

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/date_time.py --host=... --port=... --username=... --password=...


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
    alarm_time = DateTime(unique_id="alarm_time", name="Alarm time")
    device = Device(provider, info, entities=[alarm_time])

    datetime_command_received = asyncio.Event()

    async def on_datetime_command(event: Event) -> None:
        """Handle a command published to the datetime's command topic."""
        logger.info(
            "DateTime received command %r (state=%s)", event.message, event.state
        )
        if isinstance(event.state, str):
            await alarm_time.set_state(event.state)
            logger.info("DateTime value updated: %s", event.state)
        else:
            logger.warning("Ignoring unknown datetime command %r", event.message)
        datetime_command_received.set()

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await alarm_time.set_state(datetime(2024, 1, 1, 7, 0, tzinfo=UTC))
            logger.info("DateTime state updated: 2024-01-01 07:00:00")

            await alarm_time.on_event(on_datetime_command)

            command_topic = info.resolve_topic(alarm_time.command_topic)
            logger.info("Publishing 2024-02-14 10:30:00 command to %s", command_topic)
            await provider.publish(command_topic, "2024-02-14 10:30:00")

            try:
                await asyncio.wait_for(datetime_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the datetime command to be acknowledged"
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
