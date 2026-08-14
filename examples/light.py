"""Example: a grouped-topic MQTT light."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Light

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/light.py --host=... --port=... --username=... --password=...


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
    info = DeviceInfo(device_id="example_light", name="Example light")
    light = Light(
        unique_id="lamp",
        name="Lamp",
        brightness_enabled=True,
        rgb_enabled=True,
        effect_enabled=True,
        effect_list=["rainbow", "pulse"],
    )
    device = Device(provider, info, entities=[light])

    async def on_command(event: Event) -> None:
        logger.info("%s: %r -> %r", event.topic_type, event.message, event.state)
        if event.event_type == "command" and event.state is not None:
            await light.set_state(event.state == "on")
        elif event.event_type == "brightness" and isinstance(event.state, str):
            await light.set_brightness(int(event.state))

    async with provider:
        async with device:
            await light.on_event(on_command)
            await light.set_state(True)
            await light.set_brightness(75)
            await light.set_rgb((255, 80, 20))
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
