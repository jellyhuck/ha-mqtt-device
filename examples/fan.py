"""Example: a device with a single fan."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Fan

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/fan.py --host=... --port=... --username=... --password=...


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
    fan = Fan(
        unique_id="ceiling_fan",
        name="Ceiling fan",
        preset_mode_enabled=True,
        oscillation_enabled=True,
        direction_enabled=True,
    )
    device = Device(provider, info, entities=[fan])

    fan_command_received = asyncio.Event()

    async def on_fan_event(event: Event) -> None:
        """Handle a command published to one of the fan's command topics."""
        logger.info(
            "Fan received %s on %s (state=%s)",
            event.message,
            event.topic_type,
            event.state,
        )
        if event.event_type == "command":
            await fan.set_state(event.state == "on")
            logger.info("Fan state updated: %s", "ON" if event.state == "on" else "OFF")
        elif event.event_type == "percentage" and isinstance(event.state, str):
            await fan.set_percentage(int(event.state))
        elif event.event_type == "oscillation":
            await fan.set_oscillation(event.state == "on")
        elif event.event_type == "direction" and isinstance(event.state, str):
            await fan.set_direction(event.state)
        fan_command_received.set()

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await fan.set_state(True)
            await fan.set_percentage(60)
            await fan.set_oscillation(True)

            await fan.on_event(on_fan_event)

            command_topic = info.resolve_topic(fan.command_topic)
            logger.info("Publishing ON command to %s", command_topic)
            await provider.publish(command_topic, fan.payload_on)

            try:
                await asyncio.wait_for(fan_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the fan command to be acknowledged"
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
