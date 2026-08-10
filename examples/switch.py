"""Example: a device with a single switch.

This script walks through the lifecycle of a device that has one
:class:`~ha_mqtt_device.Switch`:

1. Connect an :class:`~ha_mqtt_device.AioMqttProvider` to an MQTT broker,
   with ``--host``, ``--port``, ``--username``, and ``--password`` read from
   the command line.
2. Describe the device with a :class:`~ha_mqtt_device.DeviceInfo`.
3. Build a :class:`~ha_mqtt_device.Switch`, attach it to a
   :class:`~ha_mqtt_device.Device`, and register a command handler with
   :meth:`~ha_mqtt_device.Switch.on_event`.
4. Use the device as an async context manager: entering the block publishes
   the discovery config (including the switch's ``cmps`` entry) and announces
   the device as available, and leaving the block announces it as unavailable.
5. Simulate Home Assistant turning the switch on: an ``ON`` command is
   published to the switch's command topic, and the example waits for the
   :meth:`~ha_mqtt_device.Switch.on_event` callback to acknowledge it by
   publishing the new state with :meth:`~ha_mqtt_device.Switch.set_state`.
6. Keep the provider running until interrupted, then remove the device with
   :meth:`~ha_mqtt_device.Device.remove`.

Run it from the repository root::

    uv run python examples/switch.py
    uv run python examples/switch.py --host mqtt.example.com --port 1883 \
        --username user --password secret
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Switch

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
    relay = Switch(unique_id="relay_1", name="Relay", device_class="outlet")
    device = Device(provider, info, entities=[relay])

    # Set by the relay's on_event callback once a command has been processed,
    # so the example can wait until the switch has acknowledged the command.
    relay_command_received = asyncio.Event()

    async def on_relay_command(event: Event) -> None:
        """Handle a command published to the relay's command topic."""
        logger.info("Relay received command %r (state=%s)", event.message, event.state)
        if event.state == "on":
            # Acknowledge the command by publishing the switch's new state,
            # so Home Assistant sees ON on ~/relay_1/state.
            await relay.set_state(True)
            logger.info("Relay state updated: ON")
        elif event.state == "off":
            await relay.set_state(False)
            logger.info("Relay state updated: OFF")
        relay_command_received.set()

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

            # The relay listens for commands from Home Assistant on
            # ~/relay_1/command. Register its handler, then simulate Home
            # Assistant turning the relay on by publishing "ON" to that topic.
            await relay.on_event(on_relay_command)

            command_topic = info.resolve_topic(relay.command_topic)
            logger.info("Publishing ON command to %s", command_topic)
            await provider.publish(command_topic, relay.payload_on)

            # Wait until the on_event callback has processed the command and
            # acknowledged it with set_state(True).
            try:
                await asyncio.wait_for(relay_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the relay command to be acknowledged"
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
