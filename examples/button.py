"""Example: a device with a single button."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Button, Device, DeviceInfo, Event

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/button.py --host=... --port=... --username=... --password=...


async def reboot_device() -> None:
    """Represent the application-specific reboot action."""
    logger.info("Reboot requested")


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

    info = DeviceInfo(device_id="example_device_01", name="Example device")
    restart = Button(unique_id="restart", name="Restart", device_class="restart")
    device = Device(provider, info, entities=[restart])

    button_pressed = asyncio.Event()

    async def on_press(event: Event) -> None:
        """Handle a press published to the button's command topic."""
        logger.info("Button received press %r (state=%s)", event.message, event.state)
        await reboot_device()
        button_pressed.set()

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await restart.on_event(on_press)

            command_topic = info.resolve_topic(restart.command_topic)
            logger.info("Publishing PRESS command to %s", command_topic)
            await provider.publish(command_topic, restart.payload_press)

            try:
                await asyncio.wait_for(button_pressed.wait(), timeout=10)
            except TimeoutError:
                logger.warning("Timed out waiting for the button press to be handled")

        logger.info("Removing the device from Home Assistant")
        await device.remove()

    logger.info("Provider stopped")


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
