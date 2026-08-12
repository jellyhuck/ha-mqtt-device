"""Example: a device with a single climate entity.

This script walks through the lifecycle of a device that has one
:class:`~ha_mqtt_device.Climate`:

1. Connect an :class:`~ha_mqtt_device.AioMqttProvider` to an MQTT broker,
   with ``--host``, ``--port``, ``--username``, and ``--password`` read from
   the command line.
2. Describe the device with a :class:`~ha_mqtt_device.DeviceInfo`.
3. Build a :class:`~ha_mqtt_device.Climate`, attach it to a
   :class:`~ha_mqtt_device.Device`, and register a handler with
   :meth:`~ha_mqtt_device.Climate.on_event`.
4. Use the device as an async context manager: entering the block publishes
   the discovery config (including the climate's ``cmps`` entry) and announces
   the device as available, and leaving the block announces it as unavailable.
5. Simulate Home Assistant controlling the thermostat: a temperature command
   (``"21.5"``) is published to the temperature command topic, then a mode
   command (``"heat"``) to the mode command topic. The
   :meth:`~ha_mqtt_device.Climate.on_event` callback acknowledges each one by
   publishing the new target temperature with
   :meth:`~ha_mqtt_device.Climate.set_target_temperature` and the new mode
   with :meth:`~ha_mqtt_device.Climate.set_mode`.
6. Keep the provider running until interrupted, then remove the device with
   :meth:`~ha_mqtt_device.Device.remove`.

Run it from the repository root::

    uv run python examples/climate.py
    uv run python examples/climate.py --host mqtt.example.com --port 1883 \
        --username user --password secret
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Climate, Device, DeviceInfo, Event

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883


def parse_args() -> argparse.Namespace:
    """Parse the MQTT broker connection settings from the command line."""
    parser = argparse.ArgumentParser(
        description="Publish a Home Assistant device via MQTT device discovery."
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"MQTT broker host (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"MQTT broker port (default: {DEFAULT_PORT})",
    )
    parser.add_argument("--username", default=None, help="MQTT username (optional)")
    parser.add_argument("--password", default=None, help="MQTT password (optional)")
    return parser.parse_args()


def build_device_info() -> DeviceInfo:
    """Create the device metadata that Home Assistant will display.

    Only ``device_id`` and ``name`` are required; every other field shown here
    is optional and has a sane default.
    """
    return DeviceInfo(
        device_id="example_device_01",
        name="Example device",
        manufacturer="Example Corp.",
        model="Widget 3000",
        model_id="W3K",
        sw_version="1.0.0",
        hw_version="rev. B",
        serial_number="SN-123456",
        suggested_area="Living room",
        configuration_url="http://192.168.0.50",
        connections=[("mac", "AA:BB:CC:DD:EE:FF")],
        origin_sw="0.1.0",
    )


async def main() -> None:
    args = parse_args()

    provider = AioMqttProvider(
        hostname=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        logger=logger,
    )

    info = build_device_info()
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

    # Set by the climate's on_event callback once a command has been processed,
    # so the example can wait until the thermostat has acknowledged it.
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
            # A target temperature command: report the current temperature and
            # acknowledge by publishing the new target temperature.
            await thermostat.set_current_temperature(21.0)
            await thermostat.set_target_temperature(float(event.state))
            if event.state == "21.5":
                await thermostat.set_action("heating")
            logger.info("Thermostat target temperature set to %s", event.state)
            temperature_command_received.set()
        elif event.event_type == "mode" and isinstance(event.state, str):
            # A mode command: apply the mode and acknowledge it.
            await thermostat.set_mode(event.state)
            if event.state == "off":
                await thermostat.set_action("off")
            else:
                await thermostat.set_action("heating")
            logger.info("Thermostat mode set to %s", event.state)
            mode_command_received.set()

    # Entering the block starts the provider's message loop (provider.run());
    # leaving it shuts the loop down and drains any in-flight work
    # (provider.stop()) — even when the block is exited via an exception.
    async with provider:
        # The device is an async context manager: entering the inner block
        # publishes the discovery config Home Assistant needs to pick up the
        # device and announces it as "online"; leaving the block announces it
        # as "offline" — even when the body raises.
        async with device:
            logger.info("Publishing discovery config to %s", info.discovery_topic())

            # The thermostat listens for commands from Home Assistant on
            # ~/thermostat/temperature_command and ~/thermostat/mode_command.
            # Register its handler, then simulate Home Assistant setting the
            # target temperature to 21.5 and the mode to "heat".
            await thermostat.on_event(on_climate_event)

            temperature_command_topic = info.resolve_topic(
                thermostat.temperature_command_topic
            )
            logger.info(
                "Publishing temperature command 21.5 to %s",
                temperature_command_topic,
            )
            await provider.publish(temperature_command_topic, "21.5")

            mode_command_topic = info.resolve_topic(thermostat.mode_command_topic)
            logger.info("Publishing mode command heat to %s", mode_command_topic)
            await provider.publish(mode_command_topic, "heat")

            # Wait until the on_event callback has processed both commands and
            # acknowledged them with set_target_temperature()/set_mode().
            try:
                await asyncio.wait_for(temperature_command_received.wait(), timeout=10)
                await asyncio.wait_for(mode_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the thermostat commands to be acknowledged"
                )

        # Leaving the device context announced "offline". To also make Home
        # Assistant forget the device, remove() publishes an empty config.
        logger.info("Removing the device from Home Assistant")
        await device.remove()

    logger.info("Provider stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bye")
