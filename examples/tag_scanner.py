"""Example: an MQTT tag scanner."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, TagScanner

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/tag_scanner.py --host=... --port=... --username=... --password=...


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
    info = DeviceInfo(device_id="tag_reader", name="Example tag reader")
    scanner = TagScanner(
        unique_id="reader",
        topic="~/tag_scanned",
        value_template="{{ value_json.uid }}",
    )
    device = Device(provider, info, entities=[scanner])

    async def on_scan(event: Event) -> None:
        logger.info("Tag scan %r -> %s", event.message, event.state)

    async with provider:
        async with device:
            await scanner.on_event(on_scan)
            # Hardware integrations normally call this when their reader scans.
            await scanner.scan("E9F35959")
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
