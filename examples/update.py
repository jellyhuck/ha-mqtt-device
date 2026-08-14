"""Example: an MQTT firmware update entity."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Update

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/update.py --host=... --port=... --username=... --password=...


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
    info = DeviceInfo(device_id="update_example", name="Example update device")
    update = Update(
        unique_id="firmware",
        name="Firmware update",
        title="Example device firmware",
        device_class="firmware",
        release_url="https://example.com/releases",
        latest_version_enabled=True,
    )
    device = Device(provider, info, entities=[update])

    async def on_install(event: Event) -> None:
        logger.info("Update command %r -> %s", event.message, event.state)
        if event.state == "install":
            # Start the update in hardware, then report progress via set_state.
            await update.set_state("1.21.0", latest_version="1.22.0", in_progress=True)

    async with provider:
        async with device:
            await update.on_event(on_install)
            await update.set_state("1.21.0", latest_version="1.22.0")
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
