"""Example: a grouped-topic MQTT light."""

from __future__ import annotations

import argparse
import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Light

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--username")
    parser.add_argument("--password")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    provider = AioMqttProvider(
        hostname=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        logger=logger,
    )
    info = DeviceInfo(device_id="example_light", name="Example light")
    light = Light(
        unique_id="lamp",
        name="Lamp",
        brightness_enabled=True,
        rgb_enabled=True,
        effect_enabled=True,
        effect_list=["rainbow", "pulse"],
    )
    device = Device(provider, info, entities=[light])

    async def on_command(event: Event) -> None:
        logger.info("%s: %r -> %r", event.topic_type, event.message, event.state)
        if event.event_type == "command" and event.state is not None:
            await light.set_state(event.state == "on")
        elif event.event_type == "brightness" and isinstance(event.state, str):
            await light.set_brightness(int(event.state))

    async with provider:
        async with device:
            await light.on_event(on_command)
            await light.set_state(True)
            await light.set_brightness(75)
            await light.set_rgb((255, 80, 20))
            await asyncio.sleep(10)
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt, asyncio.CancelledError:
        logger.info("Bye")
