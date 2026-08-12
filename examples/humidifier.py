"""Example: a device with a single humidifier.

This script walks through the lifecycle of a device that has one
:class:`~ha_mqtt_device.Humidifier`:

1. Connect an :class:`~ha_mqtt_device.AioMqttProvider` to an MQTT broker,
   with ``--host``, ``--port``, ``--username``, and ``--password`` read from
   the command line.
2. Describe the device with a :class:`~ha_mqtt_device.DeviceInfo`.
3. Build a :class:`~ha_mqtt_device.Humidifier`, attach it to a
   :class:`~ha_mqtt_device.Device`, and register a command handler with
   :meth:`~ha_mqtt_device.Humidifier.on_event`.
4. Use the device as an async context manager: entering the block publishes
   the discovery config (including the humidifier's ``cmps`` entry) and
   announces the device as available, and leaving the block announces it as
   unavailable.
5. Simulate Home Assistant turning the humidifier on and setting a target
   humidity: an ``ON`` command and a ``60`` target-humidity command are
   published to the humidifier's command topics, and the example waits for the
   :meth:`~ha_mqtt_device.Humidifier.on_event` callback to acknowledge them by
   publishing the new state with :meth:`~ha_mqtt_device.Humidifier.set_state`
   and :meth:`~ha_mqtt_device.Humidifier.set_target_humidity`.
6. Keep the provider running until interrupted, then remove the device with
   :meth:`~ha_mqtt_device.Device.remove`.

Run it from the repository root::

    uv run python examples/humidifier.py
    uv run python examples/humidifier.py --host mqtt.example.com --port 1883 \
        --username user --password secret
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Humidifier

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
    humidifier = Humidifier(
        unique_id="bedroom_humidifier",
        name="Bedroom humidifier",
        device_class="humidifier",
        min_humidity=30,
        max_humidity=80,
    )
    device = Device(provider, info, entities=[humidifier])

    # Set by the humidifier's on_event callback once a command has been
    # processed, so the example can wait until the humidifier has acknowledged
    # the commands.
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
                # Acknowledge the command by publishing the humidifier's new
                # state, so Home Assistant sees ON on ~/bedroom_humidifier/state.
                await humidifier.set_state(True)
                logger.info("Humidifier state updated: ON")
            elif event.state == "off":
                await humidifier.set_state(False)
                logger.info("Humidifier state updated: OFF")
        elif event.event_type == "target_humidity" and event.state is not None:
            # Acknowledge the command by publishing the new target humidity,
            # so Home Assistant sees 60 on
            # ~/bedroom_humidifier/target_humidity.
            await humidifier.set_target_humidity(float(event.state))
            logger.info("Humidifier target humidity updated: %s", event.state)
        humidifier_command_received.set()

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

            # The humidifier listens for commands from Home Assistant on
            # ~/bedroom_humidifier/command and
            # ~/bedroom_humidifier/target_humidity_command. Register its
            # handler, then simulate Home Assistant turning the humidifier on
            # and setting a 60% target humidity by publishing to those topics.
            await humidifier.on_event(on_humidifier_command)

            command_topic = info.resolve_topic(humidifier.command_topic)
            logger.info("Publishing ON command to %s", command_topic)
            await provider.publish(command_topic, humidifier.payload_on)

            humidity_topic = info.resolve_topic(
                humidifier.target_humidity_command_topic
            )
            logger.info("Publishing 60 command to %s", humidity_topic)
            await provider.publish(humidity_topic, "60")

            # Wait until the on_event callback has processed the commands and
            # acknowledged them with set_state(True) and set_target_humidity(60).
            try:
                await asyncio.wait_for(humidifier_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the humidifier commands to be acknowledged"
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
    except KeyboardInterrupt, asyncio.CancelledError:
        logger.info("Bye")
