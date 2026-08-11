"""Example: a device with a single cover.

This script walks through the lifecycle of a device that has one
:class:`~ha_mqtt_device.Cover`:

1. Connect an :class:`~ha_mqtt_device.AioMqttProvider` to an MQTT broker,
   with ``--host``, ``--port``, ``--username``, and ``--password`` read from
   the command line.
2. Describe the device with a :class:`~ha_mqtt_device.DeviceInfo`.
3. Build a :class:`~ha_mqtt_device.Cover`, attach it to a
   :class:`~ha_mqtt_device.Device`, and register a handler with
   :meth:`~ha_mqtt_device.Cover.on_event`.
4. Use the device as an async context manager: entering the block publishes
   the discovery config (including the cover's ``cmps`` entry) and announces
   the device as available, and leaving the block announces it as unavailable.
5. Simulate Home Assistant controlling the cover: an ``OPEN`` command is
   published to the cover's command topic, then a position command (``"50"``)
   to the set-position topic. The
   :meth:`~ha_mqtt_device.Cover.on_event` callback acknowledges each one by
   publishing the new state and position with
   :meth:`~ha_mqtt_device.Cover.set_state` and
   :meth:`~ha_mqtt_device.Cover.set_position`.
6. Keep the provider running until interrupted, then remove the device with
   :meth:`~ha_mqtt_device.Device.remove`.

Run it from the repository root::

    uv run python examples/cover.py
    uv run python examples/cover.py --host mqtt.example.com --port 1883 \
        --username user --password secret
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Cover, Device, DeviceInfo, Event

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
    blinds = Cover(unique_id="blinds", name="Blinds", device_class="blind")
    device = Device(provider, info, entities=[blinds])

    # Set by the cover's on_event callback once a command has been processed,
    # so the example can wait until the cover has acknowledged it.
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
                # Moving: publish the intermediate "opening" state, then the
                # final "open" state and full-open position.
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
        elif event.state is not None:
            # A position command: move the cover to the requested position.
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

            # The cover listens for commands from Home Assistant on
            # ~/blinds/command and ~/blinds/set_position. Register its
            # handler, then simulate Home Assistant opening the cover and
            # moving it to position 50.
            await blinds.on_event(on_cover_event)

            command_topic = info.resolve_topic(blinds.command_topic)
            logger.info("Publishing OPEN command to %s", command_topic)
            await provider.publish(command_topic, blinds.payload_open)

            set_position_topic = info.resolve_topic(blinds.set_position_topic)
            logger.info("Publishing position 50 to %s", set_position_topic)
            await provider.publish(set_position_topic, "50")

            # Wait until the on_event callback has processed both commands and
            # acknowledged them with set_state()/set_position().
            try:
                await asyncio.wait_for(open_command_received.wait(), timeout=10)
                await asyncio.wait_for(position_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the cover commands to be acknowledged"
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
