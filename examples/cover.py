"""Example: a device with a single cover."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Cover, Device, DeviceInfo, Event

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/cover.py --host=... --port=... --username=... --password=...


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
    blinds = Cover(unique_id="blinds", name="Blinds", device_class="blind")
    device = Device(provider, info, entities=[blinds])

    open_command_received = asyncio.Event()
    position_command_received = asyncio.Event()

    async def on_cover_event(event: Event) -> None:
        """Handle a command or position command from Home Assistant."""
        logger.info(
            "Cover received %s on %s: message=%r state=%s",
            event.event_type,
            event.topic_type,
            event.message,
            event.state,
        )
        if event.event_type == "command":
            if event.state == "open":
                await blinds.set_state("opening")
                await blinds.set_state("open")
                await blinds.set_position(100)
                logger.info("Cover opened")
            elif event.state == "close":
                await blinds.set_state("closing")
                await blinds.set_state("closed")
                await blinds.set_position(0)
                logger.info("Cover closed")
            elif event.state == "stop":
                await blinds.set_state("stopped")
                logger.info("Cover stopped")
            open_command_received.set()
        elif isinstance(event.state, str):
            position = int(event.state)
            await blinds.set_position(position)
            if position == 0:
                await blinds.set_state("closed")
            elif position == 100:
                await blinds.set_state("open")
            else:
                await blinds.set_state("stopped")
            logger.info("Cover moved to position %d", position)
            position_command_received.set()

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await blinds.on_event(on_cover_event)

            command_topic = info.resolve_topic(blinds.command_topic)
            logger.info("Publishing OPEN command to %s", command_topic)
            await provider.publish(command_topic, blinds.payload_open)

            set_position_topic = info.resolve_topic(blinds.set_position_topic)
            logger.info("Publishing position 50 to %s", set_position_topic)
            await provider.publish(set_position_topic, "50")

            try:
                await asyncio.wait_for(open_command_received.wait(), timeout=10)
                await asyncio.wait_for(position_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the cover commands to be acknowledged"
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
