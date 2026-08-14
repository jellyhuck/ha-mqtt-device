"""Example: an MQTT time entity."""

from __future__ import annotations

import asyncio
import logging
from datetime import time

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Time

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/mqtt_time.py --host=... --port=... --username=... --password=...


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
    info = DeviceInfo(device_id="time_example", name="Example time device")
    alarm = Time(unique_id="alarm", name="Alarm time")
    device = Device(provider, info, entities=[alarm])

    async def on_time_command(event: Event) -> None:
        logger.info("Time command %r -> %s", event.message, event.state)
        if isinstance(event.state, str):
            await alarm.set_state(event.state)

    async with provider:
        async with device:
            await alarm.on_event(on_time_command)
            await alarm.set_state(time(7, 30))
        await device.remove()


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
