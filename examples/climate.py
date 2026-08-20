"""Example: a device with a single climate entity."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Climate, Device, DeviceInfo, Event

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/climate.py --host=... --port=... --username=... --password=...


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
    thermostat = Climate(
        unique_id="thermostat",
        name="Thermostat",
        modes=["off", "heat", "cool", "auto"],
        temperature_unit="C",
        min_temp=10,
        max_temp=30,
        temp_step=0.5,
    )
    device = Device(provider, info, entities=[thermostat])

    temperature_command_received = asyncio.Event()
    mode_command_received = asyncio.Event()

    async def on_climate_event(event: Event) -> None:
        """Handle a temperature or mode command from Home Assistant."""
        logger.info(
            "Climate received %s on %s: message=%r state=%s",
            event.event_type,
            event.topic_type,
            event.message,
            event.state,
        )
        if event.event_type == "temperature" and isinstance(event.state, str):
            await thermostat.set_current_temperature(21.0)
            await thermostat.set_target_temperature(float(event.state))
            if event.state == "21.5":
                await thermostat.set_action("heating")
            logger.info("Thermostat target temperature set to %s", event.state)
            temperature_command_received.set()
        elif event.event_type == "mode" and isinstance(event.state, str):
            await thermostat.set_mode(event.state)
            if event.state == "off":
                await thermostat.set_action("off")
            else:
                await thermostat.set_action("heating")
            logger.info("Thermostat mode set to %s", event.state)
            mode_command_received.set()

    async with provider:
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            await thermostat.on_event(on_climate_event)

            temperature_command_topic = thermostat.temperature_command_topic
            logger.info(
                "Publishing temperature command 21.5 to %s",
                temperature_command_topic,
            )
            await provider.publish(temperature_command_topic, "21.5")

            mode_command_topic = thermostat.mode_command_topic
            logger.info("Publishing mode command heat to %s", mode_command_topic)
            await provider.publish(mode_command_topic, "heat")

            try:
                await asyncio.wait_for(temperature_command_received.wait(), timeout=10)
                await asyncio.wait_for(mode_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the thermostat commands to be acknowledged"
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
