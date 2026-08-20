"""Example: a device with a single number."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Number

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/number.py --host=... --port=... --username=... --password=...


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
    dimmer = Number(
        unique_id="dimmer",
        name="Dimmer",
        min_value=0,
        max_value=100,
        step=1,
        mode="box",
        unit_of_measurement="%",
    )
    device = Device(provider, info, entities=[dimmer])

    dimmer_command_received = asyncio.Event()

    async def on_dimmer_command(event: Event) -> None:
        """Handle a command published to the dimmer's command topic."""
        logger.info("Dimmer received command %r (state=%s)", event.message, event.state)
        if isinstance(event.state, str):
            await dimmer.set_state(float(event.state))
            logger.info("Dimmer value updated: %s%%", event.state)
        else:
            logger.warning("Ignoring unknown dimmer command %r", event.message)
        dimmer_command_received.set()

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await dimmer.on_event(on_dimmer_command)

            command_topic = dimmer.command_topic
            logger.info("Publishing 75 command to %s", command_topic)
            await provider.publish(command_topic, "75")

            try:
                await asyncio.wait_for(dimmer_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the dimmer command to be acknowledged"
                )

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
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Interrupted")


if __name__ == "__main__":
    typer.run(run_cli)
