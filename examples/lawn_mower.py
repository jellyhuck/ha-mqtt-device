"""Example: a device with a single lawn mower."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, LawnMower

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/lawn_mower.py --host=... --port=... --username=... --password=...


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
    mower = LawnMower(unique_id="mower_1", name="Lawn Mower")
    device = Device(provider, info, entities=[mower])

    mower_command_received = asyncio.Event()

    async def on_mower_command(event: Event) -> None:
        """Handle a command published to the mower's command topic."""
        logger.info("Mower received command %r (state=%s)", event.message, event.state)
        if event.state == "start_mowing":
            await mower.set_state("mowing")
            logger.info("Mower state updated: mowing")
        elif event.state == "pause":
            await mower.set_state("paused")
            logger.info("Mower state updated: paused")
        elif event.state == "dock":
            await mower.set_state("docked")
            logger.info("Mower state updated: docked")
        mower_command_received.set()

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await mower.on_event(on_mower_command)

            command_topic = info.resolve_topic(mower.command_topic)

            logger.info("Publishing start_mowing command to %s", command_topic)
            await provider.publish(command_topic, mower.payload_start_mowing)

            try:
                await asyncio.wait_for(mower_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the mower command to be acknowledged"
                )

            mower_command_received.clear()
            logger.info("Publishing pause command to %s", command_topic)
            await provider.publish(command_topic, mower.payload_pause)

            try:
                await asyncio.wait_for(mower_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the mower command to be acknowledged"
                )

            mower_command_received.clear()
            logger.info("Publishing dock command to %s", command_topic)
            await provider.publish(command_topic, mower.payload_dock)

            try:
                await asyncio.wait_for(mower_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the mower command to be acknowledged"
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
