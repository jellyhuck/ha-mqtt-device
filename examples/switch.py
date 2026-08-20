"""Example: a device with a single switch."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Switch

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/switch.py --host=... --port=... --username=... --password=...


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
    relay = Switch(unique_id="relay_1", name="Relay", device_class="outlet")
    device = Device(provider, info, entities=[relay])

    relay_command_received = asyncio.Event()

    async def on_relay_command(event: Event) -> None:
        """Handle a command published to the relay's command topic."""
        logger.info("Relay received command %r (state=%s)", event.message, event.state)
        if event.state == "on":
            await relay.set_state(True)
            logger.info("Relay state updated: ON")
        elif event.state == "off":
            await relay.set_state(False)
            logger.info("Relay state updated: OFF")
        relay_command_received.set()

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await relay.on_event(on_relay_command)

            command_topic = relay.command_topic
            logger.info("Publishing ON command to %s", command_topic)
            await provider.publish(command_topic, relay.payload_on)

            try:
                await asyncio.wait_for(relay_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the relay command to be acknowledged"
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
