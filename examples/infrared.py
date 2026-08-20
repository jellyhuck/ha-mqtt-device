"""Example: a device with an infrared emitter and an infrared receiver."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import (
    AioMqttProvider,
    Device,
    DeviceInfo,
    Event,
    InfraredEmitter,
    InfraredReceiver,
)

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/infrared.py --host=... --port=... --username=... --password=...


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
    emitter = InfraredEmitter(unique_id="tv_power", name="TV power")
    receiver = InfraredReceiver(unique_id="living_room_ir", name="Living room IR")
    device = Device(provider, info, entities=[emitter, receiver])

    emitter_command_received = asyncio.Event()

    async def on_ir_command(event: Event) -> None:
        """Handle an IR signal published to the emitter's command topic."""
        logger.info("Emitter received signal %r (state=%s)", event.message, event.state)
        if event.state is not None:
            logger.info("Would send IR signal: %s", event.state)
        emitter_command_received.set()

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await emitter.on_event(on_ir_command)

            command_topic = emitter.command_topic
            logger.info("Publishing an IR command to %s", command_topic)
            await provider.publish(
                command_topic,
                '{"timings": [9000, -4500, 562, -1687], "modulation": 38000, "repeat_count": 0}',
            )

            try:
                await asyncio.wait_for(emitter_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the IR command to be acknowledged"
                )

            await receiver.set_state(
                {
                    "timings": [9000, -4500, 562, -1687],
                    "modulation": 38000,
                }
            )
            logger.info("Published a received IR signal to the receiver state topic")

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
