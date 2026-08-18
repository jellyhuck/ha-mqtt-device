"""Example: an MQTT alarm control panel."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import (
    AioMqttProvider,
    AlarmControlPanel,
    Device,
    DeviceInfo,
    Event,
)

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/alarm_control_panel.py --host=... --port=... --username=... --password=...


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
    info = DeviceInfo(device_id="alarm_example", name="Example alarm")
    alarm = AlarmControlPanel(unique_id="alarm", name="Alarm")
    device = Device(provider, info, entities=[alarm])

    async def on_alarm_command(event: Event) -> None:
        logger.info("Alarm command %r -> %s", event.message, event.state)
        # Send the command to the alarm hardware, then report its state.
        if isinstance(event.state, str):
            await alarm.set_state(event.state)

    async with provider:
        async with device:
            await alarm.on_event(on_alarm_command)
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
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Interrupted")


if __name__ == "__main__":
    typer.run(run_cli)
