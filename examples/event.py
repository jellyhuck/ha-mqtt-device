"""Example: a device with a single event entity.

This script walks through the lifecycle of a device that has one
:class:`~ha_mqtt_device.EventEntity`:

1. Connect an :class:`~ha_mqtt_device.AioMqttProvider` to an MQTT broker,
   with ``--host``, ``--port``, ``--username``, and ``--password`` read from
   the command line.
2. Describe the device with a :class:`~ha_mqtt_device.DeviceInfo`.
3. Build a :class:`~ha_mqtt_device.EventEntity` (a doorbell) and attach it to
   a :class:`~ha_mqtt_device.Device`. An event entity is publish-only: the
   device fires transient events to Home Assistant and never receives
   anything, so unlike a switch or button it has no ``on_event`` callback.
4. Use the device as an async context manager: entering the block publishes
   the discovery config (including the entity's ``cmps`` entry) and announces
   the device as available, and leaving the block announces it as unavailable.
5. Fire a couple of doorbell events with
   :meth:`~ha_mqtt_device.EventEntity.set_event`; Home Assistant turns each
   one into an HA event (``doorbell_pressed``, ``doorbell_long_press``) that
   automations can trigger on.
6. Keep the provider running until interrupted, then remove the device with
   :meth:`~ha_mqtt_device.Device.remove`.

Run it from the repository root::

    uv run python examples/event.py
    uv run python examples/event.py --host mqtt.example.com --port 1883 \
        --username user --password secret
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, EventEntity

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
    doorbell = EventEntity(
        unique_id="doorbell",
        name="Doorbell",
        device_class="doorbell",
        event_types=["doorbell_pressed", "doorbell_long_press"],
    )
    device = Device(provider, info, entities=[doorbell])

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

            # Fire doorbell events: each publish sends the event type to
            # ~/doorbell/state and Home Assistant fires an HA event that
            # automations can trigger on.
            await doorbell.set_event("doorbell_pressed")
            logger.info("Fired event: doorbell_pressed")
            await doorbell.set_event("doorbell_long_press")
            logger.info("Fired event: doorbell_long_press")

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
