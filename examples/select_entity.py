"""Example: an MQTT select."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, SelectEntity

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/select_entity.py --host=... --port=... --username=... --password=...


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
    info = DeviceInfo(device_id="select_example", name="Example selector")
    select = SelectEntity(
        unique_id="mode",
        name="Mode",
        options=["Automatic", "Manual"],
    )
    device = Device(provider, info, entities=[select])

    async def on_selection(event: Event) -> None:
        logger.info("Selection command %r -> %s", event.message, event.state)
        if isinstance(event.state, str):
            # Apply the selection to the hardware, then report it.
            await select.set_state(event.state)

    async with provider:
        async with device:
            await select.on_event(on_selection)
            await select.set_state("Automatic")
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
