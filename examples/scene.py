"""Example: an MQTT scene."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Scene

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/scene.py --host=... --port=... --username=... --password=...


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
    info = DeviceInfo(device_id="scene_example", name="Example scenes")
    scene = Scene(unique_id="party", name="Party")
    device = Device(provider, info, entities=[scene])

    async def on_scene_command(event: Event) -> None:
        logger.info("Scene command %r -> %s", event.message, event.state)
        if event.state == "on":
            # Activate the scene in the device's hardware.
            logger.info("Activating the party scene")

    async with provider:
        async with device:
            await scene.on_event(on_scene_command)
            await scene.activate()  # publishes ON to ~/party/command
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
