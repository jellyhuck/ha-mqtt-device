"""Example: a device with a single device tracker.

This script walks through the lifecycle of a device that has one
:class:`~ha_mqtt_device.DeviceTracker`:

1. Connect an :class:`~ha_mqtt_device.AioMqttProvider` to an MQTT broker,
   with ``--host``, ``--port``, ``--username``, and ``--password`` read from
   the command line.
2. Describe the device with a :class:`~ha_mqtt_device.DeviceInfo`.
3. Build a :class:`~ha_mqtt_device.DeviceTracker`, attach it to a
   :class:`~ha_mqtt_device.Device`, and publish its presence with
   :meth:`~ha_mqtt_device.DeviceTracker.set_state` and a GPS position report
   with :meth:`~ha_mqtt_device.DeviceTracker.set_location`. Device trackers
   are read-only in Home Assistant: they report state but have no command
   topic.
4. Use the device as an async context manager: entering the block publishes
   the discovery config (including the tracker's ``cmps`` entry) and announces
   the device as available, and leaving the block announces it as unavailable.
5. Keep the provider running until interrupted, then remove the device with
   :meth:`~ha_mqtt_device.Device.remove`.

Run it from the repository root::

    uv run python examples/device_tracker.py
    uv run python examples/device_tracker.py --host mqtt.example.com --port 1883 \
        --username user --password secret
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, DeviceTracker

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
    tracker = DeviceTracker(
        unique_id="phone",
        name="Phone",
        source_type="gps",
        latitude=32.87336,
        longitude=-117.22743,
        gps_accuracy=50,
        battery_level=82,
        icon="mdi:cellphone",
    )
    device = Device(provider, info, entities=[tracker])

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

            # Publish the tracker's presence: "home" to ~/phone/state, then a
            # GPS position report (JSON) to the same topic, then "not_home".
            await tracker.set_state(True)
            logger.info("Published tracker state: home")
            await tracker.set_location(32.87336, -117.22743)
            logger.info("Published GPS position report")
            await tracker.set_state(False)
            logger.info("Published tracker state: not_home")

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
