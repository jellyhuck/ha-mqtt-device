"""Example: an MQTT vacuum entity."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Vacuum

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/vacuum.py --host=... --port=... --username=... --password=...


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
    info = DeviceInfo(device_id="vacuum_example", name="Example vacuum")
    vacuum = Vacuum(
        unique_id="cleaner",
        name="Cleaner",
        supported_features=[
            "start",
            "pause",
            "stop",
            "return_home",
            "status",
            "fan_speed",
            "send_command",
        ],
        fan_speed_list=["min", "medium", "max"],
        send_command_enabled=True,
    )
    device = Device(provider, info, entities=[vacuum])

    async def on_command(event: Event) -> None:
        logger.info("Vacuum command %r -> %s", event.message, event.state)

    async with provider:
        async with device:
            await vacuum.on_event(on_command)
            await vacuum.set_state("docked", fan_speed="min")
            await vacuum.start()
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
