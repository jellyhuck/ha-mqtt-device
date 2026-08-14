"""Example: an MQTT scene."""

from __future__ import annotations

import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Scene

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883, logger=logger)
    info = DeviceInfo(device_id="scene_example", name="Example scenes")
    scene = Scene(unique_id="party", name="Party")
    device = Device(provider, info, entities=[scene])

    async def on_scene_command(event: Event) -> None:
        logger.info("Scene command %r -> %s", event.message, event.state)
        if event.state == "on":
            # Activate the scene in the device's hardware.
            logger.info("Activating the party scene")

    async with provider:
        async with device:
            await scene.on_event(on_scene_command)
            await scene.activate()  # publishes ON to ~/party/command
            await asyncio.sleep(30)
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
