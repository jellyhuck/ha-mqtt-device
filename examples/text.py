"""Example: an MQTT text entity."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Text

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/text.py --host=... --port=... --username=... --password=...


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
    info = DeviceInfo(device_id="text_example", name="Example text device")
    text = Text(
        unique_id="message",
        name="Message",
        max_length=100,
        pattern=r"[A-Za-z0-9 ]*",
    )
    device = Device(provider, info, entities=[text])

    async def on_text_command(event: Event) -> None:
        logger.info("Text command %r -> %s", event.message, event.state)
        if isinstance(event.state, str):
            # Apply the command to hardware and publish the resulting state.
            await text.set_state(event.state)

    async with provider:
        async with device:
            await text.on_event(on_text_command)
            await text.set_state("Ready")
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
