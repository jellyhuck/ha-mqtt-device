"""Example: a device with an infrared emitter and an infrared receiver.

This script walks through the lifecycle of a device that has one
:class:`~ha_mqtt_device.InfraredEmitter` and one
:class:`~ha_mqtt_device.InfraredReceiver`:

1. Connect an :class:`~ha_mqtt_device.AioMqttProvider` to an MQTT broker,
   with ``--host``, ``--port``, ``--username``, and ``--password`` read from
   the command line.
2. Describe the device with a :class:`~ha_mqtt_device.DeviceInfo`.
3. Build an :class:`~ha_mqtt_device.InfraredEmitter` and an
   :class:`~ha_mqtt_device.InfraredReceiver`, attach them to a
   :class:`~ha_mqtt_device.Device`, and register a command handler with
   :meth:`~ha_mqtt_device.InfraredEmitter.on_event` for the emitter.
4. Use the device as an async context manager: entering the block publishes
   the discovery config (including the emitter's and receiver's ``cmps``
   entries) and announces the device as available, and leaving the block
   announces it as unavailable.
5. Simulate a received IR signal for the receiver, and wait for an emitted
   IR command from Home Assistant on the emitter's command topic.
6. Keep the provider running until interrupted, then remove the device with
   :meth:`~ha_mqtt_device.Device.remove`.

Run it from the repository root::

    uv run python examples/infrared.py
    uv run python examples/infrared.py --host mqtt.example.com --port 1883 \
        --username user --password secret
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from ha_mqtt_device import (
    AioMqttProvider,
    Device,
    DeviceInfo,
    Event,
    InfraredEmitter,
    InfraredReceiver,
)

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883


def parse_args() -> argparse.Namespace:
    """Parse the MQTT broker connection settings from the command line."""
    parser = argparse.ArgumentParser(
        description="Publish a Home Assistant infrared device via MQTT device discovery."
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
    emitter = InfraredEmitter(unique_id="tv_power", name="TV power")
    receiver = InfraredReceiver(unique_id="living_room_ir", name="Living room IR")
    device = Device(provider, info, entities=[emitter, receiver])

    # Set by the emitter's on_event callback once a command has been processed,
    # so the example can wait until the emitter has acknowledged the command.
    emitter_command_received = asyncio.Event()

    async def on_ir_command(event: Event) -> None:
        """Handle an IR signal published to the emitter's command topic."""
        logger.info("Emitter received signal %r (state=%s)", event.message, event.state)
        if event.state is not None:
            # event.state is the parsed signal dict with 'timings' and optional
            # 'modulation' / 'repeat_count'. Send it to the actual hardware here.
            logger.info("Would send IR signal: %s", event.state)
        emitter_command_received.set()

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

            # The emitter listens for IR signals from Home Assistant on
            # ~/tv_power/command. Register its handler, then simulate Home
            # Assistant issuing an IR command by publishing a signal payload to
            # that topic.
            await emitter.on_event(on_ir_command)

            command_topic = info.resolve_topic(emitter.command_topic)
            logger.info("Publishing an IR command to %s", command_topic)
            await provider.publish(
                command_topic,
                '{"timings": [9000, -4500, 562, -1687], "modulation": 38000, "repeat_count": 0}',
            )

            # Wait until the on_event callback has processed the command.
            try:
                await asyncio.wait_for(emitter_command_received.wait(), timeout=10)
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for the IR command to be acknowledged"
                )

            # The receiver publishes received IR signals to ~/living_room_ir/state.
            # In a real device, the hardware would produce this payload.
            await receiver.set_state(
                {
                    "timings": [9000, -4500, 562, -1687],
                    "modulation": 38000,
                }
            )
            logger.info("Published a received IR signal to the receiver state topic")

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
