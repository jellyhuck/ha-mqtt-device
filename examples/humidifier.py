"""Example: a device with a single humidifier."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Humidifier

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/humidifier.py --host=... --port=... --username=... --password=...


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
    humidifier = Humidifier(
        unique_id="bedroom_humidifier",
        name="Bedroom humidifier",
        device_class="humidifier",
        min_humidity=30,
        max_humidity=80,
    )
    device = Device(provider, info, entities=[humidifier])

    humidifier_command_received = asyncio.Event()

    async def on_humidifier_command(event: Event) -> None:
        """Handle a command published to the humidifier's command topics."""
        logger.info(
            "Humidifier received command %r (state=%s)",
            event.message,
            event.state,
        )
        if event.event_type == "command":
            if event.state == "on":
                await humidifier.set_state(True)
                logger.info("Humidifier state updated: ON")
            elif event.state == "off":
                await humidifier.set_state(False)
                logger.info("Humidifier state updated: OFF")
        elif event.event_type == "target_humidity" and isinstance(event.state, str):
            await humidifier.set_target_humidity(float(event.state))
            logger.info("Humidifier target humidity updated: %s", event.state)
        humidifier_command_received.set()

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await humidifier.on_event(on_humidifier_command)

            command_topic = info.resolve_topic(humidifier.command_topic)
            logger.info("Publishing ON command to %s", command_topic)
            await provider.publish(command_topic, humidifier.payload_on)

            humidity_topic = info.resolve_topic(
                humidifier.target_humidity_command_topic
            )
            logger.info("Publishing 60 command to %s", humidity_topic)
            await provider.publish(humidity_topic, "60")

            try:
                await asyncio.wait_for(humidifier_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the humidifier commands to be acknowledged"
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
