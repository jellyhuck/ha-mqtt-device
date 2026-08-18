"""Example: an MQTT valve."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Valve

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/valve.py --host=... --port=... --username=... --password=...


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
    valve = Valve(unique_id="water_valve", name="Water valve", payload_stop="STOP")
    device = Device(
        provider,
        DeviceInfo(device_id="valve_example", name="Example valve"),
        entities=[valve],
    )

    async def on_command(event: Event) -> None:
        logger.info("Valve command %r -> %s", event.message, event.state)
        if event.state == "open":
            await valve.set_state("open")
        elif event.state == "closed":
            await valve.set_state("closed")

    async with provider:
        async with device:
            await valve.on_event(on_command)
            await valve.set_state("closed")
            await valve.open()
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
