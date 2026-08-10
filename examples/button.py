"""Example: a device with a single button.

This script walks through the lifecycle of a device that has one
:class:`~ha_mqtt_device.Button`:

1. Connect an :class:`~ha_mqtt_device.AioMqttProvider` to an MQTT broker,
   with ``--host``, ``--port``, ``--username``, and ``--password`` read from
   the command line.
2. Describe the device with a :class:`~ha_mqtt_device.DeviceInfo`.
3. Build a :class:`~ha_mqtt_device.Button`, attach it to a
   :class:`~ha_mqtt_device.Device`, and register a press handler with
   :meth:`~ha_mqtt_device.Button.on_event`. Unlike a switch or binary sensor,
   a button has no state topic: Home Assistant only publishes presses, and the
   device never publishes anything for it.
4. Use the device as an async context manager: entering the block publishes
   the discovery config (including the button's ``cmps`` entry) and announces
   the device as available, and leaving the block announces it as unavailable.
5. Simulate Home Assistant pressing the button: a ``PRESS`` command is
   published to the button's command topic, and the example waits for the
   :meth:`~ha_mqtt_device.Button.on_event` callback to handle it.
6. Keep the provider running until interrupted, then remove the device with
   :meth:`~ha_mqtt_device.Device.remove`.

Run it from the repository root::

    uv run python examples/button.py
    uv run python examples/button.py --host mqtt.example.com --port 1883 \
        --username user --password secret
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Button, Device, DeviceInfo, Event

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


async def reboot_device() -> None:
    """Simulate the action triggered by the button press."""
    logger.info("Rebooting the device")


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
    restart = Button(unique_id="restart", name="Restart", device_class="restart")
    device = Device(provider, info, entities=[restart])

    # Set by the button's on_event callback once a press has been processed,
    # so the example can wait until the button was acknowledged.
    button_pressed = asyncio.Event()

    async def on_press(event: Event) -> None:
        """Handle a press published to the button's command topic."""
        logger.info("Button received press %r (state=%s)", event.message, event.state)
        # The application decides what the press does — here, reboot the device.
        await reboot_device()
        button_pressed.set()

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

            # The button listens for presses from Home Assistant on
            # ~/restart/command. Register its handler, then simulate Home
            # Assistant pressing the button by publishing "PRESS" to that
            # topic.
            await restart.on_event(on_press)

            command_topic = info.resolve_topic(restart.command_topic)
            logger.info("Publishing PRESS command to %s", command_topic)
            await provider.publish(command_topic, restart.payload_press)

            # Wait until the on_event callback has processed the press.
            try:
                await asyncio.wait_for(button_pressed.wait(), timeout=10)
            except TimeoutError:
                logger.warning("Timed out waiting for the button press to be handled")

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
